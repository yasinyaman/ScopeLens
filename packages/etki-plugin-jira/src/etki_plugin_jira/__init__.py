"""Jira request-intake + response-channel plugin — the first WRITING adapter.

Two adapters share one options model and one transport (`_JiraClient`):

- ``JiraRequestIntakeProvider`` polls new issues via JQL (REST v3 enhanced
  search). The opaque cursor is a minute-precision ``created`` watermark,
  optionally carrying a ``|nextPageToken`` suffix so consecutive polls can walk
  through a bulk-created minute (no livelock). The JQL floor backs off 60
  minutes (DST/clock-skew guard); the host's deterministic request-id dedup
  absorbs every overlap, so nothing is missed and nothing duplicates.
- ``JiraResponseChannel`` posts the host-composed decision text back as an
  issue comment (Atlassian Document Format). It RAISES on failure; the host is
  the only best-effort layer.

Auth is HTTP Basic (email:api_token, base64). Requires a live Jira Cloud site →
integration is CI-skipped; pure mapping + ADF + cursor math are unit-tested.
Depends ONLY on etki-api (+ httpx).
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, model_validator

from etki_api import (
    AdapterFactory,
    Capabilities,
    IncomingRequest,
    IntakeBatch,
    OutboundResponse,
    PluginSpec,
    PortName,
    SecurityCapabilities,
)

# Jira JQL `created` is minute-granular; the watermark uses the same precision.
_WATERMARK_FMT = "%Y-%m-%d %H:%M"
_FIELDS = "summary,description,creator,created,labels"


class JiraOptions(BaseModel):
    """Config for the `jira` intake + response adapters (secrets pre-resolved).
    One model, shared by both factories — the same credentials pull and post."""

    base_url: str
    email: str
    api_token: str
    project_key: str = ""
    jql: str = ""  # advanced override; when empty a `project = "<key>"` query is used
    page_size: int = 20
    timeout: float = 30.0

    @model_validator(mode="after")
    def _need_a_query(self) -> JiraOptions:
        if not self.project_key and not self.jql:
            raise ValueError("project_key veya jql alanlarından biri zorunludur.")
        return self


# --- ADF helpers -------------------------------------------------------------


def _adf_to_text(node: Any) -> str:
    """Flattens an Atlassian Document Format value (v3 returns ADF objects, not
    strings) to plain text — recursively collects `text` leaves. Structure
    (tables, mentions) is intentionally dropped; triage only needs the words."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_adf_to_text(n) for n in node)
    if isinstance(node, dict):
        text = node.get("text", "")
        inner = _adf_to_text(node.get("content"))
        sep = "\n" if node.get("type") in ("paragraph", "heading") else ""
        return f"{text}{inner}{sep}"
    return ""


def _text_to_adf(text: str) -> dict[str, Any]:
    """Wraps plain text in a minimal ADF document — one paragraph per line."""
    paragraphs = [
        {
            "type": "paragraph",
            "content": [{"type": "text", "text": line}] if line else [],
        }
        for line in text.split("\n")
    ]
    return {"type": "doc", "version": 1, "content": paragraphs or [{"type": "paragraph"}]}


# --- Transport ---------------------------------------------------------------


class _JiraClient:
    def __init__(self, opts: JiraOptions) -> None:
        self._opts = opts
        self._base_url = opts.base_url.rstrip("/")
        token = base64.b64encode(f"{opts.email}:{opts.api_token}".encode()).decode()
        self._auth = f"Basic {token}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """The single network seam — conformance doubles override THIS only."""
        async with httpx.AsyncClient(timeout=self._opts.timeout) as client:
            response = await client.request(
                method, f"{self._base_url}{path}", headers=self._headers(), **kwargs
            )
            response.raise_for_status()
            return response


class JiraRequestIntakeProvider(_JiraClient):
    def _base_jql(self) -> str:
        return self._opts.jql or f'project = "{self._opts.project_key}"'

    async def fetch_new(
        self, *, cursor: str | None = None, limit: int = 20
    ) -> IntakeBatch:
        """Cursor is opaque: either a bare watermark minute or
        ``"<minute>|<nextPageToken>"`` when a poll stopped mid-page. The token
        form lets consecutive polls WALK THROUGH a minute holding more issues
        than one batch (bulk import) — with a bare minute-watermark alone the
        cursor could never cross it (livelock: same first page every poll).
        The JQL floor also backs off 60 minutes (DST shift / clock skew guard);
        the host's deterministic request-id dedup absorbs the overlap."""
        minute, _, page_token = (cursor or "").partition("|")
        jql = self._base_jql()
        if minute:
            floor = minute
            try:
                floor_dt = datetime.strptime(minute, _WATERMARK_FMT) - timedelta(minutes=60)
                floor = floor_dt.strftime(_WATERMARK_FMT)
            except ValueError:
                pass  # unknown cursor shape → use it verbatim
            jql = f'({jql}) AND created >= "{floor}" ORDER BY created ASC'
        else:
            jql = f"({jql}) ORDER BY created ASC"

        items: list[IncomingRequest] = []
        next_token: str | None = page_token or None
        max_results = min(limit, self._opts.page_size)
        while len(items) < limit:
            params: dict[str, Any] = {
                "jql": jql, "maxResults": max_results, "fields": _FIELDS,
            }
            if next_token:
                params["nextPageToken"] = next_token
            response = await self._request("GET", "/rest/api/3/search/jql", params=params)
            payload = response.json()
            issues = payload.get("issues", []) or []
            items.extend(self._to_incoming(issue) for issue in issues)
            next_token = payload.get("nextPageToken") or None
            if not issues or next_token is None:
                break
        return IntakeBatch(
            items=items, cursor=self._next_cursor(items, cursor, leftover_token=next_token)
        )

    def _to_incoming(self, issue: dict[str, Any]) -> IncomingRequest:
        fields = issue.get("fields", {}) or {}
        creator = (fields.get("creator") or {}).get("displayName")
        key = str(issue.get("key", ""))
        created = fields.get("created")
        return IncomingRequest(
            external_id=str(issue.get("id", key or "?")),
            key=key,
            title=fields.get("summary", "") or "",
            description=_adf_to_text(fields.get("description")).strip(),
            reporter=creator,
            url=f"{self._base_url}/browse/{key}" if key else None,
            created_at=_parse_jira_datetime(created),
            labels=list(fields.get("labels") or []),
        )

    def _next_cursor(
        self,
        items: list[IncomingRequest],
        prev: str | None,
        *,
        leftover_token: str | None = None,
    ) -> str | None:
        stamps = [i.created_at for i in items if i.created_at is not None]
        if not stamps:
            return prev  # empty batch → keep the watermark
        minute = max(stamps).strftime(_WATERMARK_FMT)
        if leftover_token:
            # Stopped mid-page: resume the SAME query at the next page so a
            # bulk-created minute is crossed over consecutive polls.
            return f"{minute}|{leftover_token}"
        return minute

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_webhooks=False, supports_realtime=False)


