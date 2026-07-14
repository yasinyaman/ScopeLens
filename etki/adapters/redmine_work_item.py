"""Redmine WorkItemProvider (REST) — time entries are first-class citizens.

Redmine remains common in exactly the consulting/agency environments Etki
targets, and its issues carry `spent_hours` natively (float hours, aggregated
from time entries) → normalized to `WorkItem.effort_seconds` inside the adapter.

`find_similar` uses the full-text search API (`/search.json?issues=1`), whose
results don't include effort — the adapter fetches the top hits' details (≤limit
extra requests, documented trade-off). Requires a live server → integration is
CI-skipped; pure parsing is unit-tested. Config example:

    connectors:
      work_items:
        adapter: redmine
        options:
          base_url: https://redmine.example.com
          api_key: env:REDMINE_API_KEY
"""

from __future__ import annotations

from typing import Any

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities


class RedmineWorkItemProvider:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-Redmine-API-Key": self._api_key}

    def _to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        status = issue.get("status") or {}
        tracker = issue.get("tracker") or {}
        # spent_hours: float hours aggregated from the issue's time entries.
        spent_hours = float(issue.get("spent_hours") or 0.0)
        return WorkItem(
            id=str(issue.get("id", "?")),
            title=issue.get("subject", "") or "",
            description=issue.get("description") or "",
            category=str(tracker.get("name")) if tracker.get("name") else None,
            status=str(status.get("name") or ""),
            effort_seconds=int(spent_hours * 3600),
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/issues/{item_id}.json",
                headers=self._headers(),
            )
            response.raise_for_status()
            return self._to_work_item(response.json().get("issue", {}))

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/search.json",
                headers=self._headers(),
                params={"q": description, "issues": 1, "limit": limit},
            )
            response.raise_for_status()
            hits = response.json().get("results", [])[:limit]
            items: list[WorkItem] = []
            for hit in hits:  # search results carry no effort → fetch details (≤limit calls)
                issue_id = hit.get("id")
                if issue_id is None:
                    continue
                detail = await client.get(
                    f"{self._base_url}/issues/{issue_id}.json", headers=self._headers()
                )
                detail.raise_for_status()
                items.append(self._to_work_item(detail.json().get("issue", {})))
            return items

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,  # plugins only in stock Redmine — declared honestly
            supports_realtime=False,
            supports_effort_tracking=True,  # native time entries
            supports_incremental_diff=False,
        )
