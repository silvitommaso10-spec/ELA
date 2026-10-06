"""The reservation of a call that spends: ``execution_results.worst_case`` (M14.1, ADR 0057).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-06

One nullable JSON column, and an index on ``execution_results.created_at``. The column is the
worst case a ``STARTED`` row reserves under the month's spending cap; ``NULL`` is every row that
exists today, none of which reserved anything — a ``STARTED`` row written before the cap closes or
stays open without counting, because the month's ledger reads only the rows that carry a worst case.
The index is the month's ledger reading by date, at every call that spends.

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops the column and the index, and with them every reservation: a cap that
counts after a downgrade counts only what closed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("execution_results", sa.Column("worst_case", sa.JSON(), nullable=True))
    op.create_index("ix_execution_results_created_at", "execution_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_execution_results_created_at", table_name="execution_results")
    op.drop_column("execution_results", "worst_case")
