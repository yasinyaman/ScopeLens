"""Composite DocumentSourceProvider — merges multiple document sources behind one port.

The architecture's example: some documents live in FileSystem, some in SharePoint →
composite. The core sees a single DocumentSourceProvider; strong proof of pluggability.
"""

from __future__ import annotations

from etki.core.models import DocumentRef
from etki.core.ports import Capabilities, DocumentSourceProvider


class CompositeDocumentSourceProvider:
    def __init__(self, sources: list[DocumentSourceProvider]) -> None:
        self._sources = list(sources)

    async def list_documents(self) -> list[DocumentRef]:
        docs: list[DocumentRef] = []
        for idx, source in enumerate(self._sources):
            for doc in await source.list_documents():
                docs.append(doc.model_copy(update={"id": f"{idx}:{doc.id}"}))
        return docs

    async def fetch_content(self, document_id: str) -> bytes:
        prefix, _, real_id = document_id.partition(":")
        try:
            idx = int(prefix)
        except ValueError as exc:
            raise KeyError(f"Composite id beklenen formatta değil: {document_id}") from exc
        if not 0 <= idx < len(self._sources):
            raise KeyError(f"Geçersiz kaynak indeksi: {idx}")
        return await self._sources[idx].fetch_content(real_id)

    def capabilities(self) -> Capabilities:
        caps = [s.capabilities() for s in self._sources]
        if not caps:
            return Capabilities()
        # Graceful degradation: a capability is guaranteed only if ALL children support it.
        return Capabilities(
            supports_webhooks=all(c.supports_webhooks for c in caps),
            supports_realtime=all(c.supports_realtime for c in caps),
            supports_effort_tracking=all(c.supports_effort_tracking for c in caps),
            supports_incremental_diff=all(c.supports_incremental_diff for c in caps),
        )
