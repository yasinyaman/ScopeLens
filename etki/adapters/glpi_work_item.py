"""GLPI WorkItemProvider (REST API). Reference vendor adapter.

In GLPI, effort is stored on the **task**, not the ticket: `tickettasks.actiontime`
(seconds). A ticket's total effort is the sum of its tasks' actiontime →
`WorkItem.effort_seconds`. The core never sees this detail. Requires a live GLPI
server, so it is skipped in CI (tests are marked with `skipif`).
"""

from __future__ import annotations

from typing import Any

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities


class GlpiWorkItemProvider:
    def __init__(
        self,
        base_url: str,
        app_token: str,
        user_token: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._app_token = app_token
        self._user_token = user_token
        self._timeout = timeout

    def _headers(self, session_token: str | None = None) -> dict[str, str]:
        headers = {"App-Token": self._app_token, "Content-Type": "application/json"}
        if session_token:
            headers["Session-Token"] = session_token
        else:
            headers["Authorization"] = f"user_token {self._user_token}"
        return headers

    async def _init_session(self, client: httpx.AsyncClient) -> str:
        response = await client.get(f"{self._base_url}/initSession", headers=self._headers())
        response.raise_for_status()
        return response.json()["session_token"]

    async def _ticket_effort_seconds(
        self, client: httpx.AsyncClient, session: str, ticket_id: str
    ) -> int:
        # Sum of actiontime (seconds) across the ticket's tasks.
        response = await client.get(
            f"{self._base_url}/Ticket/{ticket_id}/TicketTask",
            headers=self._headers(session),
        )
        response.raise_for_status()
        tasks = response.json()
        return sum(int(task.get("actiontime", 0) or 0) for task in tasks)

    def _to_work_item(self, raw: dict[str, Any], effort_seconds: int) -> WorkItem:
        return WorkItem(
            id=str(raw["id"]),
            title=raw.get("name", ""),
            description=raw.get("content", "") or "",
            status=str(raw.get("status", "")),
            effort_seconds=effort_seconds,
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            session = await self._init_session(client)
            response = await client.get(
                f"{self._base_url}/Ticket/{item_id}", headers=self._headers(session)
            )
            response.raise_for_status()
            effort = await self._ticket_effort_seconds(client, session, item_id)
            return self._to_work_item(response.json(), effort)

    @staticmethod
    def _search_params(description: str, limit: int) -> dict[str, Any]:
        """GLPI search criteria: the request's most significant words, OR-matched as
        `contains` against title (field 1) and content (field 21). A full request
        sentence would never substring-match, so we search by salient tokens."""
        params: dict[str, Any] = {"is_deleted": 0, "range": f"0-{limit - 1}"}
        tokens = sorted(
            {word.lower() for word in description.split() if len(word) > 3},
            key=len,
            reverse=True,
        )[:3]
        index = 0
        for token in tokens:
            for field in ("1", "21"):  # 1 = ticket title, 21 = ticket content
                params[f"criteria[{index}][field]"] = field
                params[f"criteria[{index}][searchtype]"] = "contains"
                params[f"criteria[{index}][value]"] = token
                if index > 0:
                    params[f"criteria[{index}][link]"] = "OR"
                index += 1
        return params

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            session = await self._init_session(client)
            response = await client.get(
                f"{self._base_url}/search/Ticket",
                headers=self._headers(session),
                params=self._search_params(description, limit),
            )
            response.raise_for_status()
            rows = response.json().get("data", [])
            if not rows:  # no text hits → fall back to the old recent-ticket listing
                response = await client.get(
                    f"{self._base_url}/search/Ticket",
                    headers=self._headers(session),
                    params={"is_deleted": 0, "range": f"0-{limit - 1}"},
                )
                response.raise_for_status()
                rows = response.json().get("data", [])
            items: list[WorkItem] = []
            for raw in rows:
                ticket_id = str(raw.get("2") or raw.get("id"))
                effort = await self._ticket_effort_seconds(client, session, ticket_id)
                ticket = {"id": ticket_id, "name": raw.get("1", "")}
                items.append(self._to_work_item(ticket, effort))
            return items

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,
            supports_realtime=False,
            supports_effort_tracking=True,
            supports_incremental_diff=False,
        )
