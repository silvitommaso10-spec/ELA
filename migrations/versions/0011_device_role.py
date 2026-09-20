"""What an identity is: ``devices.role`` and ``enrollments.role`` (M12.5 dec. A; ADR 0043).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-20

Two columns, one per table, not nullable, with ``server_default='WORKER'``: every node enrolled
before roles existed keeps being exactly what it was — a machine that takes work — and so does
``local``, which the Core writes for itself. The default is the meaning of the world as it was, not
the safest of the two: there is no safer one here, because the two roles are refused on each other's
ground (dec. A), and a companion born by default would be a companion nobody minted a code for.

``enrollments.role`` carries the same word to the codes that are still spendable when this runs. A
code minted before this migration was minted for a node, and stays one: the conditional ``UPDATE``
that spends it asks for the role of the route presenting it (dec. C.5), and with ``WORKER`` on the
row it keeps working on ``POST /nodes/enroll`` exactly as it did.

The ``server_default`` stays on the columns rather than being dropped after the backfill, for the
reason ``0010`` gives: a row inserted by anything other than ELA's mapper would otherwise have no
role at all, and every reader of the registry reads this column.

Reversible: it does not touch ``audit_events``, so the rule of ``0002`` (no downgrade) does not
apply. The downgrade drops both columns, and with them the only mark that tells a companion from a
node — after it, a companion's cookie opens nothing, because the identity that answers the pages is
the one the role names.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("devices", "enrollments"):
        op.add_column(
            table, sa.Column("role", sa.String(32), nullable=False, server_default="WORKER")
        )


def downgrade() -> None:
    for table in ("devices", "enrollments"):
        op.drop_column(table, "role")
