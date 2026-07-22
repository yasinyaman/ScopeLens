"""Effort estimation (Epic F): three-point + triangular/PERT distribution → P10–P80 range.

Golden rule: never give a single number, give a range (cone of uncertainty).
Sources: analogy (similar past work), code metrics (LOC), churn risk. Percentiles
are computed analytically — no RNG, fully deterministic (critical for the gate).

The constants (LOC/hour, optimistic/pessimistic factors, churn widening, base
hours) are NOT EMBEDDED IN CODE — they come from config via `EstimationParams`
(`Settings.estimation_params()`; env: ETKI_EST_*). As pilot data accumulates,
`pilot/calibration.py` produces suggestions for these constants; a human approves
and updates the config.
"""

from __future__ import annotations

from pydantic import BaseModel

from etki.core.models import CodeModule, EffortEstimate, WorkItem
from etki.i18n import t


class EstimationParams(BaseModel):
    """Estimation constants — calibratable (source: config, one place)."""

    loc_per_hour: float = 120.0  # LOC → hours conversion on the code-metric path
    optimistic_factor: float = 0.6  # optimistic = likely × this
    pessimistic_factor: float = 2.0  # pessimistic = likely × this
    churn_pessimistic_factor: float = 1.5  # upper-bound widening under high churn
    high_churn_commits: int = 15  # "high churn" threshold (commits/6mo)
    base_hours: float = 2.0  # rough floor when no source exists (likely)
    # Dependency (version migration / library add) surface constants: the effort
    # driver is NOT module LOC but the package's usage surface (manifest+lock+CI
    # base, test/compat cost per using module, review cost per call site to
    # audit).
    dep_base_hours: float = 4.0  # manifest/lock/CI base (fixed work on every upgrade)
    dep_hours_per_module: float = 2.0  # per module using the package
    dep_hours_per_api: float = 0.5  # per used API symbol (call site)
    dep_unknown_widen: float = 1.5  # upper-bound factor when the call surface is not in the graph
    # Narrow-spread floor on the analogy path: two near-identical analogs ([4,5])
    # collapse p10/p80 to a sub-hour band that misses realistic actuals. When the
    # spread is thinner than likely × this ratio, widen with the factors (never
    # narrowing the observed range). 0.0 = zero-spread-only (old behavior).
    min_spread_ratio: float = 0.0


class DependencySurface(BaseModel):
    """Technical surface of a dependency request: the number of modules actually
    using the package + the number of used APIs (call sites) visible in the code
    graph."""

    modules: int = 0
    apis: int = 0


_DEFAULT_PARAMS = EstimationParams()


def consumed_by_category(items: list[WorkItem]) -> dict[str, float]:
    """Consumed effort per category (hours) — for the effort-pool check."""
    totals: dict[str, float] = {}
    for item in items:
        if item.category:
            totals[item.category] = totals.get(item.category, 0.0) + item.effort_seconds / 3600
    return totals


def _triangular_percentile(low: float, mode: float, high: float, q: float) -> float:
    """Inverse CDF of the triangular distribution (low ≤ mode ≤ high)."""
    if high <= low:
        return low
    split = (mode - low) / (high - low)
    if q <= split:
        return low + ((q * (high - low) * (mode - low)) ** 0.5)
    return high - (((1 - q) * (high - low) * (high - mode)) ** 0.5)


def estimate(
    similar: list[WorkItem],
    impacted: list[CodeModule],
    params: EstimationParams | None = None,
    *,
    lang: str = "tr",
    dep_surface: DependencySurface | None = None,
) -> EffortEstimate:
    """Estimate from the strongest source to the weakest: past effort (analogy) →
    dependency surface (on version migrations) → code metric → rough floor.
    With a missing source the estimate is kept LOW and flagged as an assumption
    (calibration: not to inflate genuinely small jobs).

    When `dep_surface` is given (the request is a dependency change) the
    code-metric path is SKIPPED: a version upgrade doesn't rewrite the module, it
    touches call sites — the modules' total LOC is the wrong denominator (the
    triage inconsistency: 14k LOC produced 98–173h while the tool floor said ~2h;
    the honest answer is proportional to the surface).

    The `basis` free text is produced in the project language (i18n catalog) and
    written frozen into the evidence chain."""
    p = params or _DEFAULT_PARAMS
    if similar:  # strongest source: real past effort (analogy)
        hours = sorted(it.effort_seconds / 3600 for it in similar)
        optimistic = hours[0]
        likely = hours[len(hours) // 2]
        pessimistic = hours[-1]
        hours_text = ", ".join(t("engine.est.hours", lang, h=f"{h:.0f}") for h in hours)
        basis = t("engine.est.similar", lang, n=len(similar), hours=hours_text)
        if pessimistic <= optimistic:
            # Zero spread (one similar ticket, or identical efforts): a point is
            # not a range — widen with the configured factors so the golden rule
            # ("never a single number") holds on the analogy path too.
            optimistic = likely * p.optimistic_factor
            pessimistic = likely * p.pessimistic_factor
            basis += "; " + t("engine.est.zero_spread", lang)
        elif pessimistic - optimistic <= likely * p.min_spread_ratio:
            # Narrow spread: near-identical analogs make p10/p80 collapse to a
            # sliver. Widen with the factors via min/max — the observed analog
            # range itself is never narrowed.
            optimistic = min(optimistic, likely * p.optimistic_factor)
            pessimistic = max(pessimistic, likely * p.pessimistic_factor)
            basis += "; " + t("engine.est.narrow_spread", lang)
    elif dep_surface is not None:  # dependency change: from the usage surface
        likely = (
            p.dep_base_hours
            + p.dep_hours_per_module * dep_surface.modules
            + p.dep_hours_per_api * dep_surface.apis
        )
        optimistic = likely * p.optimistic_factor
        pessimistic = likely * p.pessimistic_factor
        basis = t(
            "engine.est.dep_surface", lang,
            mods=dep_surface.modules, apis=dep_surface.apis,
        )
        if dep_surface.apis == 0:  # call surface invisible → uncertainty goes up
            pessimistic *= p.dep_unknown_widen
            basis += "; " + t("engine.est.dep_unknown", lang)
    elif impacted:  # code exists: from the complexity metric
        loc = sum(m.complexity.loc for m in impacted)
        likely = max(p.base_hours, loc / p.loc_per_hour)
        optimistic = likely * p.optimistic_factor
        pessimistic = likely * p.pessimistic_factor
        basis = t("engine.est.code_metric", lang)
    else:  # neither history nor code → rough floor (assumption; may grow as real scope clears up)
        likely = p.base_hours
        optimistic = likely * p.optimistic_factor
        pessimistic = likely * p.pessimistic_factor
        basis = t("engine.est.floor", lang)

    if any(m.churn.commits_last_6mo > p.high_churn_commits for m in impacted):
        pessimistic *= p.churn_pessimistic_factor
        basis += "; " + t("engine.est.churn_widen", lang)

    low_pt = min(optimistic, likely, pessimistic)
    high_pt = max(optimistic, likely, pessimistic)
    mode_pt = min(max(likely, low_pt), high_pt)

    p10 = _triangular_percentile(low_pt, mode_pt, high_pt, 0.10)
    p80 = _triangular_percentile(low_pt, mode_pt, high_pt, 0.80)
    pert_mean = (low_pt + 4 * mode_pt + high_pt) / 6
    basis += "; " + t("engine.est.pert", lang, mean=f"{pert_mean:.0f}")

    return EffortEstimate(low=round(p10, 1), high=round(p80, 1), unit="hour", basis=basis)
