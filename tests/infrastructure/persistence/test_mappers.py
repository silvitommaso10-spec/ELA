"""The mapper is a bijection, and it forgets no field (ADR 0006 §5)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from hypothesis import given, settings
from pydantic import BaseModel
from sqlalchemy import Table

from ela.domain import AuditEvent, Authorization, Task, TaskEvent
from ela.infrastructure.persistence.mappers import (
    audit_event_to_row,
    audit_event_values,
    authorization_to_row,
    authorization_values,
    event_to_row,
    row_to_audit_event,
    row_to_authorization,
    row_to_event,
    row_to_task,
    task_to_row,
    task_values,
)
from ela.infrastructure.persistence.orm import (
    AuditEventRow,
    AuthorizationRow,
    TaskEventRow,
    TaskRow,
)
from tests.contracts.test_task_repository import CHILD
from tests.domain.examples import (
    AUDIT_EVENT,
    ERROR_METADATA,
    POLICY_AUTHORIZATION,
    SINGLE_USE_AUTHORIZATION,
    TASK,
    TASK_EVENT,
)
from tests.domain.strategies import MODEL_STRATEGIES

BARE_TASK = Task(id=TASK.id, created_at=TASK.created_at, goal="bare", state=TASK.state)
BARE_EVENT = TaskEvent(
    id=TASK_EVENT.id,
    created_at=TASK_EVENT.created_at,
    task_id=TASK.id,
    event_type=TASK_EVENT.event_type,
)
FAILED_AUDIT_EVENT = AUDIT_EVENT.model_copy(update={"error": ERROR_METADATA, "usage": None})
BARE_AUDIT_EVENT = AuditEvent(
    id=AUDIT_EVENT.id,
    created_at=AUDIT_EVENT.created_at,
    event_type=AUDIT_EVENT.event_type,
    actor=AUDIT_EVENT.actor,
    summary="bare",
)

# ----------------------------------------------------------------------------------------
# Round trips
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("task", [TASK, CHILD, BARE_TASK], ids=["full", "child", "bare"])
def test_task_round_trip(task: Task) -> None:
    assert row_to_task(task_to_row(task)) == task


@pytest.mark.parametrize("event", [TASK_EVENT, BARE_EVENT], ids=["full", "bare"])
def test_event_round_trip(event: TaskEvent) -> None:
    assert row_to_event(event_to_row(event)) == event


@pytest.mark.parametrize(
    "authorization",
    [SINGLE_USE_AUTHORIZATION, POLICY_AUTHORIZATION],
    ids=["single-use", "policy"],
)
def test_authorization_round_trip(authorization: Authorization) -> None:
    assert row_to_authorization(authorization_to_row(authorization)) == authorization


@pytest.mark.parametrize(
    "event",
    [AUDIT_EVENT, FAILED_AUDIT_EVENT, BARE_AUDIT_EVENT],
    ids=["with-usage", "with-error", "bare"],
)
def test_audit_event_round_trip(event: AuditEvent) -> None:
    assert row_to_audit_event(audit_event_to_row(event)) == event


@settings(max_examples=100)
@given(MODEL_STRATEGIES[Task])
def test_any_task_round_trips(task: BaseModel) -> None:
    assert isinstance(task, Task)
    assert row_to_task(task_to_row(task)) == task


@settings(max_examples=100)
@given(MODEL_STRATEGIES[TaskEvent])
def test_any_event_round_trips(event: BaseModel) -> None:
    assert isinstance(event, TaskEvent)
    assert row_to_event(event_to_row(event)) == event


@settings(max_examples=100)
@given(MODEL_STRATEGIES[Authorization])
def test_any_authorization_round_trips(authorization: BaseModel) -> None:
    assert isinstance(authorization, Authorization)
    assert row_to_authorization(authorization_to_row(authorization)) == authorization


@settings(max_examples=100)
@given(MODEL_STRATEGIES[AuditEvent])
def test_any_audit_event_round_trips(event: BaseModel) -> None:
    assert isinstance(event, AuditEvent)
    assert row_to_audit_event(audit_event_to_row(event)) == event


# ----------------------------------------------------------------------------------------
# What a row holds
# ----------------------------------------------------------------------------------------


def test_rows_store_enum_values_and_plain_json() -> None:
    row = task_to_row(TASK)
    assert row.state == "PLANNING"
    assert type(row.metadata_) is dict
    assert isinstance(row.id, UUID)
    event = event_to_row(TASK_EVENT)
    assert (event.previous_state, event.new_state) == ("CREATED", "PLANNING")
    assert type(authorization_to_row(SINGLE_USE_AUTHORIZATION).scope) is list


def test_a_new_authorization_row_has_no_uses_yet() -> None:
    assert "uses" not in authorization_values(SINGLE_USE_AUTHORIZATION)


def test_an_audit_row_stores_the_actor_in_two_columns_and_value_objects_as_json() -> None:
    row = audit_event_to_row(AUDIT_EVENT)
    assert (row.actor_kind, row.actor_id) == ("ELA", "ela")
    assert row.event_type == "TOOL_EXECUTED"
    assert type(row.usage) is dict and row.usage["cost"] == "0.0123"  # Decimal as a string
    assert row.error is None
    assert type(row.payload) is dict
    failed = audit_event_to_row(FAILED_AUDIT_EVENT)
    assert type(failed.error) is dict and failed.error["device_id"] == str(ERROR_METADATA.device_id)


def test_a_new_audit_row_has_no_hashes_yet() -> None:
    """The chain columns belong to the log, which sets them under the write lock."""
    values = audit_event_values(AUDIT_EVENT)
    assert "prev_hash" not in values and "row_hash" not in values


# ----------------------------------------------------------------------------------------
# No forgotten field: model fields == columns the mapper writes (minus the store's own)
# ----------------------------------------------------------------------------------------

STORE_OWNED = {"seq", "uses", "prev_hash", "row_hash"}
#: A domain field stored as more than one column (the actor, ADR 0003: "who" stays queryable).
SPLIT_FIELDS = {"actor": {"actor_kind", "actor_id"}}


def _column_names(table: Table) -> set[str]:
    return {column.name for column in table.columns} - STORE_OWNED


def unmapped(model: type[BaseModel], values: dict[str, Any], table: Table) -> set[str]:
    """Fields of ``model`` that the mapper does not write, plus columns it writes that the
    model does not have. Empty means the mapper and the model agree."""
    written = {"metadata" if key == "metadata_" else key for key in values}
    fields: set[str] = set()
    for field in model.model_fields:
        fields |= SPLIT_FIELDS.get(field, {field})
    return (fields ^ written) | (written ^ _column_names(table))


def test_task_mapper_covers_every_field() -> None:
    assert unmapped(Task, task_values(TASK), TaskRow.__table__) == set()


def test_event_mapper_covers_every_field() -> None:
    row = event_to_row(TASK_EVENT)
    values = {c.key: getattr(row, c.key) for c in TaskEventRow.__mapper__.column_attrs}
    values.pop("seq")
    assert unmapped(TaskEvent, values, TaskEventRow.__table__) == set()


def test_authorization_mapper_covers_every_field() -> None:
    table = AuthorizationRow.__table__
    assert unmapped(Authorization, authorization_values(SINGLE_USE_AUTHORIZATION), table) == set()


def test_audit_event_mapper_covers_every_field() -> None:
    table = AuditEventRow.__table__
    assert unmapped(AuditEvent, audit_event_values(AUDIT_EVENT), table) == set()


def test_a_new_domain_field_is_detected() -> None:
    """Negative case: a model with one more field than the mapper writes."""

    class TaskWithColour(Task):
        colour: str = "blue"

    assert unmapped(TaskWithColour, task_values(TASK), TaskRow.__table__) == {"colour"}


def test_a_column_the_model_lacks_is_detected() -> None:
    values = {**task_values(TASK), "colour": "blue"}
    assert unmapped(Task, values, TaskRow.__table__) == {"colour"}
