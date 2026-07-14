"""C1: Wilson interval + distinguishing marginal vs. clear threshold breaches (eval/stats.py)."""

from eval.stats import gate_verdict, wilson_interval


def test_wilson_interval_basics():
    low, high = wilson_interval(60, 66)
    assert 0.80 < low < 0.91 < high < 0.97
    assert wilson_interval(0, 0) == (0.0, 0.0)
    low0, _ = wilson_interval(0, 10)
    assert low0 == 0.0


def test_gate_verdict_pass_warn_fail():
    # point estimate above threshold → pass
    assert gate_verdict(60, 66, 0.8)[0] == "gecti"
    # point estimate below threshold but upper bound still covers it → marginal → warn
    assert gate_verdict(50, 66, 0.8)[0] == "uyari"  # 76%, upper bound ~85%
    # clear breach → fail
    assert gate_verdict(30, 66, 0.8)[0] == "kaldi"
