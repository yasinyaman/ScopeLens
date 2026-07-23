"""Shadow-mode pilot + calibration closed loop."""

from pathlib import Path

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.file_work_item import FileWorkItemProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.core.enums import Decision
from etki.engine.estimation import consumed_by_category
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.indexing.engine import IndexingEngine
from etki.pilot import shadow
from etki.pilot.calibration import suggest_thresholds

_DATASET = Path(__file__).resolve().parents[1].parent / "eval" / "datasets" / "pilot_crs.json"


async def _engine(in_scope: float = 0.22, gray: float = 0.06) -> TriageEngine:
    documents = FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"])
    code = AstCodeRepositoryProvider("samples/demo_project/src")
    index = await IndexingEngine(documents, code, HeuristicScopeExtractor()).build()
    work_items = FileWorkItemProvider("samples/demo_project/work_items.json")
    return TriageEngine(
        work_items,
        StaticCodeRepository(index.modules),
        documents,
        index.baseline,
        consumed_by_category=consumed_by_category(work_items.all_items()),
        in_scope_threshold=in_scope,
        gray_threshold=gray,
    )


async def test_shadow_pilot_reports_honestly():
    """W5: the pilot is a DIAGNOSTIC, not a CI gate — the refreshed answer key
    (zero backtest copies) honestly scores below the 0.75 bar, and that number
    must be reported, not gamed. This test pins the reporting mechanism plus a
    collapse floor (well below the quality bar on purpose)."""
    report = await shadow.run(await _engine(), _DATASET)
    assert 0.4 <= report["agreement"] < 1.0  # honest mid-range, not the circular 100%
    assert report["effort_in_range"] is not None
    assert report["confidence_calibration"]  # confidence buckets were produced
    assert report["rows"]  # per-case rows feed the calibration suggestions


async def test_calibration_lowering_threshold_flips_borderline():
    # "oturum süresi uzatılsın" (extend the session duration) is borderline
    # (symmetric score ~0.08): GRAY at the default 0.22, flips to IN_SCOPE
    # once calibrated down to 0.07.
    request = "oturum süresi uzatılsın"
    default_engine = await _engine(in_scope=0.22)
    calibrated_engine = await _engine(in_scope=0.07)
    default_case = await default_engine.triage(request)
    calibrated_case = await calibrated_engine.triage(request)
    assert default_case.decisions[0].decision is Decision.GRAY_AREA
    # closed loop: the calibrated threshold changed the decision
    assert calibrated_case.decisions[0].decision is Decision.IN_SCOPE


def test_suggest_thresholds_lowers_on_gray_to_in_scope():
    mismatches = [{"system": "GRAY_AREA", "expected": "IN_SCOPE"}]
    suggestion = suggest_thresholds(mismatches, in_scope_threshold=0.34, gray_threshold=0.18)
    assert suggestion["in_scope_threshold"] < 0.34
    assert suggestion["rationale"]
