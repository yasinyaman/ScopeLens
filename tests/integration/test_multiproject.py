"""Multi-project: separate baselines -> same request, different decision.

Cases are split by project_id.
"""

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.registry import build_documents, build_work_items
from etki.config import ProjectConfig, load_projects
from etki.core.enums import Decision
from etki.core.models import CaseFile
from etki.domains import load_module_hints
from etki.engine.estimation import consumed_by_category
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.indexing.engine import IndexingEngine
from etki.persistence.memory_repo import InMemoryCaseFileRepository


def _projects() -> dict[str, ProjectConfig]:
    loaded = load_projects("config/projects.yaml", "config/connectors.example.yaml")
    return {p.id: p for p in loaded}


async def _engine_for(project: ProjectConfig) -> TriageEngine:
    documents = build_documents(project.connectors.documents)
    src = project.connectors.code_repo.options["src_root"]  # AST instead of joern (Joern-free test)
    index = await IndexingEngine(
        documents, AstCodeRepositoryProvider(src), HeuristicScopeExtractor(),
        contract_id=project.contract_id,
    ).build()
    work_items = build_work_items(project.connectors.work_items)
    return TriageEngine(
        work_items,
        StaticCodeRepository(index.modules),
        documents,
        index.baseline,
        consumed_by_category=consumed_by_category(work_items.all_items()),
        module_hints=load_module_hints(project.domain_profile),  # same as in prod (context.py)
    )


def test_two_projects_configured():
    # demo + shop must be defined; other projects added via the UI (e.g. warp) don't break this.
    assert {"demo", "shop"} <= set(_projects())


async def test_same_request_differs_across_projects():
    projects = _projects()
    shop_engine = await _engine_for(projects["shop"])
    demo_engine = await _engine_for(projects["demo"])
    request = "kripto para ile ödeme eklensin"
    shop_decision = (await shop_engine.triage(request)).decisions[0].decision
    demo_decision = (await demo_engine.triage(request)).decisions[0].decision
    assert shop_decision is Decision.OUT_OF_SCOPE  # shop: Clause 6.1 EXCLUDED (crypto)
    assert demo_decision is not Decision.OUT_OF_SCOPE  # demo: no such clause exists


async def test_baselines_are_distinct():
    projects = _projects()
    shop = await _engine_for(projects["shop"])
    demo = await _engine_for(projects["demo"])
    assert shop.baseline.contract_id != demo.baseline.contract_id


def test_cases_scoped_by_project_id():
    repo = InMemoryCaseFileRepository()
    repo.save_case(CaseFile(request_id="A", project_id="demo", raw_request="x"))
    repo.save_case(CaseFile(request_id="B", project_id="shop", raw_request="y"))
    assert {c.request_id for c in repo.list_cases("demo")} == {"A"}
    assert {c.request_id for c in repo.list_cases("shop")} == {"B"}
    assert len(repo.list_cases()) == 2
