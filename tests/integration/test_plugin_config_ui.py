"""Ayarlar → Eklentiler → plugin detail: status + UI-managed adapter defaults.

Pinned invariants: the defaults file is 0600 and secret fields are NEVER
echoed back (masked password input; an empty submit keeps the stored secret —
the llm.json idiom); defaults merge UNDER project options in
registry._try_plugin (the project value always wins); everything is pmo-only."""

import os
import stat

import pytest
from etki.adapters.plugins import get_plugin_registry
from etki.adapters.registry import build_work_items
from etki.config import ConnectorConfig
from etki.plugin import options_store
from fastapi.testclient import TestClient


@pytest.fixture
def plugins_sandbox(tmp_path, monkeypatch):
    """Relative state files (.etki/plugin-options.json, lockfile) land in a
    sandbox; the registry cache is rebuilt around the test."""
    monkeypatch.chdir(tmp_path)
    get_plugin_registry.cache_clear()
    yield
    get_plugin_registry.cache_clear()


def test_detail_renders_status_and_option_fields(client: TestClient, plugins_sandbox):
    body = client.get("/ayarlar/eklentiler/etki-plugin-linear").text
    assert "api_key" in body and "hours_per_point" in body
    assert 'type="password"' in body  # api_key masked by the secret heuristic
    assert "work_items" in body  # adapter port label


def test_unknown_plugin_404(client: TestClient, plugins_sandbox):
    assert client.get("/ayarlar/eklentiler/boyle-eklenti-yok").status_code == 404
    response = client.post(
        "/ayarlar/eklentiler/boyle-eklenti-yok/secenekler", data={"adapter": "x"}
    )
    assert response.status_code == 404


def test_save_masks_secret_and_empty_keeps_stored(client: TestClient, plugins_sandbox):
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/secenekler",
        data={"adapter": "linear", "opt_api_key": "lin_gizli_123", "opt_hours_per_point": "4"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    stored = options_store.load()
    assert stored["linear"]["api_key"] == "lin_gizli_123"
    mode = stat.S_IMODE(os.stat(options_store.OPTIONS_FILE).st_mode)
    assert mode == 0o600  # it may hold an API key — same posture as llm.json
    body = client.get("/ayarlar/eklentiler/etki-plugin-linear").text
    assert "lin_gizli_123" not in body  # the secret is never echoed back
    assert "kayıtlı" in body  # stored-secret placeholder
    assert 'value="4"' in body  # non-secret values round-trip visibly
    # Empty secret submit keeps the stored key; the non-secret field updates.
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/secenekler",
        data={"adapter": "linear", "opt_api_key": "", "opt_hours_per_point": "6"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    stored = options_store.load()
    assert stored["linear"]["api_key"] == "lin_gizli_123"
    assert stored["linear"]["hours_per_point"] == "6"


def test_reset_clears_stored_defaults_including_secret(
    client: TestClient, plugins_sandbox
):
    """Empty submits KEEP secrets by design — reset is the only clear path."""
    options_store.save("linear", {"api_key": "gizli", "hours_per_point": "4"})
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/secenekler",
        data={"adapter": "linear", "reset": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "linear" not in options_store.load()


def test_invalid_options_rejected_with_400(client: TestClient, plugins_sandbox):
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/secenekler",
        data={"adapter": "linear", "opt_api_key": "k", "opt_hours_per_point": "abc"},
    )
    assert response.status_code == 400
    assert "hours_per_point" in response.text


def test_defaults_merge_under_project_options(plugins_sandbox):
    """The build-time contract: UI defaults fill the gaps, project options win."""
    options_store.save("linear", {"api_key": "DEFAULT_KEY", "hours_per_point": "2"})
    provider = build_work_items(
        ConnectorConfig(adapter="linear", options={"hours_per_point": 5})
    )
    assert provider._api_key == "DEFAULT_KEY"  # default fills the gap
    assert provider._hours_per_point == 5.0  # project value wins
    provider2 = build_work_items(
        ConnectorConfig(adapter="linear", options={"api_key": "PROJECT_KEY"})
    )
    assert provider2._api_key == "PROJECT_KEY"  # project value wins
    assert provider2._hours_per_point == 2.0  # default fills the gap


@pytest.fixture
def auth_role(request) -> dict[str, str]:
    """conftest override: pmo by default, viewer via indirect parametrization."""
    return getattr(request, "param", {"role": "pmo", "username": "test"})


@pytest.mark.parametrize(
    "auth_role", [{"role": "viewer", "username": "viewer1"}], indirect=True
)
def test_viewer_gets_403(client: TestClient, plugins_sandbox):
    assert client.get("/ayarlar/eklentiler/etki-plugin-linear").status_code == 403
    response = client.post(
        "/ayarlar/eklentiler/etki-plugin-linear/secenekler", data={"adapter": "linear"}
    )
    assert response.status_code == 403
