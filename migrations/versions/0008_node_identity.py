"""L'identità dei nodi: revisione, revoca e hash su ``devices``, e i codici (M12.1, ADR 0037 §8).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-11

Tre colonne su `devices` e una tabella nuova. `revision` nasce `NOT NULL` con `server_default`
`0`: le righe che esistono già — `local`, su ogni database di sviluppo — la ricevono senza che
nessuno le riscriva, e `local` resta fuori dalla revisione (ADR 0037 §9). `revoked_at` e
`secret_hash` nascono nulli: nessuna riga di oggi è revocata, e `local` non si autentica dalla
rete. L'hash sta sulla riga e non sull'entità (regola 46): la riga è la cassaforte, non un
confine.

`enrollments` tiene l'hash di un codice monouso, mai il codice. `code_hash` è UNIQUE perché è la
chiave con cui l'`UPDATE` condizionale lo trova (ADR 0037 §5). Nessuna foreign key verso
`devices`: `device_id` lo scrive l'istruzione che consuma il codice, **prima** che la riga del
nodo nasca.

Reversibile: non tocca `audit_events`, quindi la regola di `0002` (nessun downgrade) non si
applica. Il downgrade toglie le colonne con l'`ALTER TABLE ... DROP COLUMN` di SQLite (dalla
3.35), senza ricostruire la tabella; nessuna delle tre sta in un indice o in un vincolo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HASH_LENGTH = 64
"""Uno SHA-256 in esadecimale minuscolo, come ``orm.HASH_LENGTH``."""


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("revision", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column("devices", sa.Column("revoked_at", sa.DateTime(), nullable=True))
    op.add_column("devices", sa.Column("secret_hash", sa.String(length=HASH_LENGTH), nullable=True))
    op.create_table(
        "enrollments",
        sa.Column("seq", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code_hash", sa.String(length=HASH_LENGTH), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("privacy", sa.String(length=32), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("device_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint("code_hash"),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("enrollments")
    op.drop_column("devices", "secret_hash")
    op.drop_column("devices", "revoked_at")
    op.drop_column("devices", "revision")
