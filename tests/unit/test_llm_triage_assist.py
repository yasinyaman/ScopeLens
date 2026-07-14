"""LLM-assisted triage matching: kicks in when the deterministic match is weak, off by default.

Tested with a fake (deterministic) LLMClient — no live API required."""

from etki.adapters.fakes.code_repo import FakeCodeRepositoryProvider
from etki.adapters.fakes.document import FakeDocumentSourceProvider
from etki.adapters.fakes.seed import SEED_BASELINE
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.engine.triage import TriageEngine


class _StubLLM:
    """A fake LLM whose complete_json returns a fixed payload — flags certain modules as
    'impacted'."""

    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls = 0

    async def complete_json(self, *, system: str, user: str) -> dict:
        self.calls += 1
        return self.payload


def _engine(llm=None, mode: str = "pick") -> TriageEngine:
    return TriageEngine(
        FakeWorkItemProvider([]),
        FakeCodeRepositoryProvider(),
        FakeDocumentSourceProvider(),
        SEED_BASELINE.model_copy(deep=True),
        llm_client=llm,
        llm_assist_mode=mode,
    )


async def test_no_llm_is_pure_deterministic():
    # With no LLM, an unrelated request -> no match, LLM isn't called (gate stays deterministic)
    engine = _engine(llm=None)
    decision = (await engine.triage("xyzzy foobar baz qux")).decisions[0]
    assert not decision.evidence.impacted_modules
    assert not any("LLM" in a for a in decision.evidence.assumptions)


async def test_llm_assist_enriches_weak_match():
    # a request with no deterministic match + LLM flags a module as impacted -> it's included
    modules = await FakeCodeRepositoryProvider().list_modules()
    target = modules[0].id
    llm = _StubLLM({"scope_item_id": None, "impacted_modules": [target], "rationale": "anlamsal"})
    engine = _engine(llm=llm)
    decision = (await engine.triage("tamamen alakasız bir talep zzz")).decisions[0]
    assert llm.calls == 1  # LLM was called on a weak match
    assert target in decision.evidence.impacted_modules
    assert any("LLM destekli" in a for a in decision.evidence.assumptions)


async def test_llm_not_called_on_strong_match():
    # with a strong deterministic match, the LLM isn't needed (saves cost/latency)
    item = SEED_BASELINE.scope_items[0]
    llm = _StubLLM({"scope_item_id": None, "impacted_modules": [], "rationale": ""})
    engine = _engine(llm=llm)
    await engine.triage(item.description)  # exact clause text -> strong match
    assert llm.calls == 0


# --- assist v2: match_strength + EXCLUDED matching ---


async def test_strong_included_match_can_reach_in_scope():
    # a paraphrase with no lexical overlap + a STRONG validated LLM match -> IN_SCOPE
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-014",  # reporting, INCLUDED
            "match_strength": "strong",
            "impacted_modules": [],
            "rationale": "paraphrased reporting deliverable",
        }
    )
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "IN_SCOPE"
    assert "SCOPE-014" in [c.id for c in decision.evidence.cited_clauses]


async def test_weak_included_match_stays_capped_at_gray():
    # weak matches keep the old conservative behavior: at most GRAY, never IN_SCOPE
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-014",
            "match_strength": "weak",
            "impacted_modules": [],
            "rationale": "loose similarity",
        }
    )
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "GRAY_AREA"


async def test_missing_strength_treated_as_weak():
    # backward compatibility: a payload without match_strength behaves like today (gray cap)
    llm = _StubLLM({"scope_item_id": "SCOPE-014", "impacted_modules": [], "rationale": ""})
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "GRAY_AREA"


async def test_strong_excluded_match_routes_to_out_of_scope():
    # the LLM may now map to an EXCLUSION clause; a strong one counts as second evidence
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-022",  # SSO/IdP, EXCLUDED
            "match_strength": "strong",
            "impacted_modules": [],
            "rationale": "corporate directory login = IdP integration",
        }
    )
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "OUT_OF_SCOPE"
    cited = [c.id for c in decision.evidence.cited_clauses]
    assert "SCOPE-022" in cited


async def test_weak_excluded_match_is_ignored():
    # a weak exclusion hint must NOT flip the decision (too risky)
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-022",
            "match_strength": "weak",
            "impacted_modules": [],
            "rationale": "maybe",
        }
    )
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value != "OUT_OF_SCOPE"


