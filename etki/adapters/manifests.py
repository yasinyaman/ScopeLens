"""Package-manifest parsing — dependency-impact analysis input (offline).

Table-driven, one parser per manifest filename. All parsers normalize into
`DeclaredDependency` with the VERBATIM version spec (`raw_spec`): no PEP 440 /
semver / maven-range resolution — the product need is evidence ("declared as
^4.17 in package.json, used by 3 modules"), not cross-ecosystem comparison.

Honest limitations (documented in docs/adapters.md):
- maven: default-namespace pom.xml is handled via local-name matching, but
  `${property}` version placeholders stay raw (no property resolution).
- No lockfile parsing (poetry.lock / package-lock.json / pom effective model).
- gradle (build.gradle is code, not data), composer.json and nuget csproj are
  follow-ups — the parser table makes each a one-function addition.
- import-name ↔ package-name matching is heuristic (`normalize_pkg` + a small
  alias table); a miss renders as "declared, no import seen" — never an error
  (dynamic imports exist).
"""

from __future__ import annotations

import json
import logging
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from etki.core.models import CodeModule, DeclaredDependency

logger = logging.getLogger("etki")

# Import names that are stdlib/builtins, never third-party packages. Heuristic:
# an npm package literally named "util" would be filtered too — acceptable and
# documented (the declared-manifest side still lists it).
_NODE_BUILTINS = {
    "fs", "path", "http", "https", "crypto", "os", "url", "util", "stream",
    "events", "buffer", "child_process", "zlib", "net", "assert", "process",
}
NOISE_IMPORTS: frozenset[str] = frozenset(sys.stdlib_module_names) | frozenset(_NODE_BUILTINS)

# Import-name aliases: distribution name → import name (lowercased, normalized).
_ALIASES = {
    "pyyaml": "yaml",
    "pillow": "pil",
    "beautifulsoup4": "bs4",
    "scikit_learn": "sklearn",
    "opencv_python": "cv2",
    "python_dateutil": "dateutil",
    "msgpack_python": "msgpack",
}

_PY_NAME_SPEC = re.compile(r"^\s*([A-Za-z0-9._-]+)(\[[^\]]*\])?\s*(.*)$")


def normalize_pkg(name: str) -> str:
    """Canonical form for import↔package matching: lowercase, -/. → _, alias
    table, npm scope stripped as a fallback (`@scope/pkg` → `pkg`)."""
    n = name.lower().strip()
    if n.startswith("@") and "/" in n:
        n = n.split("/", 1)[1]
    n = n.replace("-", "_").replace(".", "_")
    return _ALIASES.get(n, n)


# ------------------------------------------------------------------ parsers


def _parse_requirements(text: str) -> list[DeclaredDependency]:
    deps: list[DeclaredDependency] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("-", "--")):  # -r/-e/--index-url…
            continue
        line = line.split(";", 1)[0].strip()  # drop environment markers
        m = _PY_NAME_SPEC.match(line)
        if not m or not m.group(1):
            continue
        name, extras, spec = m.group(1), m.group(2) or "", (m.group(3) or "").strip()
        deps.append(
            DeclaredDependency(
                name=name, raw_spec=(extras + spec).strip(), ecosystem="pypi",
                manifest="requirements.txt",
            )
        )
    return deps


def _split_pep508(entry: str) -> tuple[str, str]:
    entry = entry.split(";", 1)[0].strip()
    m = _PY_NAME_SPEC.match(entry)
    if not m:
        return entry, ""
    return m.group(1), ((m.group(2) or "") + (m.group(3) or "")).strip()


def _parse_pyproject(text: str) -> list[DeclaredDependency]:
    data = tomllib.loads(text)
    project = data.get("project", {})
    deps: list[DeclaredDependency] = []
    for entry in project.get("dependencies", []):
        name, spec = _split_pep508(str(entry))
        deps.append(DeclaredDependency(name=name, raw_spec=spec, ecosystem="pypi",
                                       manifest="pyproject.toml"))
    for group, entries in (project.get("optional-dependencies") or {}).items():
        for entry in entries:
            name, spec = _split_pep508(str(entry))
            deps.append(
                DeclaredDependency(name=name, raw_spec=spec, ecosystem="pypi",
                                   manifest=f"pyproject.toml[{group}]", dev=True)
            )
    return deps


