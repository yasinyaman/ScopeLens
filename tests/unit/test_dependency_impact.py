"""Dependency-impact analysis (Round A): external-import capture, the
dependency_impact tool, graph package nodes, and index round-trip — all over
the samples/demo_deps fixture corpus (existing corpora stay untouched).
"""

import asyncio

from etki.adapters.ast_code_index import AstCodeRepositoryProvider, build_ast_index
from etki.adapters.code_index import MergedCodeRepository, parse_code_index
from etki.core.models import Baseline, DeclaredDependency, Index
from etki.graphquery import IndexGraphQuery
from etki.index_tools import IndexTools
from etki.indexing.engine import load_index, save_index

_ROOT = "samples/demo_deps/src"


def _modules():
    return parse_code_index(build_ast_index(_ROOT))


def _index() -> Index:
    code_index = build_ast_index(_ROOT)
    return Index(
        baseline=Baseline(contract_id="C-DEPS"),
        modules=parse_code_index(code_index),
        dependencies=code_index.dependencies,
    )


def test_external_imports_become_packages_not_depends_on():
    by_id = {m.id: m for m in _modules()}
    assert by_id["api"].packages == ["requests", "yaml"]  # stdlib/internal filtered
    assert by_id["api"].depends_on == ["jobs"]  # internal stays internal
    assert by_id["jobs"].packages == ["pandas"]


def test_dependency_impact_declared_and_used():
    tools = IndexTools(_index())
    result = tools.dependency_impact("requests")
    assert result["declared"][0]["spec"] == ">=2.28,<3"
    assert result["used_by"] == ["api"]
    assert "jobs" in result["impacted"]  # one-hop blast radius via depends_on
    assert result["total_loc"] > 0


def test_dependency_impact_alias_and_unused_and_unknown():
    tools = IndexTools(_index())
    yaml_result = tools.dependency_impact("PyYAML")  # declared name ≠ import name
    assert yaml_result["used_by"] == ["api"]
    httpx_result = tools.dependency_impact("httpx")  # declared, no import seen
    assert httpx_result["declared"] and httpx_result["used_by"] == []
    unknown = tools.dependency_impact("boyle-paket-yok")  # never raises
    est = unknown.pop("estimate")
    assert est["low"] < est["high"]  # even an unknown package answers with a range
    assert unknown == {
        "package": "boyle-paket-yok", "declared": [], "used_by": [],
        "used_apis": {}, "used_api_paths": {}, "impacted": [], "high_churn": [],
        "total_loc": 0,
    }


def test_baseline_summary_counts_dependencies():
    assert IndexTools(_index()).baseline_summary()["dependencies"] >= 5


async def test_graph_gets_package_nodes_and_uses_edges():
    gq = IndexGraphQuery(_index())
    nodes = await gq.find_k_nodes("requests http istemcisi", k=5)
    assert any(n.type == "package" for n in nodes)
    sub = await gq.expand(["package:pypi:requests"], max_hops=2)
    ids = {n.id for n in sub.nodes}
    assert "module:api" in ids  # uses_package edge walked
    assert "module:jobs" in ids  # + the module's internal dependency


async def test_graph_unchanged_when_no_dependencies():
    """Eval-safety pin: an Index without dependencies yields byte-identical
    nodes/edges to the pre-feature behavior (demo/shop gates untouched)."""
    bare = Index(baseline=Baseline(contract_id="C"), modules=_modules())
    gq = IndexGraphQuery(bare)
    assert all(n.type != "package" for n in gq._all_nodes())
    assert all(e.relation != "uses_package" for e in gq._edges())


def test_index_round_trip_and_legacy_json(tmp_path):
    index = _index()
    path = tmp_path / "index.json"
    save_index(index, path)
    loaded = load_index(path)
    assert loaded is not None and loaded.dependencies == index.dependencies
    # Legacy JSON without the new keys still validates (defaults fill in).
    legacy = Index.model_validate_json(
        '{"baseline": {"contract_id": "C"}, "modules": [{"id": "m", "path": "m/"}]}'
    )
    assert legacy.dependencies == [] and legacy.modules[0].packages == []
    assert legacy.modules[0].package_api_paths == {}  # new field defaults too


