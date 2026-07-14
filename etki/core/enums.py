"""Core enums. Values are readable strings (clear when viewed in JSON)."""

from enum import StrEnum


class Polarity(StrEnum):
    """Direction of a scope item. EXCLUDED is first-class — the strongest
    'out-of-scope' evidence."""

    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"


class Decision(StrEnum):
    """The recommendation the triage engine gives for a sub-request."""

    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CR_CANDIDATE = "CR_CANDIDATE"
    GRAY_AREA = "GRAY_AREA"
    MAINTENANCE = "MAINTENANCE"


class PmoDecision(StrEnum):
    """Human (PMO) decision. The system offers a recommendation; the decision
    stays here (copilot, not autopilot)."""

    PENDING = "PENDING"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CONVERT_TO_CR = "CONVERT_TO_CR"


class RiskLevel(StrEnum):
    """Position on the probability × impact matrix."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RequestType(StrEnum):
    """Type of the sub-request (modifying existing code, a new feature, or maintenance).

    Only MAINTENANCE branches the decision tree; DEPENDENCY_CHANGE (library add /
    version upgrade) is deliberately INERT there — recognition + evidence note
    without decision power (a decision branch requires its own dataset-first
    eval round, see the plan doc)."""

    MODIFICATION = "modification"
    NEW_FEATURE = "new_feature"
    MAINTENANCE = "maintenance"
    DEPENDENCY_CHANGE = "dependency_change"
    UNKNOWN = "unknown"
