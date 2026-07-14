"""Direct package download + API-surface diff (dependency version analysis).

The user names a package and TWO versions ("faker 24.0 → 25.0"); both artifacts
are downloaded from the registry, their PUBLIC API surfaces are extracted and
diffed: removed / added / signature-changed symbols, with the entries matching
the code's own used symbols flagged first.

SECURITY INVARIANTS (do not weaken):
- Downloaded code is NEVER installed, imported or executed — archives are
  extracted with hardened rules and parsed with `ast` only.
- Extraction guards: no absolute paths / `..` members (zip), `tarfile`
  `filter="data"` (sdist), per-archive download cap, cumulative uncompressed
  cap and a member-count cap (zip-bomb protection).
- Opt-in online (ETKI_DEPS_ONLINE) like every registry feature; CI offline.

v1 scope: pypi (wheel preferred, sdist fallback). npm/maven surface diffs need
language-specific parsers — documented follow-ups in docs/adapters.md.
"""

from __future__ import annotations

import ast
import logging
import tarfile
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger("etki")

_MAX_DOWNLOAD_MB = 80  # per artifact
_MAX_EXTRACT_MB = 300  # cumulative uncompressed (zip-bomb guard)
_MAX_MEMBERS = 20_000


class PackageDownloadError(RuntimeError):
    """Download/extraction failed or a safety cap was hit (message says which)."""


class PackageFetcher:
    """Fetches one exact version's artifact from PyPI (wheel > sdist)."""

    def __init__(
        self,
        *,
        pypi_base_url: str = "https://pypi.org",
        timeout: float = 60.0,
        max_download_mb: int = _MAX_DOWNLOAD_MB,
        transport: httpx.AsyncBaseTransport | None = None,  # tests
    ) -> None:
        self._pypi = pypi_base_url.rstrip("/")
        self._timeout = timeout
        self._max_bytes = max_download_mb * 1024 * 1024
        self._transport = transport

    async def download(self, name: str, version: str, dest_dir: Path) -> Path:
        """Downloads the artifact for `name==version` into dest_dir; returns the
        file path. Prefers a pure wheel (stable layout), falls back to sdist."""
        async with httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=True
        ) as client:
            meta = await client.get(f"{self._pypi}/pypi/{name}/{version}/json")
            meta.raise_for_status()
            url, filename = _pick_artifact(meta.json().get("urls") or [])
            if url is None:
                raise PackageDownloadError(
                    f"{name}=={version} için indirilebilir wheel/sdist bulunamadı"
                )
            target = dest_dir / filename
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                size = 0
                with target.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self._max_bytes:
                            cap_mb = self._max_bytes // 1024 // 1024
                            raise PackageDownloadError(
                                f"indirme boyut sınırı aşıldı (> {cap_mb} MB)"
                            )
                        fh.write(chunk)
            return target


def _pick_artifact(urls: list[dict]) -> tuple[str | None, str]:
    """py3-none-any wheel > any wheel > sdist (verbatim registry order within tiers)."""
    wheels = [u for u in urls if u.get("packagetype") == "bdist_wheel"]
    pure = [u for u in wheels if "py3-none-any" in (u.get("filename") or "")]
    sdists = [u for u in urls if u.get("packagetype") == "sdist"]
    for tier in (pure, wheels, sdists):
        if tier:
            return tier[0].get("url"), tier[0].get("filename") or "artifact"
    return None, ""


def extract_archive(archive: Path, dest: Path) -> Path:
    """Hardened extraction. Returns the directory containing the package tree."""
    dest.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".whl" or archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) > _MAX_MEMBERS:
                raise PackageDownloadError("arşiv üye sayısı sınırı aşıldı")
            total = 0
            for member in members:
                name = member.filename
                if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    raise PackageDownloadError(f"güvensiz arşiv yolu: {name}")
                total += member.file_size
                if total > _MAX_EXTRACT_MB * 1024 * 1024:
                    raise PackageDownloadError("açılmış boyut sınırı aşıldı (zip-bomb koruması)")
            zf.extractall(dest)  # members validated above
    else:  # sdist .tar.gz — Python 3.12 data filter blocks traversal/devices/links
        with tarfile.open(archive) as tf:
            tar_members = tf.getmembers()
            if len(tar_members) > _MAX_MEMBERS:
                raise PackageDownloadError("arşiv üye sayısı sınırı aşıldı")
            if sum(m.size for m in tar_members) > _MAX_EXTRACT_MB * 1024 * 1024:
                raise PackageDownloadError("açılmış boyut sınırı aşıldı (zip-bomb koruması)")
            tf.extractall(dest, filter="data")
    return dest


