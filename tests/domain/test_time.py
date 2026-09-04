"""``created_at`` is mandatory, aware and stored in UTC (§49). The domain never reads a clock."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import BaseModel, ValidationError

from ela.domain import Task, TaskState
from tests.domain.examples import EXAMPLES, TASK_ID
from tests.domain.introspection import domain_models

MODELS = sorted(EXAMPLES, key=lambda model: model.__name__)
DATETIME_FIELDS = {"created_at", "deadline", "expires_at", "responded_at", "last_seen_at"}


class _NoOffset(tzinfo):
    """A tzinfo that claims to exist but has no offset: aware in name only."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return "NONE"

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


def _task(created_at: object) -> Task:
    return Task.model_validate(
        {"id": TASK_ID, "created_at": created_at, "goal": "g", "state": TaskState.CREATED}
    )


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _task(datetime(2026, 9, 4, 10, 30))


def test_datetime_with_offsetless_tzinfo_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _task(datetime(2026, 9, 4, 10, 30, tzinfo=_NoOffset()))


def test_offset_datetime_is_normalised_to_utc() -> None:
    rome = timezone(timedelta(hours=2))
    task = _task(datetime(2026, 9, 4, 12, 30, tzinfo=rome))
    assert task.created_at.tzinfo is UTC
    assert task.created_at == datetime(2026, 9, 4, 10, 30, tzinfo=UTC)


def test_utc_datetime_survives_untouched() -> None:
    moment = datetime(2026, 9, 4, 10, 30, tzinfo=UTC)
    assert _task(moment).created_at == moment


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_datetime_fields_are_normalised(model: type[BaseModel]) -> None:
    """Every datetime field, not only ``created_at``, is aware and in UTC after validation."""
    example = EXAMPLES[model]
    for name in model.model_fields:
        value = getattr(example, name)
        if isinstance(value, datetime):
            assert value.tzinfo is UTC, f"{model.__name__}.{name}"


def test_every_entity_requires_created_at() -> None:
    """Value objects have no ``created_at``; entities have it and it is never optional."""
    entities = [model for model in domain_models() if "id" in model.model_fields]
    assert entities
    for model in entities:
        field = model.model_fields.get("created_at")
        assert field is not None, model.__name__
        assert field.is_required(), model.__name__


def test_no_field_reads_the_clock() -> None:
    """No ``default_factory`` on a datetime field: reading the clock is I/O, and I/O is a port."""
    for model in domain_models():
        for name, field in model.model_fields.items():
            if name in DATETIME_FIELDS:
                assert field.default_factory is None, f"{model.__name__}.{name}"
