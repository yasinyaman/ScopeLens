"""etki-plugin-jira — ADF/mapping/cursor unit tests + plugin-contract checks."""

import asyncio

import pytest

from etki_api import (
    IncomingRequest,
    OutboundResponse,
    PluginManifest,
    RequestIntakeProvider,
    ResponseChannel,
    load_manifest,
)
from etki_plugin_jira import (
    PLUGIN,
    JiraOptions,
    JiraRequestIntakeProvider,
    JiraResponseChannel,
    _adf_to_text,
    _parse_jira_datetime,
    _text_to_adf,
)

_OPTS = JiraOptions(
    base_url="https://demo.atlassian.net/",
    email="bot@example.com",
    api_token="tok",
    project_key="DEMO",
)


# --- ADF ---------------------------------------------------------------------


def test_adf_flattens_nested_document():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "satır bir"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "satır iki"}]},
        ],
    }
    text = _adf_to_text(doc)
    assert "satır bir" in text and "satır iki" in text


def test_adf_of_none_is_empty():
    assert _adf_to_text(None) == ""


def test_text_to_adf_one_paragraph_per_line():
    adf = _text_to_adf("bir\niki")
    assert adf["type"] == "doc"
    texts = [c["content"][0]["text"] for c in adf["content"] if c["content"]]
    assert texts == ["bir", "iki"]


# --- Mapping / cursor --------------------------------------------------------


def test_to_incoming_maps_fields_and_url():
    provider = JiraRequestIntakeProvider(_OPTS)
    issue = {
        "id": "10001",
        "key": "DEMO-1",
        "fields": {
            "summary": "CSV dışa aktarım",
            "description": {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "csv indir"}]}
                ],
            },
            "creator": {"displayName": "Ayşe"},
            "created": "2026-07-16T09:30:00.000+0300",
            "labels": ["raporlama"],
        },
    }
    item = provider._to_incoming(issue)
    assert item.external_id == "10001"
    assert item.key == "DEMO-1"
    assert item.title == "CSV dışa aktarım"
    assert "csv indir" in item.description
    assert item.reporter == "Ayşe"
    assert item.url == "https://demo.atlassian.net/browse/DEMO-1"
    assert item.labels == ["raporlama"]
    assert item.created_at is not None


def test_empty_batch_echoes_the_cursor():
    provider = JiraRequestIntakeProvider(_OPTS)
    assert provider._next_cursor([], "2026-07-16 10:00") == "2026-07-16 10:00"


def test_cursor_is_max_created_watermark():
    provider = JiraRequestIntakeProvider(_OPTS)
    items = [
        IncomingRequest(
            external_id="1", created_at=_parse_jira_datetime("2026-07-16T09:30:00.000+0300")
        ),
        IncomingRequest(
            external_id="2", created_at=_parse_jira_datetime("2026-07-16T10:15:00.000+0300")
        ),
    ]
    assert provider._next_cursor(items, None) == "2026-07-16 10:15"


def test_options_require_project_key_or_jql():
    with pytest.raises(ValueError):
        JiraOptions(base_url="x", email="e", api_token="t")


def test_response_channel_raises_on_unknown_issue():
    from etki_plugin_jira import _OfflineJiraChannel

    channel = _OfflineJiraChannel(_OPTS)
    with pytest.raises(RuntimeError):
        asyncio.run(channel.post_response(OutboundResponse(external_id="YOK-999", text="x")))


# --- Plugin contract ---------------------------------------------------------


def test_spec_builds_conformant_providers():
    by_port = {a.port: a for a in PLUGIN.adapters}
    assert set(by_port) == {"request_intake", "response_channel"}
    intake = by_port["request_intake"].build(_OPTS)
    channel = by_port["response_channel"].build(_OPTS)
    assert isinstance(intake, JiraRequestIntakeProvider)
    assert isinstance(intake, RequestIntakeProvider)  # structural Protocol check
    assert isinstance(channel, JiraResponseChannel)
    assert isinstance(channel, ResponseChannel)


def test_manifest_matches_the_spec():
    manifest: PluginManifest = load_manifest(__file__.rsplit("/tests/", 1)[0])
    assert manifest.name == PLUGIN.name
    assert manifest.api_compat == PLUGIN.api_compat
    assert manifest.capabilities == PLUGIN.capabilities
    assert {a.name for a in manifest.adapters} == {a.name for a in PLUGIN.adapters}
    assert {a.port for a in manifest.adapters} == {a.port for a in PLUGIN.adapters}


def test_fetch_new_pages_through_a_bulk_minute_via_token_cursor():
    """A minute holding more issues than one batch must be crossable: the poll
    follows nextPageToken up to `limit`, and a leftover token rides the opaque
    cursor so the NEXT poll resumes mid-minute (no livelock)."""
    import asyncio

    provider = JiraRequestIntakeProvider(_OPTS)
    calls: list[dict] = []

    class _Resp:
        def __init__(self, payload):  # noqa: ANN001
            self._payload = payload

        def json(self):  # noqa: ANN202
            return self._payload

    pages = {
        None: {"issues": [
            {"id": "1", "key": "D-1",
             "fields": {"summary": "a", "created": "2026-07-16T09:30:00.000+0300"}},
        ], "nextPageToken": "T1"},
        "T1": {"issues": [
            {"id": "2", "key": "D-2",
             "fields": {"summary": "b", "created": "2026-07-16T09:30:00.000+0300"}},
        ], "nextPageToken": "T2"},
    }

    async def fake_request(method, path, **kwargs):  # noqa: ANN001, ANN003
        params = kwargs["params"]
        calls.append(params)
        return _Resp(pages[params.get("nextPageToken")])

    provider._request = fake_request  # type: ignore[method-assign]
    batch = asyncio.run(provider.fetch_new(cursor="2026-07-16 09:30", limit=2))
    assert [i.external_id for i in batch.items] == ["1", "2"]
    assert batch.cursor == "2026-07-16 09:30|T2"  # leftover token rides the cursor
    assert 'created >= "2026-07-16 09:30"' in calls[0]["jql"]  # exact watermark floor

    # Next poll resumes AT the token (same query), not at page one again.
    pages["T2"] = {"issues": [
        {"id": "3", "key": "D-3",
         "fields": {"summary": "c", "created": "2026-07-16T09:31:00.000+0300"}},
    ]}
    batch2 = asyncio.run(provider.fetch_new(cursor=batch.cursor, limit=2))
    assert [i.external_id for i in batch2.items] == ["3"]
    assert batch2.cursor == "2026-07-16 09:31"  # pages exhausted → bare watermark
