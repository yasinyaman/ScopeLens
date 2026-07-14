"""Composite DocumentSource + PLUGGABILITY proof (config swap without touching the core)."""

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import StaticCodeRepository
from etki.adapters.composite_document import CompositeDocumentSourceProvider
from etki.adapters.fakes.work_item import FakeWorkItemProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.adapters.registry import build_documents
from etki.config import ConnectorConfig
from etki.engine.triage import TriageEngine
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.indexing.engine import IndexingEngine

_ROOT = "samples/demo_project"
_FS = ConnectorConfig(adapter="filesystem", options={"root": _ROOT, "globs": ["*.md"]})
_COMPOSITE = ConnectorConfig(
    adapter="composite",
    options={"sources": [{"adapter": "filesystem", "options": {"root": _ROOT, "globs": ["*.md"]}}]},
)


async def test_composite_merges_sources_and_routes_fetch():
    fs = FileSystemDocumentSourceProvider(_ROOT, ["*.md"])
    composite = CompositeDocumentSourceProvider([fs, fs])
    base = await fs.list_documents()
    docs = await composite.list_documents()
    assert len(docs) == 2 * len(base)  # the two sources merged
    assert all(":" in d.id for d in docs)  # source-indexed namespace
    content = await composite.fetch_content(docs[0].id)  # routed by prefix
    assert len(content) > 0


def test_composite_capabilities_are_conservative():
    fs = FileSystemDocumentSourceProvider(_ROOT)
    caps = CompositeDocumentSourceProvider([fs, fs]).capabilities()
    assert caps.supports_webhooks is False  # all children must support it


async def _build_engine(doc_cfg: ConnectorConfig) -> TriageEngine:
    documents = build_documents(doc_cfg)
    code = AstCodeRepositoryProvider(f"{_ROOT}/src")
    index = await IndexingEngine(documents, code, HeuristicScopeExtractor()).build()
    return TriageEngine(
        FakeWorkItemProvider(), StaticCodeRepository(index.modules), documents, index.baseline
    )


async def test_pluggability_documents_swap_keeps_same_decision():
    # documents port swapped filesystem → composite; CORE CODE UNCHANGED.
    fs_engine = await _build_engine(_FS)
    composite_engine = await _build_engine(_COMPOSITE)
    request = "login ekranına SSO entegrasyonu"
    fs_decision = (await fs_engine.triage(request)).decisions[0].decision
    composite_decision = (await composite_engine.triage(request)).decisions[0].decision
    assert fs_decision == composite_decision
