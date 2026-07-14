"""Decision wiki — orchestration over the `WikiStore` port (GraphRAG memory, Faz 1).

The wiki is ALWAYS a projection of the DB (`CaseFileRepository` is the single
source of truth): `rebuild()` regenerates every file from the persisted cases,
so a deleted or hand-edited wiki is never a data loss. Writes happen from one
place only (`ApprovalService.sync_wiki`); this module adds the offline side
(rebuild + search façade for the CLI).
"""

from __future__ import annotations

from etki.adapters.registry import build_wiki_store
from etki.config import Settings
from etki.core.ports import CaseFileRepository, WikiSearchHit, WikiStore
from etki.hitl.ingest import reproject_derived
from etki.persistence.db import build_repository


def _require_wiki(settings: Settings) -> WikiStore:
    wiki = build_wiki_store(settings)
    if wiki is None:
        raise RuntimeError("Wiki kapalı (ETKI_WIKI_DIR boş) — önce etkinleştirin.")
    return wiki


def rebuild_project(
    project_id: str,
    *,
    settings: Settings | None = None,
    repo: CaseFileRepository | None = None,
    wiki: WikiStore | None = None,
) -> int:
    """Regenerates one project's wiki from the DB (projection guarantee),
    including the derived memory (precedents/ + disputed.md). Returns the
    number of decision files written."""
    settings = settings or Settings()
    wiki = wiki or _require_wiki(settings)
    repo = repo or build_repository(settings.db_url)
    cases = repo.list_cases(project_id)
    count = wiki.rebuild(project_id, cases)
    case_ids = {c.request_id for c in cases}
    overrides = [o for o in repo.list_overrides() if o.case_id in case_ids]
    reproject_derived(wiki, project_id, cases, overrides)
    return count


def search(
    project_id: str, query: str, *, limit: int = 10, settings: Settings | None = None
) -> list[WikiSearchHit]:
    return _require_wiki(settings or Settings()).search(project_id, query, limit=limit)


def show(project_id: str, doc_id: str, *, settings: Settings | None = None) -> str | None:
    return _require_wiki(settings or Settings()).read_decision(project_id, doc_id)
