"""Config-driven adapter selection (factory).

Adding a new vendor = one branch in the relevant builder + one adapter file.
The core (engine/api) never imports concrete adapters; it only sees this module and the ports.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

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
from etki.adapters.glpi_work_item import GlpiWorkItemProvider
from etki.adapters.jira_work_item import JiraWorkItemProvider
from etki.adapters.joern_code_repo import JoernCodeRepositoryProvider
from etki.adapters.linear_work_item import LinearWorkItemProvider
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


def _unknown(label: str, name: str, known: list[str]) -> ValueError:
    return ValueError(f"Bilinmeyen {label} adaptörü: {name!r}. Mevcut: {known}")


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
    raise _unknown(
        "documents",
        cfg.adapter,
        ["fake", "filesystem", "composite", "confluence", "sharepoint"],
    )


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
    raise _unknown("code_repo", cfg.adapter, ["fake", "ast", "joern", "graphify"])


def _secret(value: str) -> str:
    """Resolves an `env:VARIABLE` reference from the environment; returns a plain value as-is.

    Secrets (Jira/GLPI tokens) are kept in projects.yaml as a reference like `env:JIRA_TOKEN`
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
    opt = cfg.options
    if cfg.adapter in ("none", "empty"):  # no history → effort falls back to code metrics
        return FakeWorkItemProvider([])
    if cfg.adapter == "fake":
        return FakeWorkItemProvider()
    if cfg.adapter == "file":
        return FileWorkItemProvider(opt["path"])
    if cfg.adapter == "glpi":
        return GlpiWorkItemProvider(
            opt["base_url"], _secret(opt["app_token"]), _secret(opt["user_token"])
        )
    if cfg.adapter == "jira":
        return JiraWorkItemProvider(
            opt["base_url"], opt["email"], _secret(opt["api_token"]), opt.get("jql", "")
        )
    if cfg.adapter == "gitlab":
        return GitlabWorkItemProvider(
            opt["base_url"],
            opt["project"],
            _secret(opt["token"]),
            labels=opt.get("labels"),
            issue_type=opt.get("issue_type"),
        )
    if cfg.adapter == "redmine":
        return RedmineWorkItemProvider(opt["base_url"], _secret(opt["api_key"]))
    if cfg.adapter == "linear":
        return LinearWorkItemProvider(
            _secret(opt["api_key"]), float(opt.get("hours_per_point", 0.0))
        )
    if cfg.adapter == "azure_devops":
        return AzureDevOpsWorkItemProvider(
            opt["organization"], opt["project"], _secret(opt["pat"])
        )
    raise _unknown(
        "work_items",
        cfg.adapter,
        [
            "none",
            "fake",
            "file",
            "glpi",
            "jira",
            "gitlab",
            "redmine",
            "azure_devops",
            "linear",
        ],
    )


def build_providers(config: ConnectorsConfig) -> Providers:
    return Providers(
        work_items=build_work_items(config.work_items),
        code_repo=build_code_repo(config.code_repo),
        documents=build_documents(config.documents),
    )
