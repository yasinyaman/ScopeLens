"""Shared application context — multi-project: each project has its own engine/baseline.

`engines[project_id] = TriageEngine`. A single `repo`/`approval` holds all projects;
cases/KPIs are separated by `project_id`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from functools import lru_cache

from etki.adapters.code_index import MergedCodeRepository, StaticCodeRepository
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.adapters.plugins import get_plugin_registry
from etki.adapters.registry import (
    build_code_repo,
    build_documents,
    build_embedder,
    build_llm_client,
    build_request_intake,
    build_reranker,
    build_response_channel,
    build_wiki_store,
    build_work_items,
)
from etki.auth import UserStore, build_user_store
from etki.config import ConnectorConfig, ProjectConfig, Settings, load_projects
from etki.core.models import Baseline, Index, ScopeItem
from etki.core.ports import CaseFileRepository, CodeRepositoryProvider, WikiStore
from etki.domains import load_module_hints
from etki.engine.estimation import consumed_by_category
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import build_scope_extractor
from etki.hitl.ingest import WikiIngest, precedents_by_clause
from etki.hitl.service import ApprovalService
from etki.indexing.engine import IndexingEngine, load_index, save_index
from etki.intake.respond import DecisionResponder, ResponderBinding
from etki.intake.service import IntakeBinding
from etki.llm_profile import build_system_preamble
from etki.persistence.db import build_repository
from etki.process_log import log_event

logger = logging.getLogger("etki")


class UnknownProjectError(KeyError):
    """Unknown project_id — does NOT silently fall back to the default project (triaging
    against the wrong baseline would produce a wrong-but-error-free decision suggestion).
    The API layer converts this to a 404."""


@dataclass
class AdapterHealth:
    """Runtime health of one configured adapter. NOT persisted — recomputed on every
    context build, so it reflects the last build (plus pool refreshes for work items).

    Distinguishes a project deliberately configured with the fake/none adapter (ok,
    no badge) from one whose REAL adapter broke and silently degraded to the Fake
    fallback (degraded, badge on the project screens)."""

    port: str  # "work_items" | "documents"
    adapter: str  # the CONFIGURED adapter name (e.g. "linear"), not the fallback
    state: str = "ok"  # "ok" | "degraded"
    error: str | None = None


@dataclass
class AppContext:
    engines: dict[str, TriageEngine]
    consumed: dict[str, dict[str, float]]
    projects: list[dict[str, str]]  # [{id, name}]
    repo: CaseFileRepository
    approval: ApprovalService
    default_project: str
    user_store: UserStore
    # Live Index carrying the same baseline object as the engine + its path on disk
    # (kept in context so the baseline-bump → index.json sync happens from a single place).
    indexes: dict[str, Index] = field(default_factory=dict)
    index_paths: dict[str, str] = field(default_factory=dict)
    # Per-project work-item providers — kept so the background pool refresh can
    # recompute consumed-by-category without a full re-index.
    work_item_providers: dict[str, object] = field(default_factory=dict)
    # Decision wiki (same instance the ApprovalService writes through; None = off).
    wiki: WikiStore | None = None
    # Per-project clause memory (precedents/disputes) — the ENGINE holds the same
    # dict by reference (like `consumed`), refresh_precedents mutates it in place.
    precedents: dict[str, dict[str, dict]] = field(default_factory=dict)
    # Per-project adapter health (see AdapterHealth) — the UI's degradation badges.
    adapter_health: dict[str, list[AdapterHealth]] = field(default_factory=dict)
    # Per-project request-intake bindings (poll loop reads these). Empty = no
    # project polls a tracker.
    intake: dict[str, IntakeBinding] = field(default_factory=dict)
    # Decision/triage write-back host. Its `bindings` dict is filled here; the
    # singleton ApprovalService holds a reference to `on_decision`.
    responder: DecisionResponder | None = None

    def degraded_adapters(self, project_id: str) -> list[AdapterHealth]:
        return [h for h in self.adapter_health.get(project_id, []) if h.state == "degraded"]

    def _set_health(self, project_id: str, port: str, state: str, error: str | None) -> None:
        for h in self.adapter_health.get(project_id, []):
            if h.port == port:
                h.state = state
                h.error = error
                return

    def refresh_precedents(self, project_id: str | None = None) -> None:
        """Recomputes the clause memory from the DB after a PMO decision and
        updates the engines' dicts IN PLACE (refresh_pools idiom). Best-effort:
        a failure leaves the previous memory, never breaks the caller."""
        targets = [project_id] if project_id else list(self.precedents)
        for pid in targets:
            memory = self.precedents.get(pid)
            if memory is None:
                continue
            try:
                cases = self.repo.list_cases(pid)
                case_ids = {c.request_id for c in cases}
                overrides = [o for o in self.repo.list_overrides() if o.case_id in case_ids]
                fresh = precedents_by_clause(cases, overrides)
            except Exception:
                logger.warning("[%s] madde hafızası tazelenemedi", pid, exc_info=True)
                continue
            memory.clear()
            memory.update(fresh)

    def refresh_pools(self) -> int:
        """Recomputes effort-pool consumption from each project's work-item provider and
        updates the engines' dicts IN PLACE (engine and context hold the same object).
        Only providers exposing `all_items()` participate (same rule as the initial
        build). Returns how many projects were refreshed."""
        refreshed = 0
        for project_id, provider in self.work_item_providers.items():
            items_fn = getattr(provider, "all_items", None)
            consumed = self.consumed.get(project_id)
            if items_fn is None or consumed is None:
                continue
            try:
                fresh = consumed_by_category(items_fn())
            except Exception as exc:
                logger.warning("[%s] efor havuzu tazelenemedi", project_id, exc_info=True)
                # A live-call failure degrades the badge; it never auto-heals here —
                # a refresh success on the FAKE fallback of a build-time failure must
                # not hide the real problem. Healing happens on the next context build.
                self._set_health(
                    project_id, "work_items", "degraded", f"{type(exc).__name__}: {exc}"
                )
                continue
            consumed.clear()
            consumed.update(fresh)
            refreshed += 1
        return refreshed

    def resolve_project(self, project_id: str | None) -> str:
        """Falls back to the default only when project_id is not given (explicit intent);
        an unknown id is never silently redirected to another project → UnknownProjectError."""
        if not project_id:
            if self.default_project not in self.engines:
                # The default project failed to index/build at startup: surface a
                # clean 404 (the UnknownProjectError path) instead of a raw
                # KeyError-500 from engines[default].
                raise UnknownProjectError(self.default_project)
            return self.default_project
        if project_id not in self.engines:
            raise UnknownProjectError(project_id)
        return project_id

    def get_engine(self, project_id: str | None) -> TriageEngine:
        return self.engines[self.resolve_project(project_id)]

    def apply_baseline_bump(self, project_id: str | None, item: ScopeItem) -> int:
        """CR approval → grows the living baseline in the engine AND in index.json together.

        The DB write happens in ApprovalService; this keeps the in-memory engine and disk
        in sync so the evidence chain doesn't diverge from the actual baseline after
        a restart."""
        pid = self.resolve_project(project_id)
        version = self.engines[pid].extend_baseline(item)
        index = self.indexes.get(pid)
        if index is not None:
            index.baseline = self.engines[pid].baseline
            save_index(index, self.index_paths[pid])
        return version


def _build_code_repo(project: ProjectConfig, settings: Settings) -> CodeRepositoryProvider:
    """Turns all of a project's repos (local/cloned) into a single (merged) code provider."""
    providers: list[tuple[str, CodeRepositoryProvider]] = []
    for repo in project.resolved_repos():
        if not repo.src_root:
            continue
        # If force_code_engine is set it overrides the repo's engine (e.g. JVM-less
        # container → "ast").
        engine = settings.force_code_engine or repo.engine
        cfg = ConnectorConfig(adapter=engine, options={"src_root": repo.src_root})
        providers.append((repo.name, build_code_repo(cfg)))
    if not providers:
        return StaticCodeRepository([])  # no repo yet → empty graph
    if len(providers) == 1:
        return providers[0][1]
    return MergedCodeRepository(providers)  # multiple repos → merged impact analysis


