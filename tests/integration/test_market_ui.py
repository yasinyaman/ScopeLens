"""Ayarlar → Eklentiler → Pazar: read-only browse over the verified index.

Pinned invariants: the fragment is a PROJECTION of the signed index (search,
compat resolution, capability declarations, copyable CLI command) and can
never acquire code — no install POST exists; the index source is env-only
(ETKI_PLUGIN_INDEX_URL, never a form field); an unreadable index degrades to
a message instead of a 500; responses are cached until ?yenile=1."""

import pytest
from etki.api import web
from etki.plugin.index_schema import IndexArtifact, IndexFile, IndexPlugin, IndexVersion
from etki.plugin.lockfile import LockedPlugin
from fastapi.testclient import TestClient

from etki_api import SecurityCapabilities


def _index_file(version: str = "0.9.0") -> IndexFile:
    return IndexFile(
        generated_at="2026-07-16T10:00:00Z",
        plugins=[
            IndexPlugin(
                name="etki-plugin-linear",
                summary="Linear work items",
                source_repo="https://github.com/yasinyaman/etki-plugins",
                ports=["work_items"],
                capabilities=SecurityCapabilities(
                    network=True, filesystem="none", endpoints=["api.linear.app"]
                ),
                versions=[
                    IndexVersion(
                        version=version,
                        api_compat=">=0.1,<0.2",
                        artifact=IndexArtifact(
                            url="etki_plugin_linear-0.9.0-py3-none-any.whl",
                            sha256="0" * 64,
                        ),
                    )
                ],
            ),
            IndexPlugin(
                name="etki-plugin-gelecek",
                summary="<script>alert(1)</script> future-api plugin",
                versions=[
                    IndexVersion(
                        version="1.0.0",
                        api_compat=">=9.9",
                        artifact=IndexArtifact(url="x.whl", sha256="1" * 64),
                    )
                ],
            ),
        ],
    )


@pytest.fixture
def market_dir(tmp_path, monkeypatch):
    """A local index dir as the env-configured source (dir → the air-gapped
    hash-only rule, so the test needs no sigstore); the web cache starts empty."""
    index_dir = tmp_path / "market"
    index_dir.mkdir()
    (index_dir / "index.json").write_bytes(_index_file().model_dump_json(indent=2).encode())
    monkeypatch.setenv("ETKI_PLUGIN_INDEX_URL", str(index_dir))
    monkeypatch.setattr(web, "_market_cache", {})
    return index_dir


def test_plugins_screen_embeds_lazy_market(client: TestClient):
    """The screen only carries the placeholder — the index fetch is lazy, so an
    unreachable marketplace can never slow down the settings screen."""
    body = client.get("/ayarlar/eklentiler").text
    assert 'hx-get="/ayarlar/eklentiler/pazar"' in body


def test_fragment_renders_compat_resolution_and_cli_command(
    client: TestClient, market_dir
):
    body = client.get("/ayarlar/eklentiler/pazar").text
    assert "etki-plugin-linear" in body and "0.9.0" in body
    # The one and only acquisition path: a copyable operator-CLI command.
    assert f"python -m etki.plugin install etki-plugin-linear --index {market_dir}" in body
    assert "SHA-256" in body  # dir source → mirror/hash trust line
    assert "api.linear.app" in body  # capability declaration surfaces
    # Workspace linear plugin is installed at 0.1.0 → newer index version badges.
    assert "güncelleme: 0.9.0" in body
    # Future-api plugin: no version covers the installed etki-api.
    assert "uyumlu sürüm yok" in body
    # Index-sourced text renders ESCAPED (stored-XSS audit rule).
    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;" in body


def test_no_update_badge_when_versions_match(client: TestClient, market_dir, monkeypatch):
    """Regression: the row key must not be named "update" — Jinja resolves
    r.update to dict.update (attribute-first), which made the badge show for
    EQUAL versions on the live index."""
    (market_dir / "index.json").write_bytes(_index_file("0.1.0").model_dump_json().encode())
    body = client.get("/ayarlar/eklentiler/pazar").text
    assert "kurulu 0.1.0" in body  # installed badge stays
    assert "güncelleme:" not in body


def test_fragment_search_filters(client: TestClient, market_dir):
    body = client.get("/ayarlar/eklentiler/pazar", params={"q": "linear"}).text
    assert "etki-plugin-linear" in body
    assert "etki-plugin-gelecek" not in body


def test_fragment_caches_until_refresh(client: TestClient, market_dir):
    assert "0.9.0" in client.get("/ayarlar/eklentiler/pazar").text
    (market_dir / "index.json").write_bytes(_index_file("0.9.1").model_dump_json().encode())
    assert "0.9.1" not in client.get("/ayarlar/eklentiler/pazar").text  # TTL cache
    assert "0.9.1" in client.get("/ayarlar/eklentiler/pazar", params={"yenile": "1"}).text


