"""Human-in-the-loop approval flow (HITL) + audit trail (Epic K + M).

"Copilot, not autopilot": the system recommends, the PMO decides. Every action
produces an auditable event; a PMO overriding the system's recommendation is
recorded as an override (over-reliance signal); a CR approval extends the baseline
by version+1 (living baseline). Decisions also flow back into the derived wiki
memory (precedents/disputed) through the optional IngestPort — best-effort,
never blocking the approval itself.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from etki.core.enums import Decision, PmoDecision
from etki.core.models import (
    AuditEvent,
    Baseline,
    CaseFile,
    FeedbackEvent,
    Override,
    ScopeItem,
)
from etki.core.ports import CaseFileRepository, IngestPort, WikiStore

logger = logging.getLogger("etki")

_TERMINAL = {PmoDecision.APPROVE, PmoDecision.REJECT, PmoDecision.CONVERT_TO_CR}


class AlreadyDecidedError(ValueError):
    """A second PMO ruling on an already-terminal decision. Without this guard a
    duplicate CONVERT_TO_CR double-bumped the living baseline and a late REJECT
    silently rewrote history (the audit trail showed both, the case only one)."""


@dataclass
class ApprovalResult:
    case: CaseFile
    new_baseline_version: int | None = None
    new_scope_item: ScopeItem | None = None


class ApprovalService:
    def __init__(
        self,
        repo: CaseFileRepository,
        wiki: WikiStore | None = None,
        ingest: IngestPort | None = None,
        on_decided: Callable[[CaseFile], None] | None = None,
    ) -> None:
        self._repo = repo
        self._wiki = wiki
        self._ingest = ingest
        # Called once a case reaches a terminal status (intake write-back hook).
        # Best-effort like sync_wiki/ingest — never blocks the approval.
        self._on_decided = on_decided

    def sync_wiki(self, case: CaseFile) -> None:
        """Re-projects the case into the decision wiki, best-effort: the wiki is a
        DB projection (single writer = this service); a wiki failure must never
        break triage or approval."""
        if self._wiki is None:
            return
        try:
            self._wiki.write_decision(case)
        except Exception:  # noqa: BLE001 — projection only; the DB record is already safe
            logger.warning("wiki projeksiyonu yazılamadı: %s", case.request_id, exc_info=True)

    def record_triage(self, case: CaseFile) -> None:
        """Persists the triage output and writes the first event to the audit chain."""
        self._repo.save_case(case)
        self._repo.append_audit(
            AuditEvent(
                case_id=case.request_id,
                seq=0,
                actor="system",
                action="TRIAGED",
                detail={
                    "decisions": [
                        {
                            "decision": d.decision.value,
                            "confidence": d.confidence,
                            "model_version": d.model_version,
                            "index_freshness": d.index_freshness,
                            "plugin_set": d.plugin_set,
                            "clauses": d.evidence.contract_clauses_cited,
                            "impacted": d.evidence.impacted_modules,
                        }
                        for d in case.decisions
                    ]
                },
                at=case.created_at or datetime.now(UTC),
            )
        )
        self.sync_wiki(case)

    def decide(
        self,
        case_id: str,
        decision_index: int,
        action: PmoDecision,
        *,
        actor: str,
        current_baseline: Baseline,
        override_decision: Decision | None = None,
    ) -> ApprovalResult:
        case = self._repo.get_case(case_id)
        if case is None:
            raise KeyError(f"Case file bulunamadı: {case_id}")
        if not 0 <= decision_index < len(case.decisions):
            raise IndexError(f"Geçersiz karar indeksi: {decision_index}")

        decision = case.decisions[decision_index]
        if decision.human_decision is not PmoDecision.PENDING:
            raise AlreadyDecidedError(
                f"Karar zaten sonuçlandırılmış: {case_id}#{decision_index} "
                f"({decision.human_decision.value})"
            )
        system_decision = decision.decision
        now = datetime.now(UTC)

        # Override (over-reliance signal): the PMO is changing the system's recommendation.
        if override_decision is not None and override_decision != system_decision:
            self._repo.record_override(
                Override(
                    case_id=case_id,
                    decision_index=decision_index,
                    system_decision=system_decision,
                    human_decision=override_decision,
                    actor=actor,
                    at=now,
                )
            )
            self._audit(case_id, actor, "OVERRIDE", {
                "index": decision_index,
                "system": system_decision.value,
                "human": override_decision.value,
            }, now)

        decision.human_decision = action
        if action in _TERMINAL:
            # Freeze the PMO ruling time (the engine stamped triage time at creation).
            decision.decided_at = now
        self._audit(case_id, actor, action.value, {
            "index": decision_index,
            "system": system_decision.value,
        }, now)

        result = ApprovalResult(case=case)

        # CR approval → baseline version+1 (living baseline).
        if action is PmoDecision.CONVERT_TO_CR:
            item = ScopeItem(
                id=f"CR-{case_id}-{decision_index}",
                contract_id=current_baseline.contract_id,
                description=f"(CR onayı) {decision.evidence.reasoning or case.raw_request}",
                category="cr",
                source_clause=f"CR-{case_id}",
            )
            new_baseline = current_baseline.model_copy(deep=True)
            new_baseline.scope_items.append(item)
            new_baseline.version += 1
            new_baseline.locked_at = now
            self._repo.save_baseline_version(new_baseline, source_case_id=case_id)
            self._audit(case_id, actor, "BASELINE_BUMP", {
                "version": new_baseline.version,
                "scope_item": item.id,
            }, now)
            result.new_baseline_version = new_baseline.version
            result.new_scope_item = item

        # Case status: the summary status once all decisions have been resolved.
        case.status = _case_status(case)
        decided = case.status in _TERMINAL
        self._repo.save_case(case)
        self._repo.set_status(case_id, case.status, now if decided else None)
        self.sync_wiki(case)  # PMO decision changed → keep the wiki projection in sync
        # HITL ingest (best-effort, idempotent): overrides promote the case to
        # precedents/, clause conflicts re-project disputed.md. Never blocks approval.
        if self._ingest is not None:
            try:
                self._ingest.ingest(
                    FeedbackEvent(
                        case_id=case_id,
                        decision_index=decision_index,
                        action=action,
                        system_decision=system_decision,
                        override=override_decision,
                        actor=actor,
                        revision=len(self._repo.list_audit(case_id)),
                        at=now,
                    )
                )
            except Exception:  # noqa: BLE001 — derived memory only; the DB record is safe
                logger.warning("HITL ingest başarısız: %s", case_id, exc_info=True)
        # Intake write-back (best-effort): only when the case just reached a
        # terminal status. Never blocks the approval.
        if self._on_decided is not None and decided:
            try:
                self._on_decided(case)
            except Exception:  # noqa: BLE001 — write-back is best-effort
                logger.warning("intake yanıtı tetiklenemedi: %s", case_id, exc_info=True)
        return result

    def _audit(self, case_id: str, actor: str, action: str, detail: dict, at: datetime) -> None:
        seq = len(self._repo.list_audit(case_id))
        self._repo.append_audit(
            AuditEvent(case_id=case_id, seq=seq, actor=actor, action=action, detail=detail, at=at)
        )


def _case_status(case: CaseFile) -> PmoDecision:
    actions = [d.human_decision for d in case.decisions]
    if any(a is PmoDecision.PENDING for a in actions):
        return PmoDecision.PENDING
    if any(a is PmoDecision.CONVERT_TO_CR for a in actions):
        return PmoDecision.CONVERT_TO_CR
    if all(a is PmoDecision.APPROVE for a in actions):
        return PmoDecision.APPROVE
    return PmoDecision.REJECT
