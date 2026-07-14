"""SQLAlchemy 2.0 ORM tables. JSON columns work on both SQLite and Postgres."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from etki.persistence.db import Base


class CaseFileRow(Base):
    __tablename__ = "case_files"

    request_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    status: Mapped[str] = mapped_column(String, index=True)
    raw_request: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class AuditEventRow(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    seq: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OverrideRow(Base):
    __tablename__ = "overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String, index=True)
    decision_index: Mapped[int] = mapped_column(Integer)
    system_decision: Mapped[str] = mapped_column(String)
    human_decision: Mapped[str] = mapped_column(String)
    actor: Mapped[str] = mapped_column(String)
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserRow(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String)
    salt: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserProjectRow(Base):
    """User ↔ project access grant (minimal RBAC v2 — per-project isolation)."""

    __tablename__ = "user_projects"

    username: Mapped[str] = mapped_column(
        String, ForeignKey("users.username", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[str] = mapped_column(String, primary_key=True)


class BaselineVersionRow(Base):
    __tablename__ = "baseline_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_case_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
