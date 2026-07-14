"""HITL ingest (Faz 3): override → precedent, clause conflicts → disputed,
idempotent projection, KPI counters.

Acceptance criteria under test: the PM correction is visible in the wiki
immediately, re-processing the same feedback produces byte-identical files
(no duplicates), and rebuild re-derives the whole derived memory from the DB.
"""

from datetime import UTC, datetime

import pytest
from etki.adapters.filesystem_wiki import FileSystemWikiAdapter
from etki.core.enums import Decision, PmoDecision
from etki.core.models import (
    Baseline,
    CaseFile,
    EffortEstimate,
    EvidenceChain,
    FeedbackEvent,
    ScopeItem,
    TriageDecision,
)
from etki.core.ports import IngestPort
from etki.hitl.ingest import (
    WikiIngest,
    derive_disputes,
    precedents_by_clause,
    reproject_derived,
)
from etki.hitl.service import ApprovalService
from etki.kpi import compute_kpis
from etki.persistence.memory_repo import InMemoryCaseFileRepository
from etki.wiki import rebuild_project

_CLAUSE = ScopeItem(
    id="S1", contract_id="C-1",
    description="Kullanıcı kimlik doğrulama ve oturum yönetimi",
    source_clause="Madde 7.1",
)


def _case(request_id: str, decision: Decision = Decision.IN_SCOPE) -> CaseFile:
    return CaseFile(
        request_id=request_id,
        project_id="demo",
        raw_request="SSO entegrasyonu",
        decisions=[
            TriageDecision(
                request_id=request_id,
                decision=decision,
                evidence=EvidenceChain(
                    reasoning="test", contract_clauses_cited=["Madde 7.1"],
                    cited_clauses=[_CLAUSE],
                ),
                effort_estimate=EffortEstimate(low=1, high=2),
            )
        ],
        created_at=datetime(2026, 7, 9, tzinfo=UTC),
    )


@pytest.fixture
def setup(tmp_path):
    repo = InMemoryCaseFileRepository()
    wiki = FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"))
    ingest = WikiIngest(repo, wiki)
    service = ApprovalService(repo, wiki=wiki, ingest=ingest)
    return repo, wiki, ingest, service, tmp_path


def _snapshot(root):
    return {p.relative_to(root): p.read_text(encoding="utf-8") for p in root.rglob("*.md")}


def test_ingest_satisfies_port(setup):
    _, _, ingest, _, _ = setup
    assert isinstance(ingest, IngestPort)


def test_override_promotes_case_to_precedent(setup):
    repo, wiki, _, service, tmp = setup
    service.record_triage(_case("REQ-demo-p1"))
    service.decide(
        "REQ-demo-p1", 0, PmoDecision.REJECT, actor="pmo",
        current_baseline=Baseline(contract_id="C-1"),
        override_decision=Decision.OUT_OF_SCOPE,  # PMO corrects the system
    )
    pre = (tmp / "wiki-demo" / "precedents" / "PRE-req-demo-p1.md").read_text(encoding="utf-8")
    assert "sistem **IN_SCOPE** dedi, PMO **OUT_OF_SCOPE** olarak düzeltti" in pre
    index = (tmp / "wiki-demo" / "index.md").read_text(encoding="utf-8")
    assert "Emsal (override) dosyası: **1**" in index


def test_approval_without_override_creates_no_precedent(setup):
    repo, _, _, service, tmp = setup
    service.record_triage(_case("REQ-demo-ok"))
    service.decide(
        "REQ-demo-ok", 0, PmoDecision.APPROVE, actor="pmo",
        current_baseline=Baseline(contract_id="C-1"),
    )
    assert not (tmp / "wiki-demo" / "precedents").exists()


def test_conflicting_resolutions_produce_disputed_page(setup):
    repo, _, _, service, tmp = setup
    service.record_triage(_case("REQ-demo-a"))
    service.record_triage(_case("REQ-demo-b"))
    baseline = Baseline(contract_id="C-1")
    service.decide("REQ-demo-a", 0, PmoDecision.APPROVE, actor="pmo", current_baseline=baseline)
    service.decide("REQ-demo-b", 0, PmoDecision.CONVERT_TO_CR, actor="pmo",
                   current_baseline=baseline)
    disputed = (tmp / "wiki-demo" / "disputed.md").read_text(encoding="utf-8")
    assert "## S1 (Madde 7.1)" in disputed
    assert "`REQ-demo-a` → **IN_SCOPE**" in disputed and "`REQ-demo-b` → **CR**" in disputed


def test_agreeing_resolutions_are_not_disputed(setup):
    repo, _, _, service, tmp = setup
    baseline = Baseline(contract_id="C-1")
    for rid in ("REQ-demo-x", "REQ-demo-y"):
        service.record_triage(_case(rid))
        service.decide(rid, 0, PmoDecision.APPROVE, actor="pmo", current_baseline=baseline)
    assert not (tmp / "wiki-demo" / "disputed.md").exists()


def test_pending_decisions_never_enter_disputes():
    assert derive_disputes([_case("REQ-demo-p")]) == []  # human_decision=PENDING


