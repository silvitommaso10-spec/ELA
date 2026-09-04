"""``UtcDateTime`` (ADR 0006 §7): aware in, aware out, naive refused."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, insert, select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from ela.infrastructure.persistence.orm import UtcDateTime

stamps = Table(
    "stamps",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("at", UtcDateTime, nullable=True),
)


@pytest.fixture
async def stamps_engine() -> AsyncEngine:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(stamps.metadata.create_all)
    return engine


async def _round_trip(engine: AsyncEngine, value: datetime | None) -> datetime | None:
    async with engine.begin() as connection:
        await connection.execute(insert(stamps).values(id=1, at=value))
        result = await connection.execute(select(stamps.c.at).where(stamps.c.id == 1))
        return result.scalar_one()


async def test_aware_utc_round_trips_with_microseconds(stamps_engine: AsyncEngine) -> None:
    value = datetime(2026, 9, 4, 10, 30, 15, 123456, tzinfo=UTC)
    stored = await _round_trip(stamps_engine, value)
    assert stored == value
    assert stored is not None and stored.tzinfo is UTC


async def test_another_offset_comes_back_as_the_same_instant_in_utc(
    stamps_engine: AsyncEngine,
) -> None:
    rome = timezone(timedelta(hours=2))
    value = datetime(2026, 9, 4, 12, 30, tzinfo=rome)
    stored = await _round_trip(stamps_engine, value)
    assert stored == value
    assert stored is not None and stored.utcoffset() == timedelta(0)
    assert stored.hour == 10


async def test_none_passes_through(stamps_engine: AsyncEngine) -> None:
    assert await _round_trip(stamps_engine, None) is None


async def test_naive_is_refused_before_reaching_the_database(stamps_engine: AsyncEngine) -> None:
    with pytest.raises(StatementError, match="timezone-aware") as excinfo:
        await _round_trip(stamps_engine, datetime(2026, 9, 4, 10, 30))
    assert isinstance(excinfo.value.orig, ValueError)


def test_bind_and_result_without_a_database() -> None:
    """The two halves, called directly: what the engine does, spelled out."""
    decorator = UtcDateTime()
    dialect = object()
    value = datetime(2026, 9, 4, 10, 30, tzinfo=timezone(timedelta(hours=-5)))
    bound = decorator.process_bind_param(value, dialect)  # type: ignore[arg-type]
    assert bound == datetime(2026, 9, 4, 15, 30)
    assert bound is not None and bound.tzinfo is None
    assert decorator.process_result_value(bound, dialect) == value  # type: ignore[arg-type]
    assert decorator.process_bind_param(None, dialect) is None  # type: ignore[arg-type]
    assert decorator.process_result_value(None, dialect) is None  # type: ignore[arg-type]
