"""Deterministic unit tests for IndexTools (MCP/agent tools) — AST index, no Joern."""

import asyncio

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.file_work_item import FileWorkItemProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.index_tools import IndexTools
from etki.indexing.engine import IndexingEngine


def _build_tools() -> IndexTools:
    async def _build() -> IndexTools:
        index = await IndexingEngine(
            FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"]),
            AstCodeRepositoryProvider("samples/demo_project/src"),
            HeuristicScopeExtractor(),
        ).build()
        items = FileWorkItemProvider("samples/demo_project/work_items.json").all_items()
        return IndexTools(index, items)

    return asyncio.run(_build())


TOOLS = _build_tools()


def test_scope_lookup_surfaces_excluded_sso():
    hits = TOOLS.scope_lookup("SSO entegrasyonu")
    assert hits
    assert hits[0]["polarity"] == "EXCLUDED"


def test_impact_analysis_spreads_from_auth():
    result = TOOLS.impact_analysis("auth")
    assert "auth" in result["impacted"]
    assert len(result["impacted"]) >= 2


def test_similar_effort_returns_range_estimate():
    result = TOOLS.similar_effort("rapora tarih filtresi")
    assert result["similar"]
    assert result["estimate"]["low"] <= result["estimate"]["high"]


def test_baseline_summary_counts_excluded_and_modules():
    summary = TOOLS.baseline_summary()
    assert summary["excluded"] >= 1
    assert "reporting" in summary["modules"]


# --- triage_request (MCP end-to-end decision) ---


async def _build_engine():
    from etki.adapters.code_index import StaticCodeRepository
    from etki.engine.triage import TriageEngine

    index = await IndexingEngine(
        FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"]),
        AstCodeRepositoryProvider("samples/demo_project/src"),
        HeuristicScopeExtractor(),
    ).build()
    return TriageEngine(
        FileWorkItemProvider("samples/demo_project/work_items.json"),
        StaticCodeRepository(index.modules),
        FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"]),
        index.baseline,
        model_version="test",
        index_freshness=index.freshness,
    )


async def test_triage_to_dict_excluded_request_cites_frozen_clause():
    from etki.index_tools import triage_to_dict

    engine = await _build_engine()
    case = await engine.triage("SSO entegrasyonu istiyoruz")
    payload = triage_to_dict(case)
    assert payload["request"] == "SSO entegrasyonu istiyoruz"
    d = payload["decisions"][0]
    assert d["decision"] == "OUT_OF_SCOPE"
    assert d["effort"]["low"] <= d["effort"]["high"]
    # The cited clause is frozen in full form — self-contained for the MCP client.
    assert any(c["polarity"] == "EXCLUDED" for c in d["cited_clauses"])
    assert d["index_freshness"]


async def test_english_defect_report_routes_to_maintenance():
    # A defect report shares vocabulary with the BROKEN feature's clause (export/4.2.2),
    # not the maintenance clause — the relaxed maintenance path must still route it.
    from etki.adapters.code_index import StaticCodeRepository
    from etki.engine.triage import TriageEngine

    index = await IndexingEngine(
        FileSystemDocumentSourceProvider("samples/demo_project_en", ["*.md"]),
        AstCodeRepositoryProvider("samples/demo_project_en/src"),
        HeuristicScopeExtractor(),
    ).build()
    engine = TriageEngine(
        FileWorkItemProvider("samples/demo_project_en/work_items.json"),
        StaticCodeRepository(index.modules),
        FileSystemDocumentSourceProvider("samples/demo_project_en", ["*.md"]),
        index.baseline,
        model_version="test",
        index_freshness=index.freshness,
    )
    case = await engine.triage("The Excel export produces a corrupt file")
    d = case.decisions[0]
    assert d.decision.value == "MAINTENANCE"
    # the maintenance clause is cited even with zero text overlap against it
    assert any(c.category == "maintenance" for c in d.evidence.cited_clauses)


async def test_triage_to_dict_in_scope_request_has_modules_and_range():
    from etki.index_tools import triage_to_dict

    engine = await _build_engine()
    case = await engine.triage("Aylık rapora tarih filtresi eklensin")
    d = triage_to_dict(case)["decisions"][0]
    assert d["decision"] == "IN_SCOPE"
    assert "reporting" in d["impacted_modules"]
    assert d["effort"]["unit"] == "hour"
