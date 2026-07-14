"""Eval statistics helpers — honest reporting on small samples.

On a golden set of n≈60-70 cases a point estimate alone is misleading (the 0.8
threshold is open to statistical noise at this size). The Wilson score interval is
reported; a threshold breach counts as "uyari" (warning) if MARGINAL (the interval
still covers the threshold) and as "kaldi" (fail) if CLEAR (even the upper bound is
below the threshold).
"""

from __future__ import annotations

import math

_Z = 1.96  # 95% confidence


def wilson_interval(successes: int, n: int, z: float = _Z) -> tuple[float, float]:
    """Wilson score interval for a binomial rate (robust vs normal approx at small n)."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, center - margin), min(1.0, center + margin)


def gate_verdict(successes: int, n: int, threshold: float) -> tuple[str, tuple[float, float]]:
    """Threshold verdict: 'gecti' (pass) | 'uyari' (marginal breach) | 'kaldi' (clear breach)."""
    low, high = wilson_interval(successes, n)
    point = successes / n if n else 0.0
    if point >= threshold:
        return "gecti", (low, high)
    if high >= threshold:
        return "uyari", (low, high)  # point below threshold but within the noise margin
    return "kaldi", (low, high)
