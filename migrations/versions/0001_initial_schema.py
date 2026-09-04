"""Initial schema: tasks, task_events, authorizations (M2.1, ADR 0006).

Revision ID: 0001
Revises: none
Create Date: 2026-09-04

Written by hand from the autogenerate output: the ``UtcDateTime`` decorator of ``orm.py`` is
``DateTime`` in the database, and a migration must not import application code to stay
replayable when that code has moved on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("intent_id", sa.Uuid(), nullable=True),
        sa.Column("plan_id", sa.Uuid(), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["parent_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tasks_state"), ["state"], unique=False)

    op.create_table(
        "task_events",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("previous_state", sa.String(length=32), nullable=True),
        sa.Column("new_state", sa.String(length=32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_task_events_task_id"), ["task_id"], unique=False)

    op.create_table(
        "authorizations",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("capability_id", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("granted_by", sa.String(length=255), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("uses", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    with op.batch_alter_table("authorizations", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_authorizations_capability_id"), ["capability_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("authorizations", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_authorizations_capability_id"))
    op.drop_table("authorizations")

    with op.batch_alter_table("task_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_task_events_task_id"))
    op.drop_table("task_events")

    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tasks_state"))
    op.drop_table("tasks")
