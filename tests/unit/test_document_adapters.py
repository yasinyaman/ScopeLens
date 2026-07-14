"""Confluence + SharePoint document adapters: mapping, HTML→text, registry wiring."""

from etki.adapters.confluence_document import (
    ConfluenceDocumentSourceProvider,
    storage_to_text,
)
from etki.adapters.registry import build_documents
from etki.adapters.sharepoint_document import SharePointDocumentSourceProvider
from etki.config import ConnectorConfig

# --- Confluence ---


def test_storage_html_becomes_clause_lines():
    storage = (
        "<h2>Madde 7 &ndash; Kapsam</h2>"
        "<p>7.1 Raporlama mod&#252;l&#252; kapsam dahilindedir.</p>"
        "<ul><li>7.2 Mobil uygulama <strong>kapsam dışıdır</strong>.</li></ul>"
    )
    text = storage_to_text(storage)
    lines = text.splitlines()
    assert "Madde 7 – Kapsam" in lines[0]
    assert "7.1 Raporlama modülü kapsam dahilindedir." in lines[1]
    assert "7.2 Mobil uygulama kapsam dışıdır ." in lines[2] or (
        "kapsam dışıdır" in lines[2]
    )
    assert "<" not in text  # no tags survive


def test_confluence_page_maps_to_document_ref():
    provider = ConfluenceDocumentSourceProvider(
        "https://x.atlassian.net/wiki", "a@b.c", "tok", "SPACE"
    )
    ref = provider._to_ref(
        {
            "id": 98765,
            "title": "Sözleşme Kapsamı",
            "version": {"when": "2026-06-01T10:00:00.000Z"},
            "_links": {"webui": "/spaces/SPACE/pages/98765"},
        }
    )
    assert ref.id == "98765"
    assert ref.name == "Sözleşme Kapsamı"  # no extension → parsed as plain text
    assert ref.source == "confluence"
    assert ref.modified_at is not None and ref.modified_at.year == 2026


# --- SharePoint ---


def _sp() -> SharePointDocumentSourceProvider:
    return SharePointDocumentSourceProvider("tid", "cid", "secret", "drive1")


def test_sharepoint_drive_item_maps_to_document_ref():
    ref = _sp()._to_ref(
        {
            "id": "01ABC",
            "name": "contract.docx",
            "webUrl": "https://t.sharepoint.com/contract.docx",
            "lastModifiedDateTime": "2026-05-20T08:30:00Z",
            "file": {
                "mimeType": "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            },
        }
    )
    assert ref.id == "01ABC"
    assert ref.name == "contract.docx"  # extension drives docx parsing downstream
    assert "wordprocessingml" in ref.mime
    assert ref.source == "sharepoint"


def test_sharepoint_folder_scopes_children_url():
    root = _sp()
    assert root._children_url().endswith("/root/children")
    scoped = SharePointDocumentSourceProvider("t", "c", "s", "d", folder="/Contracts/")
    assert scoped._children_url().endswith("/root:/Contracts:/children")


def test_document_adapter_capabilities_are_honest():
    for provider in (
        ConfluenceDocumentSourceProvider("u", "e", "t", "S"),
        _sp(),
    ):
        caps = provider.capabilities()
        assert caps.supports_webhooks is False
        assert caps.supports_effort_tracking is False


# --- registry wiring ---


def test_registry_builds_confluence_and_sharepoint(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_TOKEN", "ct")
    monkeypatch.setenv("SP_SECRET", "ss")
    confluence = build_documents(
        ConnectorConfig(
            adapter="confluence",
            options={
                "base_url": "https://x.atlassian.net/wiki",
                "email": "a@b.c",
                "api_token": "env:CONFLUENCE_TOKEN",
                "space_key": "S",
            },
        )
    )
    sharepoint = build_documents(
        ConnectorConfig(
            adapter="sharepoint",
            options={
                "tenant_id": "t",
                "client_id": "c",
                "client_secret": "env:SP_SECRET",
                "drive_id": "d",
            },
        )
    )
    assert isinstance(confluence, ConfluenceDocumentSourceProvider)
    assert isinstance(sharepoint, SharePointDocumentSourceProvider)
