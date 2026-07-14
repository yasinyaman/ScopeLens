"""Tur 1 memory consumers: pre-analysis graph context + MCP wiki_search/graph_query.

The contract under test: retrieval enriches context only (LLM path), failures are
silent, and the MCP tools degrade gracefully (wiki off → explanatory row, not an
exception).
"""

import asyncio

from etki.api import web
from etki.core.ports import GraphNode, QueryResult


def test_pre_analysis_prompt_carries_graph_context(monkeypatch):
    captured: dict = {}

    async def fake_ask(prompt, tools=None, **kwargs):  # noqa: ANN001
        captured["prompt"] = prompt
        return "analiz"

    async def fake_graph_context(project_id, raw_request):  # noqa: ANN001
        return "İLGİLİ BAĞLAM (bilgi grafiğinden, paketleme: bfs):\n- scope:S1: madde"

    monkeypatch.setattr(web, "agent_ask", fake_ask)
    monkeypatch.setattr(web, "_project_graph_context", fake_graph_context)
    monkeypatch.setattr(web, "build_llm_client", lambda settings: object())
    monkeypatch.setattr(web, "_project_tools", lambda pid: None)
    monkeypatch.setattr(web, "_project_llm_args", lambda pid: {})

    from etki.core.models import CaseFile

    case = CaseFile(request_id="REQ-x", project_id="demo", raw_request="SSO eklensin")
    text, source = asyncio.run(web._generate_pre_analysis("demo", case, use_llm=True))
    assert source == "llm" and text == "analiz"
    assert "İLGİLİ BAĞLAM" in captured["prompt"]
    # The graph block sits inside its own untrusted delimiters (injection guard).
    assert captured["prompt"].count("<untrusted_data>") == 2


def test_pre_analysis_survives_graph_context_failure(monkeypatch):
    async def fake_ask(prompt, tools=None, **kwargs):  # noqa: ANN001
        return "analiz"

    monkeypatch.setattr(web, "agent_ask", fake_ask)
    monkeypatch.setattr(web, "build_llm_client", lambda settings: object())
    monkeypatch.setattr(web, "_project_tools", lambda pid: None)
    monkeypatch.setattr(web, "_project_llm_args", lambda pid: {})
    # Unknown project → helper returns None (never raises) → prompt has one block.
    from etki.core.models import CaseFile

    case = CaseFile(request_id="REQ-x", project_id="yok", raw_request="test")
    text, source = asyncio.run(web._generate_pre_analysis("yok", case, use_llm=True))
    assert source == "llm" and text == "analiz"


def test_dep_compare_prefills_align_to_decisions():
    from etki.core.enums import RequestType
    from etki.core.models import CaseFile, SubRequest

    case = CaseFile(
        request_id="REQ-x", project_id="boyle-proje-yok",
        raw_request="cryptography 49.0.0'a yükselt, ayrıca rapor ekle",
        sub_requests=[
            SubRequest(item="cryptography 49.0.0'a yükselt",
                       type=RequestType.DEPENDENCY_CHANGE,
                       package="cryptography", target_version="49.0.0"),
            SubRequest(item="rapor ekle", type=RequestType.MODIFICATION),
        ],
    )
    prefills = web._dep_compare_prefills("boyle-proje-yok", case)
    assert prefills[0] == {"package": "cryptography", "old": "", "new": "49.0.0"}
    assert prefills[1] is None  # non-dependency decision → no block


def test_triage_cards_render_dep_compare_block(engine):
    """The triage screen (cards.html) shows the same one-click comparison block as
    the case screen — deps_online off degrades to the informational note."""
    case = asyncio.run(engine.triage("raporlama ekranı eklensin", request_id="REQ-c1"))
    case.project_id = "demo"
    prefills: list[dict | None] = [{"package": "cryptography", "old": "42.0.0", "new": "46.0.3"}]
    prefills += [None] * (len(case.decisions) - 1)
    tpl = web.templates.env.get_template("cards.html")

    html = tpl.render(case=case, dep_compare=prefills, deps_online=True)
    assert "bagimliliklar/karsilastir" in html and "cryptography" in html

    html_off = tpl.render(case=case, dep_compare=prefills, deps_online=False)
    assert "bagimliliklar/karsilastir" not in html_off and "cryptography" in html_off

    html_none = tpl.render(case=case)  # non-dependency triage → no block at all
    assert "dep-compare" not in html_none


def test_graph_context_returns_none_for_unknown_project():
    assert asyncio.run(web._project_graph_context("boyle-proje-yok", "x")) is None


def test_mcp_wiki_search_reports_when_wiki_off(monkeypatch):
    monkeypatch.setenv("ETKI_WIKI_DIR", "")
    from etki import mcp_server

    rows = mcp_server.wiki_search("sso")
    assert rows and "info" in rows[0]


def test_mcp_wiki_search_finds_seeded_decision(monkeypatch, tmp_path):
    from datetime import UTC, datetime

    from etki.adapters.filesystem_wiki import FileSystemWikiAdapter
    from etki.core.enums import Decision
    from etki.core.models import CaseFile, EffortEstimate, TriageDecision

    wiki = FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"))
    wiki.write_decision(
        CaseFile(
            request_id="REQ-demo-m1", project_id="demo", raw_request="SSO entegrasyonu",
            decisions=[TriageDecision(request_id="REQ-demo-m1",
                                      decision=Decision.CR_CANDIDATE,
                                      effort_estimate=EffortEstimate(low=1, high=2))],
            created_at=datetime(2026, 7, 9, tzinfo=UTC),
        )
    )
    monkeypatch.setenv("ETKI_WIKI_DIR", str(tmp_path / "wiki-{id}"))
    from etki import mcp_server

    rows = mcp_server.wiki_search("SSO", project_id="demo")
    assert rows and rows[0]["doc_id"] == "DEC-20260709-req-demo-m1"


