"""Confluence Cloud DocumentSourceProvider — pages of a space as contract documents.

Auth mirrors the Jira adapter (same Atlassian account): email + API token, basic
auth. Pages are listed via the REST content API (paginated); `fetch_content`
returns the page's **storage-format HTML converted to plain text** (UTF-8 bytes)
so scope extraction sees clean clause lines. Requires a live site → integration
is CI-skipped; HTML→text conversion is unit-tested. Config example:

    connectors:
      documents:
        adapter: confluence
        options:
          base_url: https://yoursite.atlassian.net/wiki
          email: you@company.com
          api_token: env:CONFLUENCE_TOKEN
          space_key: CONTRACTS
"""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime
from typing import Any

import httpx

from etki.core.models import DocumentRef
from etki.core.ports import Capabilities

_PAGE_SIZE = 50
# Block-level closers become newlines so clause lines stay separate lines.
_BLOCK_RE = re.compile(r"(?i)<\s*(?:br\s*/?|/p|/h[1-6]|/li|/tr|/div)\s*>")
_TAG_RE = re.compile(r"<[^>]+>")


def storage_to_text(storage_html: str) -> str:
    """Confluence storage-format HTML → plain text (newline per block, entities unescaped)."""
    text = _BLOCK_RE.sub("\n", storage_html)
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


class ConfluenceDocumentSourceProvider:
    def __init__(
        self,
        base_url: str,
        email: str,
        api_token: str,
        space_key: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = (email, api_token)
        self._space_key = space_key
        self._timeout = timeout

    def _to_ref(self, page: dict[str, Any]) -> DocumentRef:
        version = page.get("version") or {}
        when = version.get("when")
        return DocumentRef(
            id=str(page.get("id", "?")),
            name=str(page.get("title") or "untitled"),  # no extension → parsed as text
            path=f"{self._base_url}{(page.get('_links') or {}).get('webui', '')}",
            mime="text/plain",
            modified_at=datetime.fromisoformat(when) if when else None,
            source="confluence",
        )

    async def list_documents(self) -> list[DocumentRef]:
        docs: list[DocumentRef] = []
        start = 0
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            while True:
                response = await client.get(
                    f"{self._base_url}/rest/api/content",
                    params={
                        "spaceKey": self._space_key,
                        "type": "page",
                        "status": "current",
                        "start": start,
                        "limit": _PAGE_SIZE,
                        "expand": "version",
                    },
                )
                response.raise_for_status()
                results = response.json().get("results", [])
                docs.extend(self._to_ref(p) for p in results)
                if len(results) < _PAGE_SIZE:
                    return docs
                start += _PAGE_SIZE

    async def fetch_content(self, document_id: str) -> bytes:
        async with httpx.AsyncClient(timeout=self._timeout, auth=self._auth) as client:
            response = await client.get(
                f"{self._base_url}/rest/api/content/{document_id}",
                params={"expand": "body.storage"},
            )
            response.raise_for_status()
            storage = (
                (response.json().get("body") or {}).get("storage") or {}
            ).get("value", "")
            return storage_to_text(storage).encode("utf-8")

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,  # Cloud webhooks need a Connect/Forge app — not implemented
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=False,
        )
