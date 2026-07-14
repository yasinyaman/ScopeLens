"""Indexing engine integration test (AST-based — does not require Joern/JVM)."""

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.filesystem_document import FileSystemDocumentSourceProvider
from etki.core.enums import Polarity
from etki.extraction.scope_extractor import HeuristicScopeExtractor
from etki.indexing.engine import IndexingEngine, load_index, save_index


def _engine() -> IndexingEngine:
    return IndexingEngine(
        FileSystemDocumentSourceProvider("samples/demo_project", ["*.md"]),
        AstCodeRepositoryProvider("samples/demo_project/src"),
        HeuristicScopeExtractor(),
    )


async def test_build_index_extracts_and_maps():
    index = await _engine().build()
    # real code graph
    assert {m.id for m in index.modules} == {"api_gateway", "auth", "config", "db", "reporting"}
    # EXCLUDED items were captured (SSO/mobile/streaming)
    assert any(s.polarity is Polarity.EXCLUDED for s in index.baseline.scope_items)
    # scope<->code mapping is bidirectional
    assert any("reporting" in s.mapped_modules for s in index.baseline.scope_items)
    auth = next(m for m in index.modules if m.id == "auth")
    assert auth.mapped_scope_items


async def test_index_roundtrip(tmp_path):
    index = await _engine().build()
    path = tmp_path / "index.json"
    save_index(index, path)
    loaded = load_index(path)
    assert loaded is not None
    assert len(loaded.modules) == len(index.modules)
    assert loaded.baseline.contract_id == index.baseline.contract_id


async def test_load_index_missing_returns_none(tmp_path):
    assert load_index(tmp_path / "yok.json") is None


async def test_corrupt_document_is_skipped_not_fatal(tmp_path):
    """Graceful degradation: a single corrupt document (.pdf extension but plain-text
    content — the case that took indexing down on warp) is skipped; the baseline is
    built from the remaining documents."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sozlesme.md").write_text(
        "### Madde 1 — Raporlama\n"
        "Raporlara tarih ve kategori filtreleri eklenmesi kapsam dahilindedir.\n",
        encoding="utf-8",
    )
    (docs / "bozuk.pdf").write_bytes(b"[bu bir PDF degil]")
    engine = IndexingEngine(
        FileSystemDocumentSourceProvider(str(docs), ["*.md", "*.pdf"]),
        AstCodeRepositoryProvider("samples/demo_project/src"),
        HeuristicScopeExtractor(),
    )
    index = await engine.build()  # must not raise
    assert index.baseline.scope_items  # clauses came from the intact document
