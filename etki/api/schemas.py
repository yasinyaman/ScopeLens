"""API request/response DTOs. The core ``CaseFile`` model is returned as the response."""

from __future__ import annotations

from pydantic import BaseModel, Field

from etki.core.enums import Decision, PmoDecision


class TriageRequest(BaseModel):
    request_text: str = Field(min_length=1, description="Natural language request")
    project_id: str | None = None


class ActionRequest(BaseModel):
    """The PMO's disposition on a sub-request decision (+ optional override)."""

    action: PmoDecision
    override_decision: Decision | None = None