def test_merged_repo_dependencies_global_names_prefixed_provenance():
    a = AstCodeRepositoryProvider(_ROOT)
    b = AstCodeRepositoryProvider(_ROOT)
    merged = MergedCodeRepository([("repoA", a), ("repoB", b)])
    deps = merged.list_dependencies()
    requests_deps = [d for d in deps if d.name == "requests"]
    assert len(requests_deps) == 1  # dedupe by (ecosystem, name, raw_spec)
    assert requests_deps[0].name == "requests"  # package names stay GLOBAL
    assert requests_deps[0].manifest.startswith("repoA:")  # provenance prefixed


# ---------------------------------------------------- used-API surface


def test_ast_captures_used_api_symbols():
    """from-import names, attribute access on imports AND aliases — the
    call-site surface an upgrade/downgrade must be audited against."""
    import ast as ast_mod

    from etki.adapters.ast_code_index import _api_uses

    tree = ast_mod.parse(
        "import requests\n"
        "import numpy as np\n"
        "from yaml import safe_load, dump\n"
        "requests.get('x'); requests.post('y')\n"
        "np.array([1])\n"
    )
    uses = _api_uses(tree)
    assert uses["requests"] == ["get", "post"]
    assert uses["numpy"] == ["array"]  # alias resolved
    assert uses["yaml"] == ["dump", "safe_load"]  # from-import names


def test_module_package_apis_aggregated():
    by_id = {m.id: m for m in _modules()}
    assert by_id["api"].package_apis["requests"] == ["get"]
    assert by_id["api"].package_apis["yaml"] == ["safe_load"]
    assert by_id["jobs"].package_apis["pandas"] == ["DataFrame"]


def test_dependency_impact_reports_used_apis():
    result = IndexTools(_index()).dependency_impact("requests")
    assert result["used_apis"] == {"api": ["get"]}
    assert result["used_api_paths"] == {"api": ["requests.get"]}  # qualified
    # Alias path: declared PyYAML ↔ import yaml symbols.
    yaml_result = IndexTools(_index()).dependency_impact("PyYAML")
    assert yaml_result["used_apis"] == {"api": ["safe_load"]}
    assert yaml_result["used_api_paths"] == {"api": ["yaml.safe_load"]}


def test_api_paths_qualified_capture():
    import ast as ast_mod

    from etki.adapters.ast_code_index import _api_paths

    tree = ast_mod.parse(
        "import numpy as np\n"
        "from faker.providers.credit_card import CreditCard as CC\n"
        "from .internal import helper\n"  # relative → skipped
        "np.linalg.norm([1])\n"
    )
    paths = _api_paths(tree)
    # asname records the ORIGINAL name; full module path preserved.
    assert paths["faker"] == ["faker.providers.credit_card.CreditCard"]
    # dotted attribute chain unrolled through the alias.
    assert "numpy.linalg.norm" in paths["numpy"]
    assert "internal" not in paths and not any("helper" in v for v in paths.values())


def test_api_change_mentions_word_boundary_intersection():
    from etki.adapters.package_registries import api_change_mentions

    releases = [
        {"version": "v2.32.0", "published_at": "2024-05-01",
         "notes": "Breaking: `get` now requires timeout. Removed helpers."},
        {"version": "v2.31.0", "published_at": "2024-01-01",
         "notes": "Docs only."},
        {"version": "v2.30.0", "published_at": "2023-09-01",
         "notes": "getattr improvements"},  # substring, NOT the symbol
    ]
    mentions = api_change_mentions(["get", "post"], releases)
    assert len(mentions) == 1  # word-boundary: 'getattr' does not match 'get'
    assert mentions[0]["version"] == "v2.32.0" and mentions[0]["mentions"] == ["get"]


async def test_engine_note_lists_used_api_surface():
    code_index = build_ast_index(_ROOT)
    engine = _dep_engine(code_index.dependencies, with_maintenance_clause=True)
    decision = (
        await engine.triage("requests kütüphanesini 3.0 sürümüne yükseltelim")
    ).decisions[0]
    assert any("Kullanılan API yüzeyi" in a and "get" in a
               for a in decision.evidence.assumptions)


# ------------------------------------------------- recognition (Round B1)


