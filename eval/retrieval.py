"""Retrieval gate metric (Faz 1 exit gate).

For a known CR, does the system retrieve the correct scope clause AND the correct
code regions? Precision/recall/F1 is measured for scope, recall for code modules
(impact propagation inflates the retrieved set, so recall is used for modules).
"""

from __future__ import annotations

import json
from pathlib import Path

from etki.engine.triage import TriageEngine


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


async def evaluate(engine: TriageEngine, dataset_path: str | Path) -> dict:
    cases = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    scope_f1s: list[float] = []
    module_recalls: list[float] = []
    rows: list[dict] = []

    for cr in cases:
        case = await engine.triage(cr["request_text"], request_id=cr["id"])
        retrieved_scopes = {
            d.evidence.best_match.item for d in case.decisions if d.evidence.best_match.item
        }
        retrieved_modules: set[str] = set()
        for decision in case.decisions:
            retrieved_modules.update(decision.evidence.impacted_modules)

        expected_scopes = set(cr["scope_ids"])
        expected_modules = set(cr["modules"])

        scope_tp = len(retrieved_scopes & expected_scopes)
        scope_recall = scope_tp / len(expected_scopes) if expected_scopes else 1.0
        scope_precision = scope_tp / len(retrieved_scopes) if retrieved_scopes else 0.0
        scope_f1 = _f1(scope_precision, scope_recall)
        module_recall = (
            len(retrieved_modules & expected_modules) / len(expected_modules)
            if expected_modules
            else 1.0
        )

        scope_f1s.append(scope_f1)
        module_recalls.append(module_recall)
        rows.append(
            {
                "id": cr["id"],
                "scope_f1": round(scope_f1, 2),
                "module_recall": round(module_recall, 2),
                "retrieved_scopes": sorted(retrieved_scopes),
                "expected_scopes": sorted(expected_scopes),
            }
        )

    mean_scope_f1 = sum(scope_f1s) / len(scope_f1s) if scope_f1s else 0.0
    mean_module_recall = sum(module_recalls) / len(module_recalls) if module_recalls else 0.0
    return {
        "mean_scope_f1": mean_scope_f1,
        "mean_module_recall": mean_module_recall,
        "rows": rows,
    }