class JiraResponseChannel(_JiraClient):
    async def post_response(self, response: OutboundResponse) -> None:
        try:
            await self._request(
                "POST",
                f"/rest/api/3/issue/{response.external_id}/comment",
                json={"body": _text_to_adf(response.text)},
            )
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:200] if exc.response is not None else ""
            raise RuntimeError(
                f"Jira yorum yazma başarısız ({response.external_id}): "
                f"{exc.response.status_code if exc.response else '?'} {body}"
            ) from exc

    def capabilities(self) -> Capabilities:
        return Capabilities(supports_webhooks=False, supports_realtime=False)


def _parse_jira_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:  # Jira: "2026-07-16T09:30:00.000+0300"
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        return None


def _build_intake(options: BaseModel) -> JiraRequestIntakeProvider:
    return JiraRequestIntakeProvider(JiraOptions.model_validate(options.model_dump()))


def _build_channel(options: BaseModel) -> JiraResponseChannel:
    return JiraResponseChannel(JiraOptions.model_validate(options.model_dump()))


# --- Conformance (offline doubles) ------------------------------------------

_CANNED_ISSUES: list[dict[str, Any]] = [
    {
        "id": "10001",
        "key": "DEMO-1",
        "fields": {
            "summary": "Raporlama ekranına CSV dışa aktarım",
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "rapor listesi csv indirilebilsin"}],
                    }
                ],
            },
            "creator": {"displayName": "Ayşe"},
            "created": "2026-07-16T09:30:00.000+0300",
            "labels": ["raporlama"],
        },
    },
    {
        "id": "10002",
        "key": "DEMO-2",
        "fields": {
            "summary": "Ödeme ekranında kripto para",
            "description": None,
            "creator": {"displayName": "Mehmet"},
            "created": "2026-07-16T10:00:00.000+0300",
            "labels": [],
        },
    },
]


class _OfflineJiraIntake(JiraRequestIntakeProvider):
    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        params = kwargs.get("params", {})
        jql = params.get("jql", "")
        issues = _CANNED_ISSUES
        # The double uses a STRICT `>` (vs the live `>=`) so it re-emits nothing —
        # the conformance suite has no host dedup to absorb the boundary overlap.
        if "created >=" in jql:
            after = jql.split('created >= "', 1)[1].split('"', 1)[0]
            issues = [
                i for i in issues if i["fields"]["created"][:16].replace("T", " ") > after
            ]
        issues = issues[: params.get("maxResults", 20)]
        return httpx.Response(200, json={"issues": issues})


class _OfflineJiraChannel(JiraResponseChannel):
    def __init__(self, opts: JiraOptions) -> None:
        super().__init__(opts)
        self.posted: list[OutboundResponse] = []

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        url = f"{self._base_url}{path}"
        request = httpx.Request(method, url)
        status = 404 if "/issue/YOK-999/" in path else 204
        response = httpx.Response(status, request=request)
        response.raise_for_status()  # mirror the real seam (raises on 4xx)
        return response

    async def post_response(self, response: OutboundResponse) -> None:
        await super().post_response(response)
        self.posted.append(response)


def _conformance() -> dict[PortName, object]:
    opts = JiraOptions(
        base_url="https://demo.atlassian.net",
        email="bot@example.com",
        api_token="offline",
        project_key="DEMO",
    )
    return {
        "request_intake": _OfflineJiraIntake(opts),
        "response_channel": _OfflineJiraChannel(opts),
    }


PLUGIN = PluginSpec(
    name="etki-plugin-jira",
    api_compat=">=0.1.2,<0.2",
    capabilities=SecurityCapabilities(
        network=True,
        filesystem="none",
        external_write=True,
        endpoints=["<site>.atlassian.net (configured base_url)"],
        notes=(
            "REST v3: request pull (JQL search, read) + comment write-back. The "
            "ONLY write is posting decision summaries as issue comments."
        ),
    ),
    adapters=(
        AdapterFactory(
            port="request_intake",
            name="jira",
            options_model=JiraOptions,
            build=_build_intake,
        ),
        AdapterFactory(
            port="response_channel",
            name="jira",
            options_model=JiraOptions,
            build=_build_channel,
        ),
    ),
    conformance=_conformance,
)
