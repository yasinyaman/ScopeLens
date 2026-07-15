"""Normalized models exchanged through the external-integration ports.

These are the vendor-agnostic shapes every adapter produces. They are part of
the frozen plugin API: fields may be ADDED (minor bump) but never renamed or
removed without a major bump. Deliberately enum-free and self-contained — the
Etki domain model (ScopeItem, CaseFile, …) stays in ``etki.core`` and is NOT
part of this API.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --- Work item (normalized) --------------------------------------------------


class WorkItem(BaseModel):
    """Vendor-agnostic, normalized work item. ``effort_seconds`` is the single
    source of truth for effort (GLPI actiontime, Jira worklog... converted in
    the adapter)."""

    id: str
    title: str
    description: str = ""
    category: str | None = None
    status: str | None = None
    effort_seconds: int = 0
    assignee: str | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None


# --- Code knowledge graph -----------------------------------------------------


class Complexity(BaseModel):
    loc: int = 0
    cyclomatic: int = 0
    files: int = 0


class Churn(BaseModel):
    commits_last_6mo: int = 0


class CodeModule(BaseModel):
    """A module in the code knowledge graph (dependencies + metrics)."""

    id: str
    path: str
    responsibilities: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    depended_by: list[str] = Field(default_factory=list)
    mapped_scope_items: list[str] = Field(default_factory=list)
    # External (third-party) package names this module imports — the usage
    # surface for dependency-impact analysis. Internal modules stay in
    # depends_on; stdlib/builtins are filtered as noise.
    packages: list[str] = Field(default_factory=list)
    # Per-package API symbols this module touches ("requests" → ["get"]) — the
    # call sites to audit on a version change. ast producer only; defaulted.
    package_apis: dict[str, list[str]] = Field(default_factory=dict)
    # Qualified counterparts ("faker" → ["faker.providers.x.CreditCard"]) — the
    # your_code version-diff audit uses these; catches non-exported imports.
    package_api_paths: dict[str, list[str]] = Field(default_factory=dict)
    complexity: Complexity = Field(default_factory=Complexity)
    churn: Churn = Field(default_factory=Churn)


# --- Document source -----------------------------------------------------


class DocumentRef(BaseModel):
    id: str
    name: str
    path: str
    mime: str = "text/plain"
    modified_at: datetime | None = None
    source: str = "fake"


# --- Package registry metadata --------------------------------------------


class PackageMetadata(BaseModel):
    """Registry metadata for one package — DISPLAY data next to the raw spec.
    Never compared/resolved against the declared spec (no "outdated" boolean:
    PEP 440, semver and maven ranges are different languages)."""

    name: str
    ecosystem: str
    latest_version: str | None = None
    released_at: str | None = None  # ISO date string when the registry provides it
    homepage: str | None = None
