"""``UtcDateTime`` (ADR 0006 §7) and the column bounds the domain dictates (ADR 0006 §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

import pytest
from annotated_types import MaxLen
from pydantic import BaseModel
from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.pool import StaticPool

from ela.domain import NAME_MAX_LENGTH, Authorization, TaskEventType, TaskState
from ela.infrastructure.persistence.orm import (
    AuthorizationRow,
    TaskEventRow,
    TaskRow,
    UtcDateTime,
)

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


# ----------------------------------------------------------------------------------------
# Column bounds come from the domain (review M2.1): the database never refuses what the
# domain accepted.
# ----------------------------------------------------------------------------------------

BOUNDED_BY_THE_DOMAIN: dict[InstrumentedAttribute[str], tuple[type[BaseModel], str]] = {
    AuthorizationRow.capability_id: (Authorization, "capability_id"),
    AuthorizationRow.granted_by: (Authorization, "granted_by"),
}
PERSISTED_ENUMS: dict[
    InstrumentedAttribute[str] | InstrumentedAttribute[str | None], type[StrEnum]
] = {
    TaskRow.state: TaskState,
    TaskEventRow.event_type: TaskEventType,
    TaskEventRow.previous_state: TaskState,
    TaskEventRow.new_state: TaskState,
}


def max_length_of(model: type[BaseModel], field: str) -> int:
    """The ``max_length`` the domain declares on a field; fails if there is none."""
    lengths = [m.max_length for m in model.model_fields[field].metadata if isinstance(m, MaxLen)]
    assert len(lengths) == 1, f"{model.__name__}.{field} declares no single max_length"
    return int(lengths[0])


def column_length(attribute: InstrumentedAttribute[str] | InstrumentedAttribute[str | None]) -> int:
    column_type = attribute.property.columns[0].type
    assert isinstance(column_type, String) and column_type.length is not None
    return column_type.length


def longest_value(enum: type[StrEnum]) -> int:
    return max(len(member.value) for member in enum)


@pytest.mark.parametrize(
    "attribute", list(BOUNDED_BY_THE_DOMAIN), ids=lambda a: f"{a.class_.__name__}.{a.key}"
)
def test_string_columns_are_as_long_as_the_domain_allows(
    attribute: InstrumentedAttribute[str],
) -> None:
    model, field = BOUNDED_BY_THE_DOMAIN[attribute]
    assert max_length_of(model, field) == NAME_MAX_LENGTH == column_length(attribute)


def test_an_unbounded_domain_field_is_detected() -> None:
    """Negative case: a field without ``max_length`` cannot be tied to a column."""
    with pytest.raises(AssertionError, match="no single max_length"):
        max_length_of(Authorization, "scope")


@pytest.mark.parametrize(
    "attribute", list(PERSISTED_ENUMS), ids=lambda a: f"{a.class_.__name__}.{a.key}"
)
def test_every_persisted_enum_member_fits_its_column(
    attribute: InstrumentedAttribute[str] | InstrumentedAttribute[str | None],
) -> None:
    """``WAITING_APPROVAL`` is the longest today; a future member longer than 32 fails here."""
    assert longest_value(PERSISTED_ENUMS[attribute]) <= column_length(attribute)


def test_an_overlong_enum_member_would_be_detected() -> None:
    class Wide(StrEnum):
        FINE = "FINE"
        TOO_LONG = "A" * (column_length(TaskRow.state) + 1)

    assert longest_value(Wide) > column_length(TaskRow.state)
