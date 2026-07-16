"""Config-driven adapter selection (factory).

Adding a new vendor = one branch in the relevant builder + one adapter file.
The core (engine/api) never imports concrete adapters; it only sees this module and the ports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from pydantic import BaseModel

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.azure_devops_work_item import AzureDevOpsWorkItemProvider
from etki.adapters.composite_document import CompositeDocumentSourceProvider
from etki.adapters.confluence_document import ConfluenceDocumentSourceProvider
from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.adapters.file_work_item import FileWorkItemProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.adapters.git_churn import compute_churn
from etki.adapters.gitlab_work_item import GitlabWorkItemProvider
from etki.adapters.jira_work_item import JiraWorkItemProvider
from etki.adapters.joern_code_repo import JoernCodeRepositoryProvider
from etki.adapters.options import (
    BUILTIN_OPTION_MODELS,
    AzureDevOpsOptions,
    FileOptions,
    GitlabOptions,
    JiraOptions,
    RedmineOptions,
)
from etki.adapters.plugins import get_plugin_registry
from etki.adapters.redmine_work_item import RedmineWorkItemProvider
from etki.adapters.sharepoint_document import SharePointDocumentSourceProvider
from etki.config import ConnectorConfig, ConnectorsConfig, Settings
from etki.core.ports import (
    CodeRepositoryProvider,
    DocumentSourceProvider,
    LLMClient,
    WorkItemProvider,
)


@dataclass
class Providers:
    work_items: WorkItemProvider
    code_repo: CodeRepositoryProvider
    documents: DocumentSourceProvider


def build_llm_client(settings: Settings) -> LLMClient | None:
    """Selects the LLM client based on config (provider = config, not code).

    No key/endpoint → returns None → the caller falls back to the heuristic/deterministic path."""
    provider = (settings.llm_provider or "openai").lower()
    if provider == "anthropic":
        import os

        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        from etki.adapters.llm_anthropic import AnthropicLLMClient

        return AnthropicLLMClient(api_key=api_key, model=settings.anthropic_model)
    if provider != "openai":  # plugin hook: a non-builtin provider name resolves via plugins
        factory = get_plugin_registry().find("llm", provider)
        if factory is not None:
            options = factory.options_model.model_validate(
                {
                    "base_url": settings.llm_base_url,
                    "api_key": settings.llm_api_key,
                    "model": settings.llm_model,
                    "timeout": settings.llm_timeout,
                }
            )
            return factory.build(options)  # type: ignore[return-value]
    if settings.llm_base_url:  # openai-compatible (Ollama/vLLM)
        from etki.adapters.llm_openai import OpenAICompatibleLLMClient

        return OpenAICompatibleLLMClient(
            settings.llm_base_url,
            settings.llm_api_key,
            settings.llm_model,
            timeout=settings.llm_timeout,
        )
    return None


def build_embedder(settings: Settings):  # type: ignore[no-untyped-def]  # -> EmbeddingProvider | None
    """Embedding client from config; None when no endpoint is configured (the engine
    then runs pure lexical matching — CI stays deterministic with no env set)."""
    if not settings.embed_base_url:
        return None
    from etki.adapters.embedding_openai import OpenAICompatibleEmbeddingClient

    return OpenAICompatibleEmbeddingClient(
        settings.embed_base_url,
        settings.embed_api_key,
        settings.embed_model,
        timeout=settings.embed_timeout,
        query_prefix=settings.embed_query_prefix,
        doc_prefix=settings.embed_doc_prefix,
    )


def build_reranker(settings: Settings):  # type: ignore[no-untyped-def]  # -> RerankProvider | None
    """Cross-encoder reranker from config; None when no endpoint is configured
    (the evidence layer is simply absent — CI stays deterministic with no env set)."""
    if not settings.rerank_base_url:
        return None
    from etki.adapters.rerank_tei import TeiRerankClient

    return TeiRerankClient(settings.rerank_base_url, timeout=settings.rerank_timeout)


def build_wiki_store(settings: Settings):  # type: ignore[no-untyped-def]  # -> WikiStore | None
    """Decision wiki from config; None when disabled (ETKI_WIKI_DIR=""). The wiki
    is a best-effort projection of the DB — its absence changes no decision.
    Headings render in each PROJECT's language (default tr); a config-load failure
    degrades to the default map, never blocks the wiki."""
    if not settings.wiki_dir:
        return None
    from etki.adapters.filesystem_wiki import FileSystemWikiAdapter

    languages: dict[str, str] = {}
    try:
        from etki.config import load_projects

        languages = {
            p.id: p.language
            for p in load_projects(settings.projects_path, settings.connectors_path)
        }
    except Exception:  # noqa: BLE001 — best-effort: default language map
        pass
    return FileSystemWikiAdapter(settings.wiki_dir, languages=languages)


def build_package_registry(settings: Settings):  # type: ignore[no-untyped-def]  # -> RegistryMetadataProvider | None
    """Online registry metadata from config; None when ETKI_DEPS_ONLINE is off
    (config, never code — the dependency card simply shows manifest facts only)."""
    if not settings.deps_online:
        return None
    from etki.adapters.package_registries import PublicRegistryClient

    return PublicRegistryClient(
        pypi_base_url=settings.pypi_base_url,
        npm_base_url=settings.npm_base_url,
        maven_base_url=settings.maven_base_url,
        github_base_url=settings.github_base_url,
        osv_base_url=settings.osv_base_url,
        timeout=settings.deps_timeout,
    )


# Builtin adapter names per port — the single source for error messages and the
# UI's adapter dropdown ("empty" stays an accepted alias of "none", not listed).
_BUILTIN_ADAPTERS: dict[str, list[str]] = {
    "work_items": ["none", "fake", "file", "jira", "gitlab", "redmine", "azure_devops"],
    "code_repo": ["fake", "ast", "joern", "graphify"],
    "documents": ["fake", "filesystem", "composite", "confluence", "sharepoint"],
}


def available_adapters(port: str) -> list[str]:
    """All adapter names a port can resolve right now: builtins + ACTIVE plugins.

    Builtins always win on a name collision, so the builtin list comes first;
    plugin names come from the registry (disabled/failed plugins never register
    factories, hence never appear here)."""
    builtins = _BUILTIN_ADAPTERS.get(port, [])
    plugins = [n for n in get_plugin_registry().names(port) if n not in builtins]
    return builtins + plugins


def options_model_for(port: str, adapter: str) -> type[BaseModel] | None:
    """The Pydantic options model for an adapter name, if one exists — builtin
    table first (builtins win, as in resolution), then the plugin's declared
    ``options_model``. None → the UI falls back to the free-form textarea."""
    model = BUILTIN_OPTION_MODELS.get(port, {}).get(adapter)
    if model is not None:
        return model
    factory = get_plugin_registry().find(port, adapter)
    return factory.options_model if factory is not None else None


def _unknown(label: str, name: str, known: list[str]) -> ValueError:
    return ValueError(f"Bilinmeyen {label} adaptörü: {name!r}. Mevcut: {known}")


def _resolve_secret_refs(value: object) -> object:
    """Recursively resolves `env:VAR` references in an options tree.

    Runs BEFORE options reach a plugin: secret resolution stays in core, a
    plugin only ever sees the resolved values (never the raw reference)."""
    if isinstance(value, dict):
        return {k: _resolve_secret_refs(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_secret_refs(v) for v in value]
    if isinstance(value, str) and value.startswith("env:"):
        return _secret(value)
    return value


def _try_plugin(port: str, cfg: ConnectorConfig) -> object | None:
    """Plugin fall-through: consulted only AFTER the builtin if/elif chains, so
    a plugin can never shadow a builtin adapter name. UI-managed adapter
    DEFAULTS (Ayarlar → Eklentiler → detail) merge under the project's options
    — the project value always wins. Options are validated through the
    plugin's declared Pydantic model — a missing key is a proper validation
    message, not a bare KeyError."""
    from etki.plugin.options_store import defaults_for

    factory = get_plugin_registry().find(port, cfg.adapter)
    if factory is None:
        return None
    merged = {**defaults_for(cfg.adapter), **cfg.options}
    options = factory.options_model.model_validate(_resolve_secret_refs(merged))
    return factory.build(options)


def build_documents(cfg: ConnectorConfig) -> DocumentSourceProvider:
    opt = cfg.options
    if cfg.adapter == "fake":
        return FakeDocumentSourceProvider()
    if cfg.adapter == "filesystem":
        return FileSystemDocumentSourceProvider(opt["root"], opt.get("globs"))
    if cfg.adapter == "composite":
        sources = [build_documents(ConnectorConfig.model_validate(s)) for s in opt["sources"]]
        return CompositeDocumentSourceProvider(sources)
    if cfg.adapter == "confluence":
        return ConfluenceDocumentSourceProvider(
            opt["base_url"], opt["email"], _secret(opt["api_token"]), opt["space_key"]
        )
    if cfg.adapter == "sharepoint":
        return SharePointDocumentSourceProvider(
            opt["tenant_id"],
            opt["client_id"],
            _secret(opt["client_secret"]),
            opt["drive_id"],
            opt.get("folder", ""),
        )
    provider = _try_plugin("documents", cfg)
    if provider is not None:
        return provider  # type: ignore[return-value]  # conformance suite guards the Protocol
    raise _unknown("documents", cfg.adapter, available_adapters("documents"))


def build_code_repo(cfg: ConnectorConfig) -> CodeRepositoryProvider:
    opt = cfg.options
    if cfg.adapter == "fake":
        return FakeCodeRepositoryProvider()
    if cfg.adapter == "ast":
        src = opt["src_root"]
        return AstCodeRepositoryProvider(src, churn=compute_churn(src))
    if cfg.adapter == "joern":
        src = opt["src_root"]
        return JoernCodeRepositoryProvider(
            src,
            export_path=opt.get("export_path"),
            refresh=opt.get("refresh", True),
            churn=compute_churn(src),
        )
    if cfg.adapter == "graphify":
        # Lazy import — optional engine (extra: `etki[graphify]`), core stays clean.
        from etki.adapters.graphify_code_repo import GraphifyCodeRepositoryProvider

        src = opt["src_root"]
        return GraphifyCodeRepositoryProvider(
            src,
            export_dir=opt.get("export_dir"),
            refresh=opt.get("refresh", True),
            churn=compute_churn(src),
        )
    provider = _try_plugin("code_repo", cfg)
    if provider is not None:
        return provider  # type: ignore[return-value]
    raise _unknown("code_repo", cfg.adapter, available_adapters("code_repo"))


def _secret(value: str) -> str:
    """Resolves an `env:VARIABLE` reference from the environment; returns a plain value as-is.

    Secrets (Jira/GitLab tokens) are kept in projects.yaml as a reference like `env:JIRA_TOKEN`
    instead of being written in plain text, and are read from the environment at runtime
    (KVKK / secrets management)."""
    if value.startswith("env:"):
        var = value[4:]
        resolved = os.environ.get(var)
        if resolved is None:
            raise ValueError(f"ortam değişkeni tanımsız: {var}")
        return resolved
    return value


def build_work_items(cfg: ConnectorConfig) -> WorkItemProvider:
    # Builtins validate through the typed models in adapters/options.py — a missing
    # key is a field-level Pydantic message (like the plugin path), not a KeyError.
    if cfg.adapter in ("none", "empty"):  # no history → effort falls back to code metrics
        return FakeWorkItemProvider([])
    if cfg.adapter == "fake":
        return FakeWorkItemProvider()
    if cfg.adapter == "file":
        fo = FileOptions.model_validate(cfg.options)
        return FileWorkItemProvider(fo.path)
    if cfg.adapter == "jira":
        jo = JiraOptions.model_validate(cfg.options)
        return JiraWorkItemProvider(jo.base_url, jo.email, _secret(jo.api_token), jo.jql)
    if cfg.adapter == "gitlab":
        lo = GitlabOptions.model_validate(cfg.options)
        return GitlabWorkItemProvider(
            lo.base_url,
            lo.project,
            _secret(lo.token),
            labels=lo.labels,
            issue_type=lo.issue_type,
        )
    if cfg.adapter == "redmine":
        ro = RedmineOptions.model_validate(cfg.options)
        return RedmineWorkItemProvider(ro.base_url, _secret(ro.api_key))
    if cfg.adapter == "azure_devops":
        ao = AzureDevOpsOptions.model_validate(cfg.options)
        return AzureDevOpsWorkItemProvider(ao.organization, ao.project, _secret(ao.pat))
    provider = _try_plugin("work_items", cfg)
    if provider is not None:
        return provider  # type: ignore[return-value]
    raise _unknown("work_items", cfg.adapter, available_adapters("work_items"))


def build_providers(config: ConnectorsConfig) -> Providers:
    return Providers(
        work_items=build_work_items(config.work_items),
        code_repo=build_code_repo(config.code_repo),
        documents=build_documents(config.documents),
    )
