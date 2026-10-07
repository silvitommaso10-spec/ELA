"""Who wrote a plan: ``task_plans.author`` (M14.2, ADR 0058).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-07

One JSON column on ``task_plans``, not nullable, with ``server_default='{"by": "HAND"}'``:
before this column there was no Planner, so every plan stored was sent by a person through
``POST /tasks/{id}/plan`` — a fact of the history, not a guess. The three authors are the
domain's (``PlanAuthor``): ``HAND``, ``PLANNER`` and ``MODEL``, and only ``MODEL`` names a result
and a model.

The ``server_default`` stays on the column, for the reason ``0010`` gives its own: a row inserted
by anything other than ELA's mapper must not be a plan whose author nobody wrote.

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops the column, and with it who wrote each plan: the ``PLAN_CREATED`` of the
audit keeps it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WRITTEN_BY_HAND = '{"by": "HAND"}'


def upgrade() -> None:
    op.add_column(
        "task_plans",
        sa.Column(
            "author", sa.JSON(), nullable=False, server_default=sa.text(f"'{WRITTEN_BY_HAND}'")
        ),
    )


def downgrade() -> None:
    op.drop_column("task_plans", "author")
