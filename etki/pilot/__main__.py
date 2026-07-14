"""Shadow-mode pilot CLI: `python -m etki.pilot`.

Builds a reproducible engine without Joern (AST), runs the pilot CR set in
shadow mode, prints an accuracy + confidence-calibration report, and produces
threshold suggestions. Gate: agreement ≥0.75, effort-in-range ≥0.70.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.registry import build_documents, build_work_items
from etki.config import Settings, load_connectors
from etki.engine.estimation import consumed_by_category
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import build_scope_extractor
from etki.indexing.engine import IndexingEngine
from etki.pilot import shadow
from etki.pilot.calibration import suggest_estimation_params, suggest_thresholds

_DATASET = Path(__file__).resolve().parents[2] / "eval" / "datasets" / "pilot_crs.json"
_AGREEMENT = 0.75
_RANGE = 0.70


async def _build_engine(settings: Settings) -> TriageEngine:
    connectors = load_connectors(settings.connectors_path)
    documents = build_documents(connectors.documents)
    src = connectors.code_repo.options.get("src_root", "samples/demo_project/src")
    indexer = IndexingEngine(documents, AstCodeRepositoryProvider(src), build_scope_extractor())
    index = await indexer.build()
    work_items = build_work_items(connectors.work_items)
    consumed = (
        consumed_by_category(work_items.all_items()) if hasattr(work_items, "all_items") else {}
    )
    return TriageEngine(
        work_items,
        StaticCodeRepository(index.modules),
        documents,
        index.baseline,
        consumed_by_category=consumed,
        in_scope_threshold=settings.in_scope_threshold,
        gray_threshold=settings.gray_threshold,
        estimation_params=settings.estimation_params(),
    )


async def run() -> int:
    settings = Settings()
    engine = await _build_engine(settings)
    report = await shadow.run(engine, _DATASET)

    print(f"GÖLGE-MOD PİLOT — {report['cases']} CR (sistem önerir, PMO kıyaslar)")
    print(
        f"  karar örtüşme: {report['agreement']:.0%} | "
        f"efor-aralık isabeti: {report['effort_in_range']:.0%}"
    )
    print("  karar-tipi precision/recall:")
    for label, m in report["by_decision"].items():
        print(f"    {label:13} P={m['precision']} R={m['recall']} (n={m['support']})")
    print("  güven kalibrasyonu:")
    for bucket in report["confidence_calibration"]:
        print(f"    {bucket['bucket']:6} n={bucket['n']} isabet={bucket['accuracy']:.0%}")
    if report["mismatches"]:
        print("  uyuşmazlıklar:")
        for m in report["mismatches"]:
            print(f"    {m['id']}: {m['system']} ≠ {m['expected']}")

    cal = suggest_thresholds(
        report["mismatches"], settings.in_scope_threshold, settings.gray_threshold
    )
    if cal["rationale"]:
        print("  kalibrasyon önerisi (geri besleme):")
        for line in cal["rationale"]:
            print(f"    • {line}")

    est_cal = suggest_estimation_params(report["rows"])
    if est_cal["rationale"]:
        print("  efor sabiti kalibrasyon önerisi (ETKI_EST_*):")
        for line in est_cal["rationale"]:
            print(f"    • {line}")

    ok = report["agreement"] >= _AGREEMENT and report["effort_in_range"] >= _RANGE
    print("PİLOT SONUÇ:", "KABUL ✅" if ok else "RET ❌")
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
