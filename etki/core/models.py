"""Core domain models — Pydantic v2.

The code counterpart of the JSON schemas in the architecture document. Two
architectural invariants are embedded here: ``ScopeItem.polarity``
(INCLUDED/EXCLUDED is first-class) and ``EffortEstimate`` is always a range
(low/high) — single-point estimates are forbidden.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from etki.core.enums import Decision, PmoDecision, Polarity, RequestType, RiskLevel

# --- Scope & contract --------------------------------------------------------


class ScopeLimit(BaseModel):
    quantity: int | None = None
    period: str | None = None


class ScopeItem(BaseModel):
    """The structured form of a single scope clause from the contract."""

    id: str
    contract_id: str
    description: str
    category: str = "genel"
    polarity: Polarity = Polarity.INCLUDED
    limits: ScopeLimit = Field(default_factory=ScopeLimit)
    effort_pool_hours: float | None = None
    source_clause: str | None = None
    mapped_modules: list[str] = Field(default_factory=list)


class Baseline(BaseModel):
    """The approved, versioned scope reference. Each approved CR bumps the
    version by +1."""

    contract_id: str
    version: int = 1
    scope_items: list[ScopeItem] = Field(default_factory=list)
    locked: bool = False
    locked_at: datetime | None = None


# --- Work item (normalized) --------------------------------------------------


class WorkItem(BaseModel):
    """Vendor-agnostic, normalized work item. ``effort_seconds`` is the single
    source of truth for effort (GLPI actiontime, Jira worklog... converted in
    the adapter)."""

    id: str
    title: str
    description: str = ""
    category: str | None = None
    status: str | None = None
    effort_seconds: int = 0
    assignee: str | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None


# --- Code knowledge graph -----------------------------------------------------


class Complexity(BaseModel):
    loc: int = 0
    cyclomatic: int = 0
    files: int = 0


class Churn(BaseModel):
    commits_last_6mo: int = 0


class CodeModule(BaseModel):
    """A module in the code knowledge graph (dependencies + metrics)."""

    id: str
    path: str
    responsibilities: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    depended_by: list[str] = Field(default_factory=list)
    mapped_scope_items: list[str] = Field(default_factory=list)
    # External (third-party) package names this module imports — the usage
    # surface for dependency-impact analysis. Internal modules stay in
    # depends_on; stdlib/builtins are filtered as noise.
    packages: list[str] = Field(default_factory=list)
    # Per-package API symbols this module touches ("requests" → ["get"]) — the
    # call sites to audit on a version change. ast producer only; defaulted.
    package_apis: dict[str, list[str]] = Field(default_factory=dict)
    # Qualified counterparts ("faker" → ["faker.providers.x.CreditCard"]) — the
    # your_code version-diff audit uses these; catches non-exported imports.
    package_api_paths: dict[str, list[str]] = Field(default_factory=dict)
    complexity: Complexity = Field(default_factory=Complexity)
    churn: Churn = Field(default_factory=Churn)


class DeclaredDependency(BaseModel):
    """One dependency declared in a package manifest (requirements.txt,
    package.json, pom.xml, go.mod, Cargo.toml…).

    `raw_spec` is the VERBATIM version spec from the manifest (">=2.28,<3",
    "^4.17", "[1.2,2.0)") — never resolved or compared across ecosystems
    (PEP 440 vs semver vs maven ranges are different languages; v1 needs
    evidence, not resolution)."""

    name: str  # pypi/npm/go/cargo name; maven: "groupId:artifactId"
    raw_spec: str = ""
    ecosystem: str  # pypi | npm | maven | go | cargo
    manifest: str  # provenance, e.g. "requirements.txt" or "repo:pom.xml"
    dev: bool = False  # devDependencies / optional-dependencies / test scope


# --- Document source -----------------------------------------------------


class DocumentRef(BaseModel):
    id: str
    name: str
    path: str
    mime: str = "text/plain"
    modified_at: datetime | None = None
    source: str = "fake"


# --- Triage output -------------------------------------------------------


class BestMatch(BaseModel):
    item: str | None = None
    similarity: float = 0.0


class ModuleSignal(BaseModel):
    """Code signals for an impacted module — the basis for effort/risk estimation.

    In new projects with no commit/ticket history, the estimate rests on these
    structural metrics; frozen at decision time for transparency in the UI."""

    id: str
    loc: int = 0
    cyclomatic: int = 0
    churn: int = 0  # commits in the last 6mo (0/1 ≈ no history → fall back to complexity)


class SourceCoverage(BaseModel):
    """Whether a given evidence source covers this request (fusion of 3 sources).

    A feature shows up in each source at a different time (spec/requirement
    first, then code, then historical effort). Transparently shows which
    source provided evidence; missing sources get an explicit assumption."""

    source: str
    covered: bool = False
    detail: str = ""


class EvidenceChain(BaseModel):
    """Evidence chain — the auditable record used in customer/dispute negotiations."""

    checked_against: list[str] = Field(default_factory=list)
    best_match: BestMatch = Field(default_factory=BestMatch)
    impacted_modules: list[str] = Field(default_factory=list)
    # Code metrics of the impacted modules (basis for the estimate, shown in the UI).
    impacted_signals: list[ModuleSignal] = Field(default_factory=list)
    # Source coverage (spec/code/history) + assumptions made for missing sources.
    source_coverage: list[SourceCoverage] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    reasoning: str = ""
    contract_clauses_cited: list[str] = Field(default_factory=list)
    # FULL form of the cited scope items (frozen at decision time — self-contained).
    cited_clauses: list[ScopeItem] = Field(default_factory=list)


class EffortEstimate(BaseModel):
    """Effort estimate — ALWAYS a range + basis. Single-point estimates are forbidden."""

    low: float
    high: float
    unit: str = "hour"
    basis: str = ""

    @model_validator(mode="after")
    def _check_range(self) -> EffortEstimate:
        if self.low > self.high:
            raise ValueError("EffortEstimate.low, high'tan büyük olamaz (aralık tahmin zorunlu).")
        return self


class Risk(BaseModel):
    probability: str = "düşük"
    impact: str = "düşük"
    level: RiskLevel = RiskLevel.LOW
    escalation: bool = False  # red/critical → escalate within 24 hours
    signals: list[str] = Field(default_factory=list)  # triggering signals
    basis: str = ""  # what the probability rests on (churn history vs code complexity)


class CrDraft(BaseModel):
    impact_analysis: str = ""
    cost: str = ""


class SubRequest(BaseModel):
    """An atomic sub-request (one request can contain several, each resolved separately)."""

    item: str
    type: RequestType = RequestType.UNKNOWN
    module_hint: str | None = None
    quantity: int | None = None  # quantity mentioned in the request (for limit/quota checks)
    period: str | None = None
    # Dependency-change requests only: the recognized package (matched against
    # the manifest declarations) and the target version AS WRITTEN. A version
    # number is never a quantity — the splitter clears `quantity` for this type
    # so the limit/quota step can't misread "Spring Boot 3" as "3 items".
    package: str | None = None
    target_version: str | None = None


class TriageDecision(BaseModel):
    """Decision + evidence + estimate + risk for one sub-request. Awaits PMO approval."""

    request_id: str
    decision: Decision
    confidence: float = 0.0
    evidence: EvidenceChain = Field(default_factory=EvidenceChain)
    effort_estimate: EffortEstimate
    risk: Risk = Field(default_factory=Risk)
    cr_draft: CrDraft | None = None
    index_freshness: str | None = None
    model_version: str = "fake-0"
    human_decision: PmoDecision = PmoDecision.PENDING
    decided_at: datetime | None = None


class ChatTurn(BaseModel):
    """One turn of the pre-analysis chat conducted over a triage output
    (question + assistant answer)."""

    question: str
    answer: str = ""  # assistant's answer (raw markdown; rendered to HTML for display)
    at: datetime | None = None


class CaseFile(BaseModel):
    """The file that collects all sub-request decisions for one request. Submitted
    for PMO approval."""

    request_id: str
    project_id: str | None = None
    raw_request: str
    sub_requests: list[SubRequest] = Field(default_factory=list)
    decisions: list[TriageDecision] = Field(default_factory=list)
    status: PmoDecision = PmoDecision.PENDING
    created_at: datetime | None = None
    # Pre-analysis prepared via chat over the triage output (markdown). Saved to the case.
    pre_analysis: str | None = None
    # Pre-analysis chat about the triage — each turn is saved to the case immediately.
    chat_turns: list[ChatTurn] = Field(default_factory=list)


class Index(BaseModel):
    """Offline indexing output: baseline + code module graph + freshness stamp.
    Triage (online) reads this; it replaces the seed."""

    baseline: Baseline
    modules: list[CodeModule] = Field(default_factory=list)
    # Declared manifest dependencies (dependency-impact analysis). Defaulted —
    # pre-existing index-*.json files load unchanged.
    dependencies: list[DeclaredDependency] = Field(default_factory=list)
    indexed_at: datetime | None = None
    freshness: str = "unknown"


class AuditEvent(BaseModel):
    """An auditable event — lets a decision be reconstructed later for a
    contractual dispute."""

    case_id: str
    seq: int = 0
    actor: str = "system"
    action: str  # TRIAGED | APPROVE | REJECT | CONVERT_TO_CR | OVERRIDE
    detail: dict[str, Any] = Field(default_factory=dict)
    at: datetime | None = None


class Override(BaseModel):
    """PMO decision differs from the system recommendation — an over-reliance metric."""

    case_id: str
    decision_index: int
    system_decision: Decision
    human_decision: Decision
    actor: str = "pmo"
    at: datetime | None = None


class FeedbackEvent(BaseModel):
    """One unit of human feedback on a triage decision (the HITL ingest input).

    `revision` is the audit sequence at emit time: together with `case_id` it is
    the dedup key — but ingest is projection-idempotent anyway (re-processing
    regenerates the same files), so the key documents intent rather than
    guarding a queue."""

    case_id: str
    decision_index: int
    action: PmoDecision
    system_decision: Decision
    override: Decision | None = None  # set when the PMO corrected the system
    actor: str = "pmo"
    revision: int = 0
    at: datetime | None = None
