"""Authentication & session-based RBAC (real login flow, no X-Role)."""

from collections.abc import Iterator

import pytest
from etki.api.app import app
from etki.api.context import AppContext, get_context
from fastapi.testclient import TestClient


@pytest.fixture
def anon_client(app_context: AppContext) -> Iterator[TestClient]:
    """Client that does NOT override current_user → the real session/login path is tested."""
    app.dependency_overrides[get_context] = lambda: app_context
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_api_requires_login(anon_client: TestClient) -> None:
    assert anon_client.post("/triage", json={"request_text": "x"}).status_code == 401


def test_browser_redirects_to_login(anon_client: TestClient) -> None:
    r = anon_client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/login")


def test_x_role_header_no_longer_grants_access(anon_client: TestClient) -> None:
    # Old fake path: the X-Role header must NO LONGER grant access.
    r = anon_client.post("/triage", json={"request_text": "x"}, headers={"X-Role": "pmo"})
    assert r.status_code == 401


def test_login_flow_and_authenticated_access(
    anon_client: TestClient, app_context: AppContext
) -> None:
    app_context.user_store.create("pmo1", "sifre-123", "pmo")
    # Wrong password → 401
    assert anon_client.post(
        "/login", data={"username": "pmo1", "password": "yanlis"}
    ).status_code == 401
    # Correct password → 303 + session cookie (TestClient carries the cookie)
    r = anon_client.post(
        "/login", data={"username": "pmo1", "password": "sifre-123"}, follow_redirects=False
    )
    assert r.status_code == 303
    # The protected API is now reachable
    assert anon_client.post("/triage", json={"request_text": "rapora filtre"}).status_code == 200
    # Logout → 401 again
    anon_client.post("/logout")
    assert anon_client.post("/triage", json={"request_text": "x"}).status_code == 401


def test_logged_in_viewer_cannot_triage_or_approve(
    anon_client: TestClient, app_context: AppContext
) -> None:
    # The viewer is granted the demo project (A3 isolation); a writer creates the
    # case (W1 RBAC parity: /triage now requires a writing role, like its UI twin).
    app_context.user_store.create("eng1", "p-123456", "engineer", projects=["demo"])
    app_context.user_store.create("viewer1", "p-123456", "viewer", projects=["demo"])
    anon_client.post("/login", data={"username": "eng1", "password": "p-123456"})
    cid = anon_client.post("/triage", json={"request_text": "rapora yeni filtre"}).json()[
        "request_id"
    ]
    anon_client.post("/logout")
    anon_client.post("/login", data={"username": "viewer1", "password": "p-123456"})
    assert anon_client.post("/triage", json={"request_text": "x"}).status_code == 403
    r = anon_client.post(f"/casefiles/{cid}/decisions/0/action", json={"action": "APPROVE"})
    assert r.status_code == 403  # not PMO → approval denied


def test_multi_worker_config_fails_hard(monkeypatch) -> None:
    """D1: engines are process-local → WEB_CONCURRENCY>1 fails hard at startup (no silent drift)."""
    import pytest
    from etki.api.app import _enforce_single_worker

    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    with pytest.raises(RuntimeError, match="tek worker"):
        _enforce_single_worker()
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    _enforce_single_worker()  # 1 → fine
    monkeypatch.delenv("WEB_CONCURRENCY")
    _enforce_single_worker()  # unset → fine


def test_cross_site_post_is_rejected(anon_client: TestClient) -> None:
    """CSRF defense-in-depth: a mutating request stamped cross-site by the browser → 403."""
    r = anon_client.post(
        "/login",
        data={"username": "x", "password": "y"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403


def test_same_origin_post_passes_csrf_guard(anon_client: TestClient) -> None:
    r = anon_client.post(
        "/login",
        data={"username": "x", "password": "yanlis"},
        headers={"Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 401  # reaches the login handler (bad credentials), not 403
