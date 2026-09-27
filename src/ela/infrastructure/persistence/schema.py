"""Whether the database has the schema the adapters expect (ADR 0006, ADR 0023 §5).

ELA does **not** migrate on start-up: ADR 0006 decided that a migration is run deliberately,
``uv run alembic upgrade head``. What it does now is *say* when the schema is not there, once, at
start-up — instead of turning a missing installation step into a ``no such table`` on the first
request, far from its cause.

**The columns too, since M17.2b** (decisione 6, ADR 0049). ``0010`` and ``0011`` added columns to
tables that were already there, and a database left before them passed a check of the tables and
failed at the first read of the column; ``0012`` would have been the third. The guide promises
that a forgotten migration stops the start-up with the command to run, and it is this check that
keeps the promise.
"""

from __future__ import annotations

from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence.orm import Base

__all__ = ["missing_columns", "missing_tables"]


def _absent(connection: Connection) -> tuple[str, ...]:
    present = set(inspect(connection).get_table_names())
    return tuple(sorted(name for name in Base.metadata.tables if name not in present))


def _absent_columns(connection: Connection) -> tuple[str, ...]:
    inspector = inspect(connection)
    present = set(inspector.get_table_names())
    found: list[str] = []
    for name, table in Base.metadata.tables.items():
        if name not in present:
            continue
        columns = {column["name"] for column in inspector.get_columns(name)}
        found.extend(
            f"{name}.{column.name}" for column in table.columns if column.name not in columns
        )
    return tuple(sorted(found))


async def missing_tables(engine: AsyncEngine) -> tuple[str, ...]:
    """The mapped tables the database does not have, sorted; empty when the schema is there.

    Read-only, and it creates nothing: the answer to a missing table is a message naming
    ``alembic upgrade head``, not a table conjured behind the operator's back.
    """
    async with engine.connect() as connection:
        return await connection.run_sync(_absent)


async def missing_columns(engine: AsyncEngine) -> tuple[str, ...]:
    """The mapped columns of the tables the database has, that the database does not, as
    ``table.column``, sorted; empty when every column is there.

    A table that is missing altogether is :func:`missing_tables`' to say — naming each of its
    columns here would say the same thing twice, longer. Read-only, like the check of the tables.
    """
    async with engine.connect() as connection:
        return await connection.run_sync(_absent_columns)