def test_unreadable_index_degrades_not_500(client: TestClient, tmp_path, monkeypatch):
    empty = tmp_path / "bos"
    empty.mkdir()  # a dir without index.json — read fails
    monkeypatch.setenv("ETKI_PLUGIN_INDEX_URL", str(empty))
    monkeypatch.setattr(web, "_market_cache", {})
    response = client.get("/ayarlar/eklentiler/pazar")
    assert response.status_code == 200
    assert "İndeks okunamadı" in response.text


def test_install_gate_off_by_default(client: TestClient, market_dir):
    """Shipped posture (plan rule 4, 2026-07-16 revision): without the
    operator's env opt-in the fragment carries NO install form and the
    endpoint refuses — even for pmo."""
    assert client.post("/ayarlar/eklentiler/pazar").status_code == 405  # browse is GET-only
    body = client.get("/ayarlar/eklentiler/pazar").text
    assert "hx-post" not in body and 'method="post"' not in body.lower()
    response = client.post(
        "/ayarlar/eklentiler/pazar/kur", data={"name": "etki-plugin-linear"}
    )
    assert response.status_code == 403
    assert "ETKI_PLUGIN_UI_INSTALL" in response.text


def test_cli_search_defaults_to_env_index(market_dir, capsys):
    """`--index` is optional: the CLI resolves the same trust root as the UI
    (ETKI_PLUGIN_INDEX_URL env, else the official index) and prints it."""
    from etki.plugin.__main__ import main

    rc = main(["search", "linear"])
    out = capsys.readouterr().out
    assert rc == 0
    assert str(market_dir) in out  # resolved source is shown
    assert "etki-plugin-linear" in out


@pytest.fixture
def ui_install_on(monkeypatch):
    monkeypatch.setenv("ETKI_PLUGIN_UI_INSTALL", "true")


def test_install_source_is_env_pinned(
    client: TestClient, market_dir, ui_install_on, monkeypatch
):
    """Gate on: the button renders and the POST installs via the VERIFIED path
    with the env-pinned index source — a form-supplied source is ignored."""
    body = client.get("/ayarlar/eklentiler/pazar").text
    assert "/ayarlar/eklentiler/pazar/kur" in body  # install form present
    assert "hx-confirm" in body  # capability confirmation before the POST
    calls: dict = {}

    def fake_install(name, source, **kwargs):
        calls["name"], calls["source"] = name, source
        return LockedPlugin(
            name=name,
            source="verified",
            url="x.whl",
            sha256="0" * 64,
            api_compat=">=0.1,<0.2",
            installed_at="2026-07-16T00:00:00Z",
            verified=True,
        )

    monkeypatch.setattr("etki.plugin.marketplace.install_verified", fake_install)
    response = client.post(
        "/ayarlar/eklentiler/pazar/kur",
        data={"name": "etki-plugin-linear", "source": "https://evil.example/index.json"},
    )
    assert response.status_code == 200
    assert "kuruldu (doğrulanmış)" in response.text
    assert calls["name"] == "etki-plugin-linear"
    assert calls["source"] == str(market_dir)  # env-pinned, form field ignored


def test_install_failure_shows_banner(
    client: TestClient, market_dir, ui_install_on, monkeypatch
):
    from etki.plugin.installer import InstallError

    def boom(name, source, **kwargs):
        raise InstallError("artifact SHA-256 index'le uyuşmuyor")

    monkeypatch.setattr("etki.plugin.marketplace.install_verified", boom)
    response = client.post(
        "/ayarlar/eklentiler/pazar/kur", data={"name": "etki-plugin-linear"}
    )
    assert response.status_code == 200  # HTMX swap: banner, not a dropped 4xx
    assert "Kurulum başarısız" in response.text
    assert "uyuşmuyor" in response.text


@pytest.mark.parametrize(
    "auth_role", [{"role": "viewer", "username": "viewer1"}], indirect=True
)
def test_viewer_cannot_install(client: TestClient, market_dir, ui_install_on):
    response = client.post(
        "/ayarlar/eklentiler/pazar/kur", data={"name": "etki-plugin-linear"}
    )
    assert response.status_code == 403


@pytest.fixture
def auth_role(request) -> dict[str, str]:
    """conftest override: pmo by default, viewer via indirect parametrization."""
    return getattr(request, "param", {"role": "pmo", "username": "test"})


@pytest.mark.parametrize(
    "auth_role", [{"role": "viewer", "username": "viewer1"}], indirect=True
)
def test_viewer_gets_403(client: TestClient, market_dir):
    assert client.get("/ayarlar/eklentiler/pazar").status_code == 403