def test_mcp_graph_query_routes_and_serializes(monkeypatch):
    from etki import mcp_server

    class StubGraph:
        async def query(self, question, *, k=5):  # noqa: ANN001
            return QueryResult(strategy="find_k",
                               nodes=[GraphNode(id="scope:S1", type="scope", score=1.0)])

    monkeypatch.setattr(mcp_server, "_graph", StubGraph())
    result = asyncio.run(mcp_server.graph_query("SSO kapsamda mı"))
    assert result["strategy"] == "find_k"
    assert result["nodes"][0]["id"] == "scope:S1"


def _deps_index():
    from etki.adapters.ast_code_index import build_ast_index
    from etki.adapters.code_index import parse_code_index
    from etki.core.models import Baseline, Index

    ci = build_ast_index("samples/demo_deps/src")
    return Index(baseline=Baseline(contract_id="C-DEPS"),
                 modules=parse_code_index(ci), dependencies=ci.dependencies)


def _dep_case():
    from etki.core.enums import RequestType
    from etki.core.models import CaseFile, SubRequest

    return CaseFile(
        request_id="REQ-d1", project_id="deps",
        raw_request="requests 2.32.0'a yükseltilsin",
        sub_requests=[SubRequest(item="requests 2.32.0'a yükseltilsin",
                                 type=RequestType.DEPENDENCY_CHANGE,
                                 package="requests", target_version="2.32.0")],
    )


def test_dep_diff_context_off_by_default():
    # hermetic Settings → deps_online False → research never runs
    assert asyncio.run(web._dep_diff_context("deps", _dep_case())) is None


def test_dep_diff_context_annotates_usage_sites(monkeypatch):
    """The up-front package research: removed/changed symbols the project uses
    are annotated with the MODULES that use them; OSV findings included."""
    monkeypatch.setenv("ETKI_DEPS_ONLINE", "true")

    class _P:
        def resolved_index_path(self):  # noqa: ANN201
            return "unused"

    monkeypatch.setattr(web.projects_store, "get", lambda pid: _P())
    monkeypatch.setattr(web, "load_index", lambda path: _deps_index())

    async def fake_report(package, old, new, **kwargs):  # noqa: ANN001
        assert (package, old, new) == ("requests", "2.28", "2.32.0")
        assert "requests.get" in kwargs["used_paths"]  # project usage fed IN
        return {
            "counts": {"removed": 1, "added": 0, "changed": 1},
            "your_code": {
                "broken": [{"path": "requests.get", "hint": []}],
                "changed": [], "unresolved": [], "ok": [],
            },
            "used": {"removed": [], "changed": [
                {"symbol": "requests.Session.request", "old": "(url)", "new": "(url, *, to)"},
            ]},
            "vulnerabilities": {"old": [{"id": "GHSA-x"}], "new": []},
        }

    import etki.adapters.package_download as pd

    monkeypatch.setattr(pd, "version_diff_report", fake_report)
    text = asyncio.run(web._dep_diff_context("deps", _dep_case()))
    assert text is not None and "requests 2.28 → 2.32.0" in text
    assert "`requests.get`" in text and "modüller: api" in text  # usage site named
    assert "requests.Session.request" in text and "(url, *, to)" in text
    assert "GHSA-x" in text  # OSV finding carried

    async def boom(*a, **k):  # noqa: ANN001, ANN002, ANN003
        raise RuntimeError("registry down")

    monkeypatch.setattr(pd, "version_diff_report", boom)
    assert asyncio.run(web._dep_diff_context("deps", _dep_case())) is None  # best-effort


def test_pre_analysis_carries_dep_research(monkeypatch):
    """The research block feeds BOTH generators: the LLM prompt and the
    deterministic fallback text."""

    async def fake_dep_context(project_id, case):  # noqa: ANN001
        return "PAKET ARAŞTIRMASI — requests 2.28 → 2.32.0"

    monkeypatch.setattr(web, "_dep_diff_context", fake_dep_context)
    text, source = asyncio.run(web._generate_pre_analysis("deps", _dep_case(), use_llm=False))
    assert source == "deterministic" and "PAKET ARAŞTIRMASI" in text

    captured: dict = {}

    async def fake_ask(prompt, tools=None, **kwargs):  # noqa: ANN001
        captured["prompt"] = prompt
        return "analiz"

    async def no_graph(project_id, raw_request):  # noqa: ANN001
        return None

    monkeypatch.setattr(web, "agent_ask", fake_ask)
    monkeypatch.setattr(web, "_project_graph_context", no_graph)
    monkeypatch.setattr(web, "build_llm_client", lambda settings: object())
    monkeypatch.setattr(web, "_project_tools", lambda pid: None)
    monkeypatch.setattr(web, "_project_llm_args", lambda pid: {})
    text, source = asyncio.run(web._generate_pre_analysis("deps", _dep_case(), use_llm=True))
    assert source == "llm" and "PAKET ARAŞTIRMASI" in captured["prompt"]
