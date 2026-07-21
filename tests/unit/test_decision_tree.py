"""Unit tests for the decision tree's limit/quota and effort-pool branches."""

from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.core.enums import Decision, Polarity
from etki.core.models import Baseline, ScopeItem, ScopeLimit, WorkItem
from etki.engine.triage import TriageEngine


def _engine(baseline, *, consumed=None, items=None, precedents=None):
    return TriageEngine(
        FakeWorkItemProvider(items if items is not None else []),
        StaticCodeRepository([]),
        FakeDocumentSourceProvider(),
        baseline,
        consumed_by_category=consumed or {},
        precedents_by_clause=precedents,
    )


def _included(**kw) -> ScopeItem:
    base = {"id": "S1", "contract_id": "C", "category": "reporting", "polarity": Polarity.INCLUDED}
    return ScopeItem(**{**base, **kw})


async def test_limit_exceeded_becomes_cr():
    baseline = Baseline(
        contract_id="C",
        scope_items=[_included(description="aylık rapor üretimi", limits=ScopeLimit(quantity=5))],
    )
    case = await _engine(baseline).triage("ayda 8 rapor üretilsin")
    decision = case.decisions[0]
    assert decision.decision is Decision.CR_CANDIDATE
    assert "limit" in decision.evidence.reasoning.lower()


async def test_effort_pool_exceeded_becomes_cr():
    baseline = Baseline(
        contract_id="C",
        scope_items=[_included(description="raporlama rapor üretimi", effort_pool_hours=10)],
    )
    items = [
        WorkItem(
            id="W", title="rapor", description="raporlama", category="reporting",
            effort_seconds=6 * 3600,
        )
    ]
    case = await _engine(baseline, consumed={"reporting": 8.0}, items=items).triage(
        "raporlama rapor eklensin"
    )
    decision = case.decisions[0]
    assert decision.decision is Decision.CR_CANDIDATE
    assert "havuz" in decision.evidence.reasoning.lower()


_MEMORY = {"S1": {"count": 2, "last": "IN_SCOPE→CR_CANDIDATE", "disputed": True, "ref": ""}}


async def test_precedent_note_is_informational_only():
    """The clause-memory note appears in assumptions but decision AND confidence
    stay byte-identical with vs. without the memory (the non-signal contract —
    same shape as the rerank Noop guarantee)."""
    baseline = Baseline(contract_id="C", scope_items=[_included(description="aylık rapor üretimi")])
    plain = (await _engine(baseline).triage("rapor üretimi yapılsın")).decisions[0]
    noted = (
        await _engine(baseline, precedents=_MEMORY).triage("rapor üretimi yapılsın")
    ).decisions[0]

    assert noted.decision is plain.decision and noted.confidence == plain.confidence
    assert not any("Madde hafızası" in a for a in plain.evidence.assumptions)
    assert any("2 geçmiş PMO düzeltmesi" in a for a in noted.evidence.assumptions)
    assert any("ÇELİŞEN nihai kararlar" in a for a in noted.evidence.assumptions)


async def test_precedent_note_looks_up_source_clause_alias():
    baseline = Baseline(
        contract_id="C",
        scope_items=[_included(description="aylık rapor üretimi", source_clause="Madde 4.2")],
    )
    memory = {"Madde 4.2": {"count": 1, "last": "IN_SCOPE→OUT_OF_SCOPE", "disputed": False}}
    case = await _engine(baseline, precedents=memory).triage("rapor üretimi yapılsın")
    assert any("1 geçmiş PMO düzeltmesi" in a for a in case.decisions[0].evidence.assumptions)


async def test_precedent_memory_is_live_by_reference():
    """The engine holds the caller's dict: memory added AFTER construction is
    seen by the next triage (the consumed_by_category idiom)."""
    baseline = Baseline(contract_id="C", scope_items=[_included(description="aylık rapor üretimi")])
    memory: dict = {}
    engine = _engine(baseline, precedents=memory)
    before = await engine.triage("rapor üretimi yapılsın")
    assert not any("Madde hafızası" in a for a in before.decisions[0].evidence.assumptions)

    memory.update({"S1": {"count": 1, "last": "IN_SCOPE→CR_CANDIDATE", "disputed": False}})
    after = await engine.triage("rapor üretimi yapılsın")
    assert any("Madde hafızası" in a for a in after.decisions[0].evidence.assumptions)