def test_split_recognizes_dependency_change_with_known_package():
    from etki.core.enums import RequestType
    from etki.engine.understanding import split_request

    subs = split_request(
        "requests kütüphanesini 3.0 sürümüne yükseltelim", {},
        known_packages=["requests", "pandas"],
    )
    sub = subs[0]
    assert sub.type is RequestType.DEPENDENCY_CHANGE
    assert sub.package == "requests"
    assert sub.target_version == "3.0"
    assert sub.quantity is None  # a version is NEVER a quantity (limit-step guard)


def test_target_version_prefers_dotted_and_skips_cve_ids():
    from etki.engine.understanding import _target_version

    # Live-caught bug: the CVE year used to win over the real target version.
    assert _target_version(
        "güvenlik zafiyeti CVE-2024-26130 nedeniyle cryptography 49.0.0'a yükselt"
    ) == "49.0.0"
    assert _target_version("Spring Boot 3 sürümüne geçelim") == "3"  # small bare int OK
    assert _target_version("CVE-2024-26130 yaması") is None  # year/id never a version


def test_split_recognizes_downgrade_wording():
    from etki.core.enums import RequestType
    from etki.engine.understanding import split_request

    for text in ("requests sürümünü düşürelim", "downgrade pandas to 1.5"):
        subs = split_request(text, {}, known_packages=["requests", "pandas"])
        assert subs[0].type is RequestType.DEPENDENCY_CHANGE, text
        assert subs[0].package in ("requests", "pandas")


def test_split_version_upgrade_without_known_package():
    from etki.core.enums import RequestType
    from etki.engine.understanding import split_request

    subs = split_request("Spring Boot 3 sürümüne geçelim", {}, known_packages=[])
    assert subs[0].type is RequestType.DEPENDENCY_CHANGE  # "sürüm" + "geçelim" wording
    assert subs[0].package is None and subs[0].target_version == "3"


def test_generic_update_is_not_a_dependency_change():
    from etki.core.enums import RequestType
    from etki.engine.understanding import split_request

    subs = split_request("raporu güncelle", {}, known_packages=["requests"])
    assert subs[0].type is not RequestType.DEPENDENCY_CHANGE  # verb alone never fires
    plan = split_request("planımızı premium'a yükseltelim", {}, known_packages=[])
    assert plan[0].type is not RequestType.DEPENDENCY_CHANGE  # no noun/package/version-word


def test_maintenance_wording_beats_dependency_wording():
    from etki.core.enums import RequestType
    from etki.engine.understanding import split_request

    subs = split_request(
        "kütüphane güncellemesi sonrası çıkan hatayı düzelt", {}, known_packages=[]
    )
    assert subs[0].type is RequestType.MAINTENANCE  # defect wording keeps its routing


def _dep_engine(deps, *, with_maintenance_clause: bool):
    from etki.adapters.code_index import StaticCodeRepository
    from etki.adapters.fakes.document import FakeDocumentSourceProvider
    from etki.adapters.fakes.work_item import FakeWorkItemProvider
    from etki.core.models import Baseline, ScopeItem
    from etki.engine.triage import TriageEngine

    items = [ScopeItem(id="S1", contract_id="C",
                       description="API servisleri ve rapor üretimi")]
    if with_maintenance_clause:
        items.append(
            ScopeItem(id="S2", contract_id="C", category="maintenance",
                      description="Bakım — hata düzeltme ve kütüphane sürüm "
                                  "güncellemeleri kapsam dahilindedir",
                      source_clause="Madde 7.1")
        )
    code_index = build_ast_index(_ROOT)
    return TriageEngine(
        FakeWorkItemProvider([]), StaticCodeRepository(parse_code_index(code_index)),
        FakeDocumentSourceProvider(), Baseline(contract_id="C", scope_items=items),
        dependencies=deps,
    )


