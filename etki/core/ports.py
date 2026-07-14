"""Abstract ports (hexagonal architecture). The core talks ONLY to these; it
knows no vendor name (GLPI/GitHub/SharePoint). Adapters implement these
Protocols and normalize away the vendor differences.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from etki.core.enums import PmoDecision
from etki.core.models import (
    AuditEvent,
    Baseline,
    CaseFile,
    CodeModule,
    DocumentRef,
    FeedbackEvent,
    Override,
    WorkItem,
)


class Capabilities(BaseModel):
    """Capability declaration. The system degrades gracefully based on this:
    falls back to polling when there's no webhook, to a full re-index when
    there's no incremental diff.
    """

    supports_webhooks: bool = False
    supports_realtime: bool = False
    supports_effort_tracking: bool = False
    supports_incremental_diff: bool = False


@runtime_checkable
class WorkItemProvider(Protocol):
    """Abstracts the work-tracking tool (GLPI/Jira/ADO...). Effort arrives normalized."""

    async def get_work_item(self, item_id: str) -> WorkItem: ...

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class CodeRepositoryProvider(Protocol):
    """Abstracts the code repository (GitHub/GitLab/git...) and the indexed
    module graph."""

    async def list_modules(self) -> list[CodeModule]: ...

    async def get_impacted(self, module_hint: str | None) -> list[CodeModule]: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class DocumentSourceProvider(Protocol):
    """Abstracts the document source (FileSystem/SharePoint/Confluence...)."""

    async def list_documents(self) -> list[DocumentRef]: ...

    async def fetch_content(self, document_id: str) -> bytes: ...

    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class LLMClient(Protocol):
    """Abstracts the LLM serving layer (vLLM / OpenAI-compatible). Falls back
    to heuristics when there's no endpoint."""

    async def complete_json(self, *, system: str, user: str) -> dict: ...


@runtime_checkable
class RerankProvider(Protocol):
    """Abstracts a cross-encoder reranker endpoint (TEI-compatible `/rerank`).
    Reads (query, document) pairs JOINTLY — measured on EtkiBench as the first
    non-LLM mechanism that separates "paraphrase of a clause" from "new
    capability near a clause" (AUC 0.975). Deterministic for a given model.
    No endpoint configured → the engine runs without this evidence layer."""

    async def rerank(self, query: str, documents: list[str]) -> list[float]:
        """Returns one raw-logit score per document, aligned with the input order."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Abstracts the embedding serving layer (Ollama / vLLM / any OpenAI-compatible
    endpoint). Unlike the LLM, embeddings are DETERMINISTIC for a given model —
    semantic matching through this port stays reproducible and auditable. No
    endpoint configured → the engine runs pure lexical matching, unchanged."""

    async def embed(self, texts: list[str], *, kind: str = "document") -> list[list[float]]:
        """kind: "document" (clause texts) or "query" (the incoming request) —
        retrieval embedding models require distinct task prefixes per side."""
        ...


class GraphNode(BaseModel):
    """One retrievable node of the knowledge graph. Ids are TYPE-PREFIXED so a
    mixed result list stays unambiguous: `scope:SCOPE-001`, `module:auth`,
    `workitem:WI-101`."""

    id: str
    type: str  # scope | module | workitem
    text: str = ""
    score: float = 0.0


class GraphEdge(BaseModel):
    source: str
    relation: str  # maps_to | depends_on | depended_by | touches
    target: str


class Subgraph(BaseModel):
    """expand() output: seed neighbourhood packed under a token budget."""

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    token_estimate: int = 0
    truncated: bool = False  # budget hit before the frontier was exhausted
    packing: str = "bfs"  # how the budget was filled: "bfs" | "rerank" (Faz 4)


class QueryResult(BaseModel):
    """nl_query()/query() output. `strategy` records the path actually taken
    (find_k | expand | nl_query | nl_fallback) — auditable, like everything else."""

    strategy: str
    nodes: list[GraphNode] = []
    subgraph: Subgraph | None = None
    tool: str | None = None  # nl_query: which whitelisted tool the LLM picked
    tool_args: dict = {}
    tool_result: dict | list | None = None


@runtime_checkable
class GraphQueryPort(Protocol):
    """Unified retrieval over the knowledge graph (scope clauses + code modules +
    historical work items) — three strategies behind ONE port (GraphRAG Faz 2).
    Retrieval only: results feed context/precedent lookup, never a decision
    directly (the measured bi-encoder rule: candidates, not verdicts)."""

    async def find_k_nodes(
        self, text: str, k: int = 5, node_types: list[str] | None = None
    ) -> list[GraphNode]: ...

    async def expand(
        self,
        seed_ids: list[str],
        max_hops: int = 2,
        token_budget: int = 1500,
        query: str | None = None,  # given + reranker configured → relevance packing
    ) -> Subgraph: ...

    async def nl_query(self, question: str) -> QueryResult: ...


