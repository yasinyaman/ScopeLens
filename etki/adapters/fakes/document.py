"""In-memory DocumentSourceProvider — the port stays pure (list/fetch only).

Baseline does not belong here; it is loaded separately via the seed in the registry
(will be the Scope Extractor's output in Phase 1).
"""

from __future__ import annotations

from etki.adapters.fakes.seed import SEED_DOCUMENTS
from etki.core.models import DocumentRef
from etki.core.ports import Capabilities


class FakeDocumentSourceProvider:
    def __init__(self, documents: list[DocumentRef] | None = None) -> None:
        self._documents = list(documents) if documents is not None else list(SEED_DOCUMENTS)

    async def list_documents(self) -> list[DocumentRef]:
        return list(self._documents)

    async def fetch_content(self, document_id: str) -> bytes:
        return f"[sahte doküman içeriği: {document_id}]".encode()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=False,
        )
