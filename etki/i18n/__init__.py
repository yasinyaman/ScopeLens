"""Lightweight i18n layer — TR/EN/DE. Dictionary-based catalog + ContextVar locale.

Usage:
- Templates: the Jinja context_processor injects `t` + `lang` → `{{ t('nav.projects') }}`.
- Filters (`tr_decision` etc.): read the active language via `get_locale()`.
- Engine/LLM/errors: the route gets `lang` via `resolve_locale(request, settings)`,
  then calls `t(key, lang, ...)`.

Missing key → `tr` fallback → the key itself (the screen is never left blank).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from etki.i18n.catalog import MESSAGES

if TYPE_CHECKING:
    from starlette.requests import Request

    from etki.config import Settings

SUPPORTED: tuple[str, ...] = ("tr", "en", "de")
DEFAULT: str = "tr"
LANG_NAMES: dict[str, str] = {"tr": "Türkçe", "en": "English", "de": "Deutsch"}

_LANG: ContextVar[str] = ContextVar("etki_lang", default=DEFAULT)


def set_locale(lang: str) -> None:
    _LANG.set(lang if lang in SUPPORTED else DEFAULT)


def get_locale() -> str:
    return _LANG.get()


def t(key: str, lang: str | None = None, /, **params: object) -> str:
    """Translates the key into the active/given language. If missing, falls back
    tr→key, then applies format()."""
    code = lang if lang in SUPPORTED else (lang or _LANG.get())
    if code not in SUPPORTED:
        code = DEFAULT
    entry = MESSAGES.get(key)
    text = key if entry is None else (entry.get(code) or entry.get(DEFAULT) or key)
    return text.format(**params) if params else text


def resolve_locale(request: Request, settings: Settings) -> str:
    """Locale resolution: session['lang'] > etki_lang cookie (survives logout) >
    Accept-Language (first supported) > default."""
    sess = getattr(request, "session", None)
    if sess is not None:
        chosen = sess.get("lang")
        if chosen in SUPPORTED:
            return chosen
    cookie = getattr(request, "cookies", {}).get("etki_lang")
    if cookie in SUPPORTED:
        return cookie
    header = request.headers.get("accept-language", "")
    for part in header.split(","):
        code = part.split(";")[0].strip().split("-")[0].lower()
        if code in SUPPORTED:
            return code
    default = getattr(settings, "default_language", DEFAULT)
    return default if default in SUPPORTED else DEFAULT
