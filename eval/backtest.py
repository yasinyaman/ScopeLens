"""Back-test gate (Faz 2 exit gate).

Over labeled historical CRs: rate of decision agreement with the PMO reference,
rate of actual effort falling within the estimated range, out-of-scope precision/recall.
"""

from __future__ import annotations

import json
from pathlib import Path

from etki.engine.triage import TriageEngine

_OOS = "OUT_OF_SCOPE"


async def evaluate(engine: TriageEngine, dataset_path: str | Path) -> dict:
    cases = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    total = len(cases)
    agree = 0
    in_range = 0
    effort_scored = 0  # rows that carry actual_effort_hours (denominator for range accuracy)
    tp = fp = fn = 0
    rows: list[dict] = []

    for cr in cases:
        case = await engine.triage(cr["request_text"], request_id=cr["id"])
        decision = case.decisions[0]
        got = decision.decision.value
        expected = cr["expected_decision"]
        matched = got == expected
        agree += matched

        low, high = decision.effort_estimate.low, decision.effort_estimate.high
        # actual_effort_hours is optional (custom --dataset runs may only label decisions);
        # range accuracy is computed over the subset that has it.
        actual = cr.get("actual_effort_hours")
        hit = actual is not None and low <= actual <= high
        in_range += hit
        effort_scored += actual is not None

        if got == _OOS and expected == _OOS:
            tp += 1
        elif got == _OOS and expected != _OOS:
            fp += 1
        elif got != _OOS and expected == _OOS:
            fn += 1

        rows.append(
            {"id": cr["id"], "expected": expected, "got": got, "match": matched,
             "actual": actual, "range": [low, high], "in_range": hit}
        )

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    return {
        "agreement": agree / total if total else 0.0,
        # None when no row carries an actual effort (decision-only datasets).
        "range_accuracy": in_range / effort_scored if effort_scored else None,
        "effort_scored": effort_scored,
        "oos_precision": precision,
        "oos_recall": recall,
        "rows": rows,
    }
