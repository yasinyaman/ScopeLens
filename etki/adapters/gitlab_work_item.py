"""GitLab WorkItemProvider (REST v4) — issues with native time tracking.

GitLab is the friendliest source for effort-by-analogy: `time_stats.total_time_spent`
is already in SECONDS, so `WorkItem.effort_seconds` maps one-to-one (no unit
conversion inside the adapter — the normalization rule still applies, it just
happens to be identity here). Works with gitlab.com and self-managed instances.

Requires a live server → the integration is CI-skipped; pure parsing is unit-tested
(`tests/unit/test_gitlab.py`). Config example (secrets via `env:` references):

    connectors:
      work_items:
        adapter: gitlab
        options:
          base_url: https://gitlab.example.com
          project: mygroup/myrepo        # numeric id also works
          token: env:GITLAB_TOKEN         # scope: read_api
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities


class GitlabWorkItemProvider:
    def __init__(
        self,
        base_url: str,
        project: str,
        token: str,
        timeout: float = 30.0,
        labels: str | list[str] | None = None,
        issue_type: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Numeric id or URL-encoded full path ("group/repo") — both are valid API ids.
        self._project = quote(str(project), safe="")
        self._token = token
        self._timeout = timeout
        # Optional narrowing for teams that track effort on a subset (config, not code):
        #   labels: only issues carrying ALL of these labels (GitLab AND-semantics)
        #   issue_type: "issue" | "incident" | "test_case" | "task"
        if isinstance(labels, list):
            labels = ",".join(str(item) for item in labels)
        self._labels = labels or None
        self._issue_type = issue_type or None

    def _headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token}

    def _to_work_item(self, issue: dict[str, Any]) -> WorkItem:
        time_stats = issue.get("time_stats") or {}
        labels = issue.get("labels") or []
        return WorkItem(
            id=str(issue.get("iid", issue.get("id", "?"))),
            title=issue.get("title", "") or "",
            description=issue.get("description") or "",
            category=str(labels[0]) if labels else None,
            status=str(issue.get("state") or ""),
            effort_seconds=int(time_stats.get("total_time_spent") or 0),
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/api/v4/projects/{self._project}/issues/{item_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return self._to_work_item(response.json())

    def _search_params(self, description: str, limit: int) -> dict[str, Any]:
        # `search` covers title+description; closed issues carry the real effort.
        params: dict[str, Any] = {"search": description, "per_page": limit, "state": "closed"}
        if self._labels:
            params["labels"] = self._labels
        if self._issue_type:
            params["issue_type"] = self._issue_type
        return params

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/api/v4/projects/{self._project}/issues",
                headers=self._headers(),
                params=self._search_params(description, limit),
            )
            response.raise_for_status()
            return [self._to_work_item(issue) for issue in response.json()]

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,
            supports_realtime=False,
            supports_effort_tracking=True,  # native time tracking, seconds
            supports_incremental_diff=False,
        )