async def test_dependency_branch_measured_contract():
    """The D2 branch — justified by measurement (dependency_crs 4/14 → 13/14):
    manifest evidence IS decision evidence now. The three branch paths + the
    informational note when the branch does not decide."""
    code_index = build_ast_index(_ROOT)
    text = "requests kütüphanesini 3.0 sürümüne yükseltelim"

    # (a) declared package + maintenance clause → MAINTENANCE with dep reasoning
    with_clause = (await _dep_engine(code_index.dependencies,
                                     with_maintenance_clause=True).triage(text)).decisions[0]
    from etki.core.enums import Decision

    assert with_clause.decision is Decision.MAINTENANCE
    assert "requests" in with_clause.evidence.reasoning
    assert with_clause.evidence.cited_clauses[0].source_clause == "Madde 7.1"

    # (b) unknown-package "upgrade" → GRAY (conflicting evidence: no manifest)
    unknown = (await _dep_engine([], with_maintenance_clause=True)
               .triage(text)).decisions[0]
    assert unknown.decision is Decision.GRAY_AREA

    # (c) new library, undeclared → CR floor
    new_lib = (await _dep_engine(code_index.dependencies, with_maintenance_clause=True)
               .triage("redis kütüphanesini ekleyelim")).decisions[0]
    assert new_lib.decision is Decision.CR_CANDIDATE
    assert "manifest" in new_lib.evidence.reasoning

    # (d) declared package but NO maintenance clause → branch abstains, the
    #     informational note still lands in the evidence chain
    no_clause = (await _dep_engine(code_index.dependencies,
                                   with_maintenance_clause=False).triage(text)).decisions[0]
    assert any("Bağımlılık talebi" in a for a in no_clause.evidence.assumptions)
    assert any("requirements.txt" in a for a in no_clause.evidence.assumptions)


async def test_dependency_triage_carries_technical_impact_surface():
    """Not just effort: a dependency request's evidence chain carries the REAL
    usage surface — modules importing the package + one-hop neighbours, with
    their loc/cyclomatic/churn signals feeding the estimate."""
    code_index = build_ast_index(_ROOT)
    engine = _dep_engine(code_index.dependencies, with_maintenance_clause=True)
    decision = (
        await engine.triage("requests kütüphanesini 3.0 sürümüne yükseltelim")
    ).decisions[0]

    assert "api" in decision.evidence.impacted_modules  # imports requests
    assert "jobs" in decision.evidence.impacted_modules  # one-hop dependency
    signals = {s.id: s for s in decision.evidence.impacted_signals}
    assert signals["api"].loc > 0  # technical signals present, not placeholders
    # Effort comes from the USAGE SURFACE, not module LOC (the REQ-warp-f436c329
    # triage inconsistency: 14k LOC ≠ 98–173h for a version bump).
    assert decision.effort_estimate.high > 0
    assert "yüzey" in decision.effort_estimate.basis

    # Alias tolerance: PyYAML (declared) ↔ import yaml (code).
    yaml_decision = (
        await engine.triage("PyYAML paket sürümünü güncelleyelim")
    ).decisions[0]
    assert "api" in yaml_decision.evidence.impacted_modules


async def test_security_wording_escalates_risk_not_decision():
    """Security-motivated dependency request: the SCOPE decision follows the
    contract unchanged, but the RISK layer escalates (deferring a security fix
    is a risk regardless of scope) — 24h escalation + evidence note."""
    from etki.core.enums import RiskLevel

    code_index = build_ast_index(_ROOT)
    engine = _dep_engine(code_index.dependencies, with_maintenance_clause=True)

    plain = (await engine.triage("requests sürümünü yükseltelim")).decisions[0]
    sec = (
        await engine.triage("güvenlik zafiyeti CVE-2026-1234 için requests yükseltilmeli")
    ).decisions[0]

    assert sec.decision is plain.decision  # scope call unchanged (MAINTENANCE here)
    assert plain.risk.escalation is False
    assert sec.risk.escalation is True  # 24h escalation fires
    assert sec.risk.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert any("GÜVENLİK GEREKÇESİ" in a for a in sec.evidence.assumptions)
    assert any("güvenlik gerekçeli" in s for s in sec.risk.signals)


