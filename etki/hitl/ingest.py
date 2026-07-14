"""HITL ingest (GraphRAG Faz 3): PMO feedback → derived wiki memory.

Pushes human corrections back into the long-form memory, closing the loop:

- an **override** (PMO ≠ system) promotes the case to `precedents/` — the
  boundary-case memory future triage should consult;
- **conflicting resolved decisions on the same scope clause** are projected to
  a `disputed.md` page — read it before ruling on that clause again.

No queue and no Celery: writes are file-fast and the whole step is a
PROJECTION of the DB (repo is the single source of truth), so re-processing an
event regenerates the same bytes — idempotency by construction, not by dedup
bookkeeping (the `FeedbackEvent.case_id + revision` key documents intent).
`python -m etki.wiki rebuild` re-derives everything, so this memory is never
a second source of truth either.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from etki.core.enums import PmoDecision
from etki.core.models import CaseFile, FeedbackEvent, Override, TriageDecision
from etki.core.ports import (
    CaseFileRepository,
    DisputedClause,
    DisputedEntry,
    WikiStore,
)

logger = logging.getLogger("etki")


def _resolved_verdict(decision: TriageDecision) -> str | None:
    """The FINAL treatment of a decision once the PMO ruled; None while pending.

    APPROVE confirms the system's call (label = that decision); CONVERT_TO_CR is
    its own outcome; REJECT records that the system's call was refused without
    asserting the right answer — still a conflict signal against an approval."""
    if decision.human_decision is PmoDecision.APPROVE:
        return decision.decision.value
    if decision.human_decision is PmoDecision.CONVERT_TO_CR:
        return "CR"
    if decision.human_decision is PmoDecision.REJECT:
        return f"REJECTED({decision.decision.value})"
    return None


def derive_disputes(cases: list[CaseFile]) -> list[DisputedClause]:
    """Groups RESOLVED decisions by cited clause; ≥2 distinct final treatments of
    the same clause = a dispute. Pure function of the cases (projection input)."""
    by_clause: dict[str, DisputedClause] = {}
    for case in cases:
        for decision in case.decisions:
            verdict = _resolved_verdict(decision)
            if verdict is None:
                continue
            cited = decision.evidence.cited_clauses
            clause_ids = [c.id for c in cited] or decision.evidence.contract_clauses_cited
            for clause_id in clause_ids:
                frozen = next((c for c in cited if c.id == clause_id), None)
                entry = DisputedEntry(
                    case_id=case.request_id, verdict=verdict, at=decision.decided_at
                )
                slot = by_clause.setdefault(
                    clause_id,
                    DisputedClause(
                        clause_id=clause_id,
                        clause_ref=(frozen.source_clause or "") if frozen else "",
                        description=frozen.description if frozen else "",
                    ),
                )
                slot.entries.append(entry)
    disputes = [
        d for d in by_clause.values() if len({e.verdict for e in d.entries}) >= 2
    ]
    for d in disputes:
        d.entries.sort(key=lambda e: (str(e.at or ""), e.case_id))
    return disputes


def precedents_by_clause(
    cases: list[CaseFile], overrides: list[Override]
) -> dict[str, dict]:
    """Clause-keyed summary of the human-correction memory (pure function).

    Value: {"count": overrides touching the clause, "last": "SYS→HUMAN" of the
    most recent one, "disputed": clause appears in derive_disputes, "ref": the
    human-readable clause ref}. Each summary is inserted under BOTH the frozen
    clause id and its source_clause (aliased to the SAME dict object): the UI
    panel looks up by id, the engine by `source_clause or id` — one lookup, no
    translation layer between them.
    """
    by_case: dict[str, list[Override]] = defaultdict(list)
    for o in overrides:
        by_case[o.case_id].append(o)
    disputed_ids = {d.clause_id for d in derive_disputes(cases)}

    out: dict[str, dict] = {}
    for case in cases:
        case_overrides = by_case.get(case.request_id)
        for i, decision in enumerate(case.decisions):
            cited = decision.evidence.cited_clauses
            clause_ids = [c.id for c in cited] or decision.evidence.contract_clauses_cited
            for clause_id in clause_ids:
                frozen = next((c for c in cited if c.id == clause_id), None)
                ref = (frozen.source_clause or "") if frozen else ""
                slot = out.get(clause_id)
                if slot is None:
                    slot = {"count": 0, "last": "", "disputed": clause_id in disputed_ids,
                            "ref": ref}
                    out[clause_id] = slot
                    if ref:
                        out.setdefault(ref, slot)  # alias — same dict object
                elif ref and not slot["ref"]:
                    slot["ref"] = ref
                    out.setdefault(ref, slot)
                for o in sorted(case_overrides or [], key=lambda o: str(o.at or "")):
                    if o.decision_index == i:
                        slot["count"] += 1
                        slot["last"] = f"{o.system_decision.value}→{o.human_decision.value}"
    # Drop clauses with neither precedent nor dispute — the memory only speaks
    # when it has something to say.
    return {k: v for k, v in out.items() if v["count"] or v["disputed"]}


def reproject_derived(
    wiki: WikiStore, project_id: str, cases: list[CaseFile], overrides: list[Override]
) -> None:
    """Regenerates ALL derived pages (precedents + disputed) for a project —
    shared by the live ingest and `python -m etki.wiki rebuild`."""
    scoped = [c for c in cases if (c.project_id or "default") == project_id]
    by_case: dict[str, list[Override]] = defaultdict(list)
    for o in overrides:
        by_case[o.case_id].append(o)
    for case in scoped:
        if by_case.get(case.request_id):
            wiki.write_precedent(case, by_case[case.request_id])
    wiki.write_disputed(project_id, derive_disputes(scoped))


class WikiIngest:
    """`IngestPort` over the wiki store: one PMO feedback event → the project's
    derived memory is re-projected from the DB."""

    def __init__(self, repo: CaseFileRepository, wiki: WikiStore) -> None:
        self._repo = repo
        self._wiki = wiki

    def ingest(self, event: FeedbackEvent) -> bool:
        case = self._repo.get_case(event.case_id)
        if case is None:
            return False
        project_id = case.project_id or "default"
        cases = self._repo.list_cases(project_id)
        case_ids = {c.request_id for c in cases}
        overrides = [o for o in self._repo.list_overrides() if o.case_id in case_ids]
        reproject_derived(self._wiki, project_id, cases, overrides)
        return True
