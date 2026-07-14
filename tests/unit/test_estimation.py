from etki.core.models import Churn, CodeModule, Complexity, WorkItem
from etki.engine.estimation import consumed_by_category, estimate


def _wi(seconds: int, category: str = "reporting") -> WorkItem:
    return WorkItem(id="W", title="t", category=category, effort_seconds=seconds)


def test_estimate_returns_range_with_basis():
    est = estimate([_wi(6 * 3600), _wi(9 * 3600)], [])
    assert est.low <= est.high
    assert est.basis
    assert est.unit == "hour"


def test_high_churn_widens_upper_bound():
    churned = CodeModule(
        id="auth", path="auth/", complexity=Complexity(loc=100), churn=Churn(commits_last_6mo=30)
    )
    calm = CodeModule(id="db", path="db/", complexity=Complexity(loc=100))
    high_est = estimate([_wi(10 * 3600)], [churned])
    low_est = estimate([_wi(10 * 3600)], [calm])
    assert high_est.high > low_est.high


def test_no_analogy_falls_back_to_code_metrics():
    est = estimate([], [CodeModule(id="m", path="m/", complexity=Complexity(loc=600))])
    assert est.high > est.low
    assert "kod karmaşıklığ" in est.basis.lower()


def test_consumed_by_category_sums_hours():
    consumed = consumed_by_category(
        [_wi(3600, "reporting"), _wi(7200, "reporting"), _wi(3600, "auth")]
    )
    assert consumed["reporting"] == 3.0
    assert consumed["auth"] == 1.0


def test_estimation_params_come_from_config_not_code():
    """C2: changing the constants via config changes behavior — no code change needed."""
    from etki.config import Settings
    from etki.engine.estimation import EstimationParams, estimate

    default = estimate([], [])
    wide = estimate([], [], EstimationParams(base_hours=10.0, pessimistic_factor=4.0))
    assert wide.high > default.high
    assert wide.low > default.low
    # Settings → EstimationParams bridge (env: ETKI_EST_*)
    p = Settings(est_loc_per_hour=60.0).estimation_params()
    assert isinstance(p, EstimationParams) and p.loc_per_hour == 60.0


def test_estimation_calibration_suggests_on_systematic_overrun():
    """C2 closed loop: a suggestion is produced when actual effort is systematically
    above the range."""
    from etki.pilot.calibration import suggest_estimation_params

    rows = [{"est_low": 1, "est_high": 4, "actual": 9} for _ in range(4)] + [
        {"est_low": 1, "est_high": 4, "actual": 2} for _ in range(6)
    ]
    out = suggest_estimation_params(rows)
    assert out["over"] == 4 and out["rationale"]
    assert suggest_estimation_params([])["rationale"] == []


def test_dependency_surface_beats_module_loc():
    """Triage inconsistency (REQ-warp-f436c329): for a version upgrade the effort
    must be proportional to the usage surface, not the TOTAL LOC of the modules
    importing the package — two modules at 14k LOC yield a reasonable
    surface-based band, not 98–173h."""
    from etki.engine.estimation import DependencySurface

    big = [
        CodeModule(id="src", path="src/", complexity=Complexity(loc=9659)),
        CodeModule(id="tests", path="tests/", complexity=Complexity(loc=4452)),
    ]
    loc_est = estimate([], big)  # old path (no dependency information)
    dep_est = estimate([], big, dep_surface=DependencySurface(modules=2, apis=0))
    assert dep_est.high < loc_est.low  # surface band entirely below the LOC band
    assert dep_est.low > 2.0  # and above the ~2h tool floor (honest middle ground)
    assert "yüzey" in dep_est.basis


def test_dependency_unknown_surface_widens_upper_bound():
    """When call sites are invisible in the graph (apis=0) the upper bound
    widens and the basis says so — uncertainty is never hidden."""
    from etki.engine.estimation import DependencySurface

    known = estimate([], [], dep_surface=DependencySurface(modules=2, apis=6))
    unknown = estimate([], [], dep_surface=DependencySurface(modules=2, apis=0))
    assert "görünmüyor" in unknown.basis
    assert "görünmüyor" not in known.basis


def test_dependency_analogy_still_wins():
    """Real historical effort (analogy) is stronger evidence than the surface
    model — the precedence order is preserved."""
    from etki.engine.estimation import DependencySurface

    est = estimate(
        [_wi(6 * 3600), _wi(9 * 3600)], [],
        dep_surface=DependencySurface(modules=2, apis=0),
    )
    assert "benzer" in est.basis  # analogy basis, not the surface basis
