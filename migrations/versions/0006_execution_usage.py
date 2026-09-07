"""What a provider call consumed, on an execution result: ``usage`` (M7.2, ADR 0021 §3).

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-07

One nullable JSON column on ``execution_results``. Nullable is the whole point: every row that
exists today was written by a tool that called no provider, and ``NULL`` says "no provider call"
where ``{}`` or a zeroed document would say "a call that cost nothing" (§32).

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops the column and with it the recorded cost of every call — which is why
it is a downgrade and not a fix.

``ExecutionStatus.STARTED`` needs no migration: ``status`` is a ``String(32)`` with no check
constraint, and the vocabulary of the column lives in the domain enum, not in the schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("execution_results", sa.Column("usage", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("execution_results", "usage")
