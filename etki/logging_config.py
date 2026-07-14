"""Central logging configuration — set up once at startup (lifespan).

Structured (timestamp + level + logger + message) uniform format; the level comes
from Settings.log_level. Set up at application startup, NOT inside the cached
get_context, so it is not reconfigured on every request.
"""

from __future__ import annotations

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_configured = False


def configure_logging(level: str = "INFO") -> None:
    global _configured
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Prevents handler duplication on re-setup (e.g. uvicorn reload).
    if not _configured:
        root.handlers = [handler]
        _configured = True
    logging.getLogger("etki").setLevel(level.upper())
