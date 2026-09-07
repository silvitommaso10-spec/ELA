"""``missing_tables`` (ADR 0006, ADR 0023 §5): ELA says when the schema is not there.

ELA does not migrate on start-up — that decision is ADR 0006's — but it must not turn a missing
installation step into a ``no such table`` on the first request either. This is the check that
lets the composition root say it once, at start-up, naming the command to run.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence import make_engine, missing_tables
from ela.infrastructure.persistence.orm import Base
from tests.contracts.implementations import MEMORY_URL


async def test_a_migrated_database_is_missing_nothing(engine: AsyncEngine) -> None:
    assert await missing_tables(engine) == ()


async def test_an_empty_database_is_missing_every_table() -> None:
    empty = make_engine(MEMORY_URL)
    try:
        absent = await missing_tables(empty)
    finally:
        await empty.dispose()

    assert absent == tuple(sorted(Base.metadata.tables))
    assert "tasks" in absent and "audit_events" in absent


async def test_the_check_creates_nothing(engine: AsyncEngine) -> None:
    """Read-only: the answer to a missing table is a message, not a table conjured behind the
    operator's back."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    assert await missing_tables(engine) == tuple(sorted(Base.metadata.tables))
    assert await missing_tables(engine) == tuple(sorted(Base.metadata.tables))
