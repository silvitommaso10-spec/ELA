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

from pydantic import BaseModel, JsonValue, TypeAdapter

from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilityId,
    DecisionId,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceId,
    DeviceStatus,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    IntentId,
    JsonMapping,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PlanId,
    PowerSource,
    PrivacyLevel,
    ProviderUsage,
    StepId,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.infrastructure.persistence.orm import (
    ApprovalRow,
    AuditEventRow,
    AuthorizationRow,
    DeviceRow,
    ExecutionResultRow,
    TaskEventRow,
    TaskPlanRow,
    TaskRow,
)

__all__ = [
    "approval_to_row",
    "approval_values",
    "audit_event_to_row",
    "audit_event_values",
    "authorization_to_row",
    "authorization_values",
    "device_to_row",
    "device_values",
    "event_to_row",
    "plan_to_row",
    "plan_values",
    "result_to_row",
    "result_values",
    "row_to_approval",
    "row_to_audit_event",
    "row_to_authorization",
    "row_to_device",
    "row_to_event",
    "row_to_plan",
    "row_to_result",
    "row_to_task",
    "task_to_row",
    "task_values",
]

_JSON: TypeAdapter[JsonMapping] = TypeAdapter(JsonMapping)


def _plain(payload: JsonMapping) -> dict[str, JsonValue]:
    """A frozen domain payload as plain JSON containers, ready for a ``JSON`` column."""
    return cast(dict[str, JsonValue], _JSON.dump_python(payload, mode="json"))


def _plain_model(value: BaseModel | None) -> dict[str, Any] | None:
    """A frozen value object as one JSON document (``Decimal`` and UUID become strings)."""
    return None if value is None else value.model_dump(mode="json")


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
# TaskPlan
# --------------------------------------------------------------------------------------


def plan_values(plan: TaskPlan) -> dict[str, Any]:
    """Column values of a plan; the steps become one JSON array (ADR 0008)."""
    return {
        "id": plan.id,
        "created_at": plan.created_at,
        "task_id": plan.task_id,
        "goal": plan.goal,
        "steps": [step.model_dump(mode="json") for step in plan.steps],
        "metadata_": _plain(plan.metadata),
    }


def plan_to_row(plan: TaskPlan) -> TaskPlanRow:
    return TaskPlanRow(**plan_values(plan))


