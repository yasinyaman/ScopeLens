"""Abstract ports (hexagonal architecture). The core talks ONLY to these; it
knows no vendor name (Jira/GitHub/SharePoint). Adapters implement these
Protocols and normalize away the vendor differences.

The EXTERNAL-integration ports (WorkItemProvider, CodeRepositoryProvider,
DocumentSourceProvider, LLMClient, EmbeddingProvider, RerankProvider,
RegistryMetadataProvider, RequestIntakeProvider, ResponseChannel) +
Capabilities/PackageMetadata now live in the frozen plugin API package
``etki_api`` and are re-exported here (redundant-alias form = explicit
re-export): SAME class objects, so every existing import and isinstance
check keeps working. The INTERNAL ports below (persistence, wiki, graph
query, HITL ingest) are deliberately NOT part of the plugin API and may
change freely.

Shadow contract note: the host probes ``WorkItemProvider`` instances for an
optional ``all_items()`` method via hasattr/getattr (effort-pool consumption,
pool refresh, KPI); providers without it degrade to an empty pool. It is not
part of the frozen port — declared via ``Capabilities.supports_enumeration``
(etki-api 0.1.3) and verified conditionally by the conformance suite; see
docs/writing-an-adapter.md §"Optional methods".
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from etki.core.enums import PmoDecision
from etki.core.models import (
    AuditEvent,
    Baseline,
    CaseFile,
    FeedbackEvent,
    Override,
)
from etki_api.models import PackageMetadata as PackageMetadata
from etki_api.ports import Capabilities as Capabilities
from etki_api.ports import CodeRepositoryProvider as CodeRepositoryProvider
from etki_api.ports import DocumentSourceProvider as DocumentSourceProvider
from etki_api.ports import EmbeddingProvider as EmbeddingProvider
from etki_api.ports import LLMClient as LLMClient
from etki_api.ports import RegistryMetadataProvider as RegistryMetadataProvider
from etki_api.ports import RequestIntakeProvider as RequestIntakeProvider
from etki_api.ports import RerankProvider as RerankProvider
from etki_api.ports import ResponseChannel as ResponseChannel
from etki_api.ports import WorkItemProvider as WorkItemProvider


class GraphNode(BaseModel):
    """One retrievable node of the knowledge graph. Ids are TYPE-PREFIXED so a
    mixed result list stays unambiguous: `scope:SCOPE-001`, `module:auth`,
    `workitem:WI-101`."""

    id: str
    type: str  # scope | module | workitem | package
    text: str = ""
    score: float = 0.0


class GraphEdge(BaseModel):
    source: str
    relation: str  # maps_to | depends_on | depended_by | touches | uses_package
    target: str


class Subgraph(BaseModel):
    """expand() output: seed neighbourhood packed under a token budget."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    token_estimate: int = 0
    truncated: bool = False  # budget hit before the frontier was exhausted
    packing: str = "bfs"  # how the budget was filled: "bfs" | "rerank" (Faz 4)


class QueryResult(BaseModel):
    """nl_query()/query() output. `strategy` records the path actually taken
    (find_k | expand | nl_query | nl_fallback) — auditable, like everything else."""

    strategy: str
    nodes: list[GraphNode] = Field(default_factory=list)
    subgraph: Subgraph | None = None
    tool: str | None = None  # nl_query: which whitelisted tool the LLM picked
    tool_args: dict = Field(default_factory=dict)
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

    async def query(self, question: str, *, k: int = 5) -> QueryResult:
        """Facade the production callers use: picks a strategy by rule and
        RECORDS the path taken in `QueryResult.strategy` (auditable)."""
        ...


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
    entries: list[DisputedEntry] = Field(default_factory=list)


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
        """Frontmatter metas of every decision file, newest first (tests/CLI
        today; no UI consumer yet)."""
        ...

    def search(
        self, project_id: str, query: str, *, limit: int = 10
    ) -> list[WikiSearchHit]: ...

    def get_entity_page(self, project_id: str, kind: str, name: str) -> str | None:
        """Not called in production — entity pages are generated and linked as
        files; this retrieval path is test-only."""
        ...

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


@runtime_checkable
class CaseFileRepository(Protocol):
    """Abstracts persistence of case files + audit trail + overrides + versioned
    baseline (SQLite/Postgres... chosen via config). The core knows no concrete DB."""

    def save_case(self, case: CaseFile) -> None: ...

    def get_case(self, request_id: str) -> CaseFile | None: ...

    def list_cases(self, project_id: str | None = None) -> list[CaseFile]: ...

    def set_status(
        self, request_id: str, status: PmoDecision, decided_at: datetime | None
    ) -> None:
        """`decided_at` is persisted where the backend has a column (SQL); the
        in-memory repo ignores it — `CaseFile` carries no case-level field."""
        ...

    def append_audit(self, event: AuditEvent) -> None: ...

    def list_audit(self, case_id: str) -> list[AuditEvent]:
        """Returns the case's events in ascending `seq` order."""
        ...

    def record_override(self, override: Override) -> None: ...

    def list_overrides(self) -> list[Override]: ...

    def save_baseline_version(self, baseline: Baseline, source_case_id: str | None) -> None: ...

    def latest_baseline(self, contract_id: str) -> Baseline | None: ...

    def list_baseline_versions(self, contract_id: str) -> list[Baseline]: ...
