"""SQLAlchemy-based CaseFileRepository (implements the CaseFileRepository port)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from etki.core.enums import Decision, PmoDecision
from etki.core.models import AuditEvent, Baseline, CaseFile, Override
from etki.persistence.models import (
    AuditEventRow,
    BaselineVersionRow,
    CaseFileRow,
    OverrideRow,
)

# Cap on ids per IN (…) clause in list_audit_many — well under SQLite's
# pre-3.32 999-parameter limit; Postgres allows far more. Larger id sets are
# chunked, which is byte-identical (their union is the full set).
_AUDIT_IN_CHUNK = 500


def _jsonable(model: object) -> dict:
    return json.loads(model.model_dump_json())  # type: ignore[attr-defined]


class SqlCaseFileRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def save_case(self, case: CaseFile) -> None:
        with self._sf() as session:
            row = session.get(CaseFileRow, case.request_id)
            if row is None:
                row = CaseFileRow(request_id=case.request_id)
                session.add(row)
            row.project_id = case.project_id
            row.status = case.status.value
            row.raw_request = case.raw_request
            row.created_at = case.created_at
            row.payload = _jsonable(case)
            session.commit()

    def get_case(self, request_id: str) -> CaseFile | None:
        with self._sf() as session:
            row = session.get(CaseFileRow, request_id)
            return CaseFile.model_validate(row.payload) if row else None

    def list_cases(self, project_id: str | None = None) -> list[CaseFile]:
        with self._sf() as session:
            stmt = select(CaseFileRow)
            if project_id is not None:
                stmt = stmt.where(CaseFileRow.project_id == project_id)
            rows = session.scalars(stmt).all()
            return [CaseFile.model_validate(r.payload) for r in rows]

    def set_status(
        self, request_id: str, status: PmoDecision, decided_at: datetime | None
    ) -> None:
        with self._sf() as session:
            row = session.get(CaseFileRow, request_id)
            if row is None:
                return
            row.status = status.value
            row.decided_at = decided_at
            payload = dict(row.payload)
            payload["status"] = status.value
            row.payload = payload
            session.commit()

    def append_audit(self, event: AuditEvent) -> None:
        with self._sf() as session:
            session.add(
                AuditEventRow(
                    case_id=event.case_id,
                    seq=event.seq,
                    actor=event.actor,
                    action=event.action,
                    detail=event.detail,
                    at=event.at,
                )
            )
            session.commit()

    def list_audit(self, case_id: str) -> list[AuditEvent]:
        with self._sf() as session:
            rows = session.scalars(
                select(AuditEventRow).where(AuditEventRow.case_id == case_id).order_by(
                    AuditEventRow.seq
                )
            ).all()
            return [
                AuditEvent(
                    case_id=r.case_id, seq=r.seq, actor=r.actor, action=r.action,
                    detail=r.detail, at=r.at,
                )
                for r in rows
            ]

    def list_audit_many(self, case_ids: Iterable[str]) -> dict[str, list[AuditEvent]]:
        # One SELECT (chunked to stay under the backend's bound-parameter cap:
        # SQLite pre-3.32 = 999, Postgres ~65535) instead of a query per case.
        # Each case id appears in exactly one chunk, so ORDER BY seq keeps every
        # case's events in the same ascending order list_audit returns.
        ids = list(dict.fromkeys(case_ids))
        result: dict[str, list[AuditEvent]] = {}
        if not ids:
            return result
        with self._sf() as session:
            for start in range(0, len(ids), _AUDIT_IN_CHUNK):
                rows = session.scalars(
                    select(AuditEventRow)
                    .where(AuditEventRow.case_id.in_(ids[start : start + _AUDIT_IN_CHUNK]))
                    .order_by(AuditEventRow.seq)
                ).all()
                for r in rows:
                    result.setdefault(r.case_id, []).append(
                        AuditEvent(
                            case_id=r.case_id, seq=r.seq, actor=r.actor, action=r.action,
                            detail=r.detail, at=r.at,
                        )
                    )
        return result

    def record_override(self, override: Override) -> None:
        with self._sf() as session:
            session.add(
                OverrideRow(
                    case_id=override.case_id,
                    decision_index=override.decision_index,
                    system_decision=override.system_decision.value,
                    human_decision=override.human_decision.value,
                    actor=override.actor,
                    at=override.at,
                )
            )
            session.commit()

    def list_overrides(self) -> list[Override]:
        with self._sf() as session:
            rows = session.scalars(select(OverrideRow)).all()
            return [
                Override(
                    case_id=r.case_id,
                    decision_index=r.decision_index,
                    system_decision=Decision(r.system_decision),
                    human_decision=Decision(r.human_decision),
                    actor=r.actor,
                    at=r.at,
                )
                for r in rows
            ]

    def save_baseline_version(self, baseline: Baseline, source_case_id: str | None) -> None:
        with self._sf() as session:
            session.add(
                BaselineVersionRow(
                    contract_id=baseline.contract_id,
                    version=baseline.version,
                    payload=_jsonable(baseline),
                    source_case_id=source_case_id,
                    created_at=baseline.locked_at,
                )
            )
            session.commit()

    def latest_baseline(self, contract_id: str) -> Baseline | None:
        with self._sf() as session:
            row = session.scalars(
                select(BaselineVersionRow)
                .where(BaselineVersionRow.contract_id == contract_id)
                .order_by(BaselineVersionRow.version.desc())
            ).first()
            return Baseline.model_validate(row.payload) if row else None

    def list_baseline_versions(self, contract_id: str) -> list[Baseline]:
        with self._sf() as session:
            rows = session.scalars(
                select(BaselineVersionRow)
                .where(BaselineVersionRow.contract_id == contract_id)
                .order_by(BaselineVersionRow.version.asc())
            ).all()
            return [Baseline.model_validate(r.payload) for r in rows]
