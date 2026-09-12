"""How far a task's content may travel: ``tasks.max_privacy`` (M12.2, D18, D20; ADR 0038 §16).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-12

One column on ``tasks``, not nullable, with ``server_default='LOCAL_ONLY'``: every task written
before this column existed keeps doing exactly what it did — staying on this machine. The default is
the strictest level on purpose (§33, §57): a task whose sensitivity nobody declared is not a task
anybody allowed to leave.

**Separate from ``0009`` and after it** (criterion 32, dec. O): the remote branch comes first, and a
column born before its reader would be a stub. ``0009`` carries the ``assignments`` table, which the
port of the work needs; this one carries the field the runner reads.

The ``server_default`` stays on the column rather than being dropped after the backfill. Dropping it
would make the schema lie about itself: a row inserted by anything other than ELA's mapper — a
migration of tomorrow, a repair by hand — would have no level at all, and "no level" must read as
"this machine" everywhere, not only where the domain happens to put it.

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops the column and with it every declared sensitivity, which is why it is a
downgrade and not a fix.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("max_privacy", sa.String(32), nullable=False, server_default="LOCAL_ONLY"),
    )


def downgrade() -> None:
    op.drop_column("tasks", "max_privacy")
