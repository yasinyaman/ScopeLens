"""Configuration loading. Which adapter is active is decided HERE, never in code."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# UI-managed settings overrides (currently the LLM section of the /ayarlar screen).
# Written by etki.llm_settings; loaded as the highest-priority source after init
# kwargs, so a value saved in the UI wins over env/.env (an absent file is a no-op).
UI_OVERRIDES_FILE = Path(".etki/llm.json")


class ConnectorConfig(BaseModel):
    adapter: str = "fake"
    options: dict[str, Any] = Field(default_factory=dict)


class ConnectorsConfig(BaseModel):
    work_items: ConnectorConfig = Field(default_factory=ConnectorConfig)
    code_repo: ConnectorConfig = Field(default_factory=ConnectorConfig)
    documents: ConnectorConfig = Field(default_factory=ConnectorConfig)


class Settings(BaseSettings):
    """Application settings, overridable via environment variables (ETKI_ prefix)."""

    # Settings come from env vars (ETKI_ prefix) or a .env file at the repo root.
    # .env is in .gitignore → secrets (API keys) are never committed.
    model_config = SettingsConfigDict(
        env_prefix="ETKI_", env_file=".env", env_file_encoding="utf-8", extra="ignore",
        json_file=UI_OVERRIDES_FILE,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # UI overrides (.etki/llm.json) beat env/.env: a value saved on the
        # /ayarlar screen must take effect even when the same env var is set.
        return (
            init_settings,
            JsonConfigSettingsSource(settings_cls),
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    connectors_path: str = "config/connectors.example.yaml"
    projects_path: str = "config/projects.yaml"
    index_path: str = ".etki/index.json"
    # Decision wiki (file-based long-form memory — ALWAYS a projection of the DB,
    # see adapters/filesystem_wiki.py). {id} = project id. Empty string → off.
    wiki_dir: str = ".etki/wiki-{id}"
    # Online package-registry metadata (dependency impact) — OFF by default so
    # CI/air-gapped deployments never call out. Query-time display enrichment
    # only; never persisted into the index, never a decision input.
    deps_online: bool = False
    deps_timeout: float = 10.0
    pypi_base_url: str = "https://pypi.org"
    npm_base_url: str = "https://registry.npmjs.org"
    maven_base_url: str = "https://search.maven.org"
    github_base_url: str = "https://api.github.com"  # release notes (API-change check)
    osv_base_url: str = "https://api.osv.dev"  # known-vulnerability lookups (security)
    # Version-diff downloads (dependency_version_diff): per-artifact cap + timeout.
    deps_max_download_mb: int = 80
    deps_download_timeout: float = 60.0
    # Overrides every repo's code engine, forcing a single engine (e.g. "ast" in a
    # JVM-free container). If empty, each repo uses its own `engine` value.
    force_code_engine: str | None = None
    db_url: str = "sqlite:///./etki.db"  # live: postgresql+psycopg://...
    # Session-cookie signing secret — MUST come from env in PRODUCTION.
    # Dev uses a fixed default (a warning is logged at startup); prod must override.
    session_secret: str = "dev-insecure-change-me"
    # First PMO user (created at startup only if no users exist at all).
    admin_user: str | None = None
    admin_password: str | None = None
    # Upload size cap (MB) — OOM / zip-bomb protection.
    max_upload_mb: int = 20
    # The pmo role can access all projects (single-customer pilot default). In a
    # multi-customer deployment set false → everyone, pmo included, sees only their
    # user_projects grants.
    pmo_global: bool = True
    # Demo content (sample request chips on the meeting screen) is shown only when on.
    demo_mode: bool = False
    # Default UI language (when no session/Accept-Language). tr | en | de.
    default_language: str = "tr"
    # Decision thresholds — tunable via calibration (feedback loop).
    # Calibrated on the eval set for the symmetric-normalized score (B2; old
    # asymmetric values: 0.34/0.18).
    in_scope_threshold: float = 0.22
    gray_threshold: float = 0.06
    # Effort-estimation constants (C2) — not hard-coded in the engine; calibrated from
    # pilot data (pilot/calibration.suggest_estimation_params suggests, a human applies).
    est_loc_per_hour: float = 120.0
    est_optimistic_factor: float = 0.6
    est_pessimistic_factor: float = 2.0
    est_churn_pessimistic_factor: float = 1.5
    est_high_churn_commits: int = 15
    est_base_hours: float = 2.0
    # Dependency-change surface constants (version upgrades scale with usage
    # surface, not module LOC — see engine/estimation.py).
    est_dep_base_hours: float = 4.0
    est_dep_hours_per_module: float = 2.0
    est_dep_hours_per_api: float = 0.5
    est_dep_unknown_widen: float = 1.5
    # Decision-stamp default (in the API the real value comes from
    # context._resolve_model_version; this is only a fallback for tests/tools that
    # use the engine directly).
    model_version: str = "deterministic-v1"
    # Freshness-stamp fallback; live value derives from index build time (index.freshness).
    index_freshness: str = "2026-06-21"
    log_level: str = "INFO"
    # In-app background refresh (both OFF by default — 0 disables; cron remains the
    # recommended production path, these serve single-container/pilot deployments):
    #   reindex_interval_hours: full re-index of every project, then context rebuild.
    #   pool_refresh_minutes: lightweight effort-pool recompute from the work-item
    #   provider's all_items() (no code/document re-index) — updates the engines'
    #   consumed-by-category totals in place.
    reindex_interval_hours: float = 0.0
    pool_refresh_minutes: float = 0.0

    # LLM seam (optional) — OFF BY DEFAULT (keep the gate deterministic).
    # Two providers: "openai" (Ollama/vLLM, OpenAI-compatible) or "anthropic" (Claude API).
    llm_provider: str = "openai"  # openai | anthropic
    # OpenAI-compatible: ETKI_LLM_BASE_URL=http://localhost:11434/v1 (Ollama).
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "qwen2.5:3b"
    # Request timeout (s) for the OpenAI-compatible client. Large local models (70B+ on
    # unified-memory boxes) can exceed the 60s default on first load/slow decode; a timeout
    # silently falls back to the deterministic path, so benchmark runs of big models should
    # raise this (e.g. ETKI_LLM_TIMEOUT=300).
    llm_timeout: float = 60.0
    # Embedding seam (optional, OFF by default like the LLM): semantic matching via an
    # OpenAI-compatible embeddings endpoint (Ollama/vLLM). Embeddings are deterministic
    # for a given model — reproducible, auditable semantic scores. No endpoint → pure
    # lexical matching, unchanged.
    embed_base_url: str | None = None  # e.g. http://localhost:11434/v1 (Ollama)
    embed_api_key: str | None = None
    embed_model: str = "qwen3-embedding:0.6b"
    embed_timeout: float = 30.0
    # Cosine thresholds, calibrated for qwen3-embedding:0.6b on the dev benchmark
    # (model-dependent — recalibrate if you change embed_model). strong gates the
    # exclusion routing (with a clear-cosine-margin requirement in the engine);
    # weak gates the informational "semantically nearest clause" evidence note.
    # Measured finding: cosine cannot separate "paraphrase of a clause (IN)" from
    # "new capability near a clause (CR)", so the include side never changes
    # decisions — that judgment belongs to the guarded LLM assist.
    embed_strong: float = 0.58
    embed_weak: float = 0.53
    # Task prefixes — some retrieval models require them (nomic-embed-text:
    # "search_query: "/"search_document: "; e5: "query: "/"passage: ").
    # qwen3-embedding (the default) needs none.
    embed_query_prefix: str = ""
    embed_doc_prefix: str = ""
    # Cross-encoder reranker (v4b) — TEI-compatible /rerank endpoint. Unlike
    # bi-encoder embeddings, a cross-encoder reads the (request, clause) pair
    # JOINTLY and measurably separates "paraphrase of a clause" from "new
    # capability near a clause" (AUC 0.975 on the dev benchmark). Deterministic
    # for a given model; no endpoint → this evidence layer is off (CI unchanged).
    rerank_base_url: str | None = None  # e.g. http://localhost:8021 (TEI)
    rerank_timeout: float = 30.0
    # RAW-logit threshold for the include-side floor, calibrated for
    # BAAI/bge-reranker-v2-m3 on the dev benchmark (model-dependent). Above it,
    # the best INCLUDED clause acts like a strong match (in-scope floor; the
    # limit/quota/pool/short-query guards still apply afterwards).
    rerank_strong: float = -6.8
    # Disputed-clause escalation: a request citing a clause with CONFLICTING final
    # PMO rulings escalates the RISK layer (24h PMO look) — decision/confidence
    # untouched (the memory stays non-signal for the decision itself).
    disputed_escalation: bool = True
    # Assist strategy when an LLM is configured: "pick" (single-shot clause pick over
    # the full list — v2, current default), "judge" (candidate shortlist + per-clause
    # verdicts — v3, measured NEGATIVE: the lexical shortlist misses the right clause
    # on paraphrases, see the EtkiBench README) or "verify" (v4a: pick unchanged +
    # one covers/new_capability follow-up on the accepted INCLUDED clause; fails open
    # to pick on any error).
    llm_assist_mode: str = "pick"
    # Anthropic Claude API: the key is also read from the ANTHROPIC_API_KEY env (SDK).
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"

    def estimation_params(self):  # type: ignore[no-untyped-def]  # (late import to avoid a circular import)
        from etki.engine.estimation import EstimationParams

        return EstimationParams(
            loc_per_hour=self.est_loc_per_hour,
            optimistic_factor=self.est_optimistic_factor,
            pessimistic_factor=self.est_pessimistic_factor,
            churn_pessimistic_factor=self.est_churn_pessimistic_factor,
            high_churn_commits=self.est_high_churn_commits,
            base_hours=self.est_base_hours,
            dep_base_hours=self.est_dep_base_hours,
            dep_hours_per_module=self.est_dep_hours_per_module,
            dep_hours_per_api=self.est_dep_hours_per_api,
            dep_unknown_widen=self.est_dep_unknown_widen,
        )


def load_connectors(path: str | Path) -> ConnectorsConfig:
    p = Path(path)
    if not p.exists():
        return ConnectorsConfig()
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return ConnectorsConfig.model_validate(data.get("connectors", {}))


class RepoConfig(BaseModel):
    """A code repo attached to a project (for impact analysis; there may be several)."""

    name: str = "main"
    src_root: str | None = None  # local path (for git, written here after clone)
    git_url: str | None = None  # clone source (metadata)
    engine: str = "ast"  # ast | joern | graphify


class ProjectConfig(BaseModel):
    id: str
    name: str
    contract_id: str = "CTR-DEMO-001"
    index_path: str = ".etki/index-{id}.json"
    connectors: ConnectorsConfig = Field(default_factory=ConnectorsConfig)
    doc_root: str | None = None  # directory of specs/requirements uploaded via the UI
    repos: list[RepoConfig] = Field(default_factory=list)  # UI-managed code sources
    # Per-project LLM profile (domain + language). NOT limited to the UI's tr/en/de;
    # LLM output can be any language. Affects only the LLM path (deterministic unchanged).
    language: str = "tr"  # LLM output/answer language
    domain_profile: str | None = None  # config/domains/<id>.md (selected preset profile)
    instructions: str = ""  # free-text extra domain instructions
    pivot_language: str | None = None  # if set, translation pivot is on (e.g. "en");
    # otherwise multilingual
    # Project-specific module hints (module → keywords); merged on top of the domain
    # profile hints (config/domains/*.hints.yaml). No dictionary baked into the engine core.
    module_hints: dict[str, list[str]] = Field(default_factory=dict)

    def resolved_index_path(self) -> str:
        return self.index_path.replace("{id}", self.id)

    def documents_connector(self) -> ConnectorConfig:
        # Uploaded specs (doc_root) do NOT replace the base corpus; they are ADDED
        # to it (composite).
        sources: list[ConnectorConfig] = []
        base = self.connectors.documents
        if base.adapter == "filesystem" and base.options.get("root"):
            sources.append(base)
        if self.doc_root:
            sources.append(
                ConnectorConfig(
                    adapter="filesystem",
                    options={"root": self.doc_root, "globs": ["*.md", "*.txt"]},
                )
            )
        if not sources:
            return base
        if len(sources) == 1:
            return sources[0]
        return ConnectorConfig(
            adapter="composite", options={"sources": [s.model_dump() for s in sources]}
        )

    def resolved_repos(self) -> list[RepoConfig]:
        if self.repos:
            return self.repos
        code = self.connectors.code_repo
        src = code.options.get("src_root")
        if src and code.adapter in ("ast", "joern", "graphify"):  # backward compat
            return [RepoConfig(name="main", src_root=src, engine=code.adapter)]
        return []  # no repo attached yet


def load_projects(
    projects_path: str | Path, fallback_connectors_path: str | Path
) -> list[ProjectConfig]:
    """Loads projects from projects.yaml. If the file is absent, synthesizes a single
    'demo' project from connectors_path for backward compatibility."""
    p = Path(projects_path)
    if p.exists():
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        projects = [ProjectConfig.model_validate(proj) for proj in data.get("projects", [])]
        if projects:
            return projects
    return [
        ProjectConfig(
            id="demo",
            name="Demo Proje",
            connectors=load_connectors(fallback_connectors_path),
        )
    ]
