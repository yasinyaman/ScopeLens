"""Risk probability: falls back to code complexity when there is no commit/ticket history."""

from etki.core.models import Churn, CodeModule, Complexity
from etki.engine.estimation import estimate
from etki.engine.triage import TriageEngine, _risk


def _mod(id: str, *, loc: int = 0, cx: int = 0, churn: int = 0) -> CodeModule:
    return CodeModule(
        id=id, path=id, complexity=Complexity(loc=loc, cyclomatic=cx),
        churn=Churn(commits_last_6mo=churn),
    )


def test_complexity_drives_risk_when_no_churn():
    # no history (churn 0) but a complex module -> NOT 'low', relies on code complexity
    risk = _risk([_mod("api", loc=1600, cx=140), _mod("core", loc=300, cx=10)])
    assert risk.probability == "orta"  # cyclomatic 140 > 50
    assert "kod karmaşıklığı" in risk.basis
    assert any("cyclomatic" in s for s in risk.signals)


def test_simple_new_module_is_low():
    risk = _risk([_mod("util", loc=40, cx=3)])
    assert risk.level.value == "LOW"
    assert "geçmişi yok" in risk.basis


def test_churn_dominates_when_present():
    # when real history exists, churn can raise the probability (the worse case wins)
    risk = _risk([_mod("hot", cx=5, churn=25)])
    assert risk.probability == "yüksek"
    assert "commit/6ay" in risk.basis


# --- Source fusion: assumption for missing layers (min->max source) ---------


def test_estimate_no_sources_is_low_floor():
    # neither history nor code -> rough LOWER-BOUND (calibration: don't inflate small tasks)
    est = estimate([], [])
    assert "alt-sınır" in est.basis
    assert est.low < est.high <= 4.0


def test_estimate_prefers_code_when_present():
    # when code is available, derive from the complexity metric (strongest available source)
    est = estimate([], [_mod("api", loc=1200)])
    assert "kod karmaşıklığına dayalı" in est.basis


def test_coverage_lists_three_sources_with_flags():
    cov = TriageEngine._coverage(covered_scope=True, inc_score=0.4, impacted=[], similar=[])
    assert [c.source for c in cov] == ["Şartname / ister", "Kod grafiği", "Geçmiş efor"]
    assert cov[0].covered and not cov[1].covered and not cov[2].covered


def test_assumptions_flag_spec_only_and_missing_history():
    notes = TriageEngine._assumptions(covered_scope=True, has_code=False, has_history=False)
    assert any("kodda henüz yok" in n for n in notes)  # spec exists, no code -> lower-bound
    assert any("geçmiş iş yok" in n for n in notes)
