"""Real FileSystem document adapter (DocumentSourceProvider)."""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from pathlib import Path

from etki.core.models import DocumentRef
from etki.core.ports import Capabilities

_MIME = {".md": "text/markdown", ".txt": "text/plain"}


class FileSystemDocumentSourceProvider:
    def __init__(self, root: str | Path, globs: list[str] | None = None) -> None:
        self._root = Path(root)
        self._globs = globs or ["*.md", "*.txt"]

    async def list_documents(self) -> list[DocumentRef]:
        docs: list[DocumentRef] = []
        if not self._root.exists():
            return docs
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            if not any(fnmatch.fnmatch(path.name, g) for g in self._globs):
                continue
            docs.append(
                DocumentRef(
                    id=str(path.relative_to(self._root)),
                    name=path.name,
                    path=str(path),
                    mime=_MIME.get(path.suffix.lower(), "application/octet-stream"),
                    modified_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
                    source="filesystem",
                )
            )
        return docs

    async def fetch_content(self, document_id: str) -> bytes:
        return (self._root / document_id).read_bytes()

    def capabilities(self) -> Capabilities:
        return Capabilities(
            supports_webhooks=False,
            supports_realtime=False,
            supports_effort_tracking=False,
            supports_incremental_diff=False,
        )
