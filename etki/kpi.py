"""Monitoring & KPI + feedback (Epic N + P).

Effort-pool early-warning thresholds, over-reliance (override) rate, CR approval speed,
reconciliation %, budget usage; plus threshold-calibration suggestions from overrides.
"""

from __future__ import annotations

from collections import Counter

from etki.core.enums import PmoDecision
from etki.core.models import Baseline, Override
from etki.core.ports import CaseFileRepository
from etki.hitl.ingest import derive_disputes

_TERMINAL = {PmoDecision.APPROVE, PmoDecision.REJECT, PmoDecision.CONVERT_TO_CR}


def effort_pool_status(consumed: float, pool: float) -> dict:
    ratio = consumed / pool if pool > 0 else 0.0
    if ratio >= 0.85:
        status = "🔴 kritik"
    elif ratio >= 0.60:
        status = "🟡 uyarı"
    else:
        status = "🟢 normal"
    return {
        "consumed": round(consumed, 1),
        "pool": pool,
        "ratio": round(ratio, 2),
        "status": status,
    }


def calibration_suggestions(overrides: list[Override]) -> list[str]:
    pairs = Counter((o.system_decision.value, o.human_decision.value) for o in overrides)
    return [
        f"{count}× '{system}' → '{human}' düzeltmesi: ilgili eşik/işaret gözden geçirilmeli."
        for (system, human), count in pairs.most_common()
    ]


def compute_kpis(
    repo: CaseFileRepository,
    baseline: Baseline,
    consumed_by_category: dict[str, float],
    project_id: str | None = None,
) -> dict:
    cases = repo.list_cases(project_id)
    case_ids = {c.request_id for c in cases}
    overrides = [o for o in repo.list_overrides() if o.case_id in case_ids]
    total_decisions = sum(len(c.decisions) for c in cases)
    decided = [c for c in cases if c.status in _TERMINAL]

    by_decision: dict[str, int] = {}
    for case in cases:
        for decision in case.decisions:
            by_decision[decision.decision.value] = by_decision.get(decision.decision.value, 0) + 1

    # Approval speed only makes sense for cases with a terminal PMO decision;
    # counting undecided cases would measure triage→last-edit, not approval time.
    speeds: list[float] = []
    for case in decided:
        events = repo.list_audit(case.request_id)
        if len(events) >= 2 and events[0].at and events[-1].at:
            speeds.append((events[-1].at - events[0].at).total_seconds() / 3600)

    pools = {
        s.category: effort_pool_status(
            consumed_by_category.get(s.category, 0.0), s.effort_pool_hours
        )
        for s in baseline.scope_items
        if s.effort_pool_hours
    }

    return {
        "total_cases": len(cases),
        "total_decisions": total_decisions,
        "reconciliation_pct": round(100 * len(decided) / len(cases)) if cases else 0,
        "override_count": len(overrides),
        "override_rate": round(len(overrides) / total_decisions, 2) if total_decisions else 0.0,
        # Derived HITL memory (Faz 3): boundary cases + clause conflicts — computed
        # from the DB (same source the wiki projects), not read back from files.
        "precedent_count": len({o.case_id for o in overrides}),
        "disputed_count": len(derive_disputes(cases)),
        "avg_cr_approval_hours": round(sum(speeds) / len(speeds), 2) if speeds else None,
        "by_decision": by_decision,
        "effort_pools": pools,
        "calibration": calibration_suggestions(overrides),
        "baseline_version": baseline.version,
        "project_id": project_id,
    }