def _resolve_model_version(settings: Settings, llm_enabled: bool) -> str:
    """Decision stamp: whether it's deterministic, or which LLM provider/model is active."""
    if not llm_enabled:
        return "deterministic-v1"
    if (settings.llm_provider or "").lower() == "anthropic":
        return f"anthropic:{settings.anthropic_model}"
    return f"openai:{settings.llm_model}"


def merge_db_baseline(index: Index, db_baseline: Baseline | None) -> bool:
    """Merges the DB's approved (living) baseline into the index baseline; True on change.

    Approvals live in the DB as the single source of truth: the index's document-sourced
    fresh items are kept, the DB's CR-sourced items are added, and the version is pulled up
    to the DB's version. This way neither a restart nor a reindex overwrites approved CRs
    (so the audit trail's "BASELINE_BUMP vN" doesn't diverge from the actual state)."""
    if db_baseline is None or db_baseline.version <= index.baseline.version:
        return False
    existing = {i.id for i in index.baseline.scope_items}
    for item in db_baseline.scope_items:
        if (item.category == "cr" or item.id.startswith("CR-")) and item.id not in existing:
            index.baseline.scope_items.append(item)
    index.baseline.version = db_baseline.version
    index.baseline.locked_at = db_baseline.locked_at
    return True


def _reconcile_with_db(
    index: Index, project: ProjectConfig, settings: Settings, repo: CaseFileRepository | None
) -> None:
    """Reconciles the index baseline with the latest approved version in the DB (failure
    is non-fatal)."""
    try:
        if repo is None:
            repo = build_repository(settings.db_url)
        if merge_db_baseline(index, repo.latest_baseline(project.contract_id)):
            save_index(index, project.resolved_index_path())
            logger.info(
                "[%s] baseline DB'den v%s'e yükseltildi (onaylı CR'lar korunuyor)",
                project.id, index.baseline.version,
            )
    except Exception:  # noqa: BLE001 — a reconciliation failure must not break indexing/startup
        logger.warning("[%s] DB baseline uzlaştırması başarısız", project.id, exc_info=True)


