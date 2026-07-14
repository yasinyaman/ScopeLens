"""Registry-metadata clients (deps Round C): canned-JSON parsing via
httpx.MockTransport (no network), silent degrade, config gating, live skipif.
"""

import json
import os

import httpx
import pytest
from etki.adapters.package_registries import PublicRegistryClient, enrich_dependencies
from etki.adapters.registry import build_package_registry
from etki.config import Settings
from etki.core.models import DeclaredDependency

_CANNED = {
    "/pypi/requests/json": {
        "info": {
            "version": "2.32.3",
            "project_url": "https://pypi.org/project/requests/",
            "project_urls": {"Source": "https://github.com/psf/requests"},
        },
        "releases": {"2.32.3": [{"upload_time_iso_8601": "2024-05-29T15:00:00Z"}]},
    },
    "/repos/psf/requests/releases": [
        {"tag_name": "v2.32.3", "published_at": "2024-05-29T15:00:00Z",
         "body": "Fixed `get` timeout handling."},
        {"tag_name": "v2.32.2", "published_at": "2024-05-20T15:00:00Z",
         "body": "Docs only."},
    ],
    "/express": {
        "dist-tags": {"latest": "4.19.2"},
        "time": {"4.19.2": "2024-03-25T12:00:00.000Z"},
        "homepage": "https://expressjs.com",
    },
    "/solrsearch/select": {
        "response": {"docs": [{"latestVersion": "3.3.0", "timestamp": 1715000000000}]},
    },
    "/v1/query": {
        "vulns": [
            {"id": "GHSA-xxxx-yyyy", "aliases": ["CVE-2024-26130"],
             "summary": "NULL pointer dereference in pkcs12 parsing"},
        ],
    },
}


def _client() -> PublicRegistryClient:
    def handler(request: httpx.Request) -> httpx.Response:
        for path, payload in _CANNED.items():
            if request.url.path == path or request.url.path.startswith(path):
                return httpx.Response(200, text=json.dumps(payload))
        return httpx.Response(404)

    return PublicRegistryClient(transport=httpx.MockTransport(handler))


async def test_pypi_latest_parses_version_and_release_date():
    meta = await _client().latest("pypi", "requests")
    assert meta is not None
    assert meta.latest_version == "2.32.3" and meta.released_at == "2024-05-29"


async def test_npm_latest_parses_dist_tags():
    meta = await _client().latest("npm", "express")
    assert meta is not None
    assert meta.latest_version == "4.19.2" and meta.released_at == "2024-03-25"


async def test_maven_latest_parses_search_doc():
    meta = await _client().latest("maven", "org.springframework.boot:spring-boot-starter-web")
    assert meta is not None
    assert meta.latest_version == "3.3.0" and meta.released_at == "2024-05-06"


async def test_release_notes_resolved_via_github_repo():
    releases = await _client().release_notes("pypi", "requests")
    assert [r["version"] for r in releases] == ["v2.32.3", "v2.32.2"]
    assert releases[0]["published_at"] == "2024-05-29"
    # maven has no reliable repo mapping → empty, silently.
    assert await _client().release_notes("maven", "g:a") == []


async def test_known_vulnerabilities_osv_parse_and_degrade():
    vulns = await _client().known_vulnerabilities("pypi", "cryptography", "42.0.0")
    assert vulns[0]["aliases"] == ["CVE-2024-26130"]
    assert "pkcs12" in vulns[0]["summary"]
    # Unknown OSV ecosystem → empty, silently (never raises).
    assert await _client().known_vulnerabilities("swift", "x") == []


async def test_unknown_ecosystem_and_http_error_degrade_to_none():
    client = _client()
    assert await client.latest("cargo", "serde") is None  # follow-up ecosystem
    assert await client.latest("pypi", "boyle-paket-yok") is None  # 404 → None


async def test_enrich_degrades_to_offline_rows_without_provider():
    deps = [DeclaredDependency(name="requests", raw_spec=">=2", ecosystem="pypi",
                               manifest="requirements.txt")]
    offline = await enrich_dependencies(deps, None)
    assert offline[0]["latest"] is None and offline[0]["spec"] == ">=2"
    online = await enrich_dependencies(deps, _client())
    assert online[0]["latest"] == "2.32.3"  # same row shape, enriched


def test_build_package_registry_is_config_gated(monkeypatch):
    monkeypatch.delenv("ETKI_DEPS_ONLINE", raising=False)
    assert build_package_registry(Settings()) is None  # off by default (CI offline)
    monkeypatch.setenv("ETKI_DEPS_ONLINE", "true")
    assert build_package_registry(Settings()) is not None


@pytest.mark.skipif(
    not os.environ.get("ETKI_TEST_DEPS_ONLINE"),
    reason="canlı registry testi: ETKI_TEST_DEPS_ONLINE=1 ile koşun",
)
async def test_live_pypi_lookup():  # pragma: no cover — live integration
    meta = await PublicRegistryClient().latest("pypi", "requests")
    assert meta is not None and meta.latest_version
