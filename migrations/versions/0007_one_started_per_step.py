"""Un solo record ``STARTED`` per step: indice unico parziale (M7.2 review, ADR 0021 §1-bis).

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-07

Un record ``STARTED`` dice che un tool che non si può rifare stava per girare. Un secondo, per lo
stesso step, sarebbe esattamente la cosa che il protocollo esiste per impedire, scritta come se
fosse normale. L'executor lo rifiuta già; questo vincolo lo rifiuta per **ogni** scrittore, che è
la ragione per cui `id` è UNIQUE invece di essere controllato nell'adapter.

Parziale: `WHERE status = 'STARTED'`. Gli esiti non sono vincolati — un UNIQUE su
`(task_id, step_id)` è stato rinviato apposta (ADR 0015, alternative), e questa migrazione non lo
anticipa.

Una migrazione a sé e non un'estensione di `0006`: `0006` è già stata applicata a un database di
sviluppo, e Alembic non riesegue una revisione che ha già registrato — modificarla lascerebbe
quel database senza l'indice, in silenzio.

Il predicato è un `sa.text`, non un `op.inline_literal`: il secondo lo avrebbe scritto come
una *stringa* fra apici, cioè una costante e non una condizione, e l'indice sarebbe stato
totale invece che parziale — vietando due risultati di qualunque stato per uno step. Lo ha
trovato `test_upgrade_creates_the_same_indexes_as_the_orm`, che confronta il DDL del database
migrato con quello che `create_all` costruisce.

Reversibile: non tocca `audit_events`, quindi la regola di `0002` (nessun downgrade) non si
applica.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ux_execution_results_started_step"


def upgrade() -> None:
    op.create_index(
        INDEX,
        "execution_results",
        ["task_id", "step_id"],
        unique=True,
        sqlite_where=sa.text("status = 'STARTED'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="execution_results")
