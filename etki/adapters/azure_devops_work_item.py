"""Azure DevOps (Boards) WorkItemProvider — REST 7.x, PAT auth.

Effort comes from `Microsoft.VSTS.Scheduling.CompletedWork` (float HOURS on
task-level items) → normalized to `WorkItem.effort_seconds` inside the adapter.
Similar-item search runs a WIQL query over title/description, then batch-fetches
fields. Requires a live organization → integration is CI-skipped; pure parsing is
unit-tested. Config example:

    connectors:
      work_items:
        adapter: azure_devops
        options:
          organization: myorg            # dev.azure.com/myorg
          project: MyProject
          pat: env:AZDO_PAT               # scope: Work Items (Read)
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from etki.core.models import WorkItem
from etki.core.ports import Capabilities

_FIELDS = (
    "System.Title,System.State,System.WorkItemType,System.Description,"
    "Microsoft.VSTS.Scheduling.CompletedWork"
)
_API = "api-version=7.1"


class AzureDevOpsWorkItemProvider:
    def __init__(
        self, organization: str, project: str, pat: str, timeout: float = 30.0
    ) -> None:
        self._base_url = f"https://dev.azure.com/{organization}/{project}"
        token = base64.b64encode(f":{pat}".encode()).decode()  # PAT: empty user + token
        self._auth = f"Basic {token}"
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._auth, "Content-Type": "application/json"}

    def _to_work_item(self, raw: dict[str, Any]) -> WorkItem:
        fields = raw.get("fields") or {}
        completed_hours = float(
            fields.get("Microsoft.VSTS.Scheduling.CompletedWork") or 0.0
        )
        return WorkItem(
            id=str(raw.get("id", "?")),
            title=fields.get("System.Title", "") or "",
            description=str(fields.get("System.Description") or ""),
            category=str(fields.get("System.WorkItemType") or "") or None,
            status=str(fields.get("System.State") or ""),
            effort_seconds=int(completed_hours * 3600),
        )

    async def get_work_item(self, item_id: str) -> WorkItem:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(
                f"{self._base_url}/_apis/wit/workitems/{item_id}?fields={_FIELDS}&{_API}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return self._to_work_item(response.json())

    async def find_similar(self, description: str, *, limit: int = 5) -> list[WorkItem]:
        term = description.replace("'", " ").strip()[:200]
        wiql = (
            "SELECT [System.Id] FROM WorkItems "
            f"WHERE [System.Title] CONTAINS '{term}' "
            "ORDER BY [System.ChangedDate] DESC"
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/_apis/wit/wiql?$top={limit}&{_API}",
                headers=self._headers(),
                json={"query": wiql},
            )
            response.raise_for_status()
            ids = [str(w["id"]) for w in response.json().get("workItems", [])][:limit]
            if not ids:
                return []
            batch = await client.get(
                f"{self._base_url}/_apis/wit/workitems?ids={','.join(ids)}"
                f"&fields={_FIELDS}&{_API}",
                headers=self._headers(),
            )
            batch.raise_for_status()
            return [self._to_work_item(w) for w in batch.json().get("value", [])]

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=True,  # service hooks
            supports_realtime=False,
            supports_effort_tracking=True,  # CompletedWork (hours → seconds here)
            supports_incremental_diff=False,
        )