def package_root(dest: Path) -> Path:
    """Directory the dotted module paths should be computed FROM.

    Wheels extract flat (`pkg/__init__.py` at top). sdists extract under a
    versioned dir (`pkg-24.0.0/…`, sometimes with a `src/` layout) — without
    this detection two sdist versions share NO surface keys and the diff
    degenerates into everything-removed+added. Rules (deterministic, at most
    two descents): top-level package or .py module present → dest is the root;
    else exactly one real top dir → descend; inside, a `src/` containing a
    package → descend again."""
    def _entries(d: Path) -> list[Path]:
        return [
            p for p in d.iterdir()
            if not p.name.endswith((".dist-info", ".egg-info"))
        ]

    def _has_python(d: Path) -> bool:
        return any(
            (p.is_dir() and (p / "__init__.py").exists()) or p.suffix == ".py"
            for p in _entries(d)
        )

    current = dest
    for _ in range(2):
        if _has_python(current):
            return current
        dirs = [p for p in _entries(current) if p.is_dir()]
        if len(dirs) == 1:
            current = dirs[0]
            src = current / "src"
            if not _has_python(current) and src.is_dir() and _has_python(src):
                return src
            continue
        break
    return current if _has_python(current) else dest


def api_surface(root: Path) -> dict[str, str]:
    """Public API surface of an extracted package tree: dotted symbol name →
    normalized signature. Functions/classes/methods; `_private` names, tests
    and *.dist-info are skipped. Parse-only (`ast`) — nothing is imported."""
    surface: dict[str, str] = {}
    for py in sorted(root.rglob("*.py")):
        rel = py.relative_to(root)
        parts = rel.with_suffix("").parts
        if any(p.endswith(".dist-info") or p in ("tests", "test") for p in parts):
            continue
        if any(p.startswith("_") and p != "__init__" for p in parts):
            continue
        module = ".".join(p for p in parts if p != "__init__")
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue  # py2 leftovers etc. — surface stays best-effort
        for node in tree.body:
            _collect(node, module, surface)
    return surface


def _collect(node: ast.stmt, prefix: str, surface: dict[str, str]) -> None:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        if not node.name.startswith("_"):
            qual = f"{prefix}.{node.name}" if prefix else node.name
            surface[qual] = f"({ast.unparse(node.args)})"
    elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
        qual = f"{prefix}.{node.name}" if prefix else node.name
        surface[qual] = "class"
        for child in node.body:
            _collect(child, qual, surface)


def exported_api(root: Path, full: dict[str, str] | None = None) -> dict[str, str]:
    """API-LEVEL surface: what a consumer actually imports — each package's
    `__init__` exports (`__all__` when present, else public defs + re-exports),
    keyed by the EXPORT path (`faker.Faker`, not `faker.proxy.Faker`), with
    re-export signatures resolved from the full tree. Exported classes bring
    their public methods along (a class's API includes its methods). Internal
    helpers that no `__init__` exports do not appear — that is the point.
    Pass a precomputed `full` surface to avoid a second tree parse."""
    full = full if full is not None else api_surface(root)
    exports: dict[str, str] = {}
    for init in sorted(root.rglob("__init__.py")):
        rel = init.relative_to(root)
        pkg_parts = rel.parts[:-1]
        if any(
            p.endswith(".dist-info") or p in ("tests", "test") or p.startswith("_")
            for p in pkg_parts
        ):
            continue
        pkg = ".".join(pkg_parts)
        try:
            tree = ast.parse(init.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        all_names: set[str] | None = None
        reexport: dict[str, str] = {}  # exported name → source dotted path
        local: set[str] = set()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        with_consts = getattr(node.value, "elts", [])
                        all_names = {
                            c.value for c in with_consts
                            if isinstance(c, ast.Constant) and isinstance(c.value, str)
                        }
            elif isinstance(node, ast.ImportFrom) and node.module and node.level >= 1:
                # from .proxy import Faker  (relative re-export)
                base_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                src = ".".join((*base_parts, *node.module.split(".")))
                for alias in node.names:
                    if alias.name != "*":
                        reexport[alias.asname or alias.name] = f"{src}.{alias.name}"
            elif isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ) and not node.name.startswith("_"):
                local.add(node.name)
        exported = all_names if all_names is not None else (local | set(reexport))
        for name in sorted(n for n in exported if not n.startswith("_")):
            export_path = f"{pkg}.{name}" if pkg else name
            source_path = (
                f"{pkg}.{name}" if name in local else reexport.get(name, "")
            )
            signature = full.get(source_path) or full.get(export_path) or "?"
            exports[export_path] = signature
            # Exported class → its public methods are part of the API.
            if signature == "class" and source_path:
                prefix = source_path + "."
                for symbol, sig in full.items():
                    if symbol.startswith(prefix):
                        method = symbol[len(prefix):]
                        exports[f"{export_path}.{method}"] = sig
    return exports


def diff_surfaces(old: dict[str, str], new: dict[str, str]) -> dict:
    """removed / added / signature-changed symbols between two surfaces."""
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = [
        {"symbol": name, "old": old[name], "new": new[name]}
        for name in sorted(set(old) & set(new))
        if old[name] != new[name]
    ]
    return {"removed": removed, "added": added, "changed": changed}