# --- assist v3: judge mode (candidate shortlist + per-clause verdicts) ---


async def test_judge_covers_strong_reaches_in_scope():
    llm = _StubLLM(
        {
            "verdicts": [{"id": "SCOPE-014", "verdict": "covers", "strength": "strong"}],
            "rationale": "paraphrased reporting deliverable",
        }
    )
    decision = (
        await _engine(llm=llm, mode="judge").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "IN_SCOPE"
    assert "SCOPE-014" in [c.id for c in decision.evidence.cited_clauses]


async def test_judge_new_capability_protects_cr():
    # THE point of judge mode: an explicit new_capability verdict changes NOTHING —
    # the CR answer survives, and the judgment is recorded in the evidence.
    llm = _StubLLM(
        {
            "verdicts": [{"id": "SCOPE-014", "verdict": "new_capability", "strength": "strong"}],
            "rationale": "related to reporting but a new capability",
        }
    )
    decision = (
        await _engine(llm=llm, mode="judge").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"
    assert any("LLM destekli" in a for a in decision.evidence.assumptions)


async def test_judge_excluded_strong_routes_out_of_scope():
    llm = _StubLLM(
        {
            "verdicts": [{"id": "SCOPE-022", "verdict": "excluded", "strength": "strong"}],
            "rationale": "asks for the excluded IdP integration",
        }
    )
    decision = (
        await _engine(llm=llm, mode="judge").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "OUT_OF_SCOPE"
    assert "SCOPE-022" in [c.id for c in decision.evidence.cited_clauses]


async def test_judge_hallucinated_ids_and_weak_exclusions_are_safe():
    llm = _StubLLM(
        {
            "verdicts": [
                {"id": "SCOPE-999", "verdict": "covers", "strength": "strong"},
                {"id": "SCOPE-022", "verdict": "excluded", "strength": "weak"},
            ],
            "rationale": "made up",
        }
    )
    decision = (
        await _engine(llm=llm, mode="judge").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    # hallucinated id ignored; weak exclusion ignored → deterministic outcome stands
    assert decision.decision.value == "CR_CANDIDATE"


async def test_hallucinated_item_id_is_rejected():
    # whitelist: an id not present in the baseline changes nothing
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-999",
            "match_strength": "strong",
            "impacted_modules": [],
            "rationale": "made up",
        }
    )
    decision = (await _engine(llm=llm).triage("tamamen alakasız kelimeler qqq www")).decisions[0]
    assert decision.decision.value == "CR_CANDIDATE"  # unchanged deterministic outcome


# --- assist v4a: pick-then-verify (mode="verify") ---


class _SeqLLM:
    """Fake LLM returning successive payloads (call 1 = pick, call 2 = verify)."""

    def __init__(self, payloads: list) -> None:
        self.payloads = payloads
        self.calls = 0

    async def complete_json(self, *, system: str, user: str) -> dict:
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        if isinstance(payload, Exception):
            raise payload
        return payload


_PICK_STRONG = {
    "scope_item_id": "SCOPE-014",  # reporting, INCLUDED
    "match_strength": "strong",
    "impacted_modules": [],
    "rationale": "near the reporting clause",
}


async def test_verify_covers_keeps_in_scope_floor():
    # verify says the clause covers the request -> identical to pick (IN_SCOPE)
    llm = _SeqLLM([_PICK_STRONG, {"verdict": "covers", "rationale": "same deliverable"}])
    decision = (
        await _engine(llm=llm, mode="verify").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert llm.calls == 2
    assert decision.decision.value == "IN_SCOPE"


async def test_verify_new_capability_cancels_floor_protects_cr():
    # verify flags a new capability -> the in-scope floor is cancelled, the
    # deterministic tree proceeds (CR for an unmatched deliverable)
    llm = _SeqLLM([_PICK_STRONG, {"verdict": "new_capability", "rationale": "not granted"}])
    decision = (
        await _engine(llm=llm, mode="verify").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert llm.calls == 2
    assert decision.decision.value == "CR_CANDIDATE"
    assert any("LLM" in a for a in decision.evidence.assumptions)


async def test_verify_error_fails_open_to_pick():
    # the verify call blowing up must not change pick behavior (fail-open)
    llm = _SeqLLM([_PICK_STRONG, RuntimeError("boom")])
    decision = (
        await _engine(llm=llm, mode="verify").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "IN_SCOPE"


async def test_verify_skips_excluded_picks():
    # exclusion routing is not the verify layer's business: one call only
    llm = _SeqLLM(
        [
            {
                "scope_item_id": "SCOPE-022",  # EXCLUDED in the seed baseline
                "match_strength": "strong",
                "impacted_modules": [],
                "rationale": "explicitly excluded work",
            }
        ]
    )
    decision = (
        await _engine(llm=llm, mode="verify").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert llm.calls == 1
    assert decision.decision.value == "OUT_OF_SCOPE"


async def test_verify_unknown_verdict_treated_as_covers():
    # conservative parsing: garbage verdict -> covers (pick behavior preserved)
    llm = _SeqLLM([_PICK_STRONG, {"verdict": "banana", "rationale": ""}])
    decision = (
        await _engine(llm=llm, mode="verify").triage("tamamen alakasız kelimeler qqq www")
    ).decisions[0]
    assert decision.decision.value == "IN_SCOPE"


# --- v7a: the assist gate opens at a margin-failed exclusion graze ---


async def test_exclusion_graze_reaches_the_assist_and_can_route_out():
    # "sso" grazes SCOPE-022 once (margin fails vs the inc side) -> previously the
    # assist was never consulted; now a strong EXCLUDED pick routes OUT_OF_SCOPE.
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-022",
            "match_strength": "strong",
            "impacted_modules": [],
            "rationale": "asks for identity-provider integration",
        }
    )
    decision = (
        await _engine(llm=llm).triage("rapor verileri sso hesabıyla açılsın")
    ).decisions[0]
    assert llm.calls == 1
    assert decision.decision.value == "OUT_OF_SCOPE"


async def test_included_floor_stays_strict_under_exclusion_graze():
    # with an exclusion graze present, an INCLUDED pick must NOT lift the score
    llm = _StubLLM(
        {
            "scope_item_id": "SCOPE-014",
            "match_strength": "strong",
            "impacted_modules": [],
            "rationale": "loosely reporting-ish",
        }
    )
    decision = (
        await _engine(llm=llm).triage("rapor verileri sso hesabıyla açılsın")
    ).decisions[0]
    assert decision.decision.value != "IN_SCOPE"


# --- v7b: exclusion veto on margin-passing single-hit exclusions ---

# One "sso" graze with near-zero include overlap -> the margin rule routs OUT
# deterministically; the veto question is the only thing standing in the way.
_MARGIN_OUT_REQ = "sso hesabıyla bağlanılsın"


async def test_margin_exclusion_confirmed_stays_out():
    llm = _SeqLLM([{"verdict": "excluded", "rationale": "asks for SSO login itself"}])
    decision = (await _engine(llm=llm).triage(_MARGIN_OUT_REQ)).decisions[0]
    assert llm.calls == 1  # only the veto question; assist skipped on a decided case
    assert decision.decision.value == "OUT_OF_SCOPE"


async def test_margin_exclusion_refuted_is_vetoed():
    llm = _SeqLLM(
        [
            {"verdict": "not_excluded", "rationale": "word overlap only"},
            {"scope_item_id": None, "impacted_modules": [], "rationale": ""},  # assist: no match
        ]
    )
    decision = (await _engine(llm=llm).triage(_MARGIN_OUT_REQ)).decisions[0]
    assert decision.decision.value != "OUT_OF_SCOPE"  # exclusion ignored
    assert any("LLM" in a or "dışlama" in a.lower() for a in decision.evidence.assumptions)


async def test_veto_error_fails_open_to_deterministic_out():
    llm = _SeqLLM([RuntimeError("boom")])
    decision = (await _engine(llm=llm).triage(_MARGIN_OUT_REQ)).decisions[0]
    assert decision.decision.value == "OUT_OF_SCOPE"


async def test_two_hit_exclusions_are_never_questioned():
    # kimlik->auth + sso = 2 hits: strong exclusion evidence, no veto question
    llm = _SeqLLM([{"verdict": "not_excluded", "rationale": "should never be asked"}])
    decision = (
        await _engine(llm=llm).triage("kimlik dogrulamayi sso saglayicisina baglayalim")
    ).decisions[0]
    assert llm.calls == 0
    assert decision.decision.value == "OUT_OF_SCOPE"
