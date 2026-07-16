"""Ayarlar → Eklentiler screen: read-only visibility + the ONE safe mutation.

Pinned invariants: the policy value renders read-only and NO route can change
it; enable/disable round-trips through .etki/plugins.json → registry state;
mutation is pmo-only; the screen cannot acquire code (no install endpoint)."""

import pytest
from etki.adapters.plugins import get_plugin_registry
from fastapi.testclient import TestClient


@pytest.fixture
def plugins_sandbox(tmp_path, monkeypatch):
    """State file + lockfile land in a sandbox; the registry cache is rebuilt
    around the test so a toggled state never leaks into other tests."""
    monkeypatch.chdir(tmp_path)
    get_plugin_registry.cache_clear()
    yield
    get_plugin_registry.cache_clear()


def test_screen_renders_statuses_and_readonly_policy(
    client: TestClient, plugins_sandbox
):
    response = client.get("/ayarlar/eklentiler")
    assert response.status_code == 200
    body = response.text
    assert "etki-plugin-linear" in body
    assert "ETKI_PLUGIN_POLICY" in body  # policy shown…
    assert "verified_only" in body  # …with its (default) value
    # No form posts to a policy endpoint — the admin lock is env-only.
    assert "/ayarlar/eklentiler/policy" not in body


def test_no_route_can_mutate_the_policy(client: TestClient, plugins_sandbox):
    assert client.post("/ayarlar/eklentiler").status_code == 405  # screen: GET-only
    # /{name} exists only as a GET (plugin detail) → POST is 405; and "policy"
    # is not an installed plugin, so even the GET is a 404. Either way the
    # invariant holds: NO route can write the policy.
    assert (
        client.post("/ayarlar/eklentiler/policy", data={"policy": "allow_local"}).status_code
        == 405
    )
    assert client.get("/ayarlar/eklentiler/policy").status_code == 404


def test_toggle_roundtrip_disable_then_enable(client: TestClient, plugins_sandbox):
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/durum",
        data={"disabled": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    states = {s.name: s.state for s in get_plugin_registry().statuses()}
    assert states["etki-plugin-linear"] == "disabled"
    assert get_plugin_registry().stamp() == []  # disabled plugin leaves the audit stamp

    client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/durum",
        data={"disabled": "0"},
        follow_redirects=False,
    )
    states = {s.name: s.state for s in get_plugin_registry().statuses()}
    assert states["etki-plugin-linear"] == "active"


def test_toggle_unknown_plugin_404(client: TestClient, plugins_sandbox):
    response = client.post(
        "/ayarlar/eklentiler/boyle-plugin-yok/durum",
        data={"disabled": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 404


@pytest.fixture
def auth_role(request) -> dict[str, str]:
    """conftest override: pmo by default, viewer via indirect parametrization."""
    return getattr(request, "param", {"role": "pmo", "username": "test"})


@pytest.mark.parametrize(
    "auth_role", [{"role": "viewer", "username": "viewer1"}], indirect=True
)
def test_viewer_gets_403(client: TestClient, plugins_sandbox):
    assert client.get("/ayarlar/eklentiler").status_code == 403
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/durum",
        data={"disabled": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 403

def test_screen_shows_source_compat_and_disable_confirm(
    client: TestClient, plugins_sandbox
):
    body = client.get("/ayarlar/eklentiler").text
    assert "Kaynak" in body and "Uyum" in body  # source + compat columns (tr)
    assert "&lt;0.2" in body  # linear's api_compat range (html-escaped)
    assert "return confirm(" in body  # disabling asks for confirmation


def test_workitem_dropdown_lists_plugin_adapters(client: TestClient):
    """The adapter dropdown is fed by registry.available_adapters — an installed
    plugin appears with zero template edits; the fake test double stays out."""
    body = client.get("/projeler/demo/dosyalar").text
    for name in ("jira", "gitlab", "redmine", "azure_devops"):
        assert f'<option value="{name}"' in body
    assert '<option value="linear"' in body
    assert '<option value="fake"' not in body


def test_workitem_unknown_adapter_rejected(client: TestClient):
    """The UI form is the narrow surface: unresolvable names get a 400 with the
    available list (YAML remains the escape hatch for not-yet-installed plugins)."""
    response = client.post(
        "/projeler/demo/ayarlar/work-items",
        data={"adapter": "tanimsiz-adaptor", "options": ""},
    )
    assert response.status_code == 400
    assert "Bilinmeyen iş-takip adaptörü" in response.text