async def test_evidence_embeds_cited_clause_detail():
    baseline = Baseline(
        contract_id="C",
        scope_items=[_included(description="aylık rapor üretimi", limits=ScopeLimit(quantity=5))],
    )
    case = await _engine(baseline).triage("rapor üretimi yapılsın")
    cited = case.decisions[0].evidence.cited_clauses
    assert cited  # the FULL text of the cited clause is embedded in the evidence
    assert cited[0].description == "aylık rapor üretimi"
    assert cited[0].limits.quantity == 5


async def test_within_limit_stays_in_scope():
    baseline = Baseline(
        contract_id="C",
        scope_items=[_included(description="aylık rapor üretimi", limits=ScopeLimit(quantity=5))],
    )
    case = await _engine(baseline).triage("ayda 2 rapor üretilsin")
    assert case.decisions[0].decision is Decision.IN_SCOPE


async def test_short_request_never_high_confidence_in_scope(engine):
    """B2 min-token guard: a request with only 1-2 meaningful tokens can at most
    become GRAY (escalate to PMO) — never a high-confidence IN_SCOPE."""
    case = await engine.triage("rapor filtresi")
    decision = case.decisions[0]
    assert decision.decision is not Decision.IN_SCOPE



async def test_disputed_clause_escalates_risk_not_decision():
    """Dispute → RISK-layer escalation (24h PMO look), same pattern as the
    security-wording rule: decision, confidence and effort stay byte-identical;
    only escalation + a risk signal are added."""
    baseline = Baseline(contract_id="C", scope_items=[_included(description="aylık rapor üretimi")])
    plain = (await _engine(baseline).triage("rapor üretimi yapılsın")).decisions[0]
    disputed = (
        await _engine(baseline, precedents=_MEMORY).triage("rapor üretimi yapılsın")
    ).decisions[0]

    assert disputed.risk.escalation and not plain.risk.escalation
    assert any("ihtilaf" in s for s in disputed.risk.signals)
    # The non-signal contract holds for everything the decision is made of.
    assert disputed.decision is plain.decision and disputed.confidence == plain.confidence
    assert (disputed.effort_estimate.low, disputed.effort_estimate.high) == (
        plain.effort_estimate.low, plain.effort_estimate.high,
    )


async def test_precedents_without_dispute_do_not_escalate():
    baseline = Baseline(contract_id="C", scope_items=[_included(description="aylık rapor üretimi")])
    memory = {"S1": {"count": 3, "last": "IN_SCOPE→CR_CANDIDATE", "disputed": False}}
    decision = (
        await _engine(baseline, precedents=memory).triage("rapor üretimi yapılsın")
    ).decisions[0]
    assert not decision.risk.escalation  # corrections alone are not a dispute


async def test_disputed_escalation_kill_switch():
    baseline = Baseline(contract_id="C", scope_items=[_included(description="aylık rapor üretimi")])
    from etki.adapters.code_index import StaticCodeRepository
    from etki.adapters.fakes.document import FakeDocumentSourceProvider
    from etki.adapters.fakes.work_item import FakeWorkItemProvider

    engine = TriageEngine(
        FakeWorkItemProvider([]), StaticCodeRepository([]), FakeDocumentSourceProvider(),
        baseline, precedents_by_clause=_MEMORY, disputed_escalation=False,
    )
    decision = (await engine.triage("rapor üretimi yapılsın")).decisions[0]
    assert not decision.risk.escalation  # off → note only (old behavior)
    assert any("ÇELİŞEN nihai kararlar" in a for a in decision.evidence.assumptions)


async def test_period_mismatch_adds_note_without_changing_the_decision():
    """'10 yearly' vs a 5/monthly clause limit: the quota branch still fires
    (period-blind by design for now), but the evidence chain now SAYS the
    periods were not reconciled. Decision/confidence/effort stay byte-identical
    to the matching-period phrasing of the same breach."""
    def fresh_baseline():
        return Baseline(
            contract_id="C",
            scope_items=[_included(
                description="aylık rapor üretimi",
                limits=ScopeLimit(quantity=5, period="monthly"),
            )],
        )

    mismatch = (await _engine(fresh_baseline()).triage("yılda 8 rapor üretilsin")).decisions[0]
    same = (await _engine(fresh_baseline()).triage("ayda 8 rapor üretilsin")).decisions[0]

    assert mismatch.decision is same.decision is Decision.CR_CANDIDATE
    assert mismatch.confidence == same.confidence
    assert (mismatch.effort_estimate.low, mismatch.effort_estimate.high) == (
        same.effort_estimate.low, same.effort_estimate.high
    )
    assert any("periyot" in a for a in mismatch.evidence.assumptions)
    assert not any("periyot" in a for a in same.evidence.assumptions)
