"""Le assegnazioni: il lavoro affidato a un nodo che non è questo processo (M12.2, ADR 0038).

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-11

Una tabella nuova, `assignments`, e un indice unico **parziale**: al più un'assegnazione per step
che non sia `EXPIRED`. Parziale e non totale perché uno step rilasciato si riaffida, e fra la
scadenza e l'assegnazione nuova c'è sempre la scrittura di `EXPIRED`. Il predicato è `sa.text`,
mai `op.inline_literal`, per la ragione che scrive `0007`: un letterale lo quoterebbe come una
stringa, e l'indice diventerebbe totale in silenzio.

Nessuna colonna per gli argomenti dello step: la chiamata è la decisione più gli argomenti del
piano, letti per riferimento quando il nodo prende il lavoro (M12.1, D1), e una copia qui sarebbe
un posto in più dove vive il contenuto dell'utente (§57). La decisione sta in una colonna JSON,
una volta sola, con il suo id dentro. «Una per nodo alla volta» non è un indice: un indice non
conosce il tempo (M12.1, D16), e sta nell'`UPDATE` della presa.

La colonna `tasks.max_privacy` non è qui: nasce con la `0010`, nel commit della sensibilità del
task, che viene dopo il ramo remoto (criterio 32 di M12.2). Una colonna nata qui aspetterebbe il
suo lettore per diversi commit, cioè sarebbe uno stub.

Reversibile: non tocca `audit_events`, quindi la regola di `0002` (nessun downgrade) non si
applica.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ux_assignments_open_step"
HASH_LENGTH = 64
"""Uno SHA-256 in esadecimale minuscolo, come ``orm.HASH_LENGTH``: l'impronta della busta."""


def upgrade() -> None:
    op.create_table(
        "assignments",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("authorization_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("delivery_digest", sa.String(length=HASH_LENGTH), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index(
        INDEX,
        "assignments",
        ["task_id", "step_id"],
        unique=True,
        sqlite_where=sa.text("state <> 'EXPIRED'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="assignments")
    op.drop_table("assignments")
