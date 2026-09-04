"""The only bridge between domain entities and ORM rows: one function per direction (ADR 0006).

Field by field, on purpose. A ``model_dump()`` in and a ``model_validate(row.__dict__)`` out would
let a new domain field reach the database untested and unmigrated; here a new field has to be
named twice, and ``tests/infrastructure/persistence/test_mappers.py`` checks that no field of the
model is forgotten.

Rehydrating is not transitioning: ``row_to_task`` builds a :class:`~ela.domain.Task` in the state
the database holds, which is why this module is exempt by name from rule 5 (ADR 0004) — the only
module besides the state machine.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import JsonValue, TypeAdapter

from ela.domain import (
    ApprovalId,
    Authorization,
    AuthorizationId,
    CapabilityId,
    IntentId,
    JsonMapping,
    PlanId,
    StepId,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.infrastructure.persistence.orm import AuthorizationRow, TaskEventRow, TaskRow

__all__ = [
    "authorization_to_row",
    "authorization_values",
    "event_to_row",
    "row_to_authorization",
    "row_to_event",
    "row_to_task",
    "task_to_row",
    "task_values",
]

_JSON: TypeAdapter[JsonMapping] = TypeAdapter(JsonMapping)


def _plain(payload: JsonMapping) -> dict[str, JsonValue]:
    """A frozen domain payload as plain JSON containers, ready for a ``JSON`` column."""
    return cast(dict[str, JsonValue], _JSON.dump_python(payload, mode="json"))


def _optional_state(value: TaskState | None) -> str | None:
    return None if value is None else value.value


# --------------------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------------------


def task_values(task: Task) -> dict[str, Any]:
    """Column values of a task, for an insert or an update."""
    return {
        "id": task.id,
        "created_at": task.created_at,
        "goal": task.goal,
        "state": task.state.value,
        "intent_id": task.intent_id,
        "plan_id": task.plan_id,
        "parent_id": task.parent_id,
        "deadline": task.deadline,
        "metadata_": _plain(task.metadata),
    }


def task_to_row(task: Task) -> TaskRow:
    return TaskRow(**task_values(task))


def row_to_task(row: TaskRow) -> Task:
    return Task(
        id=TaskId(row.id),
        created_at=row.created_at,
        goal=row.goal,
        state=TaskState(row.state),
        intent_id=None if row.intent_id is None else IntentId(row.intent_id),
        plan_id=None if row.plan_id is None else PlanId(row.plan_id),
        parent_id=None if row.parent_id is None else TaskId(row.parent_id),
        deadline=row.deadline,
        metadata=row.metadata_,
    )


# --------------------------------------------------------------------------------------
# TaskEvent
# --------------------------------------------------------------------------------------


def event_to_row(event: TaskEvent) -> TaskEventRow:
    return TaskEventRow(
        id=event.id,
        task_id=event.task_id,
        created_at=event.created_at,
        event_type=event.event_type.value,
        step_id=event.step_id,
        previous_state=_optional_state(event.previous_state),
        new_state=_optional_state(event.new_state),
        message=event.message,
        metadata_=_plain(event.metadata),
    )


def _optional_task_state(value: str | None) -> TaskState | None:
    return None if value is None else TaskState(value)


def row_to_event(row: TaskEventRow) -> TaskEvent:
    return TaskEvent(
        id=TaskEventId(row.id),
        created_at=row.created_at,
        task_id=TaskId(row.task_id),
        event_type=TaskEventType(row.event_type),
        step_id=None if row.step_id is None else StepId(row.step_id),
        previous_state=_optional_task_state(row.previous_state),
        new_state=_optional_task_state(row.new_state),
        message=row.message,
        metadata=row.metadata_,
    )


# --------------------------------------------------------------------------------------
# Authorization
# --------------------------------------------------------------------------------------


def authorization_values(authorization: Authorization) -> dict[str, Any]:
    """Column values of a grant; ``uses`` is not among them, it belongs to the store."""
    return {
        "id": authorization.id,
        "created_at": authorization.created_at,
        "capability_id": authorization.capability_id,
        "scope": list(authorization.scope),
        "granted_by": authorization.granted_by,
        "approval_id": authorization.approval_id,
        "task_id": authorization.task_id,
        "step_id": authorization.step_id,
        "expires_at": authorization.expires_at,
        "max_uses": authorization.max_uses,
        "metadata_": _plain(authorization.metadata),
    }


def authorization_to_row(authorization: Authorization) -> AuthorizationRow:
    return AuthorizationRow(**authorization_values(authorization))


def row_to_authorization(row: AuthorizationRow) -> Authorization:
    return Authorization(
        id=AuthorizationId(row.id),
        created_at=row.created_at,
        capability_id=CapabilityId(row.capability_id),
        scope=tuple(row.scope),
        granted_by=row.granted_by,
        approval_id=None if row.approval_id is None else ApprovalId(row.approval_id),
        task_id=None if row.task_id is None else TaskId(row.task_id),
        step_id=None if row.step_id is None else StepId(row.step_id),
        expires_at=row.expires_at,
        max_uses=row.max_uses,
        metadata=row.metadata_,
    )
