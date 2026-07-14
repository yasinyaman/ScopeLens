from etki.core.enums import Decision
from etki.core.models import Override
from etki.kpi import calibration_suggestions, effort_pool_status


def test_effort_pool_status_thresholds():
    assert "normal" in effort_pool_status(10, 100)["status"]
    assert "uyarı" in effort_pool_status(70, 100)["status"]
    assert "kritik" in effort_pool_status(90, 100)["status"]


def test_effort_pool_zero_pool_is_safe():
    assert effort_pool_status(5, 0)["ratio"] == 0.0


def test_calibration_suggestions_counts_transitions():
    overrides = [
        Override(case_id="c1", decision_index=0,
                 system_decision=Decision.GRAY_AREA, human_decision=Decision.IN_SCOPE),
        Override(case_id="c2", decision_index=0,
                 system_decision=Decision.GRAY_AREA, human_decision=Decision.IN_SCOPE),
    ]
    out = calibration_suggestions(overrides)
    assert out
    assert "GRAY_AREA" in out[0] and "IN_SCOPE" in out[0]
    assert out[0].startswith("2×")
