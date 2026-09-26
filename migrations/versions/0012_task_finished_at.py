"""The hour of an outcome: ``tasks.finished_at`` (M17.2b, ADR 0049).

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26

One column, nullable: ``NULL`` is what a live task has, and what a finished task has when its hour
cannot be known. The homes list «the last N outcomes» in the order of this column, and it is written
by the same ``UPDATE`` that writes the final state — so from here on a final state is never saved
without its hour.

The tasks that finished before the column existed take their hour from **the last event that
brought them into the state they are in**: a ``STATE_CHANGED`` whose ``new_state`` is the task's
``state``. Only for a task in one of the five final states — written here by name, because a
migration does not import code that changes after it, and because a live task has such an event
too. Where that event is missing — the window of ADR 0015 §8, a state saved and its event lost —
the column stays empty: an hour made up here would be a value without a source, and the list puts
such a task last instead of leaving it out.

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops the column, and with it the order of the outcomes on the homes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FINAL = ("COMPLETED", "FAILED", "CANCELLED", "DENIED", "EXPIRED")
"""The final states of ADR 0004, by name, as they are on the day of this migration."""


def upgrade() -> None:
    op.add_column("tasks", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE tasks SET finished_at = ("
            " SELECT event.created_at FROM task_events AS event"
            " WHERE event.task_id = tasks.id AND event.new_state = tasks.state"
            " ORDER BY event.seq DESC LIMIT 1"
            ") WHERE state IN (" + ", ".join(f"'{state}'" for state in FINAL) + ")"
        )
    )


def downgrade() -> None:
    op.drop_column("tasks", "finished_at")
