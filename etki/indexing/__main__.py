"""Offline (re)indexing CLI: `python -m etki.indexing [project_id]`.

Indexes all projects with no argument, or a single project with one. Each project is written
to its own `.etki/index-{id}.json` from its own contract + codebase + work-item tracking.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from etki.api.context import index_project
from etki.config import Settings, load_projects
from etki.core.enums import Polarity


async def run(target: str | None = None) -> None:
    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    projects = load_projects(settings.projects_path, settings.connectors_path)

    for project in projects:
        if target and project.id != target:
            continue
        # The SAME path as the UI's _reindex (context.index_project): doc_root composite,
        # multi-repo merged graph, DB baseline reconcile. The CLI's raw-connectors copy
        # drifted once (warp: fake document/code repo + risk of overwriting approved
        # CRs) — there must remain a single indexing path.
        index = await index_project(project, settings)
        excluded = sum(1 for s in index.baseline.scope_items if s.polarity is Polarity.EXCLUDED)
        print(
            f"[{project.id}] {len(index.modules)} modül | "
            f"{len(index.baseline.scope_items)} madde ({excluded} EXCLUDED) "
            f"→ {project.resolved_index_path()}"
        )


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run(target))


if __name__ == "__main__":
    main()
