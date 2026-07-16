"""Verified-marketplace client: search / resolve / install / mirror.

Trust chain, in order and pinned by tests:
1. REMOTE index → sigstore signature verification is MANDATORY (online side).
   LOCAL/mirror dir → signature optional (verified at mirror time; the
   air-gapped compromise), SHA-256 stays mandatory everywhere.
2. Version resolution picks the HIGHEST version whose `api_compat` covers the
   installed etki-api.
3. The artifact's SHA-256 must match the index BEFORE any install subprocess.
4. The capability prompt renders INDEX data — plugin code is never executed.
5. Success writes a lockfile entry with `verified = true` (which is also what
   unblocks the plugin at runtime under `verified_only`).
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from etki.plugin import installer, signing
from etki.plugin.index_schema import (
    BUNDLE_FILENAME,
    INDEX_FILENAME,
    MIRROR_MANIFEST,
    IndexFile,
    IndexPlugin,
    IndexVersion,
    parse_index,
)
from etki.plugin.installer import InstallError
from etki.plugin.lockfile import LockedPlugin, now_iso
from etki_api import __version__ as _api_version

_DOWNLOAD_TIMEOUT = 120.0

# The live signed index (GitHub Pages of yasinyaman/etki-plugins).
DEFAULT_INDEX_URL = "https://yasinyaman.github.io/etki-plugins/index.json"
ENV_INDEX_SOURCE = "ETKI_PLUGIN_INDEX_URL"


def index_source() -> str:
    """Marketplace index source (URL or mirror dir). Env-only ON PURPOSE — like
    ETKI_PLUGIN_POLICY this is a trust root, so the UI-writable settings file
    (.etki/llm.json → Settings) must never be able to redirect it."""
    return os.environ.get(ENV_INDEX_SOURCE, DEFAULT_INDEX_URL)


ENV_UI_INSTALL = "ETKI_PLUGIN_UI_INSTALL"


def ui_install_enabled() -> bool:
    """Opt-in switch for installing VERIFIED marketplace plugins from the UI
    (2026-07-16 revision of plan rule 4 — only the signed-index path, never
    git/wheel). Env-only and default OFF: the operator explicitly delegates
    code acquisition to pmo UI users; the shipped posture stays CLI-only."""
    return os.environ.get(ENV_UI_INSTALL, "").strip().lower() in ("1", "true", "yes")


def _http_get(url: str) -> bytes:
    import httpx

    response = httpx.get(url, timeout=_DOWNLOAD_TIMEOUT, follow_redirects=True)
    response.raise_for_status()
    return response.content


def load_index(source: str) -> tuple[IndexFile, bytes]:
    """`source` = mirror DIRECTORY (offline: signature optional) or index URL
    (online: signature MANDATORY — the bundle must exist next to it)."""
    src = Path(source)
    if src.is_dir():
        raw = (src / INDEX_FILENAME).read_bytes()
        bundle = src / BUNDLE_FILENAME
        if bundle.exists():
            try:
                signing.verify_index_bytes(raw, bundle.read_bytes())
            except signing.SigningError as exc:
                # Offline rule: a PRESENT-but-unverifiable signature is only a
                # warning when the tooling is absent; a FAILED verification is
                # always fatal.
                if "sigstore kurulu değil" not in str(exc):
                    raise
        return parse_index(raw), raw
    raw = _http_get(source)
    bundle_raw = _http_get(urljoin(source, BUNDLE_FILENAME))
    signing.verify_index_bytes(raw, bundle_raw)  # remote → no signature, no index
    return parse_index(raw), raw


def search(index: IndexFile, term: str) -> list[IndexPlugin]:
    needle = term.strip().lower()
    return [
        p
        for p in index.plugins
        if needle in p.name.lower()
        or needle in p.summary.lower()
        or any(needle in port for port in p.ports)
    ]


def resolve(index: IndexFile, name: str) -> tuple[IndexPlugin, IndexVersion]:
    """Highest version whose api_compat covers the INSTALLED etki-api."""
    plugin = index.get(name)
    if plugin is None:
        known = ", ".join(sorted(p.name for p in index.plugins)) or "(index boş)"
        raise InstallError(f"{name!r} index'te yok. Mevcut: {known}")
    installed = Version(_api_version)
    compatible = [
        v
        for v in plugin.versions
        if SpecifierSet(v.api_compat).contains(installed, prereleases=True)
    ]
    if not compatible:
        ranges = ", ".join(v.api_compat for v in plugin.versions) or "-"
        raise InstallError(
            f"{name}: kurulu etki-api {_api_version} ile uyumlu versiyon yok "
            f"(index'tekiler: {ranges})."
        )
    best = max(compatible, key=lambda v: Version(v.version))
    return plugin, best


def _fetch_artifact(source: str, version: IndexVersion, dest_dir: Path) -> Path:
    """Artifact bytes → a local wheel file. Mirror dir: the SIGNED index keeps
    its original urls, so artifacts sit under their basename next to it;
    remote: download."""
    src = Path(source)
    if src.is_dir():
        wheel = src / Path(version.artifact.url).name
        if not wheel.exists():
            raise InstallError(f"mirror'da artifact yok: {wheel}")
        return wheel
    url = version.artifact.url
    if not url.startswith(("http://", "https://")):
        url = urljoin(source, url)
    target = dest_dir / Path(url).name
    target.write_bytes(_http_get(url))
    return target


def install_verified(
    name: str,
    source: str,
    *,
    yes: bool = False,
    # CLI injects the capability prompt; None + yes=False → install proceeds
    # silently only for programmatic callers that did their own confirmation.
    confirm: Callable[[IndexPlugin, IndexVersion], bool] | None = None,
    python: str | None = None,
    lockfile_path: str | Path | None = None,
    uv_args: list[str] | None = None,
) -> LockedPlugin:
    index, _raw = load_index(source)
    plugin, version = resolve(index, name)
    if not yes and confirm is not None and not confirm(plugin, version):
        raise InstallError("vazgeçildi — hiçbir şey kurulmadı.")
    with tempfile.TemporaryDirectory(prefix="etki-marketplace-") as tmp:
        wheel = _fetch_artifact(source, version, Path(tmp))
        actual = installer.sha256_of(wheel)
        if actual != version.artifact.sha256.lower():
            raise InstallError(
                f"{name} {version.version}: artifact SHA-256 index'le uyuşmuyor — "
                f"kurulum İPTAL.\n  index:   {version.artifact.sha256}\n  dosyanın: {actual}"
            )
        proc = installer._uv_pip(
            ["install", str(wheel), *(uv_args or [])], python=python
        )
        if proc.returncode != 0:
            raise InstallError(f"uv pip install başarısız:\n{proc.stderr.strip()}")
    installer._pip_check_warn(name, python)
    entry = LockedPlugin(
        name=plugin.name,
        source="verified",
        url=version.artifact.url,
        sha256=version.artifact.sha256.lower(),
        api_compat=version.api_compat,
        capabilities=plugin.capabilities,
        installed_at=now_iso(),
        verified=True,
    )
    installer._lock_upsert(entry, lockfile_path)
    return entry


def mirror(source_url: str, dest: str | Path) -> list[str]:
    """Online-side mirror: download index + bundle, VERIFY THE SIGNATURE HERE,
    download every artifact, check each SHA-256, record the verification in
    mirror-manifest.json. The inner (air-gapped) side then installs from the
    directory hash-only."""
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = _http_get(source_url)
    bundle_raw = _http_get(urljoin(source_url, BUNDLE_FILENAME))
    signing.verify_index_bytes(raw, bundle_raw)  # the whole point of mirroring online
    index = parse_index(raw)
    (dest_dir / INDEX_FILENAME).write_bytes(raw)
    (dest_dir / BUNDLE_FILENAME).write_bytes(bundle_raw)
    mirrored: list[str] = []
    for plugin in index.plugins:
        for version in plugin.versions:
            url = version.artifact.url
            if not url.startswith(("http://", "https://")):
                url = urljoin(source_url, url)
            wheel_name = Path(url).name
            data = _http_get(url)
            import hashlib

            if hashlib.sha256(data).hexdigest() != version.artifact.sha256.lower():
                raise InstallError(
                    f"{plugin.name} {version.version}: indirilen artifact hash'i "
                    "index'le uyuşmuyor — mirror İPTAL."
                )
            (dest_dir / wheel_name).write_bytes(data)
            mirrored.append(f"{plugin.name}@{version.version}")
    # The index on disk keeps ORIGINAL urls (it is the signed artifact and must
    # stay byte-identical); the manifest records the local mapping + verification.
    identity, issuer = signing.expected_identity()
    manifest = {
        "mirrored_at": now_iso(),
        "source_url": source_url,
        "signature_verified": True,
        "identity": identity,
        "issuer": issuer,
        "artifacts": mirrored,
    }
    import json

    (dest_dir / MIRROR_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return mirrored


