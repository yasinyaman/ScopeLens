"""UI-managed LLM provider settings (the /ayarlar screen).

Persists a small override dict to `.etki/llm.json`, which `Settings` loads as its
highest-priority source (after init kwargs) — see `config.Settings.settings_customise_sources`.
Only the keys below are ever written; the file is chmod 600 because it may hold an API key.
Production deployments should still prefer env vars (`ETKI_*`); an absent file is a no-op.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from etki.config import UI_OVERRIDES_FILE

logger = logging.getLogger("etki")

# Whitelist of Settings fields the UI may override (LLM section).
ALLOWED_KEYS = frozenset({
    "llm_provider",
    "llm_base_url",
    "llm_api_key",
    "llm_model",
    "llm_timeout",
    "anthropic_api_key",
    "anthropic_model",
})

# Secret-valued keys: never echoed back to the form; empty form field = keep stored value.
SECRET_KEYS = frozenset({"llm_api_key", "anthropic_api_key"})


def load() -> dict[str, Any]:
    """Current UI overrides ({} if the file is absent or unreadable)."""
    try:
        raw = json.loads(UI_OVERRIDES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        logger.warning("llm.json okunamadı; boş varsayılıyor", exc_info=True)
        return {}
    return {k: v for k, v in raw.items() if k in ALLOWED_KEYS}


def save(updates: dict[str, Any]) -> dict[str, Any]:
    """Merges `updates` into the stored overrides and writes the file (chmod 600).

    A None value removes the key (falls back to env/default); unknown keys are ignored.
    Returns the resulting dict."""
    data = load()
    for key, value in updates.items():
        if key not in ALLOWED_KEYS:
            continue
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    UI_OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    UI_OVERRIDES_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.chmod(UI_OVERRIDES_FILE, 0o600)
    return data
