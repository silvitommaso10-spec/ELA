"""Whether the database has the schema the adapters expect (ADR 0006, ADR 0023 §5).

ELA does **not** migrate on start-up: ADR 0006 decided that a migration is run deliberately,
``uv run alembic upgrade head``. What it does now is *say* when the schema is not there, once, at
start-up — instead of turning a missing installation step into a ``no such table`` on the first
request, far from its cause.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence.orm import Base

__all__ = ["missing_tables"]


def _absent(connection: Connection) -> tuple[str, ...]:
    present = set(inspect(connection).get_table_names())
    return tuple(sorted(name for name in Base.metadata.tables if name not in present))


async def missing_tables(engine: AsyncEngine) -> tuple[str, ...]:
    """The mapped tables the database does not have, sorted; empty when the schema is there.

    Read-only, and it creates nothing: the answer to a missing table is a message naming
    ``alembic upgrade head``, not a table conjured behind the operator's back.
    """
    async with engine.connect() as connection:
        return await connection.run_sync(_absent)
