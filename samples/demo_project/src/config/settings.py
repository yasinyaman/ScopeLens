"""Uygulama yapılandırması."""

DEFAULTS = {"session_ttl": 3600, "max_reports": 5, "max_sessions": 3}


def get(key: str) -> int | None:
    return DEFAULTS.get(key)
