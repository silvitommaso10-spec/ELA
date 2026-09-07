"""What the API accepts and returns, written out (ADR 0023 §6).

The wire shape is a **decision**, so it is declared here instead of being ``model_dump()`` of a
domain entity: a field added to the domain tomorrow must not leave the machine because nobody
noticed. The names follow the domain's — ``required_capabilities``, ``dependencies`` — because a
second vocabulary for the same things would be a translation table nobody asked for.

Two leaf values are reused as they are: :class:`~ela.domain.ProviderUsage` and
:class:`~ela.domain.ErrorMetadata`. They are values and not entities, and what an
:class:`~ela.domain.AuditEvent` carries in them *is* their shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from pydantic import BaseModel, Field

from ela.domain import (
    Actor,
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    CapabilityId,
    DeviceCapabilityName,
    DeviceId,
    ErrorMetadata,
    JsonMapping,
    PlanId,
    ProviderUsage,
    RiskLevel,
    StepId,
    StepState,
    Task,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.tasks.graph import GraphState

__all__ = [
    "AnswerIn",
    "ApprovalOut",
    "AuditEventOut",
    "CancelIn",
    "DiagnosticsOut",
    "HealthOut",
    "PlanIn",
    "RunOut",
    "StepIn",
    "StepOut",
    "TaskCreate",
    "TaskDetail",
    "TaskOut",
]


def _plain(entity: BaseModel, field: str) -> JsonMapping:
    """A frozen JSON field as plain JSON containers again.

    The domain stores free-form JSON deeply immutable — mappings become ``MappingProxyType``,
    arrays become tuples — and a tuple is not a JSON value: handing one straight to a response
    model would be refused by the very type that describes it. The domain's own serializer is
    what turns it back, so the API does not keep a second opinion about what JSON is.
    """
    return cast(JsonMapping, entity.model_dump()[field])


class TaskCreate(BaseModel):
    """What the user asked. The plan comes separately, and today by hand (ADR 0023 §6)."""

    text: Annotated[str, Field(min_length=1)]
    goal: str | None = None
    deadline: datetime | None = None


class StepIn(BaseModel):
    """One step of a plan written by the caller, until the Planner (§13) writes them.

    ``id`` is the caller's: ``dependencies`` name the other steps by id, and a step id minted here
    would leave the caller with no way to express the shape of its own plan.
    """

    id: UUID
    goal: str
    required_capabilities: tuple[CapabilityId, ...] = ()
    arguments: JsonMapping = Field(default_factory=dict)
    preferred_device_traits: tuple[DeviceCapabilityName, ...] = ()
    dependencies: tuple[UUID, ...] = ()
    risk: RiskLevel
    expected_result: str
    success_conditions: tuple[str, ...] = ()
    requires_authorization: bool = False

    def to_domain(self, created_at: datetime) -> TaskStep:
        return TaskStep(
            id=StepId(self.id),
            created_at=created_at,
            goal=self.goal,
            required_capabilities=self.required_capabilities,
            arguments=self.arguments,
            preferred_device_traits=self.preferred_device_traits,
            dependencies=tuple(StepId(one) for one in self.dependencies),
            risk=self.risk,
            expected_result=self.expected_result,
            success_conditions=self.success_conditions,
            requires_authorization=self.requires_authorization,
        )


class PlanIn(BaseModel):
    """A plan for a task that has none. That it is a DAG is checked where every plan is."""

    goal: str
    steps: Annotated[tuple[StepIn, ...], Field(min_length=1)]

    def to_domain(self, task_id: UUID, plan_id: UUID, created_at: datetime) -> TaskPlan:
        return TaskPlan(
            id=PlanId(plan_id),
            created_at=created_at,
            task_id=task_id,  # type: ignore[arg-type]  # TaskId is a NewType over UUID
            goal=self.goal,
            steps=tuple(step.to_domain(created_at) for step in self.steps),
        )


class AnswerIn(BaseModel):
    """Which request is being answered. *Who* answers is ``ELA_USER_NAME`` (ADR 0023 §8)."""

    approval_id: UUID


class CancelIn(BaseModel):
    """Why the user stopped the task (§65). It reaches the audit trail as the reason."""

    reason: str = ""


class TaskOut(BaseModel):
    id: UUID
    created_at: datetime
    goal: str
    state: TaskState
    intent_id: UUID | None
    plan_id: UUID | None
    parent_id: UUID | None
    deadline: datetime | None

    @classmethod
    def of(cls, task: Task) -> TaskOut:
        return cls(
            id=task.id,
            created_at=task.created_at,
            goal=task.goal,
            state=task.state,
            intent_id=task.intent_id,
            plan_id=task.plan_id,
            parent_id=task.parent_id,
            deadline=task.deadline,
        )


class StepOut(BaseModel):
    """A step and where it stands.

    ``arguments`` are here: they are the user's own content coming back to the user, on loopback,
    behind the user's token — and a task whose steps show no arguments does not say what it does.
    The audit log is another matter, and architecture rule 23 keeps them out of it (ADR 0023 §6).
    """

    id: UUID
    goal: str
    state: StepState
    required_capabilities: tuple[CapabilityId, ...]
    arguments: JsonMapping
    preferred_device_traits: tuple[DeviceCapabilityName, ...]
    dependencies: tuple[UUID, ...]
    risk: RiskLevel
    expected_result: str
    success_conditions: tuple[str, ...]
    requires_authorization: bool

    @classmethod
    def of(cls, step: TaskStep, state: StepState) -> StepOut:
        return cls(
            id=step.id,
            goal=step.goal,
            state=state,
            required_capabilities=step.required_capabilities,
            arguments=_plain(step, "arguments"),
            preferred_device_traits=step.preferred_device_traits,
            dependencies=tuple(step.dependencies),
            risk=step.risk,
            expected_result=step.expected_result,
            success_conditions=step.success_conditions,
            requires_authorization=step.requires_authorization,
        )


class TaskDetail(TaskOut):
    """A task with its plan, in topological order. Empty steps means: no plan yet."""

    steps: tuple[StepOut, ...] = ()

    @classmethod
    def of_graph(cls, task: Task, graph: GraphState | None) -> TaskDetail:
        detail = cls(**TaskOut.of(task).model_dump())
        if graph is None:
            return detail
        steps = tuple(
            StepOut.of(graph.graph.step(step_id), graph.states[step_id])
            for step_id in graph.graph.order
        )
        return detail.model_copy(update={"steps": steps})


class RunOut(BaseModel):
    """What one call of ``run`` did: where the task is now, and which steps it executed."""

    task: TaskOut
    outcome: str
    steps: tuple[UUID, ...]


class ApprovalOut(BaseModel):
    """A request for the user's consent (§30). ``prompt`` is what the user is asked."""

    id: UUID
    created_at: datetime
    task_id: UUID
    step_id: UUID
    capability_id: CapabilityId
    targets: tuple[str, ...]
    prompt: str
    status: ApprovalStatus
    expires_at: datetime | None
    responded_at: datetime | None
    responded_by: str | None

    @classmethod
    def of(cls, approval: Approval) -> ApprovalOut:
        return cls(
            id=approval.id,
            created_at=approval.created_at,
            task_id=approval.task_id,
            step_id=approval.step_id,
            capability_id=approval.capability_id,
            targets=approval.targets,
            prompt=approval.prompt,
            status=approval.status,
            expires_at=approval.expires_at,
            responded_at=approval.responded_at,
            responded_by=approval.responded_by,
        )