async def index_project(
    project: ProjectConfig, settings: Settings, repo: CaseFileRepository | None = None
) -> Index:
    """Indexes the project (documents→baseline, all repos→merged graph) and saves it.

    Merges with the DB's approved baseline before saving — a reindex never overwrites
    approved CRs."""
    started = time.monotonic()
    documents = build_documents(project.documents_connector())
    code_repo = _build_code_repo(project, settings)
    extractor = build_scope_extractor(build_llm_client(settings))
    index = await IndexingEngine(
        documents, code_repo, extractor, contract_id=project.contract_id
    ).build()
    _reconcile_with_db(index, project, settings, repo)
    save_index(index, project.resolved_index_path())
    # Index-run history (best-effort): served on the summary's freshness detail.
    try:
        log_event("index", project.id, {
            "modules": len(index.modules),
            "clauses": len(index.baseline.scope_items),
            "seconds": round(time.monotonic() - started, 1),
        })
    except Exception:
        logger.warning("[%s] indeksleme olayı loglanamadı", project.id, exc_info=True)
    return index


def _load_or_build_index(
    project: ProjectConfig, settings: Settings, repo: CaseFileRepository | None = None
) -> Index:
    existing = load_index(project.resolved_index_path())
    if existing is not None:
        return existing
    logger.warning("[%s] indeks yok; canlı indeksleniyor...", project.id)
    return asyncio.run(index_project(project, settings, repo))


def _build_approval(
    repo: CaseFileRepository,
    wiki: WikiStore | None,
    responder: DecisionResponder | None = None,
) -> ApprovalService:
    """Approval + wiki projection + HITL ingest (both absent when the wiki is off)
    + the intake write-back hook (no-ops when no project has a response channel)."""
    ingest = WikiIngest(repo, wiki) if wiki is not None else None
    return ApprovalService(
        repo,
        wiki=wiki,
        ingest=ingest,
        on_decided=responder.on_decision if responder is not None else None,
    )


