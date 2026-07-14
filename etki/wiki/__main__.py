"""Decision-wiki CLI: `python -m etki.wiki <search|show|rebuild> …`.

    python -m etki.wiki search "SSO entegrasyonu" [--project demo] [--limit 10]
    python -m etki.wiki show DEC-20260709-req-demo-1a2b3c4d [--project demo]
    python -m etki.wiki rebuild [project_id]        # no argument → every project
"""

from __future__ import annotations

import argparse
import logging
import sys

from etki.config import Settings, load_projects
from etki.wiki import rebuild_project, search, show


def _default_project(settings: Settings) -> str:
    return load_projects(settings.projects_path, settings.connectors_path)[0].id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m etki.wiki", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="karar wiki'sinde ara (token AND eşleşmesi)")
    p_search.add_argument("query")
    p_search.add_argument("--project", default=None)
    p_search.add_argument("--limit", type=int, default=10)

    p_show = sub.add_parser("show", help="bir karar dosyasını görüntüle")
    p_show.add_argument("doc_id")
    p_show.add_argument("--project", default=None)

    p_rebuild = sub.add_parser("rebuild", help="wiki'yi DB'den yeniden üret (projeksiyon)")
    p_rebuild.add_argument("project_id", nargs="?", default=None)

    args = parser.parse_args(argv)
    settings = Settings()
    logging.basicConfig(level=settings.log_level)

    if args.command == "rebuild":
        targets = (
            [args.project_id]
            if args.project_id
            else [p.id for p in load_projects(settings.projects_path, settings.connectors_path)]
        )
        for pid in targets:
            count = rebuild_project(pid, settings=settings)
            print(f"[{pid}] {count} karar dosyası yeniden üretildi")
        return 0

    project = args.project or _default_project(settings)
    if args.command == "search":
        hits = search(project, args.query, limit=args.limit, settings=settings)
        if not hits:
            print("Eşleşme yok.")
            return 1
        for h in hits:
            print(f"{h.doc_id}  (skor {h.score:g})")
            if h.snippet:
                print(f"    {h.snippet}")
        return 0

    # show
    content = show(project, args.doc_id, settings=settings)
    if content is None:
        print(f"Bulunamadı: {args.doc_id} (proje: {project})", file=sys.stderr)
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
