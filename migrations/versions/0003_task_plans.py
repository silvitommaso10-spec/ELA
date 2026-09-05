"""Task plans: the ``task_plans`` table, one plan per task (M3.1, ADR 0008).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-04

Written by hand from the autogenerate output, like ``0001``. Reversible: it does not touch
``audit_events``, so the rule of ``0002`` (no downgrade) does not apply. ``downgrade`` from head
therefore works down to ``0002`` and stops there, as before.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_plans",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sa.UniqueConstraint("task_id"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("task_plans")
