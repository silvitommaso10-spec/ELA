"""The policies of §59: ``authorizations.bounds`` and ``.revoked_at`` (M13.12, ADR 0062).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-09

Two nullable columns on ``authorizations``, and no other table changes (decision 10): ``bounds``,
JSON — the limits of a policy with the terms they were born under —, and ``revoked_at`` — when the
policy was revoked, written once. A grant born from a yes has neither, so every row written before
this migration keeps both empty: no producer ever wrote a policy before M13.12.

**It defends the invariant of decision 3d before it adds the columns**: a grant without
``approval_id`` always ends. A row without both — written by hand, since no code ever wrote one —
would be a row the mapper cannot read, and it would stop every grant of its capability at the read:
a step would end in an error instead of a question. So the upgrade counts them, and stops with a
message if there is one, instead of leaving a database ELA cannot read.

Reversible: it does not touch ``audit_events``. The downgrade drops the two columns, and with them
the limits and the revocations of the policies: the ``AUTHORIZATION_GRANTED`` and
``AUTHORIZATION_REVOKED`` of the audit keep both.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WITHOUT_AN_END = (
    "SELECT count(*) FROM authorizations WHERE approval_id IS NULL AND expires_at IS NULL"
)


def upgrade() -> None:
    endless = op.get_bind().execute(sa.text(WITHOUT_AN_END)).scalar_one()
    if endless:
        raise RuntimeError(
            f"{endless} standing authorization(s) without an end: since M13.12 a grant without "
            "approval_id always expires (ADR 0062). No code of ELA wrote them; give each an "
            "expires_at, or delete it, and upgrade again."
        )
    op.add_column("authorizations", sa.Column("bounds", sa.JSON(), nullable=True))
    op.add_column("authorizations", sa.Column("revoked_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("authorizations", "revoked_at")
    op.drop_column("authorizations", "bounds")
