"""Hafıza screen: wiki decision-files card + viewer fragment (İş 4c).

The card is a READ-ONLY view of the wiki projection (DB stays the single
source of truth); the viewer route path-joins doc_id in the adapter, so the
DEC-… shape guard is security-relevant (traversal)."""

from etki.adapters.filesystem_wiki import FileSystemWikiAdapter
from etki.api.context import AppContext
from fastapi.testclient import TestClient


def _wiki_on(app_context: AppContext, tmp_path) -> FileSystemWikiAdapter:
    wiki = FileSystemWikiAdapter(str(tmp_path / "wiki-{id}"))
    app_context.wiki = wiki
    return wiki


def test_files_card_lists_projection_and_viewer_renders(
    client: TestClient, app_context: AppContext, tmp_path
) -> None:
    wiki = _wiki_on(app_context, tmp_path)
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    doc_id = wiki.write_decision(app_context.repo.get_case(cid))

    page = client.get("/projeler/demo/hafiza")
    assert page.status_code == 200
    assert doc_id in page.text  # card lists the projection file
    assert f"/projeler/demo/hafiza/dosya/{doc_id}" in page.text  # hx-get target

    frag = client.get(f"/projeler/demo/hafiza/dosya/{doc_id}")
    assert frag.status_code == 200
    assert doc_id in frag.text
    assert "---" not in frag.text.split(">")[0]  # frontmatter stripped, not echoed raw


def test_viewer_rejects_non_dec_ids(client: TestClient, app_context: AppContext, tmp_path) -> None:
    _wiki_on(app_context, tmp_path)
    # Shape guard: anything that is not DEC-[\w-]+ never reaches the path join.
    assert client.get("/projeler/demo/hafiza/dosya/NOT-A-DEC").status_code == 404
    assert client.get("/projeler/demo/hafiza/dosya/DEC-a.b").status_code == 404  # dots blocked
    assert client.get("/projeler/demo/hafiza/dosya/DEC-yok-boyle-dosya").status_code == 404


def test_viewer_404_when_wiki_off(client: TestClient) -> None:
    # Default test context has no wiki: the card is hidden and the route 404s.
    page = client.get("/projeler/demo/hafiza")
    assert page.status_code == 200
    assert "hafiza/dosya/" not in page.text
    assert client.get("/projeler/demo/hafiza/dosya/DEC-x").status_code == 404


def test_viewer_role_can_read_the_memory_screen(
    client: TestClient, app_context: AppContext, auth_role: dict, tmp_path
) -> None:
    wiki = _wiki_on(app_context, tmp_path)
    cid = client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()["request_id"]
    doc_id = wiki.write_decision(app_context.repo.get_case(cid))
    # A non-pmo role sees only granted projects (RBAC v3) — grant demo first.
    app_context.user_store.create("test", "pw-123456", role="viewer", projects=["demo"])
    auth_role["role"] = "viewer"  # read-only role: memory screens stay readable
    assert client.get("/projeler/demo/hafiza").status_code == 200
    assert client.get(f"/projeler/demo/hafiza/dosya/{doc_id}").status_code == 200
