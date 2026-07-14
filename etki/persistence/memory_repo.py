"""In-memory CaseFileRepository — for tests (needs no DB)."""

from __future__ import annotations

from datetime import datetime

from etki.core.enums import PmoDecision
from etki.core.models import AuditEvent, Baseline, CaseFile, Override


class InMemoryCaseFileRepository:
    def __init__(self) -> None:
        self._cases: dict[str, CaseFile] = {}
        self._audit: list[AuditEvent] = []
        self._overrides: list[Override] = []
        self._baselines: list[Baseline] = []

    def save_case(self, case: CaseFile) -> None:
        self._cases[case.request_id] = case.model_copy(deep=True)

    def get_case(self, request_id: str) -> CaseFile | None:
        case = self._cases.get(request_id)
        return case.model_copy(deep=True) if case else None

    def list_cases(self, project_id: str | None = None) -> list[CaseFile]:
        return [
            c.model_copy(deep=True)
            for c in self._cases.values()
            if project_id is None or c.project_id == project_id
        ]

    def set_status(
        self, request_id: str, status: PmoDecision, decided_at: datetime | None
    ) -> None:
        case = self._cases.get(request_id)
        if case is not None:
            case.status = status

    def append_audit(self, event: AuditEvent) -> None:
        self._audit.append(event.model_copy(deep=True))

    def list_audit(self, case_id: str) -> list[AuditEvent]:
        return [e for e in self._audit if e.case_id == case_id]

    def record_override(self, override: Override) -> None:
        self._overrides.append(override.model_copy(deep=True))

    def list_overrides(self) -> list[Override]:
        return list(self._overrides)

    def save_baseline_version(self, baseline: Baseline, source_case_id: str | None) -> None:
        self._baselines.append(baseline.model_copy(deep=True))

    def latest_baseline(self, contract_id: str) -> Baseline | None:
        versions = [b for b in self._baselines if b.contract_id == contract_id]
        return max(versions, key=lambda b: b.version) if versions else None

    def list_baseline_versions(self, contract_id: str) -> list[Baseline]:
        return sorted(
            (b.model_copy(deep=True) for b in self._baselines if b.contract_id == contract_id),
            key=lambda b: b.version,
        )
