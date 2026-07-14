from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.core.enums import Decision
from etki.engine.triage import TriageEngine, split_request

from tests.fixtures.sample_request import FILTER_AND_SSO, FILTER_ONLY, SSO_ONLY
from tests.fixtures.sample_scope import MINI_BASELINE


def test_split_request_separates_two_subrequests():
    subs = split_request(FILTER_AND_SSO)
    assert len(subs) == 2


async def test_filter_request_is_in_scope(engine: TriageEngine):
    case = await engine.triage(FILTER_ONLY)
    assert case.decisions[0].decision is Decision.IN_SCOPE


async def test_sso_request_is_out_of_scope_with_cited_clause(engine: TriageEngine):
    case = await engine.triage(SSO_ONLY)
    decision = case.decisions[0]
    assert decision.decision is Decision.OUT_OF_SCOPE
    assert decision.cr_draft is not None
    assert decision.evidence.contract_clauses_cited  # the EXCLUDED clause is cited


async def test_estimate_is_always_a_range(engine: TriageEngine):
    case = await engine.triage(FILTER_ONLY)
    est = case.decisions[0].effort_estimate
    assert est.low <= est.high
    assert est.basis


async def test_engine_works_with_injected_baseline():
    # The core depends on the injected baseline, not the seed — proof of vendor-agnosticism.
    engine = TriageEngine(
        FakeWorkItemProvider(),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        MINI_BASELINE,
    )
    case = await engine.triage("sso entegrasyonu eklensin")
    assert case.decisions[0].decision is Decision.OUT_OF_SCOPE
