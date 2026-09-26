"""``missing_tables`` (ADR 0006, ADR 0023 §5): ELA says when the schema is not there.

ELA does not migrate on start-up — that decision is ADR 0006's — but it must not turn a missing
installation step into a ``no such table`` on the first request either. This is the check that
lets the composition root say it once, at start-up, naming the command to run.
"""

from __future__ import annotations

from pathlib import Path

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


async def test_a_database_left_at_0011_lacks_one_column_and_no_table(tmp_path: Path) -> None:
    """M17.2b decisione 6: the precondition built as it happens — a database that ``alembic`` took
    to ``0011``, the revision before the hour of an outcome, and not a column taken away by hand.

    The tables are all there, so the check of the tables says nothing; the column is what is
    missing, and it is what the start-up has to name.
    """
    from alembic import command

    from ela.infrastructure.persistence import missing_columns
    from tests.infrastructure.persistence.test_migrations import config_for

    database = tmp_path / "ela.db"
    command.upgrade(config_for(database), "0011")
    engine = make_engine(f"sqlite:///{database.as_posix()}")
    try:
        assert await missing_tables(engine) == ()
        assert await missing_columns(engine) == ("tasks.finished_at",)
    finally:
        await engine.dispose()


async def test_a_migrated_database_lacks_no_column(engine: AsyncEngine) -> None:
    from ela.infrastructure.persistence import missing_columns

    assert await missing_columns(engine) == ()


async def test_a_table_that_is_missing_is_not_named_again_column_by_column() -> None:
    """A missing table is :func:`missing_tables`' to say: naming each of its columns as well would
    say the same thing twice, longer, in the message that stops the start-up."""
    from ela.infrastructure.persistence import missing_columns

    empty = make_engine(MEMORY_URL)
    try:
        assert await missing_columns(empty) == ()
    finally:
        await empty.dispose()
