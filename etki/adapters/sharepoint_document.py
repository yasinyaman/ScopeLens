"""SharePoint / OneDrive DocumentSourceProvider via Microsoft Graph.

App-only auth (client-credentials): the adapter fetches its own bearer token from
`login.microsoftonline.com` with plain httpx (no MSAL dependency) and caches it
until expiry. Documents are the files of one drive (optionally one folder);
`fetch_content` returns the RAW bytes — the indexing engine parses docx/xlsx/pdf
by extension (`extraction.parsers.parse_document`), so Office contracts work
end-to-end. Requires a live tenant → integration is CI-skipped; pure mapping is
unit-tested. Config example:

    connectors:
      documents:
        adapter: sharepoint
        options:
          tenant_id: 00000000-0000-0000-0000-000000000000
          client_id: 11111111-1111-1111-1111-111111111111
          client_secret: env:SHAREPOINT_CLIENT_SECRET   # app permission: Files.Read.All
          drive_id: b!AbC...                            # GET /sites/{site-id}/drives
          folder: Contracts                             # optional, default: drive root
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx

from etki.core.models import DocumentRef
from etki.core.ports import Capabilities

_GRAPH = "https://graph.microsoft.com/v1.0"


class SharePointDocumentSourceProvider:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        drive_id: str,
        folder: str = "",
        timeout: float = 30.0,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._drive_id = drive_id
        self._folder = folder.strip("/")
        self._timeout = timeout
        self._token: str | None = None
        self._token_expires_at = 0.0

    async def _bearer(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self._token is None or time.monotonic() >= self._token_expires_at:
            response = await client.post(
                f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            response.raise_for_status()
            payload = response.json()
            self._token = payload["access_token"]
            # Refresh one minute early to avoid using a token at the expiry edge.
            self._token_expires_at = (
                time.monotonic() + float(payload.get("expires_in", 3600)) - 60
            )
        return {"Authorization": f"Bearer {self._token}"}

    def _children_url(self) -> str:
        if self._folder:
            return f"{_GRAPH}/drives/{self._drive_id}/root:/{self._folder}:/children"
        return f"{_GRAPH}/drives/{self._drive_id}/root/children"

    def _to_ref(self, item: dict[str, Any]) -> DocumentRef:
        modified = item.get("lastModifiedDateTime")
        return DocumentRef(
            id=str(item.get("id", "?")),
            name=str(item.get("name") or "untitled"),  # real filename → extension-aware parsing
            path=str(item.get("webUrl") or ""),
            mime=str((item.get("file") or {}).get("mimeType") or "application/octet-stream"),
            modified_at=datetime.fromisoformat(modified) if modified else None,
            source="sharepoint",
        )

    async def list_documents(self) -> list[DocumentRef]:
        docs: list[DocumentRef] = []
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            url: str | None = self._children_url()
            while url:
                response = await client.get(url, headers=await self._bearer(client))
                response.raise_for_status()
                payload = response.json()
                docs.extend(
                    self._to_ref(item)
                    for item in payload.get("value", [])
                    if "file" in item  # folders carry no "file" facet
                )
                url = payload.get("@odata.nextLink")
        return docs

    async def fetch_content(self, document_id: str) -> bytes:
        # Graph answers /content with a 302 to a pre-authenticated download URL.
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            response = await client.get(
                f"{_GRAPH}/drives/{self._drive_id}/items/{document_id}/content",
                headers=await self._bearer(client),
            )
            response.raise_for_status()
            return response.content

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,  # Graph subscriptions exist but are not implemented here
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=False,  # Graph delta queries: future work
        )
