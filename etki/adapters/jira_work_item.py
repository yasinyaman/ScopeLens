"""Jira WorkItemProvider (Cloud REST v3) — general-purpose PM environment.

In Jira, effort comes from the issue's `timespent` field (seconds). The core never
sees this; it only sees the normalized `WorkItem.effort_seconds`. Since it requires
a live Jira, the integration is skipped in CI with `skipif`; pure parsing is unit-tested.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities

_FIELDS = "summary,status,timespent,labels"


class JiraWorkItemProvider:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        jql_extra: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth = f"Basic {token}"
        self._jql_extra = jql_extra
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._auth, "Accept": "application/json"}

    def _to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        fields = issue.get("fields", {}) or {}
        status = (fields.get("status") or {}).get("name", "")
        # First label = contract category (same convention as the GitLab adapter),
        # so Jira items feed effort-pool consumption too.
        labels = fields.get("labels") or []
        return WorkItem(
            id=str(issue.get("key", "?")),
            title=fields.get("summary", "") or "",
            category=str(labels[0]) if labels else None,
            status=str(status),
            effort_seconds=int(fields.get("timespent") or 0),
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/issue/{item_id}",
                headers=self._headers(),
                params={"fields": _FIELDS},
            )
            response.raise_for_status()
            return self._to_work_item(response.json())

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        jql = f'text ~ "{description.replace(chr(34), " ")}"'
        if self._jql_extra:
            jql = f"({jql}) AND {self._jql_extra}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/3/search",
                headers=self._headers(),
                params={"jql": jql, "maxResults": limit, "fields": _FIELDS},
            )
            response.raise_for_status()
            return [self._to_work_item(issue) for issue in response.json().get("issues", [])]

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,
            supports_realtime=False,
            supports_effort_tracking=True,
            supports_incremental_diff=False,
        )