def row_to_plan(row: TaskPlanRow) -> TaskPlan:
    return TaskPlan(
        id=PlanId(row.id),
        created_at=row.created_at,
        task_id=TaskId(row.task_id),
        goal=row.goal,
        steps=tuple(TaskStep.model_validate(step) for step in row.steps),
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


# --------------------------------------------------------------------------------------
# Approval
# --------------------------------------------------------------------------------------


def approval_values(approval: Approval) -> dict[str, Any]:
    """Column values of a request for consent, for an insert or the answer's update."""
    return {
        "id": approval.id,
        "created_at": approval.created_at,
        "task_id": approval.task_id,
        "step_id": approval.step_id,
        "capability_id": approval.capability_id,
        "targets": list(approval.targets),
        "prompt": approval.prompt,
        "status": approval.status.value,
        "decision_id": approval.decision_id,
        "responded_at": approval.responded_at,
        "responded_by": approval.responded_by,
        "expires_at": approval.expires_at,
        "metadata_": _plain(approval.metadata),
    }


def approval_to_row(approval: Approval) -> ApprovalRow:
    return ApprovalRow(**approval_values(approval))


def row_to_approval(row: ApprovalRow) -> Approval:
    return Approval(
        id=ApprovalId(row.id),
        created_at=row.created_at,
        task_id=TaskId(row.task_id),
        step_id=StepId(row.step_id),
        capability_id=CapabilityId(row.capability_id),
        targets=tuple(row.targets),
        prompt=row.prompt,
        status=ApprovalStatus(row.status),
        decision_id=None if row.decision_id is None else DecisionId(row.decision_id),
        responded_at=row.responded_at,
        responded_by=row.responded_by,
        expires_at=row.expires_at,
        metadata=row.metadata_,
    )


# --------------------------------------------------------------------------------------
# ExecutionResult
# --------------------------------------------------------------------------------------


def result_values(result: ExecutionResult) -> dict[str, Any]:
    """Column values of a result; ``output`` and ``error`` travel as JSON documents."""
    return {
        "id": result.id,
        "created_at": result.created_at,
        "capability_id": result.capability_id,
        "status": result.status.value,
        "task_id": result.task_id,
        "step_id": result.step_id,
        "tool_name": result.tool_name,
        "device_id": result.device_id,
        "decision_id": result.decision_id,
        "authorization_id": result.authorization_id,
        "output": _plain(result.output),
        "error": _plain_model(result.error),
        "usage": _plain_model(result.usage),
        "duration_ms": result.duration_ms,
        "metadata_": _plain(result.metadata),
    }


def result_to_row(result: ExecutionResult) -> ExecutionResultRow:
    return ExecutionResultRow(**result_values(result))


def row_to_result(row: ExecutionResultRow) -> ExecutionResult:
    return ExecutionResult(
        id=ExecutionId(row.id),
        created_at=row.created_at,
        capability_id=CapabilityId(row.capability_id),
        status=ExecutionStatus(row.status),
        task_id=None if row.task_id is None else TaskId(row.task_id),
        step_id=None if row.step_id is None else StepId(row.step_id),
        tool_name=row.tool_name,
        device_id=None if row.device_id is None else DeviceId(row.device_id),
        decision_id=None if row.decision_id is None else DecisionId(row.decision_id),
        authorization_id=(
            None if row.authorization_id is None else AuthorizationId(row.authorization_id)
        ),
        output=row.output,
        error=None if row.error is None else ErrorMetadata.model_validate(row.error),
        usage=None if row.usage is None else ProviderUsage.model_validate(row.usage),
        duration_ms=row.duration_ms,
        metadata=row.metadata_,
    )


# --------------------------------------------------------------------------------------
# Device
# --------------------------------------------------------------------------------------


def device_values(device: Device) -> dict[str, Any]:
    """Column values of a node; the traits and the tool names travel as JSON arrays (§16)."""
    return {
        "id": device.id,
        "created_at": device.created_at,
        "name": device.name,
        "os": device.os.value,
        "availability": device.availability.value,
        "status": device.status.value,
        "capabilities": [capability.model_dump(mode="json") for capability in device.capabilities],
        "available_tools": list(device.available_tools),
        "performance": device.performance.value,
        "network": device.network.value,
        "power_source": device.power_source.value,
        "privacy": device.privacy.value,
        "current_workload": device.current_workload,
        "last_seen_at": device.last_seen_at,
        "metadata_": _plain(device.metadata),
    }


def device_to_row(device: Device) -> DeviceRow:
    return DeviceRow(**device_values(device))


def row_to_device(row: DeviceRow) -> Device:
    return Device(
        id=DeviceId(row.id),
        created_at=row.created_at,
        name=row.name,
        os=OperatingSystem(row.os),
        availability=DeviceAvailability(row.availability),
        status=DeviceStatus(row.status),
        capabilities=tuple(
            DeviceCapability.model_validate(capability) for capability in row.capabilities
        ),
        available_tools=tuple(row.available_tools),
        performance=PerformanceClass(row.performance),
        network=NetworkKind(row.network),
        power_source=PowerSource(row.power_source),
        privacy=PrivacyLevel(row.privacy),
        current_workload=row.current_workload,
        last_seen_at=row.last_seen_at,
        metadata=row.metadata_,
    )


# --------------------------------------------------------------------------------------
# AuditEvent
# --------------------------------------------------------------------------------------


def audit_event_values(event: AuditEvent) -> dict[str, Any]:
    """Column values of an audit event; the two chain hashes are the log's, not the event's."""
    return {
        "id": event.id,
        "created_at": event.created_at,
        "event_type": event.event_type.value,
        "actor_kind": event.actor.kind.value,
        "actor_id": event.actor.id,
        "summary": event.summary,
        "task_id": event.task_id,
        "step_id": event.step_id,
        "capability_id": event.capability_id,
        "decision_id": event.decision_id,
        "authorization_id": event.authorization_id,
        "device_id": event.device_id,
        "tool_name": event.tool_name,
        "usage": _plain_model(event.usage),
        "error": _plain_model(event.error),
        "payload": _plain(event.payload),
    }


def audit_event_to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(**audit_event_values(event))


def row_to_audit_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        id=AuditEventId(row.id),
        created_at=row.created_at,
        event_type=AuditEventType(row.event_type),
        actor=Actor(kind=ActorKind(row.actor_kind), id=row.actor_id),
        summary=row.summary,
        task_id=None if row.task_id is None else TaskId(row.task_id),
        step_id=None if row.step_id is None else StepId(row.step_id),
        capability_id=None if row.capability_id is None else CapabilityId(row.capability_id),
        decision_id=None if row.decision_id is None else DecisionId(row.decision_id),
        authorization_id=(
            None if row.authorization_id is None else AuthorizationId(row.authorization_id)
        ),
        device_id=None if row.device_id is None else DeviceId(row.device_id),
        tool_name=row.tool_name,
        usage=None if row.usage is None else ProviderUsage.model_validate(row.usage),
        error=None if row.error is None else ErrorMetadata.model_validate(row.error),
        payload=row.payload,
    )
