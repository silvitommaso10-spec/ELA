"""Engines for the persistence tests: in memory with the schema created, or on a file."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence import make_engine
from ela.infrastructure.persistence.orm import Base
from tests.contracts.implementations import MEMORY_URL


async def create_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """An in-memory engine with the schema in place, disposed after the test."""
    engine = make_engine(MEMORY_URL)
    await create_schema(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def file_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"


Recorder = Callable[[], list[str]]


@pytest.fixture
def statements() -> Callable[[AsyncEngine], Recorder]:
    """Record the SQL an engine executes; the returned callable gives the statements so far."""

    def attach(engine: AsyncEngine) -> Recorder:
        seen: list[str] = []

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _record(
            conn: object, cursor: object, statement: str, *args: object, **kwargs: object
        ) -> None:
            seen.append(" ".join(statement.split()))

        return lambda: list(seen)

    return attach
