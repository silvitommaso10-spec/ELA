"""Approvals and execution results: the ``approvals`` and ``execution_results`` tables (M5.3,
ADR 0015).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06

Written by hand from the autogenerate output, like ``0001`` and ``0003``. Reversible: it does
not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not apply. No foreign key
on ``task_id``: these are stores apart from the repository, like ``authorizations``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approvals",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("capability_id", sa.String(length=255), nullable=False),
        sa.Column("targets", sa.JSON(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column("responded_by", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_approvals_task_id", "approvals", ["task_id"], unique=False)
    op.create_index("ix_approvals_status", "approvals", ["status"], unique=False)
    op.create_table(
        "execution_results",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("capability_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_id", sa.Uuid(), nullable=True),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_execution_results_task_id", "execution_results", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_results_task_id", table_name="execution_results")
    op.drop_table("execution_results")
    op.drop_index("ix_approvals_status", table_name="approvals")
    op.drop_index("ix_approvals_task_id", table_name="approvals")
    op.drop_table("approvals")