def check_used_paths(
    old_surface: dict[str, str],
    new_surface: dict[str, str],
    used_paths: list[str],
) -> dict:
    """THE false-negative closer: your code's qualified import paths, checked
    against the COMBINED (full ∪ exported) surfaces — Python does not enforce
    privacy, so a non-exported import breaking is still a break. Resolution
    tiers per path: exact key → module prefix (the path is a module and keys
    live under it) → unique suffix → unresolved (dynamic access, C-extension
    symbols — the honest bucket, never silently "ok")."""

    def _resolve(path: str, surface: dict[str, str]) -> str | None:
        if path in surface:
            return path
        if any(k.startswith(path + ".") for k in surface):
            return path  # module import: members live under it
        rest = path.split(".", 1)
        if len(rest) == 2 and rest[1]:
            suffix_hits = [k for k in surface if k.endswith("." + rest[1])]
            if len(suffix_hits) == 1:
                return suffix_hits[0]
        return None

    broken: list[dict] = []
    changed: list[dict] = []
    ok: list[str] = []
    unresolved: list[str] = []
    for path in sorted(set(used_paths)):
        old_key = _resolve(path, old_surface)
        if old_key is None:
            unresolved.append(path)
            continue
        new_key = old_key if old_key in new_surface else _resolve(path, new_surface)
        if new_key is None:
            last = path.rsplit(".", 1)[-1]
            hint = sorted(k for k in new_surface if k.rsplit(".", 1)[-1] == last)[:5]
            broken.append({"path": path, "hint": hint})  # hint: moved, not deleted?
            continue
        old_sig = old_surface.get(old_key, "")
        new_sig = new_surface.get(new_key, "")
        if old_sig != new_sig:
            changed.append({"path": path, "old": old_sig, "new": new_sig})
        else:
            ok.append(path)
    return {"broken": broken, "changed": changed, "ok": ok, "unresolved": unresolved}


async def version_diff_report(
    package: str,
    old_version: str,
    new_version: str,
    *,
    used_paths: list[str],
    used_symbols: list[str],
    fetcher: PackageFetcher,
    registry: object | None = None,  # RegistryMetadataProvider (OSV) — optional
    level: str = "api",
    cap: int = 200,
) -> dict:
    """The full version-comparison report, shared by the MCP tool and the web
    UI: your_code section (qualified paths vs the COMBINED full∪exported
    surfaces of both versions), exact-version OSV vulnerabilities, and the
    api/full summary diff (bounded at `cap`). Errors come back as
    {"error": …} — a tool/screen answer, never a crash."""
    import tempfile

    full: dict[str, dict[str, str]] = {}
    exported: dict[str, dict[str, str]] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="etki-verdiff-") as tmp:
            for version in (old_version, new_version):
                vdir = Path(tmp) / version
                vdir.mkdir(parents=True)
                artifact = await fetcher.download(package, version, vdir)
                root = package_root(extract_archive(artifact, vdir / "src"))
                full[version] = api_surface(root)
                exported[version] = exported_api(root, full[version])
    except Exception as exc:  # noqa: BLE001 — incl. PackageDownloadError
        return {"error": f"indirme/çözümleme başarısız: {exc}"}
    your_code = check_used_paths(
        {**full[old_version], **exported[old_version]},
        {**full[new_version], **exported[new_version]},
        used_paths,
    )
    vulnerabilities: dict[str, list[dict]] = {"old": [], "new": []}
    if registry is not None:
        vulnerabilities = {
            "old": await registry.known_vulnerabilities("pypi", package, old_version),  # type: ignore[attr-defined]
            "new": await registry.known_vulnerabilities("pypi", package, new_version),  # type: ignore[attr-defined]
        }
    surfaces = full if level == "full" else exported
    diff = diff_surfaces(surfaces[old_version], surfaces[new_version])
    truncated = any(len(diff[k]) > cap for k in ("removed", "added", "changed"))
    bounded = {k: diff[k][:cap] for k in ("removed", "added", "changed")}
    return {
        "package": package,
        "old_version": old_version,
        "new_version": new_version,
        "level": "full" if level == "full" else "api",
        "your_code": your_code,
        "vulnerabilities": vulnerabilities,
        "used_paths": used_paths,
        "old_symbols": len(surfaces[old_version]),
        "new_symbols": len(surfaces[new_version]),
        "counts": {k: len(diff[k]) for k in ("removed", "added", "changed")},
        "truncated": truncated,
        "used_symbols": used_symbols,
        **mark_used(bounded, used_symbols),
    }


def mark_used(diff: dict, used_symbols: list[str]) -> dict:
    """Splits the diff into the entries that touch the code's OWN used symbols
    (match on the last dotted component) and the rest — the caller reads the
    `used` section first."""
    used = set(used_symbols)

    def _hit(symbol: str) -> bool:
        return symbol.rsplit(".", 1)[-1] in used

    return {
        "used": {
            "removed": [s for s in diff["removed"] if _hit(s)],
            "changed": [c for c in diff["changed"] if _hit(c["symbol"])],
        },
        "all": diff,
    }
