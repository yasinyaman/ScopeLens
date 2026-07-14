"""A2: an unknown project_id does NOT silently fall back to the default -> 404.

Triaging against the wrong baseline means a wrong decision that looks error-free;
an unknown id must be an explicit error. Falling back to the default only happens
when project_id is not supplied at all.
"""

import pytest
from etki.api.context import AppContext, UnknownProjectError
from fastapi.testclient import TestClient


def test_unknown_project_id_is_404_on_triage(client: TestClient):
    resp = client.post(
        "/triage", json={"request_text": "rapora filtre", "project_id": "boyle-proje-yok"}
    )
    assert resp.status_code == 404


def test_unknown_project_id_is_404_on_kpi(client: TestClient):
    assert client.get("/kpi", params={"project_id": "boyle-proje-yok"}).status_code == 404


def test_missing_project_id_falls_back_to_default(client: TestClient):
    resp = client.post("/triage", json={"request_text": "rapora yeni filtre eklensin"})
    assert resp.status_code == 200
    assert resp.json()["project_id"] == "demo"


def test_resolve_project_raises_for_unknown(app_context: AppContext):
    with pytest.raises(UnknownProjectError):
        app_context.resolve_project("boyle-proje-yok")
    assert app_context.resolve_project(None) == "demo"
    assert app_context.resolve_project("demo") == "demo"