def _parse_package_json(text: str) -> list[DeclaredDependency]:
    data = json.loads(text)
    deps: list[DeclaredDependency] = []
    for key, dev in (("dependencies", False), ("devDependencies", True)):
        for name, spec in (data.get(key) or {}).items():
            deps.append(DeclaredDependency(name=name, raw_spec=str(spec), ecosystem="npm",
                                           manifest="package.json", dev=dev))
    return deps


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]  # strip xmlns — pom.xml has a default namespace


def _parse_pom(text: str) -> list[DeclaredDependency]:
    root = ET.fromstring(text)
    deps: list[DeclaredDependency] = []
    for dep in root.iter():
        if _local(dep.tag) != "dependency":
            continue
        fields = {_local(c.tag): (c.text or "").strip() for c in dep}
        name = f"{fields.get('groupId', '?')}:{fields.get('artifactId', '?')}"
        deps.append(
            DeclaredDependency(
                name=name,
                raw_spec=fields.get("version", ""),  # ${property} stays raw
                ecosystem="maven",
                manifest="pom.xml",
                dev=fields.get("scope", "") in ("test", "provided"),
            )
        )
    return deps


def _parse_go_mod(text: str) -> list[DeclaredDependency]:
    deps: list[DeclaredDependency] = []
    in_block = False
    for raw_line in text.splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line == ")":
            in_block = False
            continue
        entry = line.removeprefix("require ").strip() if line.startswith("require ") else (
            line if in_block else ""
        )
        parts = entry.split()
        if len(parts) >= 2 and "/" in parts[0]:
            deps.append(DeclaredDependency(name=parts[0], raw_spec=parts[1],
                                           ecosystem="go", manifest="go.mod"))
    return deps


def _parse_cargo(text: str) -> list[DeclaredDependency]:
    data = tomllib.loads(text)
    deps: list[DeclaredDependency] = []
    for key, dev in (("dependencies", False), ("dev-dependencies", True)):
        for name, spec in (data.get(key) or {}).items():
            # Both forms: `serde = "1.0"` and `serde = { version = "1.0", ... }`
            raw = spec if isinstance(spec, str) else str(spec.get("version", ""))
            deps.append(DeclaredDependency(name=name, raw_spec=raw, ecosystem="cargo",
                                           manifest="Cargo.toml", dev=dev))
    return deps


MANIFEST_PARSERS: dict[str, Callable[[str], list[DeclaredDependency]]] = {
    "requirements.txt": _parse_requirements,
    "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json,
    "pom.xml": _parse_pom,
    "go.mod": _parse_go_mod,
    "Cargo.toml": _parse_cargo,
}


def parse_manifests(root: str | Path) -> list[DeclaredDependency]:
    """Parses every known manifest at `root` and `root.parent` ONLY (src_root is
    typically `<corpus>/src`, manifests sit at `<corpus>/`). Never walks deeper
    (vendored node_modules) or higher; a broken manifest is logged and skipped —
    dependency data is an enrichment, never an indexing failure."""
    base = Path(root)
    deps: list[DeclaredDependency] = []
    seen_files: set[Path] = set()
    for directory in (base, base.parent):
        for filename, parser in MANIFEST_PARSERS.items():
            path = directory / filename
            if path in seen_files or not path.is_file():
                continue
            seen_files.add(path)
            try:
                deps.extend(parser(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001 — a bad manifest must not break indexing
                logger.warning("manifest ayrıştırılamadı: %s", path, exc_info=True)
    return deps


_SPEC_VERSION = re.compile(r"\d+(?:\.\d+){1,2}")


def first_version(spec: str) -> str:
    """Best-effort concrete version from a raw spec (">=42.0.0,<50" → "42.0.0")
    — a PREFILL convenience for the compare form, never a resolution claim."""
    match = _SPEC_VERSION.search(spec or "")
    return match.group(0) if match else ""


def match_packages(
    deps: list[DeclaredDependency], modules: list[CodeModule]
) -> dict[str, list[str]]:
    """Declared dependency name → module ids whose imported `packages` match
    after normalization. Query-time derivation (tens of nodes) — nothing extra
    is persisted in the index."""
    by_import: dict[str, list[str]] = {}
    for module in modules:
        for pkg in module.packages:
            by_import.setdefault(normalize_pkg(pkg), []).append(module.id)
    return {
        d.name: sorted(set(by_import.get(normalize_pkg(d.name), [])))
        for d in deps
    }
