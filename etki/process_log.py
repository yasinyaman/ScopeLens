"""Process log — writes triage + chat interactions to an append-only JSONL file;
later served as Markdown/JSONL for download.

Separate from the audit trail (DB, persistent decision records): this collects
the entire on-screen workflow (request → decision summary → assistant commentary
→ follow-up questions) into one downloadable transcript. The file lives under
`.etki/` (gitignored)."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LOG = Path(".etki/process-log.jsonl")
_LOCK = threading.Lock()  # prevents line interleaving on concurrent appends


def log_event(kind: str, project_id: str, data: dict[str, Any]) -> None:
    """Appends an event (triage|chat) to the log with a timestamp."""
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "kind": kind,
        "project_id": project_id,
        **data,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _LOCK, _LOG.open("a", encoding="utf-8") as fh:
        fh.write(line)


def read_events() -> list[dict[str, Any]]:
    if not _LOG.exists():
        return []
    return [
        json.loads(line)
        for line in _LOG.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def raw_jsonl() -> str:
    return _LOG.read_text(encoding="utf-8") if _LOG.exists() else ""


def render_markdown(events: list[dict[str, Any]]) -> str:
    """Converts events to a human-readable Markdown transcript (for download)."""
    out: list[str] = ["# Etki — Süreç Logu", "", f"Toplam {len(events)} olay.", ""]
    for e in events:
        ts, pid = e.get("ts", ""), e.get("project_id", "")
        if e.get("kind") == "triage":
            out.append(f"## 🔍 Triyaj · {ts} · [{pid}]")
            out.append(f"**Talep:** {e.get('request', '')}")
            if e.get("summary"):
                out.append("\n```\n" + e["summary"] + "\n```")
            if e.get("commentary"):
                out.append(f"\n**Asistan yorumu:**\n\n{e['commentary']}")
        elif e.get("kind") == "chat":
            out.append(f"## 💬 Takip sorusu · {ts} · [{pid}]")
            out.append(f"**Soru:** {e.get('question', '')}\n\n**Yanıt:** {e.get('answer', '')}")
        out.append("\n---\n")
    return "\n".join(out)
