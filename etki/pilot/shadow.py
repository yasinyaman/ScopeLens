"""Shadow-mode pilot (Phase 4): the system recommends, compared against the PMO reference.

Does not affect the live flow; measures accuracy over a labeled pilot CR set. Report:
decision agreement, effort-in-range accuracy, per-decision-type precision/recall, and
confidence calibration (does higher confidence mean higher accuracy?).
"""

from __future__ import annotations

import json
from pathlib import Path

from etki.engine.triage import TriageEngine

_BUCKETS = [(0.0, 0.6, "düşük"), (0.6, 0.8, "orta"), (0.8, 1.01, "yüksek")]


def _precision_recall(rows: list[dict]) -> dict[str, dict]:
    labels = {r["expected"] for r in rows} | {r["system"] for r in rows}
    out: dict[str, dict] = {}
    for label in sorted(labels):
        tp = sum(1 for r in rows if r["system"] == label and r["expected"] == label)
        sys_n = sum(1 for r in rows if r["system"] == label)
        exp_n = sum(1 for r in rows if r["expected"] == label)
        out[label] = {
            "precision": round(tp / sys_n, 2) if sys_n else None,
            "recall": round(tp / exp_n, 2) if exp_n else None,
            "support": exp_n,
        }
    return out


def _confidence_calibration(rows: list[dict]) -> list[dict]:
    buckets = []
    for low, high, name in _BUCKETS:
        members = [r for r in rows if low <= r["confidence"] < high]
        if not members:
            continue
        correct = sum(1 for r in members if r["match"])
        buckets.append({
            "bucket": name,
            "n": len(members),
            "accuracy": round(correct / len(members), 2),
        })
    return buckets


async def run(engine: TriageEngine, dataset_path: str | Path) -> dict:
    cases = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    rows: list[dict] = []
    for cr in cases:
        case = await engine.triage(cr["request_text"], request_id=cr["id"])
        decision = case.decisions[0]
        actual = cr["actual_effort_hours"]
        rows.append({
            "id": cr["id"],
            "system": decision.decision.value,
            "expected": cr["expected_decision"],
            "match": decision.decision.value == cr["expected_decision"],
            "confidence": decision.confidence,
            "in_range": decision.effort_estimate.low <= actual <= decision.effort_estimate.high,
            # Calibration input (C2): estimate range vs actual effort.
            "est_low": decision.effort_estimate.low,
            "est_high": decision.effort_estimate.high,
            "actual": actual,
        })

    total = len(rows)
    return {
        "cases": total,
        "agreement": round(sum(r["match"] for r in rows) / total, 3) if total else 0.0,
        "effort_in_range": round(sum(r["in_range"] for r in rows) / total, 3) if total else 0.0,
        "by_decision": _precision_recall(rows),
        "confidence_calibration": _confidence_calibration(rows),
        "mismatches": [r for r in rows if not r["match"]],
        "rows": rows,  # the calibration loop (est range vs actual) is fed from here
    }
