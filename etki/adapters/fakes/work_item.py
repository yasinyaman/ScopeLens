"""In-memory WorkItemProvider — a test fixture and the Phase 0 skeleton's effort source."""

from __future__ import annotations

from etki.adapters.fakes.seed import SEED_WORK_ITEMS
from etki.core.models import WorkItem
from etki.core.ports import Capabilities
from etki.core.text import score, tokenize


class FakeWorkItemProvider:
    def __init__(self, items: list[WorkItem] | None = None) -> None:
        self._items = list(items) if items is not None else list(SEED_WORK_ITEMS)

    async def get_work_item(self, item_id: str) -> WorkItem:
        for it in self._items:
            if it.id == item_id:
                return it
        raise KeyError(f"WorkItem bulunamadı: {item_id}")

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        query = tokenize(description)
        scored = [
            (score(query, tokenize(f"{it.title} {it.description} {it.category or ''}")), it)
            for it in self._items
        ]
        ranked = sorted(
            (pair for pair in scored if pair[0] > 0.0),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return [it for _, it in ranked[:limit]]

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,
            supports_realtime=False,
            supports_effort_tracking=True,
            supports_incremental_diff=False,
        )
