"""UI-managed DEFAULT options for plugin adapters (Ayarlar → Eklentiler → detail).

Defaults merge UNDER a project's connector options at build time (the project
value always wins), so a secret like the Linear ``api_key`` can be entered once
in the UI instead of living in ``projects.yaml`` or requiring shell access for
an env var. The file gets the same posture as ``.etki/llm.json`` (it may hold
API keys): 0600, created atomically. Values may still be ``env:VAR``
references — they resolve at build time in core (`registry._resolve_secret_refs`),
never here, and never for display."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

OPTIONS_FILE = Path(".etki/plugin-options.json")

# Mask heuristic for form rendering: any underscore-separated word that is a
# credential noun. Whole-word so `path`/`pattern`/`hours_per_point` stay visible.
_SECRET_TOKENS = frozenset({"key", "token", "secret", "password", "pat", "apikey"})


def is_secret_field(name: str) -> bool:
    return any(part in _SECRET_TOKENS for part in name.lower().split("_"))


def load(path: str | Path = OPTIONS_FILE) -> dict[str, dict[str, Any]]:
    """{adapter_name: {option: value}} — {} when absent/corrupt (never raises)."""
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("plugin-options.json okunamadı; boş varsayılıyor", exc_info=True)
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def defaults_for(adapter: str, path: str | Path = OPTIONS_FILE) -> dict[str, Any]:
    return load(path).get(adapter, {})


def save(
    adapter: str, options: dict[str, Any], path: str | Path = OPTIONS_FILE
) -> dict[str, dict[str, Any]]:
    """Replaces the stored defaults of ONE adapter ({} removes the entry) and
    writes the whole file atomically with mode 0600 — the secret is never
    briefly world-readable and a crash mid-write can't leave a looser file."""
    p = Path(path)
    data = load(p)
    if options:
        data[adapter] = options
    else:
        data.pop(adapter, None)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.chmod(p, 0o600)
    return data
