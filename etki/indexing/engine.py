"""Offline indexing engine (the indexing phase of the architecture).

Three ports → a persisted Index: extracts a Baseline from documents, fetches the
code module graph, builds the **scope↔code mapping**. Triage (online) reads this Index.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from etki.core.models import Baseline, CodeModule, Index, ScopeItem
from etki.core.ports import CodeRepositoryProvider, DocumentSourceProvider
from etki.core.text import tokenize
from etki.extraction.parsers import parse_document
from etki.extraction.scope_extractor import ScopeExtractor

logger = logging.getLogger("etki")


def map_scope_to_code(items: list[ScopeItem], modules: list[CodeModule]) -> None:
    """Builds each ScopeItem ↔ CodeModule link bidirectionally (category/keyword)."""
    by_id = {m.id: m for m in modules}
    for item in items:
        item_tokens = tokenize(f"{item.description} {item.category}")
        matched = sorted(
            {m.id for m in modules if item.category == m.id or m.id in item_tokens}
        )
        item.mapped_modules = matched
        for module_id in matched:
            if item.id not in by_id[module_id].mapped_scope_items:
                by_id[module_id].mapped_scope_items.append(item.id)


class IndexingEngine:
    def __init__(
        self,
        documents: DocumentSourceProvider,
        code_repo: CodeRepositoryProvider,
        extractor: ScopeExtractor,
        *,
        contract_id: str = "CTR-DEMO-001",
    ) -> None:
        self._documents = documents
        self._code_repo = code_repo
        self._extractor = extractor
        self._contract_id = contract_id

    async def build(self) -> Index:
        items: list[ScopeItem] = []
        for doc in await self._documents.list_documents():
            try:
                raw = await self._documents.fetch_content(doc.id)
                # Extension-aware parsing (docx/xlsx/pdf/csv → text; .md/.txt/unknown →
                # UTF-8 decode) so binary contracts work through ANY document adapter.
                text, _ = parse_document(doc.name, raw)
            except Exception:  # noqa: BLE001 — one broken document must not take down
                # the whole project's indexing (graceful degradation); the skipped
                # document stays visible via the warning, baseline built from the rest.
                logger.warning("doküman atlandı (okunamadı/ayrıştırılamadı): %s", doc.name)
                continue
            items.extend(await self._extractor.extract(self._contract_id, text))
        baseline = Baseline(
            contract_id=self._contract_id, version=1, locked=True, scope_items=items
        )
        modules = await self._code_repo.list_modules()
        map_scope_to_code(baseline.scope_items, modules)
        # Declared manifest dependencies — structural degradation seam: providers
        # without the method (fakes) simply contribute none.
        deps_fn = getattr(self._code_repo, "list_dependencies", None)
        dependencies = deps_fn() if deps_fn else []
        now = datetime.now(UTC)
        return Index(
            baseline=baseline, modules=modules, dependencies=dependencies,
            indexed_at=now, freshness=now.date().isoformat(),
        )


def save_index(index: Index, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: temp file first, then os.replace → a partial/concurrent write
    # can't corrupt index.json (prevents a load failure on the next startup).
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)


def load_index(path: str | Path) -> Index | None:
    source = Path(path)
    if not source.exists():
        return None
    return Index.model_validate_json(source.read_text(encoding="utf-8"))