class WikiSearchHit(BaseModel):
    """One wiki search result: the file + the matching snippet."""

    doc_id: str  # e.g. "DEC-20260709-req-demo-1a2b3c4d"
    path: str  # file path (for display/CLI; the id is what identifies the doc)
    title: str = ""
    snippet: str = ""
    score: float = 0.0


class DisputedEntry(BaseModel):
    """One resolved decision that participates in a clause dispute."""

    case_id: str
    verdict: str  # resolved label: confirmed system decision, "CR" or "REJECTED(…)"
    at: datetime | None = None


class DisputedClause(BaseModel):
    """A scope clause that accumulated CONFLICTING resolved decisions — the
    'disputed' memory the PMO should read before ruling on that clause again."""

    clause_id: str
    clause_ref: str = ""  # source clause ("Madde 7.1") when known
    description: str = ""
    entries: list[DisputedEntry] = []


@runtime_checkable
class WikiStore(Protocol):
    """File-based long-form decision memory (decision wiki). ALWAYS a projection of
    the DB (`CaseFileRepository` is the single source of truth): every file can be
    regenerated from the persisted cases via `rebuild()`; hand edits are not
    supported (they get overwritten). Graph/DB = relations, wiki = readable content.
    A wiki failure must never break triage — callers treat writes as best-effort."""

    def write_decision(self, case: CaseFile) -> str:
        """Projects one case to `decisions/DEC-…md` (overwrite = idempotent).
        Returns the doc id."""
        ...

    def read_decision(self, project_id: str, doc_id: str) -> str | None: ...

    def list_decisions(self, project_id: str) -> list[dict]:
        """Frontmatter metas of every decision file, newest first (UI listing)."""
        ...

    def search(
        self, project_id: str, query: str, *, limit: int = 10
    ) -> list[WikiSearchHit]: ...

    def get_entity_page(self, project_id: str, kind: str, name: str) -> str | None: ...

    def rebuild(self, project_id: str, cases: list[CaseFile]) -> int:
        """Regenerates the whole project wiki from the DB's cases (projection
        guarantee). Returns the number of decision files written."""
        ...

    def write_precedent(self, case: CaseFile, overrides: list[Override]) -> str:
        """Projects an overridden case into `precedents/PRE-…md` (boundary-case
        memory). Overwrite = idempotent. Returns the doc id."""
        ...

    def write_disputed(self, project_id: str, disputes: list[DisputedClause]) -> None:
        """Regenerates the whole `disputed.md` page from the given conflicts
        (empty list removes the page)."""
        ...


@runtime_checkable
class IngestPort(Protocol):
    """HITL feedback ingest (GraphRAG Faz 3): pushes a PMO decision back into the
    derived memory (precedents / disputed / graph). Implementations MUST be
    idempotent — processing the same event twice yields the same state (dedup
    key `case_id + revision`; the wiki implementation is projection-idempotent
    by construction). Best-effort like the wiki itself: a failure never breaks
    the approval flow."""

    def ingest(self, event: FeedbackEvent) -> bool:
        """Returns True when the event was applied (False = unknown case)."""
        ...


class PackageMetadata(BaseModel):
    """Registry metadata for one package — DISPLAY data next to the raw spec.
    Never compared/resolved against the declared spec (no "outdated" boolean:
    PEP 440, semver and maven ranges are different languages)."""

    name: str
    ecosystem: str
    latest_version: str | None = None
    released_at: str | None = None  # ISO date string when the registry provides it
    homepage: str | None = None


@runtime_checkable
class RegistryMetadataProvider(Protocol):
    """Abstracts the public package registries (PyPI / npm / Maven Central…).
    OPTIONAL and off by default (ETKI_DEPS_ONLINE) — CI and air-gapped
    deployments never call out; any failure degrades to None."""

    async def latest(self, ecosystem: str, name: str) -> PackageMetadata | None: ...


@runtime_checkable
class CaseFileRepository(Protocol):
    """Abstracts persistence of case files + audit trail + overrides + versioned
    baseline (SQLite/Postgres... chosen via config). The core knows no concrete DB."""

    def save_case(self, case: CaseFile) -> None: ...

    def get_case(self, request_id: str) -> CaseFile | None: ...

    def list_cases(self, project_id: str | None = None) -> list[CaseFile]: ...

    def set_status(
        self, request_id: str, status: PmoDecision, decided_at: datetime | None
    ) -> None: ...

    def append_audit(self, event: AuditEvent) -> None: ...

    def list_audit(self, case_id: str) -> list[AuditEvent]: ...

    def record_override(self, override: Override) -> None: ...

    def list_overrides(self) -> list[Override]: ...

    def save_baseline_version(self, baseline: Baseline, source_case_id: str | None) -> None: ...

    def latest_baseline(self, contract_id: str) -> Baseline | None: ...

    def list_baseline_versions(self, contract_id: str) -> list[Baseline]: ...
