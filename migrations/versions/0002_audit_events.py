"""Audit log: the append-only, hash-chained ``audit_events`` table (M2.2, ADR 0007).

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04

Written by hand from the autogenerate output, plus the two triggers alembic does not know about:
they are the database level of append-only and carry the same SQL as ``orm.py`` (a test compares
the two). This migration has no downgrade: removing the audit log is never a tooling operation
(ADR 0007 §7). The rule from here on: a migration that touches ``audit_events`` has no downgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APPEND_ONLY_MESSAGE = "audit_events is append-only"
TRIGGERS = (
    "CREATE TRIGGER audit_events_no_update BEFORE UPDATE ON audit_events "
    f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}'); END",
    "CREATE TRIGGER audit_events_no_delete BEFORE DELETE ON audit_events "
    f"BEGIN SELECT RAISE(ABORT, '{APPEND_ONLY_MESSAGE}'); END",
)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_kind", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("capability_id", sa.String(length=255), nullable=True),
        sa.Column("decision_id", sa.Uuid(), nullable=True),
        sa.Column("authorization_id", sa.Uuid(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.Column("tool_name", sa.Text(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("prev_hash"),
        sa.UniqueConstraint("row_hash"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_audit_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_task_id"), ["task_id"], unique=False)
    for trigger in TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    raise NotImplementedError(
        "migration 0002 has no downgrade: the audit log is append-only and no migration removes "
        "it (ADR 0007); deleting it is a deliberate manual act, not a tooling operation"
    )
