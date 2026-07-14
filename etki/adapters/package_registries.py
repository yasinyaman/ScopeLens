"""Public package-registry clients (RegistryMetadataProvider) — opt-in, online.

One tiny client per ecosystem behind a single provider. Deliberately NOT named
`registry_*.py` — `adapters/registry.py` is the config→adapter factory, this
module talks to PyPI/npm/Maven Central.

Conventions (same as the other network adapters): one `httpx.AsyncClient` per
call with a short timeout; ANY failure (network, 404, schema drift) returns
None with a warning — metadata is display enrichment, never a dependency of
triage or indexing. CI stays offline (`ETKI_DEPS_ONLINE` defaults to false);
live tests are env-gated. go (proxy.golang.org) and cargo (crates.io) are
documented follow-ups in docs/adapters.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from etki.core.models import DeclaredDependency
from etki.core.ports import PackageMetadata, RegistryMetadataProvider

logger = logging.getLogger("etki")


class PublicRegistryClient:
    """PyPI + npm + Maven Central behind the RegistryMetadataProvider port."""

    def __init__(
        self,
        *,
        pypi_base_url: str = "https://pypi.org",
        npm_base_url: str = "https://registry.npmjs.org",
        maven_base_url: str = "https://search.maven.org",
        github_base_url: str = "https://api.github.com",
        osv_base_url: str = "https://api.osv.dev",
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,  # tests: MockTransport
    ) -> None:
        self._pypi = pypi_base_url.rstrip("/")
        self._npm = npm_base_url.rstrip("/")
        self._maven = maven_base_url.rstrip("/")
        self._github = github_base_url.rstrip("/")
        self._osv = osv_base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def latest(self, ecosystem: str, name: str) -> PackageMetadata | None:
        fetcher = {
            "pypi": self._latest_pypi,
            "npm": self._latest_npm,
            "maven": self._latest_maven,
        }.get(ecosystem)
        if fetcher is None:
            return None  # go/cargo: documented follow-ups
        try:
            return await fetcher(name)
        except Exception:  # noqa: BLE001 — enrichment only, degrade silently
            logger.warning("registry metadata alınamadı: %s/%s", ecosystem, name,
                           exc_info=True)
            return None

    async def _github_repo_for(self, ecosystem: str, name: str) -> str | None:
        """Resolves the package's GitHub repo from registry metadata (PyPI
        project_urls / npm repository.url). Maven: no reliable mapping → None."""
        if ecosystem == "pypi":
            data = await self._get_json(f"{self._pypi}/pypi/{name}/json")
            info = data.get("info", {})
            urls = list((info.get("project_urls") or {}).values())
            urls += [info.get("home_page"), info.get("project_url")]
            return _extract_github_repo(urls)
        if ecosystem == "npm":
            data = await self._get_json(f"{self._npm}/{name}")
            repo = data.get("repository")
            url = repo.get("url") if isinstance(repo, dict) else repo
            return _extract_github_repo([url, data.get("homepage")])
        return None

    async def release_notes(self, ecosystem: str, name: str, *, limit: int = 10) -> list[dict]:
        """Latest GitHub release notes for a package: [{version, published_at,
        notes}]. Unauthenticated GitHub API (60 req/h) — acceptable for the
        opt-in click-path; a token story is a documented follow-up. Any
        failure → [] (enrichment, never a dependency)."""
        try:
            repo = await self._github_repo_for(ecosystem, name)
            if repo is None:
                return []
            data = await self._get_json(
                f"{self._github}/repos/{repo}/releases?per_page={limit}"
            )
            return [
                {
                    "version": r.get("tag_name") or r.get("name") or "",
                    "published_at": (r.get("published_at") or "")[:10],
                    "notes": r.get("body") or "",
                }
                for r in data
                if isinstance(r, dict)
            ]
        except Exception:  # noqa: BLE001 — enrichment only
            logger.warning("release notları alınamadı: %s/%s", ecosystem, name,
                           exc_info=True)
            return []

    async def known_vulnerabilities(
        self, ecosystem: str, name: str, version: str | None = None, *, limit: int = 10
    ) -> list[dict]:
        """Known vulnerabilities from OSV.dev (free, deterministic, no key).
        With a `version` the answer is exact ("42.0.0 has CVE-…"); without one
        it lists the package's known advisories (capped). Security-motivated
        dependency requests get their evidence from here. Failure → []."""
        eco = _OSV_ECOSYSTEMS.get(ecosystem)
        if eco is None:
            return []
        payload: dict = {"package": {"name": name, "ecosystem": eco}}
        if version:
            payload["version"] = version
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(f"{self._osv}/v1/query", json=payload)
                response.raise_for_status()
                vulns = response.json().get("vulns") or []
            return [
                {
                    "id": v.get("id", ""),
                    "aliases": (v.get("aliases") or [])[:4],
                    "summary": (v.get("summary") or "")[:200],
                }
                for v in vulns[:limit]
                if isinstance(v, dict)
            ]
        except Exception:  # noqa: BLE001 — enrichment only
            logger.warning("OSV sorgusu başarısız: %s/%s", ecosystem, name, exc_info=True)
            return []

    async def _get_json(self, url: str) -> Any:  # dict for registries, list for releases
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def _latest_pypi(self, name: str) -> PackageMetadata:
        data = await self._get_json(f"{self._pypi}/pypi/{name}/json")
        version = data["info"]["version"]
        uploads = data.get("releases", {}).get(version) or []
        released = (uploads[0].get("upload_time_iso_8601") or "")[:10] if uploads else None
        return PackageMetadata(
            name=name, ecosystem="pypi", latest_version=version,
            released_at=released or None,
            homepage=data["info"].get("project_url") or data["info"].get("home_page"),
        )

    async def _latest_npm(self, name: str) -> PackageMetadata:
        data = await self._get_json(f"{self._npm}/{name}")
        version = (data.get("dist-tags") or {}).get("latest")
        released = (data.get("time") or {}).get(version or "", "")[:10] or None
        return PackageMetadata(
            name=name, ecosystem="npm", latest_version=version,
            released_at=released, homepage=data.get("homepage"),
        )

    async def _latest_maven(self, name: str) -> PackageMetadata:
        group, _, artifact = name.partition(":")
        data = await self._get_json(
            f"{self._maven}/solrsearch/select?q=g:{group}+AND+a:{artifact}&rows=1&wt=json"
        )
        docs = data.get("response", {}).get("docs") or []
        if not docs:
            return PackageMetadata(name=name, ecosystem="maven")
        doc = docs[0]
        ts = doc.get("timestamp")
        released = None
        if isinstance(ts, int):  # epoch millis → ISO date, computed from the value
            from datetime import UTC, datetime

            released = datetime.fromtimestamp(ts / 1000, tz=UTC).date().isoformat()
        return PackageMetadata(
            name=name, ecosystem="maven",
            latest_version=doc.get("latestVersion"), released_at=released,
        )


_GITHUB_REPO = re.compile(r"github\.com[:/]+([\w.-]+)/([\w.-]+?)(?:\.git)?(?:[/#?].*)?$")

# OSV.dev ecosystem identifiers (https://ossf.github.io/osv-schema/).
_OSV_ECOSYSTEMS = {
    "pypi": "PyPI", "npm": "npm", "maven": "Maven", "go": "Go", "cargo": "crates.io",
}


def _extract_github_repo(urls: list[str | None]) -> str | None:
    for url in urls:
        if not url:
            continue
        m = _GITHUB_REPO.search(url)
        if m:
            return f"{m.group(1)}/{m.group(2)}"
    return None


def api_change_mentions(used_symbols: list[str], releases: list[dict]) -> list[dict]:
    """DETERMINISTIC change report: which of the code's USED symbols are
    mentioned in each release's notes — the releases to read before an
    upgrade/downgrade. Word-boundary matching; no LLM, no interpretation."""
    out = []
    for release in releases:
        text = release.get("notes") or ""
        mentions = sorted(
            s for s in set(used_symbols)
            if re.search(rf"(?<![\w.]){re.escape(s)}(?![\w])", text)
        )
        if mentions:
            out.append(
                {
                    "version": release.get("version", ""),
                    "published_at": release.get("published_at", ""),
                    "mentions": mentions,
                }
            )
    return out


async def enrich_dependencies(
    deps: list[DeclaredDependency], provider: RegistryMetadataProvider | None
) -> list[dict]:
    """Display rows: declared manifest facts + registry metadata side by side.
    Per-package degrade — one flaky registry answer never hides the others."""
    import asyncio

    if provider is not None:
        metas = list(await asyncio.gather(*(provider.latest(d.ecosystem, d.name) for d in deps)))
    else:
        metas = [None] * len(deps)
    rows = []
    for d, meta in zip(deps, metas, strict=True):
        rows.append(
            {
                "name": d.name, "spec": d.raw_spec or "*", "ecosystem": d.ecosystem,
                "dev": d.dev, "manifest": d.manifest,
                "latest": meta.latest_version if meta else None,
                "released_at": meta.released_at if meta else None,
            }
        )
    return rows
