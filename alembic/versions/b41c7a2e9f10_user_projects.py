"""user_projects — per-project access isolation (minimal RBAC v2)

Revision ID: b41c7a2e9f10
Revises: dfe7abcdd649
Create Date: 2026-07-02
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b41c7a2e9f10"
down_revision: str | None = "dfe7abcdd649"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_projects",
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["username"], ["users.username"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("username", "project_id"),
    )


def downgrade() -> None:
    op.drop_table("user_projects")
