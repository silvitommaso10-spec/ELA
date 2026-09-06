"""The nodes of §16: the ``devices`` table (M6.1, ADR 0016).

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-07

Written by hand from the autogenerate output, like ``0001``, ``0003`` and ``0004``. Reversible:
it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not apply. No
foreign key: a store apart from the repository, like ``authorizations`` and ``approvals``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("os", sa.String(length=32), nullable=False),
        sa.Column("availability", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("available_tools", sa.JSON(), nullable=False),
        sa.Column("performance", sa.String(length=32), nullable=False),
        sa.Column("network", sa.String(length=32), nullable=False),
        sa.Column("power_source", sa.String(length=32), nullable=False),
        sa.Column("privacy", sa.String(length=32), nullable=False),
        sa.Column("current_workload", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_devices_availability", "devices", ["availability"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_devices_availability", table_name="devices")
    op.drop_table("devices")
