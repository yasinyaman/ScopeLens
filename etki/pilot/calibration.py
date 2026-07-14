"""Calibration (Epic P closed loop): threshold suggestions from pilot mismatches.

Suggests adjustments to decision thresholds from systematic deviations between the
system's recommendation and the PMO reference. Does NOT apply automatically — it produces
suggestions; thresholds are config-driven and a human approves changes.
"""

from __future__ import annotations

from collections import Counter

_STEP = 0.05


def suggest_thresholds(
    mismatches: list[dict], in_scope_threshold: float, gray_threshold: float
) -> dict:
    pairs = Counter((m["system"], m["expected"]) for m in mismatches)
    rationale: list[str] = []
    new_in_scope = in_scope_threshold

    too_strict = pairs.get(("GRAY_AREA", "IN_SCOPE"), 0)
    if too_strict:
        new_in_scope = round(max(0.10, in_scope_threshold - _STEP), 2)
        rationale.append(
            f"{too_strict}× GRAY_AREA→IN_SCOPE düzeltmesi: in_scope eşiği "
            f"{in_scope_threshold} → {new_in_scope} düşürülebilir."
        )

    too_loose = pairs.get(("IN_SCOPE", "GRAY_AREA"), 0) + pairs.get(("IN_SCOPE", "CR_CANDIDATE"), 0)
    if too_loose:
        new_in_scope = round(min(0.90, in_scope_threshold + _STEP), 2)
        rationale.append(
            f"{too_loose}× IN_SCOPE fazla geniş: in_scope eşiği "
            f"{in_scope_threshold} → {new_in_scope} yükseltilebilir."
        )

    return {
        "in_scope_threshold": new_in_scope,
        "gray_threshold": gray_threshold,
        "rationale": rationale,
    }


_OVERRUN_RATIO = 0.30  # systematic deviation if ≥30% of rows fall on the same side of the range


def suggest_estimation_params(rows: list[dict]) -> dict:
    """Suggests constant changes (C2) from the estimate-range vs actual-effort deviation
    on closed work.

    Does NOT apply automatically — a human updates the `ETKI_EST_*` config. Input:
    shadow/pilot rows (`est_low`, `est_high`, `actual`). On systematic under/overrun it
    suggests a pessimistic/optimistic factor change."""
    scored = [r for r in rows if "actual" in r and "est_high" in r]
    rationale: list[str] = []
    if not scored:
        return {"rationale": rationale}
    n = len(scored)
    over = sum(1 for r in scored if r["actual"] > r["est_high"])
    under = sum(1 for r in scored if r["actual"] < r["est_low"])
    if over / n >= _OVERRUN_RATIO:
        rationale.append(
            f"{over}/{n} işte gerçek efor tahmin aralığının ÜSTÜNDE: "
            "est_pessimistic_factor (ETKI_EST_PESSIMISTIC_FACTOR) artırılmalı "
            "ya da est_loc_per_hour düşürülmeli."
        )
    if under / n >= _OVERRUN_RATIO:
        rationale.append(
            f"{under}/{n} işte gerçek efor tahmin aralığının ALTINDA: "
            "est_optimistic_factor düşürülmeli ya da est_loc_per_hour artırılmalı."
        )
    return {"n": n, "over": over, "under": under, "rationale": rationale}
