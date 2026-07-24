"""SQLAlchemy CaseFileRepository roundtrip (file-based SQLite)."""

from datetime import UTC, datetime

from etki.core.enums import Decision, PmoDecision
from etki.core.models import (
    AuditEvent,
    Baseline,
    CaseFile,
    EffortEstimate,
    Override,
    ScopeItem,
    SubRequest,
    TriageDecision,
)
from etki.persistence.db import init_schema, make_engine, make_session_factory
from etki.persistence.repository import SqlCaseFileRepository


def _repo(tmp_path) -> SqlCaseFileRepository:
    engine = make_engine(f"sqlite:///{tmp_path}/t.db")
    init_schema(engine)
    return SqlCaseFileRepository(make_session_factory(engine))


def _case() -> CaseFile:
    return CaseFile(
        request_id="R1",
        raw_request="rapora filtre",
        sub_requests=[SubRequest(item="rapora filtre")],
        decisions=[
            TriageDecision(
                request_id="R1#1",
                decision=Decision.IN_SCOPE,
                effort_estimate=EffortEstimate(low=1, high=2),
            )
        ],
        status=PmoDecision.PENDING,
        created_at=datetime.now(UTC),
    )


def test_case_roundtrip(tmp_path):
    repo = _repo(tmp_path)
    repo.save_case(_case())
    loaded = repo.get_case("R1")
    assert loaded is not None
    assert loaded.decisions[0].decision is Decision.IN_SCOPE
    assert len(repo.list_cases()) == 1


def test_audit_and_override_persist(tmp_path):
    repo = _repo(tmp_path)
    repo.append_audit(AuditEvent(case_id="R1", seq=0, action="TRIAGED"))
    repo.record_override(
        Override(
            case_id="R1",
            decision_index=0,
            system_decision=Decision.OUT_OF_SCOPE,
            human_decision=Decision.IN_SCOPE,
        )
    )
    assert [e.action for e in repo.list_audit("R1")] == ["TRIAGED"]
    assert repo.list_overrides()[0].human_decision is Decision.IN_SCOPE


def test_list_audit_orders_by_seq_even_when_appended_out_of_order(tmp_path):
    """Port contract: ascending seq. Pinned for BOTH repos (KPI reads
    events[0]/events[-1] as chronological endpoints)."""
    from etki.persistence.memory_repo import InMemoryCaseFileRepository

    for repo in (_repo(tmp_path), InMemoryCaseFileRepository()):
        repo.append_audit(AuditEvent(case_id="R1", seq=2, action="APPROVE"))
        repo.append_audit(AuditEvent(case_id="R1", seq=0, action="TRIAGED"))
        repo.append_audit(AuditEvent(case_id="R1", seq=1, action="PRE_ANALYSIS"))
        assert [e.seq for e in repo.list_audit("R1")] == [0, 1, 2]


def test_list_audit_many_matches_per_case_list_audit(tmp_path):
    """The batched read that feeds the KPI approval-speed metric must be
    byte-identical to calling list_audit per case: same events, same ascending
    seq order, only cases WITH events present. Pinned for BOTH repos."""
    from etki.persistence.memory_repo import InMemoryCaseFileRepository

    for repo in (_repo(tmp_path), InMemoryCaseFileRepository()):
        # R1: two events appended out of order; R2: one; R3: none.
        repo.append_audit(AuditEvent(case_id="R1", seq=1, action="APPROVE"))
        repo.append_audit(AuditEvent(case_id="R1", seq=0, action="TRIAGED"))
        repo.append_audit(AuditEvent(case_id="R2", seq=0, action="TRIAGED"))

        ids = ["R1", "R2", "R3"]
        batched = repo.list_audit_many(ids)
        expected = {cid: repo.list_audit(cid) for cid in ids if repo.list_audit(cid)}

        assert set(batched) == set(expected) == {"R1", "R2"}  # R3 (no events) absent
        for cid in expected:
            assert [(e.seq, e.action, e.at) for e in batched[cid]] == [
                (e.seq, e.action, e.at) for e in expected[cid]
            ]
        assert repo.list_audit_many([]) == {}  # empty id set → no query, empty map


def test_baseline_versioning(tmp_path):
    repo = _repo(tmp_path)
    repo.save_baseline_version(Baseline(contract_id="C", version=1), source_case_id=None)
    item = ScopeItem(id="CR-1", contract_id="C", description="x")
    repo.save_baseline_version(
        Baseline(contract_id="C", version=2, scope_items=[item]),
        source_case_id="R1",
    )
    latest = repo.latest_baseline("C")
    assert latest is not None
    assert latest.version == 2