def test_duplicate_ingest_is_idempotent(setup):
    repo, wiki, ingest, service, tmp = setup
    service.record_triage(_case("REQ-demo-dup"))
    service.decide(
        "REQ-demo-dup", 0, PmoDecision.REJECT, actor="pmo",
        current_baseline=Baseline(contract_id="C-1"),
        override_decision=Decision.OUT_OF_SCOPE,
    )
    first = _snapshot(tmp / "wiki-demo")
    event = FeedbackEvent(
        case_id="REQ-demo-dup", decision_index=0, action=PmoDecision.REJECT,
        system_decision=Decision.IN_SCOPE, override=Decision.OUT_OF_SCOPE, revision=2,
    )
    assert ingest.ingest(event) is True  # same event again (e.g. a retry)
    assert _snapshot(tmp / "wiki-demo") == first  # no duplicate writes, same bytes


def test_ingest_unknown_case_returns_false(setup):
    _, _, ingest, _, _ = setup
    event = FeedbackEvent(
        case_id="REQ-yok", decision_index=0, action=PmoDecision.APPROVE,
        system_decision=Decision.IN_SCOPE,
    )
    assert ingest.ingest(event) is False


def test_rebuild_rederives_precedents_and_disputed(setup):
    repo, wiki, _, service, tmp = setup
    baseline = Baseline(contract_id="C-1")
    service.record_triage(_case("REQ-demo-a"))
    service.record_triage(_case("REQ-demo-b"))
    service.decide("REQ-demo-a", 0, PmoDecision.APPROVE, actor="pmo", current_baseline=baseline)
    service.decide("REQ-demo-b", 0, PmoDecision.REJECT, actor="pmo",
                   current_baseline=baseline, override_decision=Decision.OUT_OF_SCOPE)
    root = tmp / "wiki-demo"
    before = _snapshot(root)
    rebuild_project("demo", repo=repo, wiki=wiki)  # wipes + regenerates from the DB
    assert _snapshot(root) == before  # derived memory is part of the projection guarantee


def test_broken_ingest_never_breaks_approval(setup):
    repo, wiki, _, _, _ = setup

    class Exploding:
        def ingest(self, event):  # noqa: ANN001
            raise OSError("disk dolu")

    service = ApprovalService(repo, wiki=wiki, ingest=Exploding())  # type: ignore[arg-type]
    service.record_triage(_case("REQ-demo-err"))
    result = service.decide(  # must not raise
        "REQ-demo-err", 0, PmoDecision.APPROVE, actor="pmo",
        current_baseline=Baseline(contract_id="C-1"),
    )
    assert result.case.status is PmoDecision.APPROVE


def test_kpi_exposes_precedent_and_disputed_counts(setup):
    repo, _, _, service, _ = setup
    baseline = Baseline(contract_id="C-1")
    service.record_triage(_case("REQ-demo-a"))
    service.record_triage(_case("REQ-demo-b"))
    service.decide("REQ-demo-a", 0, PmoDecision.APPROVE, actor="pmo", current_baseline=baseline)
    service.decide("REQ-demo-b", 0, PmoDecision.REJECT, actor="pmo",
                   current_baseline=baseline, override_decision=Decision.OUT_OF_SCOPE)
    k = compute_kpis(repo, baseline, {}, project_id="demo")
    assert k["precedent_count"] == 1
    assert k["disputed_count"] == 1  # IN_SCOPE approval vs REJECTED(IN_SCOPE) on S1


def test_precedents_by_clause_counts_and_aliases():
    from etki.core.models import Override

    case = _case("REQ-demo-a")
    override = Override(
        case_id="REQ-demo-a", decision_index=0,
        system_decision=Decision.IN_SCOPE, human_decision=Decision.OUT_OF_SCOPE,
    )
    memory = precedents_by_clause([case], [override])
    assert memory["S1"]["count"] == 1
    assert memory["S1"]["last"] == "IN_SCOPE→OUT_OF_SCOPE"
    assert memory["Madde 7.1"] is memory["S1"]  # alias: SAME dict object
    assert memory["S1"]["disputed"] is False  # single pending case → no dispute


def test_precedents_by_clause_flags_disputes_without_overrides():
    a, b = _case("REQ-demo-a"), _case("REQ-demo-b")
    a.decisions[0].human_decision = PmoDecision.APPROVE
    b.decisions[0].human_decision = PmoDecision.CONVERT_TO_CR
    memory = precedents_by_clause([a, b], [])
    assert memory["S1"]["disputed"] is True and memory["S1"]["count"] == 0


def test_precedents_by_clause_silent_when_no_memory():
    assert precedents_by_clause([_case("REQ-demo-a")], []) == {}


def test_reproject_derived_scopes_to_project(tmp_path):
    wiki = FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"))
    other = _case("REQ-shop-z")
    other.project_id = "shop"
    reproject_derived(wiki, "demo", [_case("REQ-demo-a"), other], [])
    assert not (tmp_path / "wiki-shop").exists()  # other projects untouched