class AuditEventOut(BaseModel):
    """One entry of the append-only trail (§32), as it is stored.

    It carries no arguments and no output, and not because this schema leaves them out: an
    ``AuditEvent`` never holds them (§57, architecture rule 23).
    """

    id: UUID
    created_at: datetime
    event_type: AuditEventType
    actor: Actor
    summary: str
    task_id: UUID | None
    step_id: UUID | None
    capability_id: CapabilityId | None
    decision_id: UUID | None
    authorization_id: UUID | None
    device_id: DeviceId | None
    tool_name: str | None
    usage: ProviderUsage | None
    error: ErrorMetadata | None
    payload: JsonMapping

    @classmethod
    def of(cls, event: AuditEvent) -> AuditEventOut:
        return cls(
            id=event.id,
            created_at=event.created_at,
            event_type=event.event_type,
            actor=event.actor,
            summary=event.summary,
            task_id=event.task_id,
            step_id=event.step_id,
            capability_id=event.capability_id,
            decision_id=event.decision_id,
            authorization_id=event.authorization_id,
            device_id=event.device_id,
            tool_name=event.tool_name,
            usage=event.usage,
            error=event.error,
            payload=_plain(event, "payload"),
        )


class HealthOut(BaseModel):
    """Alive, and the database answered: ``/health`` reads through the port to say so."""

    status: str
    database: str
    now: datetime


class DiagnosticsOut(BaseModel):
    """How ELA is composed right now — never a secret, never the user's content (ADR 0023 §6)."""

    version: str
    database: str
    workspace: str
    user_name: str
    providers: dict[str, str]
    task_types: tuple[str, ...]
    default_profile: str
    capabilities: tuple[CapabilityId, ...]
    tools: tuple[str, ...]
    devices: dict[str, str]
    tasks: dict[str, int]
    pending_approvals: int
    recovered: dict[str, int]
