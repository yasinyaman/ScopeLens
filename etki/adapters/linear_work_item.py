"""Linear WorkItemProvider (GraphQL) — honest about the missing time tracking.

Linear has no native time tracking: issues carry an `estimate` in POINTS, not
hours. Two consequences, both deliberate:

- `effort_seconds` is 0 unless the team opts into a conversion via
  `hours_per_point` (a team convention, e.g. 1 point ≈ 4 hours). When set,
  `effort_seconds = estimate × hours_per_point × 3600` — declared, not measured.
- `find_similar` DROPS zero-effort issues: feeding 0-hour "similars" into the
  PERT analogy would collapse the estimate range, whereas returning nothing
  makes the engine degrade gracefully to code metrics (existing behavior).

Auth: a personal API key goes into the `Authorization` header as-is (no
"Bearer" prefix). Requires a live workspace → integration is CI-skipped; pure
mapping is unit-tested. Config example:

    connectors:
      work_items:
        adapter: linear
        options:
          api_key: env:LINEAR_API_KEY
          hours_per_point: 4        # optional; omit to keep effort at 0
"""

from __future__ import annotations

from typing import Any

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities

_ENDPOINT = "https://api.linear.app/graphql"

_ISSUE_FIELDS = """
identifier
title
description
estimate
state { name }
labels { nodes { name } }
"""

_GET_QUERY = f"query($id: String!) {{ issue(id: $id) {{ {_ISSUE_FIELDS} }} }}"
_SEARCH_QUERY = (
    "query($term: String!, $first: Int!) { searchIssues(term: $term, first: $first) "
    f"{{ nodes {{ {_ISSUE_FIELDS} }} }} }}"
)


class LinearWorkItemProvider:
    def __init__(
        self, api_key: str, hours_per_point: float = 0.0, timeout: float = 30.0
    ) -> None:
        self._api_key = api_key
        self._hours_per_point = hours_per_point
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._api_key, "Content-Type": "application/json"}

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                _ENDPOINT,
                headers=self._headers(),
                json={"query": query, "variables": variables},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("errors"):
                raise RuntimeError(f"Linear GraphQL error: {payload['errors']}")
            return payload.get("data") or {}

    def _to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        labels = ((issue.get("labels") or {}).get("nodes")) or []
        estimate = float(issue.get("estimate") or 0.0)
        return WorkItem(
            id=str(issue.get("identifier", "?")),
            title=issue.get("title", "") or "",
            description=issue.get("description") or "",
            category=str(labels[0]["name"]) if labels else None,
            status=str((issue.get("state") or {}).get("name") or ""),
            effort_seconds=int(estimate * self._hours_per_point * 3600),
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        data = await self._graphql(_GET_QUERY, {"id": item_id})
        return self._to_work_item(data.get("issue") or {})

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        data = await self._graphql(
            _SEARCH_QUERY, {"term": description[:200], "first": limit}
        )
        nodes = ((data.get("searchIssues") or {}).get("nodes")) or []
        items = [self._to_work_item(n) for n in nodes]
        # Zero-effort analogies would collapse the PERT range to 0h; drop them so
        # the engine falls back to code metrics instead.
        return [it for it in items if it.effort_seconds > 0]

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,
            supports_realtime=False,
            # Only "tracked" in the declared-convention sense; honest otherwise.
            supports_effort_tracking=self._hours_per_point > 0,
            supports_incremental_diff=False,
        )
