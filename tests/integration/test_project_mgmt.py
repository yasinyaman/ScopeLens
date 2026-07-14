"""Project management from the UI: writable store + spec docs + multi-repo merging."""

from etki.adapters.ast_code_index import AstCodeRepositoryProvider
from etki.adapters.code_index import MergedCodeRepository


def test_create_and_persist_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    project = projects_store.create_project("acme", "Acme Projesi", "CTR-ACME")
    assert project.doc_root
    reloaded = projects_store.get("acme")
    assert reloaded is not None
    assert reloaded.name == "Acme Projesi"
    assert reloaded.contract_id == "CTR-ACME"


def test_new_project_defaults_to_no_work_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    # A new project should have no fake seed ticket -> effort comes from code metrics instead.
    project = projects_store.create_project("acme", "Acme", "C")
    assert project.connectors.work_items.adapter == "none"


def test_add_repo_local_path_persists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    projects_store.add_repo("acme", "backend", src_root="/srv/backend", engine="ast")
    repos = projects_store.get("acme").repos
    assert [r.name for r in repos] == ["backend"]
    assert repos[0].src_root == "/srv/backend"


def test_add_documents_extracts_to_markdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    spec = b"Madde 1.1 - Raporlama\nAylik rapor uretimi kapsam dahilindedir.\n"
    written = projects_store.add_documents("acme", [("sartname.txt", spec)])
    assert written == 1
    docs = list((tmp_path / ".etki" / "projects" / "acme" / "docs").glob("*.md"))
    assert docs and "Raporlama" in docs[0].read_text(encoding="utf-8")


def test_list_and_delete_document(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    projects_store.add_documents("acme", [("sartname.txt", b"Madde 1.1 - Raporlama\n")])
    docs = projects_store.list_documents("acme")
    assert [d["name"] for d in docs] == ["sartname.md"]
    assert docs[0]["size"] > 0

    assert projects_store.delete_document("acme", "sartname.md") is True
    assert projects_store.list_documents("acme") == []
    assert projects_store.delete_document("acme", "sartname.md") is False  # already gone


def test_delete_document_path_traversal_blocked(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    # an attempt to escape the docs root via the name is blocked -> does not delete
    assert projects_store.delete_document("acme", "../../../etc/hosts") is False


def test_delete_repo_removes_definition(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    projects_store.add_repo("acme", "backend", src_root="/srv/backend")
    assert projects_store.delete_repo("acme", "backend") is True
    assert projects_store.get("acme").repos == []
    assert projects_store.delete_repo("acme", "backend") is False


def test_delete_project_removes_definition_and_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from etki import projects_store

    projects_store.create_project("acme", "Acme", "C")
    workspace = tmp_path / ".etki" / "projects" / "acme"
    assert workspace.exists()

    assert projects_store.delete_project("acme") is True
    assert projects_store.get("acme") is None
    assert not workspace.exists()
    assert projects_store.delete_project("acme") is False


async def test_merged_repo_namespaces_modules():
    # when two repos are merged, module ids are namespaced by repo name (multi-repo impact analysis)
    core = AstCodeRepositoryProvider("samples/demo_project/src")
    shop = AstCodeRepositoryProvider("samples/demo_project_b/src")
    merged = MergedCodeRepository([("core", core), ("shop", shop)])
    ids = {m.id for m in await merged.list_modules()}
    assert "core:auth" in ids
    assert "shop:payment" in ids
