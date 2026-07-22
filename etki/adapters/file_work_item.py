"""File-based WorkItemProvider — normalizes a JSON/CSV ticket export.

Vendor-agnostic: converts exported ticket data into `WorkItem.effort_seconds`.
Provides a testable feed path in place of a real Jira/GitLab.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from etki.core.models import WorkItem
from etki.core.ports import Capabilities
from etki.core.text import score, tokenize


class FileWorkItemProvider:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._items = self._load()

    def _load(self) -> list[WorkItem]:
        if not self._path.exists():
            return []
        suffix = self._path.suffix.lower()
        if suffix == ".json":
            rows = json.loads(self._path.read_text(encoding="utf-8"))
        elif suffix in (".csv", ".tsv"):
            delimiter = "\t" if suffix == ".tsv" else ","
            with self._path.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh, delimiter=delimiter))
        else:
            raise ValueError(f"Desteklenmeyen export biçimi: {self._path.suffix}")
        return [WorkItem.model_validate(row) for row in rows]

    def all_items(self) -> list[WorkItem]:
        return list(self._items)

    async def get_work_item(self, item_id: str) -> WorkItem:
        for item in self._items:
            if item.id == item_id:
                return item
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
            supports_webhooks=False,
            supports_realtime=False,
            supports_effort_tracking=True,
            supports_incremental_diff=False,
            supports_enumeration=True,  # a local JSON export enumerates for free
        )
