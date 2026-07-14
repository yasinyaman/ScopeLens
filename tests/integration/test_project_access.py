"""A3: per-project access isolation (minimal RBAC v2).

Not every logged-in user can see every project: access comes from the `user_projects` table.
The `pmo` role gets access to all projects via `ETKI_PMO_GLOBAL` (on by default).
On case endpoints, the project is derived from the CASE, not from the PATH (closes IDOR).
"""

from collections.abc import Iterator

import pytest
from etki.api.app import app
from etki.api.context import AppContext, get_context
from etki.api.security import current_user
from etki.config import Settings
from etki.core.models import CaseFile
from fastapi.testclient import TestClient


@pytest.fixture
def iso_client(app_context: AppContext, auth_role: dict[str, str]) -> Iterator[TestClient]:
    """Client backed by user_projects: users exist in the real user_store, with their grants."""
    store = app_context.user_store
    store.create("pmo-user", "x-secret", "pmo")
    store.create("eng-x", "x-secret", "engineer", projects=["baska-proje"])
    store.create("eng-demo", "x-secret", "engineer", projects=["demo"])
    app.dependency_overrides[get_context] = lambda: app_context
    app.dependency_overrides[current_user] = lambda: {
        "username": auth_role["username"],
        "role": auth_role["role"],
    }
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_case(app_context: AppContext, case_id: str = "REQ-demo-1") -> str:
    app_context.repo.save_case(
        CaseFile(request_id=case_id, project_id="demo", raw_request="rapor filtre")
    )
    return case_id


def test_user_without_grant_cannot_see_other_projects_case(
    iso_client: TestClient, app_context: AppContext, auth_role: dict[str, str]
):
    """user A (project: baska-proje) -> demo project's case -> 404."""
    cid = _seed_case(app_context)
    auth_role.update(username="eng-x", role="engineer")
    assert iso_client.get(f"/casefiles/{cid}").status_code == 404
    assert iso_client.get(f"/ui/casefiles/{cid}").status_code == 404
    assert iso_client.get(f"/ui/casefiles/{cid}/report.docx").status_code == 404


def test_granted_user_sees_own_projects_case(
    iso_client: TestClient, app_context: AppContext, auth_role: dict[str, str]
):
    cid = _seed_case(app_context)
    auth_role.update(username="eng-demo", role="engineer")
    assert iso_client.get(f"/casefiles/{cid}").status_code == 200
    assert iso_client.get("/projeler/demo/onaylar").status_code == 200


def test_pmo_global_bypass(
    iso_client: TestClient, app_context: AppContext, auth_role: dict[str, str]
):
    cid = _seed_case(app_context)
    auth_role.update(username="pmo-user", role="pmo")
    assert iso_client.get(f"/casefiles/{cid}").status_code == 200
    assert iso_client.get("/projeler/demo").status_code == 200


def test_pmo_without_global_flag_is_scoped(
    iso_client: TestClient,
    app_context: AppContext,
    auth_role: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    """Multi-tenant mode: ETKI_PMO_GLOBAL=false -> pmo also sees only granted projects."""
    monkeypatch.setenv("ETKI_PMO_GLOBAL", "false")
    assert Settings().pmo_global is False
    cid = _seed_case(app_context)
    auth_role.update(username="pmo-user", role="pmo")  # has no project in the grant table
    assert iso_client.get(f"/casefiles/{cid}").status_code == 404
    assert iso_client.get("/projects").json() == []


def test_project_routes_blocked_without_grant(
    iso_client: TestClient, auth_role: dict[str, str]
):
    auth_role.update(username="eng-x", role="engineer")
    assert iso_client.get("/projeler/demo/triyaj").status_code == 404
    assert iso_client.get("/projeler/demo/raporlar").status_code == 404
    assert (
        iso_client.post(
            "/ui/triage", data={"request_text": "x", "project_id": "demo"}
        ).status_code
        == 404
    )
    assert iso_client.get("/kpi", params={"project_id": "demo"}).status_code == 404


def test_case_list_filtered_by_grants(
    iso_client: TestClient, app_context: AppContext, auth_role: dict[str, str]
):
    _seed_case(app_context)
    auth_role.update(username="eng-x", role="engineer")
    assert iso_client.get("/casefiles").json() == []
    assert iso_client.get("/projects").json() == []
    auth_role.update(username="eng-demo", role="engineer")
    assert len(iso_client.get("/casefiles").json()) == 1
    assert [p["id"] for p in iso_client.get("/projects").json()] == ["demo"]
