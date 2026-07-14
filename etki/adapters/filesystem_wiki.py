"""File-system decision wiki — the `WikiStore` port's default adapter.

Layout (per project, mirrors the `index-{id}.json` convention):

    .etki/wiki-{project_id}/
    ├── index.md                     # generated table of contents + stats
    ├── decisions/DEC-{yyyymmdd}-{slug}.md   # one case = one file (projection)
    └── entities/
        ├── contracts/{contract_id}.md       # backlinks: which decisions cited it
        └── modules/{module}.md              # backlinks: which decisions touched it

Every file is a PROJECTION of the DB (`CaseFileRepository`): regenerable via
`rebuild()`, overwritten on re-write (idempotent), never hand-edited. Frontmatter
is plain YAML written/parsed with PyYAML — no extra dependency.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import yaml

from etki.core.models import CaseFile, Override
from etki.core.ports import DisputedClause, WikiSearchHit
from etki.core.text import hits as token_hits
from etki.core.text import score, tokenize
from etki.i18n import t

logger = logging.getLogger("etki")

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
_SLUG = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[m.end() :]


class FileSystemWikiAdapter:
    """Markdown + YAML-frontmatter wiki on the local file system.

    Search prefers ripgrep (`rg`) when present and falls back to a pure-Python
    scan — the wiki stays dependency-free either way (graceful degradation,
    same rule as the other adapters)."""

    def __init__(
        self,
        root_template: str = ".etki/wiki-{id}",
        languages: dict[str, str] | None = None,
    ) -> None:
        self._root_template = root_template
        # Per-project heading language (project → tr/en/de; default tr). Note:
        # `rebuild` regenerates headings in the CURRENT config language — the
        # wiki is a projection, not an archive, so that is correct behavior.
        self._languages = languages or {}

    def _lang(self, project_id: str) -> str:
        return self._languages.get(project_id, "tr")

    # ------------------------------------------------------------------ paths

    def _root(self, project_id: str) -> Path:
        return Path(self._root_template.format(id=project_id))

    def _decisions_dir(self, project_id: str) -> Path:
        return self._root(project_id) / "decisions"

    @staticmethod
    def doc_id_for(case: CaseFile) -> str:
        stamp = case.created_at.strftime("%Y%m%d") if case.created_at else "00000000"
        return f"DEC-{stamp}-{_slug(case.request_id)}"

    # ------------------------------------------------------------ write side

    def write_decision(self, case: CaseFile) -> str:
        """Projects one case into `decisions/` and refreshes the generated pages
        (index.md + entity backlinks). Overwrite = idempotent; a re-write after a
        PMO decision keeps the wiki in sync with the DB."""
        project_id = case.project_id or "default"
        doc_id = self.doc_id_for(case)
        target = self._decisions_dir(project_id) / f"{doc_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_decision(doc_id, case), encoding="utf-8")
        self._regenerate(project_id)
        return doc_id

    def rebuild(self, project_id: str, cases: list[CaseFile]) -> int:
        """Wipes the project wiki and regenerates it from the DB's cases — the
        projection guarantee (`python -m etki.wiki rebuild`)."""
        root = self._root(project_id)
        if root.exists():
            shutil.rmtree(root)
        count = 0
        for case in cases:
            if (case.project_id or "default") != project_id:
                continue
            doc_id = self.doc_id_for(case)
            target = self._decisions_dir(project_id) / f"{doc_id}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self._render_decision(doc_id, case), encoding="utf-8")
            count += 1
        self._regenerate(project_id)
        return count

    def write_precedent(self, case: CaseFile, overrides: list[Override]) -> str:
        """Boundary-case memory: an overridden case is promoted to `precedents/`.
        Pure projection of case + override records → overwrite-idempotent."""
        project_id = case.project_id or "default"
        doc_id = f"PRE-{_slug(case.request_id)}"
        target = self._root(project_id) / "precedents" / f"{doc_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_precedent(doc_id, case, overrides), encoding="utf-8")
        self._regenerate(project_id)
        return doc_id

    def write_disputed(self, project_id: str, disputes: list[DisputedClause]) -> None:
        """`disputed.md` is regenerated whole on every call (projection); an empty
        conflict list removes the page."""
        target = self._root(project_id) / "disputed.md"
        if not disputes:
            target.unlink(missing_ok=True)
            self._regenerate(project_id)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_disputed(project_id, disputes), encoding="utf-8")
        self._regenerate(project_id)

    # ------------------------------------------------------------- read side

    def read_decision(self, project_id: str, doc_id: str) -> str | None:
        path = self._decisions_dir(project_id) / f"{doc_id}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def get_entity_page(self, project_id: str, kind: str, name: str) -> str | None:
        path = self._root(project_id) / "entities" / kind / f"{_slug(name)}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def list_decisions(self, project_id: str) -> list[dict]:
        """Frontmatter metas of every decision file, newest first (for the UI)."""
        return self._all_decision_meta(project_id)

    def search(self, project_id: str, query: str, *, limit: int = 10) -> list[WikiSearchHit]:
        """Token-AND matching with the engine's own tokenizer (`core/text`):
        stopword-aware, prefix/synonym-tolerant ("ödemeler" finds "ödeme").
        Every meaningful query token must match; ranked by the symmetric score."""
        root = self._root(project_id)
        q = tokenize(query)
        if not q or not root.exists():
            return []
        results: list[WikiSearchHit] = []
        for path in self._candidate_files(root, query):
            text = path.read_text(encoding="utf-8")
            target = tokenize(text)
            if token_hits(q, target) < len(q):  # AND semantics, tolerance included
                continue
            meta, body = _split_frontmatter(text)
            snippet = next(
                (ln.strip() for ln in body.splitlines()
                 if ln.strip() and token_hits(q, tokenize(ln)) > 0),
                "",
            )
            title = next(
                (ln.lstrip("# ").strip() for ln in body.splitlines() if ln.startswith("#")), ""
            )
            results.append(
                WikiSearchHit(
                    doc_id=str(meta.get("doc_id") or path.stem),
                    path=str(path),
                    title=title,
                    snippet=snippet[:200],
                    score=round(score(q, target), 4),
                )
            )
        results.sort(key=lambda h: (-h.score, h.doc_id))
        return results[:limit]

    def _candidate_files(self, root: Path, query: str) -> list[Path]:
        """rg fast path: intersect `--files-with-matches` per token PREFIX (first
        5 chars — a superset, so the prefix-tolerant Python scoring still decides).
        Empty intersection or rg missing/failing → every markdown file (synonym
        canons may not share a raw prefix; correctness beats the shortcut)."""
        all_files = sorted(root.rglob("*.md"))
        raw_tokens = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        rg = shutil.which("rg")
        if rg is None or not raw_tokens:
            return all_files
        try:
            candidates: set[Path] | None = None
            for token in raw_tokens:
                out = subprocess.run(
                    [rg, "-l", "-i", "-F", token[:5], str(root)],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                found = {Path(p) for p in out.stdout.splitlines() if p.endswith(".md")}
                candidates = found if candidates is None else candidates & found
            return sorted(candidates) if candidates else all_files
        except (OSError, subprocess.SubprocessError):
            return all_files

    # ------------------------------------------------------------- rendering

    def _render_decision(self, doc_id: str, case: CaseFile) -> str:
        cited = [c for d in case.decisions for c in d.evidence.cited_clauses]
        meta = {
            "doc_id": doc_id,
            "case_id": case.request_id,
            "project_id": case.project_id or "default",
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "status": case.status.value,
            "verdicts": [d.decision.value for d in case.decisions],
            "confidence": [round(d.confidence, 2) for d in case.decisions],
            "scope_refs": sorted(
                {r for d in case.decisions for r in d.evidence.contract_clauses_cited}
            ),
            "modules": sorted({m for d in case.decisions for m in d.evidence.impacted_modules}),
            "contract_id": cited[0].contract_id if cited else None,
            "model_version": case.decisions[0].model_version if case.decisions else None,
            "index_freshness": case.decisions[0].index_freshness if case.decisions else None,
        }
        lang = self._lang(case.project_id or "default")
        lines = [
            "---",
            yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip(),
            "---",
            "",
            f"# {doc_id}",
            "",
            *[f"> {ln}" for ln in t("wiki.autogen_case", lang).splitlines()],
            "",
            f"## {t('wiki.request', lang)}",
            "",
        ]
        lines += [f"> {ln}" for ln in (case.raw_request or "").strip().splitlines() or [""]]
        for i, d in enumerate(case.decisions):
            ev = d.evidence
            heading = t(
                "wiki.decision_heading", lang,
                n=i + 1, decision=d.decision.value, conf=f"{d.confidence:.2f}",
            )
            lines += [
                "",
                f"## {heading}",
                "",
                f"- **{t('wiki.pmo_decision', lang)}:** {d.human_decision.value}",
                f"- **{t('wiki.reasoning', lang)}:** {ev.reasoning or '—'}",
            ]
            if ev.cited_clauses:
                lines.append(f"- **{t('wiki.cited', lang)}:**")
                lines += [
                    f"  - `{c.source_clause or c.id}` [{c.polarity.value}] {c.description}"
                    for c in ev.cited_clauses
                ]
            elif ev.contract_clauses_cited:
                cited_refs = ", ".join(ev.contract_clauses_cited)
                lines.append(f"- **{t('wiki.cited', lang)}:** {cited_refs}")
            if ev.impacted_modules:
                lines.append(
                    f"- **{t('wiki.impacted', lang)}:** {', '.join(ev.impacted_modules)}"
                )
            est = d.effort_estimate
            lines.append(
                f"- **{t('wiki.effort', lang)}:** {est.low:g}–{est.high:g} {est.unit}"
                + (f" — {est.basis}" if est.basis else "")
            )
            lines.append(
                f"- **{t('wiki.risk', lang)}:** {d.risk.level.value}"
                + (f" — {d.risk.basis}" if d.risk.basis else "")
            )
            if ev.assumptions:
                lines.append(f"- **{t('wiki.assumptions', lang)}:**")
                lines += [f"  - {a}" for a in ev.assumptions]
            if d.cr_draft is not None and d.cr_draft.impact_analysis:
                lines += ["", f"### {t('wiki.cr_draft', lang)}", "", d.cr_draft.impact_analysis]
        if case.pre_analysis:
            lines += ["", f"## {t('wiki.pre_analysis', lang)}", "", case.pre_analysis.strip()]
        return "\n".join(lines) + "\n"

    def _render_precedent(self, doc_id: str, case: CaseFile, overrides: list[Override]) -> str:
        dec_id = self.doc_id_for(case)
        meta = {
            "doc_id": doc_id,
            "case_id": case.request_id,
            "project_id": case.project_id or "default",
            "decision_doc": dec_id,
            "overrides": [
                {
                    "index": o.decision_index,
                    "system": o.system_decision.value,
                    "human": o.human_decision.value,
                    "actor": o.actor,
                    "at": o.at.isoformat() if o.at else None,
                }
                for o in sorted(overrides, key=lambda o: (o.decision_index, str(o.at or "")))
            ],
        }
        lang = self._lang(case.project_id or "default")
        lines = [
            "---",
            yaml.safe_dump(meta, allow_unicode=True, sort_keys=False).rstrip(),
            "---",
            "",
            f"# {doc_id} — {t('wiki.precedent_title', lang)}",
            "",
            *[f"> {ln}" for ln in t("wiki.autogen_override", lang).splitlines()],
            "",
            f"## {t('wiki.request', lang)}",
            "",
        ]
        lines += [f"> {ln}" for ln in (case.raw_request or "").strip().splitlines() or [""]]
        lines += ["", f"## {t('wiki.why_precedent', lang)}", ""]
        for o in sorted(overrides, key=lambda o: (o.decision_index, str(o.at or ""))):
            when = f", {o.at.date().isoformat()}" if o.at else ""
            lines.append(
                "- " + t(
                    "wiki.override_line", lang,
                    n=o.decision_index + 1, sys=o.system_decision.value,
                    human=o.human_decision.value, who=f"{o.actor}{when}",
                )
            )
        lines += ["", f"{t('wiki.decision_file', lang)}: [{dec_id}](../decisions/{dec_id}.md)"]
        return "\n".join(lines) + "\n"

    def _render_disputed(self, project_id: str, disputes: list[DisputedClause]) -> str:
        lang = self._lang(project_id)
        lines = [
            f"# {t('wiki.disputed_title', lang)} — {project_id}",
            "",
            *[f"> {ln}" for ln in t("wiki.disputed_note", lang).splitlines()],
            "",
        ]
        for d in sorted(disputes, key=lambda d: d.clause_id):
            ref = f" ({d.clause_ref})" if d.clause_ref else ""
            lines.append(f"## {d.clause_id}{ref}")
            if d.description:
                lines += ["", f"> {d.description}", ""]
            for e in d.entries:
                when = f", {e.at.date().isoformat()}" if e.at else ""
                lines.append(f"- `{e.case_id}` → **{e.verdict}**{when}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    # ---------------------------------------------------- generated pages

    def _regenerate(self, project_id: str) -> None:
        """Rebuilds index.md + entity backlink pages from the decision files'
        frontmatter (cheap: a wiki holds hundreds of small files, not millions)."""
        metas = self._all_decision_meta(project_id)
        self._write_index(project_id, metas)
        self._write_entities(project_id, metas)

    def _all_decision_meta(self, project_id: str) -> list[dict]:
        d = self._decisions_dir(project_id)
        metas = []
        for path in sorted(d.glob("DEC-*.md")) if d.exists() else []:
            meta, _ = _split_frontmatter(path.read_text(encoding="utf-8"))
            if meta.get("doc_id"):
                metas.append(meta)
        metas.sort(key=lambda m: str(m.get("created_at") or ""), reverse=True)
        return metas

    def _write_index(self, project_id: str, metas: list[dict]) -> None:
        lang = self._lang(project_id)
        verdicts = Counter(v for m in metas for v in m.get("verdicts", []))
        root = self._root(project_id)
        precedents = sorted(p.stem for p in (root / "precedents").glob("PRE-*.md"))
        lines = [
            f"# {t('wiki.index_title', lang)} — {project_id}",
            "",
            f"> {t('wiki.index_autogen', lang)}",
            "",
            f"- {t('wiki.total', lang)}: **{len(metas)}**",
            f"- {t('wiki.dist', lang)}: "
            + (", ".join(f"{k}: {v}" for k, v in sorted(verdicts.items())) or "—"),
            f"- {t('wiki.precedent_files', lang)}: **{len(precedents)}**"
            + (" — " + ", ".join(f"[{p}](precedents/{p}.md)" for p in precedents)
               if precedents else ""),
        ]
        if (root / "disputed.md").exists():
            lines.append(f"- {t('wiki.disputed_link', lang)}")
        lines += [
            "",
            f"## {t('wiki.recent', lang)}",
            "",
        ]
        for m in metas[:10]:
            lines.append(
                f"- [{m['doc_id']}](decisions/{m['doc_id']}.md) — "
                f"{'/'.join(m.get('verdicts', []))} ({m.get('status', '')}, "
                f"{str(m.get('created_at') or '')[:10]})"
            )
        root = self._root(project_id)
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_entities(self, project_id: str, metas: list[dict]) -> None:
        by_module: dict[str, list[dict]] = {}
        by_contract: dict[str, list[dict]] = {}
        for m in metas:
            for mod in m.get("modules", []):
                by_module.setdefault(mod, []).append(m)
            if m.get("contract_id"):
                by_contract.setdefault(str(m["contract_id"]), []).append(m)
        lang = self._lang(project_id)
        ent = self._root(project_id) / "entities"
        for kind, groups, label in (
            ("modules", by_module, t("wiki.module_backlinks", lang)),
            ("contracts", by_contract, t("wiki.contract_backlinks", lang)),
        ):
            target_dir = ent / kind
            if target_dir.exists():
                shutil.rmtree(target_dir)  # stale backlink pages must not survive
            for name, group in groups.items():
                target_dir.mkdir(parents=True, exist_ok=True)
                lines = [f"# {name}", "", f"`{name}` {label}:", ""]
                lines += [
                    f"- [{g['doc_id']}](../../decisions/{g['doc_id']}.md) — "
                    f"{'/'.join(g.get('verdicts', []))}"
                    for g in group
                ]
                (target_dir / f"{_slug(name)}.md").write_text(
                    "\n".join(lines) + "\n", encoding="utf-8"
                )
