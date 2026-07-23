"""Decision/triage write-back to the request source.

The host COMPOSES the reply text (localized to the project language, same rule
as engine free text) and freezes it into the audit chain; the adapter only
transports it. Every post is best-effort: a channel failure records
``RESPONSE_POSTED ok=false`` and degrades the adapter's health, but NEVER blocks
a PMO approval.

Wiring: ``DecisionResponder.bindings`` is a LIVE dict filled by ``AppContext``
(the ``precedents_by_clause`` idiom) — the singleton ``ApprovalService`` holds a
reference to ``on_decision`` and never imports intake.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from etki import process_log
from etki.core.models import AuditEvent, CaseFile, OutboundResponse
from etki.core.ports import CaseFileRepository, ResponseChannel
from etki.i18n import SUPPORTED
from etki.i18n import t as _t

logger = logging.getLogger(__name__)

RESPONSE_POSTED = "RESPONSE_POSTED"


@dataclass
class ResponderBinding:
    adapter: str
    channel: ResponseChannel
    mode: str  # on_decision | on_triage | both
    language: str  # project language for the composed reply


def _lang(language: str) -> str:
    from etki.config import Settings

    return language if language in SUPPORTED else Settings().default_language


def _unit_label(unit: str, lang: str) -> str:
    return _t("common.hours_short", lang) if unit in ("hour", "hours", "h") else unit


def compose_response(
    case: CaseFile,
    *,
    kind: str,
    language: str,
    public_base_url: str = "",
) -> OutboundResponse:
    """Builds the localized write-back for one case. ``kind`` is "triage" (an
    interim recommendation) or "decision" (the final PMO outcome)."""
    lang = _lang(language)
    lines: list[str] = []
    title_key = "intake.reply_decision_title" if kind == "decision" else "intake.reply_triage_title"
    lines.append(_t(title_key, lang))

    if kind == "decision":
        lines.append(_t(f"intake.reply_outcome_{case.status.value}", lang))

    for d in case.decisions:
        rec = _t(f"decision.{d.decision.value}", lang)
        eff = d.effort_estimate
        effort = _t(
            "intake.reply_effort",
            lang,
            low=f"{eff.low:g}",
            high=f"{eff.high:g}",
            unit=_unit_label(eff.unit, lang),
        )
        lines.append(f"• {rec} — {effort}")
        clauses = d.evidence.contract_clauses_cited
        if clauses:
            lines.append("  " + _t("intake.reply_clauses", lang, clauses=", ".join(clauses)))

    lines.append("")
    lines.append(_t("intake.reply_disclaimer", lang))

    case_url = None
    if public_base_url:
        case_url = f"{public_base_url.rstrip('/')}/ui/casefiles/{case.request_id}"
        lines.append(_t("intake.reply_case_link", lang, url=case_url))

    src = case.source_ref
    extras = {
        "status": case.status.value,
        "decisions": ",".join(d.decision.value for d in case.decisions),
    }
    return OutboundResponse(
        external_id=src.external_id if src else "",
        text="\n".join(lines),
        kind=kind,
        case_id=case.request_id,
        case_url=case_url,
        extras=extras,
    )


class DecisionResponder:
    def __init__(
        self,
        repo: CaseFileRepository,
        *,
        public_base_url: str = "",
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        self._repo = repo
        self._public_base_url = public_base_url
        self._on_error = on_error
        self.bindings: dict[str, ResponderBinding] = {}
        self._pending: set[asyncio.Task[bool]] = set()

    def _binding_for(self, case: CaseFile) -> ResponderBinding | None:
        if case.source_ref is None or case.project_id is None:
            return None
        return self.bindings.get(case.project_id)

    def _already_posted(self, case_id: str, trigger: str) -> bool:
        # Only a SUCCESSFUL post counts: an ok=false audit row used to satisfy
        # this check and make a single write-back failure permanent.
        return any(
            e.action == RESPONSE_POSTED
            and e.detail.get("trigger") == trigger
            and e.detail.get("ok") is True
            for e in self._repo.list_audit(case_id)
        )

    async def drain(self, timeout: float = 20.0) -> None:
        """Awaits in-flight fire-and-forget posts (intake tick / shutdown) so a
        process exit cannot orphan a scheduled write-back."""
        if not self._pending:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*list(self._pending), return_exceptions=True), timeout
            )

    def on_decision(self, case: CaseFile) -> None:
        """Sync hook for ApprovalService.decide — schedules the final write-back
        when the project's mode allows it. Fire-and-forget on the running loop
        (HTTP path); synchronous when there is none (CLI/tests)."""
        binding = self._binding_for(case)
        if binding is None or binding.mode not in ("on_decision", "both"):
            return
        if self._already_posted(case.request_id, "decision"):
            return
        self._schedule(self._post_and_audit(case, binding, kind="decision"))

    async def respond_now(self, case: CaseFile, *, kind: str) -> bool:
        """Await path used by the intake loop (on_triage/both). Returns success;
        never raises — a post failure must not stop the loop."""
        binding = self._binding_for(case)
        if binding is None:
            return False
        if self._already_posted(case.request_id, kind):
            return True
        return await self._post_and_audit(case, binding, kind=kind)

    def _schedule(self, coro: Coroutine[Any, Any, bool]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        task: asyncio.Task[bool] = loop.create_task(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _post_and_audit(
        self, case: CaseFile, binding: ResponderBinding, *, kind: str
    ) -> bool:
        resp = compose_response(
            case,
            kind=kind,
            language=binding.language,
            public_base_url=self._public_base_url,
        )
        ok = True
        error: str | None = None
        try:
            await binding.channel.post_response(resp)
        except Exception as exc:  # noqa: BLE001 — write-back is best-effort
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            logger.warning("geri yazma başarısız: %s (%s)", case.request_id, error)

        pid = case.project_id or "-"
        src = case.source_ref
        detail: dict[str, object] = {
            "trigger": kind,
            "adapter": binding.adapter,
            "external_id": src.external_id if src else "",
            "key": src.key if src else "",
            "mode": binding.mode,
            "ok": ok,
            "text": resp.text[:2000],
        }
        if error:
            detail["error"] = error
        seq = len(self._repo.list_audit(case.request_id))
        self._repo.append_audit(
            AuditEvent(
                case_id=case.request_id,
                seq=seq,
                actor="system",
                action=RESPONSE_POSTED,
                detail=detail,
                at=datetime.now(UTC),
            )
        )
        process_log.log_event(
            "intake_response",
            pid,
            {"request_id": case.request_id, "trigger": kind, "ok": ok, "adapter": binding.adapter},
        )
        if not ok and self._on_error is not None:
            self._on_error(pid, error or "geri yazma hatası")
        return ok
