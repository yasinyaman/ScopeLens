"""Custom --dataset eval mode: backtest.evaluate must tolerate decision-only cases
(no actual_effort_hours) and score range accuracy over the labeled subset only."""

import json

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.file_work_item import FileWorkItemProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.indexing.engine import IndexingEngine
from eval import backtest


async def _engine() -> TriageEngine:
    docs = FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"])
    index = await IndexingEngine(
        docs, AstCodeRepositoryProvider("samples/demo_project/src"), HeuristicScopeExtractor()
    ).build()
    return TriageEngine(
        FileWorkItemProvider("samples/demo_project/work_items.json"),
        StaticCodeRepository(index.modules),
        docs,
        index.baseline,
        model_version="test",
        index_freshness=index.freshness,
    )


async def test_mixed_dataset_scores_effort_over_labeled_subset_only(tmp_path):
    cases = [
        {
            "id": "X-1",
            "request_text": "SSO entegrasyonu istiyoruz",
            "expected_decision": "OUT_OF_SCOPE",
            "actual_effort_hours": 21,
        },
        # Decision-only case — must not crash and must not dilute range accuracy.
        {
            "id": "X-2",
            "request_text": "Aylık rapora tarih filtresi eklensin",
            "expected_decision": "IN_SCOPE",
        },
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")

    result = await backtest.evaluate(await _engine(), path)
    assert result["agreement"] == 1.0
    assert result["effort_scored"] == 1  # only X-1 carries an actual effort
    assert result["range_accuracy"] == 1.0  # 1/1, NOT 1/2
    row2 = next(r for r in result["rows"] if r["id"] == "X-2")
    assert row2["actual"] is None and row2["in_range"] is False


async def test_decision_only_dataset_reports_no_range_accuracy(tmp_path):
    cases = [
        {
            "id": "Y-1",
            "request_text": "SSO entegrasyonu istiyoruz",
            "expected_decision": "OUT_OF_SCOPE",
        }
    ]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")

    result = await backtest.evaluate(await _engine(), path)
    assert result["range_accuracy"] is None
    assert result["effort_scored"] == 0