@lru_cache
def get_context() -> AppContext:
    # Log configuration happens at startup (app.py lifespan → configure_logging); it is not
    # redone here (a cached function shouldn't reconfigure on every request).
    settings = Settings()
    projects = load_projects(settings.projects_path, settings.connectors_path)
    repo = build_repository(settings.db_url)
    wiki_store = build_wiki_store(settings)  # shared: ApprovalService writes, UI reads

    engines: dict[str, TriageEngine] = {}
    consumed_map: dict[str, dict[str, float]] = {}
    precedents_map: dict[str, dict[str, dict]] = {}
    work_item_providers: dict[str, object] = {}
    health_map: dict[str, list[AdapterHealth]] = {}
    intake_map: dict[str, IntakeBinding] = {}
    indexes: dict[str, Index] = {}
    index_paths: dict[str, str] = {}
    meta: list[dict[str, str]] = []

    def _degrade(pid: str, port: str, msg: str) -> None:
        for h in health_map.get(pid, []):
            if h.port == port:
                h.state = "degraded"
                h.error = msg
                return

    responder = DecisionResponder(
        repo, public_base_url=settings.public_base_url, on_error=lambda pid, msg: _degrade(
            pid, "response_channel", msg
        )
    )
    llm = build_llm_client(settings)  # semantic assist on weak matches (if configured)
    embedder = build_embedder(settings)  # deterministic semantic matching (if configured)
    reranker = build_reranker(settings)  # cross-encoder evidence layer (if configured)
    # Decision stamp: the real decision path/version rather than a fake constant
    # (for audit/disputes).
    model_version = _resolve_model_version(settings, llm is not None)
    # Active plugin set (name@version[+gsha]) — stamped onto every decision so a
    # dispute can reconstruct which adapter code produced the evidence. [] when
    # no plugins are installed → historical decisions stay byte-identical.
    plugin_set = get_plugin_registry().stamp()

    for project in projects:
        # Don't let the whole app crash if one project's indexing/setup blows up: log, skip.
        # (Graceful degradation — the remaining projects keep serving; reflects /ready readiness.)
        try:
            index = _load_or_build_index(project, settings, repo)
        except Exception:
            logger.exception("[%s] indeksleme başarısız; proje atlanıyor", project.id)
            continue
        # Rehydration: after a restart, the living baseline (approved CRs) comes back from
        # the DB; if index.json is stale it gets synced. Otherwise the engine would revert
        # to v1 while the audit trail still says vN.
        _reconcile_with_db(index, project, settings, repo)
        # Adapter isolation (finer than the whole-project skip above): a broken
        # work-item/document adapter — e.g. a failed plugin — degrades THIS
        # capability and the project keeps serving. Same philosophy as
        # TriageEngine._safe_find_similar: enrichment failures never kill triage.
        # Each fallback is recorded in AdapterHealth so the UI can show a badge
        # instead of proudly displaying the configured adapter name while the
        # runtime provider is actually the empty Fake.
        health: list[AdapterHealth] = []
        wi_adapter = project.connectors.work_items.adapter
        try:
            work_items = build_work_items(project.connectors.work_items)
            health.append(AdapterHealth("work_items", wi_adapter))
        except Exception as exc:
            logger.exception(
                "[%s] work-item adaptörü kurulamadı; efor geçmişi devre dışı "
                "(tahmin kod metriğine düşer)",
                project.id,
            )
            work_items = FakeWorkItemProvider([])
            health.append(
                AdapterHealth(
                    "work_items", wi_adapter, "degraded", f"{type(exc).__name__}: {exc}"
                )
            )
        consumed = (
            consumed_by_category(work_items.all_items())
            if hasattr(work_items, "all_items")
            else {}
        )
        preamble = build_system_preamble(
            project.language, project.domain_profile, project.instructions
        )
        # Module hints: domain profile (config/domains/*.hints.yaml) + project-specific additions.
        module_hints = {
            **load_module_hints(project.domain_profile),
            **{k: tuple(v) for k, v in project.module_hints.items()},
        }
        # Clause memory (precedents/disputes) from the DB — informational note
        # only, never a decision signal. Failure → empty memory, engine unchanged.
        try:
            cases = repo.list_cases(project.id)
            case_ids = {c.request_id for c in cases}
            project_overrides = [
                o for o in repo.list_overrides() if o.case_id in case_ids
            ]
            precedents = precedents_by_clause(cases, project_overrides)
        except Exception:  # noqa: BLE001 — memory is an enrichment, not a dependency
            logger.warning("[%s] madde hafızası yüklenemedi", project.id, exc_info=True)
            precedents = {}
        doc_adapter = project.connectors.documents.adapter
        try:
            documents = build_documents(project.connectors.documents)
            health.append(AdapterHealth("documents", doc_adapter))
        except Exception as exc:
            logger.exception(
                "[%s] doküman adaptörü kurulamadı; boş kaynakla devam", project.id
            )
            documents = FakeDocumentSourceProvider([])
            health.append(
                AdapterHealth(
                    "documents", doc_adapter, "degraded", f"{type(exc).__name__}: {exc}"
                )
            )
        # Request intake + response channel (both OFF unless configured). Same
        # adapter-isolation pattern: a broken build degrades the badge and the
        # project keeps serving; a healthy "none" adapter records no badge.
        intake_adapter = project.connectors.request_intake.adapter
        if intake_adapter not in ("", "none"):
            try:
                intake_provider = build_request_intake(project.connectors.request_intake)
                if intake_provider is not None:
                    intake_map[project.id] = IntakeBinding(
                        adapter=intake_adapter,
                        provider=intake_provider,
                        mode=project.intake_response_mode,
                        language=project.language,
                    )
                    health.append(AdapterHealth("request_intake", intake_adapter))
            except Exception as exc:
                logger.exception("[%s] talep alma adaptörü kurulamadı", project.id)
                health.append(
                    AdapterHealth(
                        "request_intake", intake_adapter, "degraded",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
        channel_adapter = project.connectors.response_channel.adapter
        if channel_adapter not in ("", "none"):
            try:
                channel = build_response_channel(project.connectors.response_channel)
                if channel is not None:
                    responder.bindings[project.id] = ResponderBinding(
                        adapter=channel_adapter,
                        channel=channel,
                        mode=project.intake_response_mode,
                        language=project.language,
                    )
                    health.append(AdapterHealth("response_channel", channel_adapter))
            except Exception as exc:
                logger.exception("[%s] yanıt kanalı adaptörü kurulamadı", project.id)
                health.append(
                    AdapterHealth(
                        "response_channel", channel_adapter, "degraded",
                        f"{type(exc).__name__}: {exc}",
                    )
                )
        engines[project.id] = TriageEngine(
            work_items,
            StaticCodeRepository(index.modules),
            documents,
            index.baseline,
            model_version=model_version,
            plugin_set=plugin_set,
            index_freshness=index.freshness,
            consumed_by_category=consumed,
            in_scope_threshold=settings.in_scope_threshold,
            gray_threshold=settings.gray_threshold,
            llm_client=llm,
            llm_assist_mode=settings.llm_assist_mode,
            embedder=embedder,
            embed_strong=settings.embed_strong,
            embed_weak=settings.embed_weak,
            reranker=reranker,
            rerank_strong=settings.rerank_strong,
            language=project.language,
            system_preamble=preamble,
            pivot_language=project.pivot_language,
            module_hints=module_hints,
            estimation_params=settings.estimation_params(),
            precedents_by_clause=precedents,
            disputed_escalation=settings.disputed_escalation,
            dependencies=index.dependencies,
        )
        precedents_map[project.id] = precedents
        consumed_map[project.id] = consumed
        work_item_providers[project.id] = work_items
        health_map[project.id] = health
        indexes[project.id] = index
        index_paths[project.id] = project.resolved_index_path()
        meta.append({"id": project.id, "name": project.name})
        logger.info("[%s] motor hazır (%s madde)", project.id, len(index.baseline.scope_items))

    return AppContext(
        engines=engines,
        consumed=consumed_map,
        projects=meta,
        repo=repo,
        approval=_build_approval(repo, wiki_store, responder),
        default_project=projects[0].id,
        user_store=build_user_store(settings.db_url),
        indexes=indexes,
        index_paths=index_paths,
        work_item_providers=work_item_providers,
        wiki=wiki_store,
        precedents=precedents_map,
        adapter_health=health_map,
        intake=intake_map,
        responder=responder,
    )