async def test_dependency_branch_never_overrides_exclusions():
    """Exclusion guard: an EXCLUDED hit wins over the dependency branch —
    'SSO kütüphanesi ekleyelim' stays on the exclusion path."""
    from etki.adapters.code_index import StaticCodeRepository
    from etki.adapters.fakes.document import FakeDocumentSourceProvider
    from etki.adapters.fakes.work_item import FakeWorkItemProvider
    from etki.core.enums import Decision, Polarity
    from etki.core.models import Baseline, ScopeItem
    from etki.engine.triage import TriageEngine

    baseline = Baseline(
        contract_id="C",
        scope_items=[
            ScopeItem(id="S1", contract_id="C", polarity=Polarity.EXCLUDED,
                      description="Tek oturum açma SSO entegrasyonu kapsam dışıdır",
                      source_clause="Madde 9"),
            ScopeItem(id="S2", contract_id="C", category="maintenance",
                      description="Bakım ve kütüphane sürüm güncellemeleri"),
        ],
    )
    engine = TriageEngine(
        FakeWorkItemProvider([]), StaticCodeRepository([]),
        FakeDocumentSourceProvider(), baseline, dependencies=[],
    )
    decision = (await engine.triage("SSO kütüphanesini ekleyelim")).decisions[0]
    # The branch abstained (exc_hits > 0): the outcome comes from the NORMAL
    # tree — here GRAY via the single-hit exclusion margin rule (escalation),
    # never the branch's "new dependency → CR" call.
    assert decision.decision in (Decision.OUT_OF_SCOPE, Decision.GRAY_AREA)
    assert "manifest" not in decision.evidence.reasoning  # dep_new reasoning absent


def test_indexing_engine_persists_dependencies():
    from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
    from etki.extraction.scope_extractor import HeuristicScopeExtractor
    from etki.indexing.engine import IndexingEngine

    index = asyncio.run(
        IndexingEngine(
            FileSystemDocumentSourceProvider("samples/demo_deps", ["*.md"]),
            AstCodeRepositoryProvider(_ROOT),
            HeuristicScopeExtractor(),
        ).build()
    )
    assert any(isinstance(d, DeclaredDependency) and d.name == "requests"
               for d in index.dependencies)


def test_deps_diff_template_lists_symbol_level_api_changes():
    """The comparison fragment shows the ACTUAL removed/changed/added symbols
    (not just counts) — and degrades to an 'identical API' note at zero."""
    from etki.api import web

    report = {
        "package": "pydantic", "old_version": "2.5.0", "new_version": "2.8.0",
        "counts": {"removed": 1, "added": 1, "changed": 1},
        "used_paths": [], "used_symbols": [],
        "your_code": {"broken": [], "changed": [], "unresolved": [], "ok": []},
        "vulnerabilities": {"old": [], "new": []},
        "used": {"removed": ["pydantic.v1.BaseSettings.Config"], "changed": []},
        "all": {
            "removed": ["pydantic.v1.BaseSettings.Config"],
            "added": ["pydantic.TypeAdapter"],
            "changed": [
                {"symbol": "pydantic.Field", "old": "(default)", "new": "(default, *, alias)"}
            ],
        },
        "truncated": False,
    }
    tpl = web.templates.env.get_template("deps_diff.html")
    html = tpl.render(r=report)
    assert "pydantic.v1.BaseSettings.Config" in html  # removed symbol shown
    assert "pydantic.TypeAdapter" in html  # added symbol shown
    assert "(default, *, alias)" in html  # changed signature old → new

    report["counts"] = {"removed": 0, "added": 0, "changed": 0}
    report["all"] = {"removed": [], "added": [], "changed": []}
    report["used"] = {"removed": [], "changed": []}
    html_same = tpl.render(r=report)
    assert "pydantic.TypeAdapter" not in html_same


async def test_tool_and_engine_effort_agree_on_dependency_requests():
    """Closing the triage inconsistency (REQ-warp-f436c329): the dependency_impact
    tool and the triage engine use the SAME surface-based estimator — the band the
    agent/MCP sees can never contradict the band in the case file."""
    code_index = build_ast_index(_ROOT)
    tool_est = IndexTools(_index()).dependency_impact("requests")["estimate"]
    engine = _dep_engine(code_index.dependencies, with_maintenance_clause=True)
    decision = (
        await engine.triage("requests kütüphanesini 3.0 sürümüne yükseltelim")
    ).decisions[0]
    est = decision.effort_estimate
    assert (est.low, est.high) == (tool_est["low"], tool_est["high"])
    assert "yüzey" in tool_est["basis"] and "yüzey" in est.basis
