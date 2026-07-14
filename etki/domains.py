"""Domain profile registry — skill-file-like selectable LLM context.

`config/domains/*.md`: each file is a domain profile. The first `# ` line is the title;
the rest is domain instruction text appended to the LLM prompt. Air-gapped/file-based
(the existing `config/` pattern). Projects can **select** one of these profiles or
**enter** free text (`ProjectConfig.domain_profile` + `instructions`).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

_DOMAINS_DIR = Path("config/domains")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def list_domain_profiles() -> list[dict[str, str]]:
    """Available domain profiles: [{id, title}] (config/domains/*.md)."""
    if not _DOMAINS_DIR.exists():
        return []
    out: list[dict[str, str]] = []
    for f in sorted(_DOMAINS_DIR.glob("*.md")):
        out.append({"id": f.stem, "title": _title(f.read_text(encoding="utf-8"), f.stem)})
    return out


def load_domain_profile(profile_id: str | None) -> str | None:
    """Full text of a domain profile (path-traversal safe). None if absent."""
    if not profile_id or not _SAFE_ID.match(profile_id):
        return None
    f = _DOMAINS_DIR / f"{profile_id}.md"
    if not f.is_file():
        return None
    return f.read_text(encoding="utf-8").strip()


@lru_cache(maxsize=32)
def load_module_hints(profile_id: str | None = None) -> dict[str, tuple[str, ...]]:
    """Module hints (module → keywords): `_common.hints.yaml` + `{profile}.hints.yaml`.

    There is NO hint dictionary baked into the engine core — each project is fed from
    its own domain profile (one project's demo dictionary cannot leak into another's
    triage). If the file is absent an empty dict is returned; `guess_module` then
    yields None (falling back to the LLM/similarity path)."""
    merged: dict[str, tuple[str, ...]] = {}
    stems = ["_common"]
    if profile_id and _SAFE_ID.match(profile_id):
        stems.append(profile_id)
    for stem in stems:
        f = _DOMAINS_DIR / f"{stem}.hints.yaml"
        if not f.is_file():
            continue
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for module, keywords in (data.get("module_hints") or {}).items():
            if isinstance(keywords, list):
                merged[str(module)] = tuple(str(k).lower() for k in keywords)
    return merged
