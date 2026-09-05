"""Task Engine (spec §14): the one entry point of a task's life cycle.

Every operation here goes through the state machine of M1.2 (:func:`ela.tasks.state_machine.
transition`), persists the task and its :class:`~ela.domain.TaskEvent` in the
:class:`~ela.ports.TaskRepository`, and writes one :class:`~ela.domain.AuditEvent` in the
:class:`~ela.ports.AuditLog` (§32). Nothing else in the Core changes the state of a task: rule 5
(ADR 0004) keeps the state machine the only place that moves a task, rule 10 (ADR 0008) keeps this
module the only caller of the state machine.

The engine is table-driven. :data:`OPERATIONS` says, for each operation, from which states it
applies, where it leads, which audit type it writes and which key makes it idempotent; the table
is checked against ADR 0008 by ``tests/docs/test_adr_engine.py`` and against the transition table
by ``tests/tasks/test_engine_table.py`` (every legal transition of ADR 0004 is some operation's).

Three rules run through every operation (ADR 0008):

* **The stored task is the truth.** Methods take a ``TaskId``, reload the task under a per-task
  lock and apply the table to what is stored, never to a caller's copy.
* **Already applied is a no-op, differently applied is an error.** An operation whose target is
  the stored state returns the stored task and writes nothing; if the operation has a key (an
  approval, a decision, a result) the key must be the one the trail recorded, else
  :class:`~ela.tasks.errors.TaskEngineError` (§14 "evitare duplicazioni", §33).
* **Save, then event, then audit.** There is no unit of work across ports (ADR 0006 §4); this
  order is the one where a crash in the middle leaves a gap, never a duplicate, on retry.

The clock is checked before every write: an instant earlier than the last one recorded for the
task is a fault and raises :class:`~ela.tasks.errors.ClockSkewError` (the deferral of M1.2).
Recovery (§14 "recuperare attività") is :meth:`TaskEngine.recover`: EXECUTING tasks without a
sign of life for ``orphan_after`` are failed with code :data:`ORPHANED`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Final, NamedTuple
from uuid import UUID, uuid5

from pydantic import JsonValue

from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    DecisionId,
    DeviceId,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    UserIntent,
)
from ela.ports import AlreadyExistsError, AuditLog, Clock, IdGenerator, TaskRepository
from ela.tasks.errors import ClockSkewError, TaskEngineError
from ela.tasks.state_machine import (
    TERMINAL_STATES,
    IllegalTransitionError,
    can_transition,
    transition,
)

__all__ = [
    "LIVE_STATES",
    "OPERATIONS",
    "ORPHANED",
    "SYSTEM_ACTOR",
    "TASK_NAMESPACE",
    "Operation",
    "TaskEngine",
]

_S = TaskState

TASK_NAMESPACE: Final = UUID("6f1c2a4e-3b7d-4d8a-9e21-5c0b7a1d2e33")
"""The UUID namespace of root task ids: ``TaskId = uuid5(TASK_NAMESPACE, str(intent.id))``.

Arbitrary and fixed forever: one intent gives one root task, however many times the request is
retried (ADR 0008 §8). Changing it would change the id of every root task.
"""

ORPHANED: Final = "orphaned"
"""The error code of a task failed by :meth:`TaskEngine.recover`."""

SYSTEM_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="task-engine")
"""Who acts when nobody asked: expiries and recovery (ADR 0003, ``ActorKind.SYSTEM``)."""

LIVE_STATES: Final[frozenset[TaskState]] = frozenset(TaskState) - TERMINAL_STATES
"""The states a task can still leave: the sources of ``cancel`` and ``expire`` (ADR 0004 P3)."""


class Operation(NamedTuple):
    """One row of :data:`OPERATIONS`: what an operation is allowed to do and how it is recorded."""

    name: str
    sources: frozenset[TaskState]
    target: TaskState
    audit_type: AuditEventType
    key: str | None
    """The metadata field that makes the operation idempotent, or ``None`` for state alone."""


OPERATIONS: Final[Mapping[str, Operation]] = MappingProxyType(
    {
        op.name: op
        for op in (
            Operation(
                "start_planning",
                frozenset({_S.CREATED}),
                _S.PLANNING,
                AuditEventType.TASK_PLANNING_STARTED,
                None,
            ),
            Operation(
                "request_approval",
                frozenset({_S.PLANNING, _S.EXECUTING}),
                _S.WAITING_APPROVAL,
                AuditEventType.APPROVAL_REQUESTED,
                "approval_id",
            ),
            Operation(
                "approve",
                frozenset({_S.WAITING_APPROVAL}),
                _S.QUEUED,
                AuditEventType.APPROVAL_RESOLVED,
                "approval_id",
            ),
            Operation(
                "deny_by_approval",
                frozenset({_S.WAITING_APPROVAL}),
                _S.DENIED,
                AuditEventType.APPROVAL_RESOLVED,
                "approval_id",
            ),
            Operation(
                "deny_by_decision",
                frozenset({_S.PLANNING, _S.EXECUTING}),
                _S.DENIED,
                AuditEventType.TASK_DENIED,
                "decision_id",
            ),
            Operation(
                "queue",
                frozenset({_S.PLANNING, _S.EXECUTING}),
                _S.QUEUED,
                AuditEventType.TASK_QUEUED,
                None,
            ),
            Operation(
                "start", frozenset({_S.QUEUED}), _S.EXECUTING, AuditEventType.TASK_STARTED, None
            ),
            Operation(
                "complete",
                frozenset({_S.EXECUTING}),
                _S.COMPLETED,
                AuditEventType.TASK_COMPLETED,
                "result_id",
            ),
            Operation(
                "fail",
                frozenset({_S.PLANNING, _S.EXECUTING}),
                _S.FAILED,
                AuditEventType.TASK_FAILED,
                None,
            ),
            Operation("cancel", LIVE_STATES, _S.CANCELLED, AuditEventType.TASK_CANCELLED, None),
            Operation("expire", LIVE_STATES, _S.EXPIRED, AuditEventType.TASK_EXPIRED, None),
            Operation(
                "recover", frozenset({_S.EXECUTING}), _S.FAILED, AuditEventType.TASK_FAILED, None
            ),
        )
    }
)
"""The operations that change state, as decided in ADR 0008 §3, in the order of its table.

``create``, ``plan`` and ``heartbeat`` are not here: they do not move the task through the
transition table. ``deny`` is two rows because it records two different facts: an approval the
user rejected (``APPROVAL_RESOLVED``) and a decision of the Guardian (``TASK_DENIED``).
"""

Guard = Callable[[Task, datetime], None]
Payload = Mapping[str, JsonValue]


def _last_seen(task: Task, events: tuple[TaskEvent, ...]) -> datetime:
    """The last instant anything was recorded for the task: its trail, or its birth."""
    return max([task.created_at, *(event.created_at for event in events)])


def _last_change(events: tuple[TaskEvent, ...]) -> Mapping[str, JsonValue]:
    """The metadata of the last state change: which operation moved the task, with which key."""
    for event in reversed(events):
        if event.event_type is TaskEventType.STATE_CHANGED:
            return event.metadata
    return {}


def _require_plan(task: Task, _now: datetime) -> None:
    if task.plan_id is None:
        raise TaskEngineError(task.id, "the task has no plan: nothing to queue or approve")


def _require_deadline_passed(task: Task, now: datetime) -> None:
    if task.deadline is None:
        raise TaskEngineError(task.id, "the task has no deadline: it cannot expire")
    if task.deadline > now:
        raise TaskEngineError(
            task.id, f"the deadline {task.deadline.isoformat()} has not passed at {now.isoformat()}"
        )


class TaskEngine:
    """The life cycle of tasks, on a repository, an audit log, a clock and an id source (§14).

    ``actor`` is who the engine says it is in the audit trail when ELA acts; the user acts through
    an :class:`~ela.domain.Approval`, the system through expiry and recovery. ``orphan_after`` is
    how long an EXECUTING task may stay silent before :meth:`recover` fails it.
    """

    def __init__(
        self,
        repository: TaskRepository,
        audit_log: AuditLog,
        clock: Clock,
        ids: IdGenerator,
        *,
        actor: Actor,
        orphan_after: timedelta,
    ) -> None:
        if orphan_after <= timedelta(0):
            raise ValueError(f"orphan_after must be positive, not {orphan_after}")
        self._repository = repository
        self._audit_log = audit_log
        self._clock = clock
        self._ids = ids
        self._actor = actor
        self._orphan_after = orphan_after
        self._locks: dict[TaskId, asyncio.Lock] = {}

    # ----------------------------------------------------------------------------------
    # Operations that do not go through the transition table
    # ----------------------------------------------------------------------------------

    async def create(
        self, intent: UserIntent, *, goal: str | None = None, deadline: datetime | None = None
    ) -> Task:
        """The root task of ``intent``: created once, returned as stored on every retry."""
        task_id = TaskId(uuid5(TASK_NAMESPACE, str(intent.id)))
        async with self._lock(task_id):
            now = self._clock.now()
            task = Task(
                id=task_id,
                created_at=now,
                goal=intent.text if goal is None else goal,
                state=TaskState.CREATED,
                intent_id=intent.id,
                deadline=deadline,
            )
            try:
                await self._repository.add(task)
            except AlreadyExistsError:
                return await self._repository.get(task_id)
            await self._audit_log.append(
                AuditEvent(
                    id=AuditEventId(self._ids.new_uuid()),
                    created_at=now,
                    event_type=AuditEventType.TASK_CREATED,
                    actor=self._actor,
                    summary=f"create: task {task_id} from intent {intent.id}",
                    task_id=task_id,
                    payload={
                        "operation": "create",
                        "intent_id": str(intent.id),
                        "channel": intent.channel.value,
                        "goal": task.goal,
                    },
                )
            )
            return task

    async def plan(self, task_id: TaskId, plan: TaskPlan) -> Task:
        """Attach ``plan`` to a PLANNING task: store it, set ``plan_id``, record and audit it."""
        if plan.task_id != task_id:
            raise TaskEngineError(task_id, f"the plan belongs to task {plan.task_id}")
        async with self._lock(task_id):
            task = await self._repository.get(task_id)
            if task.plan_id is not None:
                if task.plan_id == plan.id:
                    return task
                raise TaskEngineError(task_id, f"the task already has plan {task.plan_id}")
            if task.state is not TaskState.PLANNING:
                raise TaskEngineError(task_id, f"a plan needs a PLANNING task, not {task.state}")
            now = self._now(task, await self._repository.events(task_id))
            try:
                await self._repository.add_plan(plan)
            except AlreadyExistsError:
                # Stored before a crash that came before ``save``: continue with the same plan.
                stored = await self._repository.plan(task_id)
                if stored.id != plan.id:
                    raise TaskEngineError(task_id, f"a plan {stored.id} is stored") from None
            planned = task.model_copy(update={"plan_id": plan.id})
            await self._repository.save(planned)
            await self._repository.append_event(
                TaskEvent(
                    id=TaskEventId(self._ids.new_uuid()),
                    created_at=now,
                    task_id=task_id,
                    event_type=TaskEventType.PLAN_ATTACHED,
                    message=plan.goal,
                    metadata={"operation": "plan", "plan_id": str(plan.id)},
                )
            )
            await self._audit_log.append(
                AuditEvent(
                    id=AuditEventId(self._ids.new_uuid()),
                    created_at=now,
                    event_type=AuditEventType.PLAN_CREATED,
                    actor=self._actor,
                    summary=f"plan: {len(plan.steps)} step(s) for task {task_id}",
                    task_id=task_id,
                    payload={
                        "operation": "plan",
                        "plan_id": str(plan.id),
                        "steps": len(plan.steps),
                        "goal": plan.goal,
                    },
                )
            )
            return planned

    async def heartbeat(self, task_id: TaskId) -> Task:
        """A sign of life for an EXECUTING task: a trail event, no audit (ADR 0008 §5)."""
        async with self._lock(task_id):
            task = await self._repository.get(task_id)
            if task.state is not TaskState.EXECUTING:
                raise TaskEngineError(
                    task_id, f"a heartbeat needs an EXECUTING task, not {task.state}"
                )
            now = self._now(task, await self._repository.events(task_id))
            await self._repository.append_event(
                TaskEvent(
                    id=TaskEventId(self._ids.new_uuid()),
                    created_at=now,
                    task_id=task_id,
                    event_type=TaskEventType.HEARTBEAT,
                )
            )
            return task

    async def recover(self) -> tuple[Task, ...]:
        """Fail every EXECUTING task silent for ``orphan_after`` or longer (§14, closed bound)."""
        now = self._clock.now()
        marked: list[Task] = []
        for task in await self._repository.tasks(states=frozenset({TaskState.EXECUTING})):
            last_seen = _last_seen(task, await self._repository.events(task.id))
            if now - last_seen < self._orphan_after:
                continue
            error = ErrorMetadata(
                code=ORPHANED,
                message=f"no sign of life since {last_seen.isoformat()}",
                retryable=True,
                details={
                    "last_seen_at": last_seen.isoformat(),
                    "orphan_after_seconds": self._orphan_after.total_seconds(),
                },
            )
            marked.append(
                await self._apply(
                    OPERATIONS["recover"],
                    task.id,
                    actor=SYSTEM_ACTOR,
                    reason=error.message,
                    error=error,
                    payload={"code": ORPHANED},
                )
            )
        return tuple(marked)

    # ----------------------------------------------------------------------------------
    # Operations of the table
    # ----------------------------------------------------------------------------------

    async def start_planning(self, task_id: TaskId) -> Task:
        """CREATED → PLANNING: the planner took the task."""
        return await self._apply(
            OPERATIONS["start_planning"],
            task_id,
            actor=self._actor,
            reason="the planner took the task",
        )

    async def request_approval(self, task_id: TaskId, approval: Approval) -> Task:
        """PLANNING/EXECUTING → WAITING_APPROVAL: a step needs the user's consent (§30)."""
        self._check_approval(task_id, approval, ApprovalStatus.PENDING)
        return await self._apply(
            OPERATIONS["request_approval"],
            task_id,
            actor=self._actor,
            reason=approval.prompt,
            key=approval.id,
            payload={"step_id": str(approval.step_id), "capability_id": approval.capability_id},
            guard=_require_plan,
        )

    async def approve(self, task_id: TaskId, approval: Approval) -> Task:
        """WAITING_APPROVAL → QUEUED: the user granted the approval."""
        self._check_approval(task_id, approval, ApprovalStatus.GRANTED)
        return await self._apply(
            OPERATIONS["approve"],
            task_id,
            actor=_user_actor(task_id, approval),
            reason=f"approved by {approval.responded_by}",
            key=approval.id,
            payload={"status": approval.status.value, "responded_by": approval.responded_by},
        )

    async def deny(
        self,
        task_id: TaskId,
        *,
        decision: PermissionDecision | None = None,
        approval: Approval | None = None,
    ) -> Task:
        """→ DENIED, by the user (a rejected approval) or by the Guardian (a DENIED decision)."""
        if approval is not None and decision is None:
            self._check_approval(task_id, approval, ApprovalStatus.REJECTED)
            return await self._apply(
                OPERATIONS["deny_by_approval"],
                task_id,
                actor=_user_actor(task_id, approval),
                reason=f"rejected by {approval.responded_by}",
                key=approval.id,
                payload={"status": approval.status.value, "responded_by": approval.responded_by},
            )
        if decision is not None and approval is None:
            if decision.outcome is not PermissionOutcome.DENIED:
                raise TaskEngineError(task_id, f"the decision is {decision.outcome}, not DENIED")
            if decision.task_id != task_id:
                raise TaskEngineError(task_id, f"the decision is about task {decision.task_id}")
            return await self._apply(
                OPERATIONS["deny_by_decision"],
                task_id,
                actor=self._actor,
                reason=decision.reason,
                key=decision.id,
                decision_id=decision.id,
                payload={"capability_id": decision.capability_id},
            )
        raise TaskEngineError(task_id, "deny needs exactly one of decision and approval")

    async def queue(self, task_id: TaskId, *, reason: str = "") -> Task:
        """PLANNING/EXECUTING → QUEUED: ready to run, or interrupted and to be resumed (§15)."""
        return await self._apply(
            OPERATIONS["queue"], task_id, actor=self._actor, reason=reason, guard=_require_plan
        )

    async def start(self, task_id: TaskId, *, device_id: DeviceId | None = None) -> Task:
        """QUEUED → EXECUTING: a node took the task (§17 decides which)."""
        return await self._apply(
            OPERATIONS["start"],
            task_id,
            actor=self._actor,
            reason="" if device_id is None else f"on device {device_id}",
            device_id=device_id,
        )

    async def complete(self, task_id: TaskId, result: ExecutionResult) -> Task:
        """EXECUTING → COMPLETED, on a result that says SUCCEEDED (§63)."""
        if result.task_id != task_id:
            raise TaskEngineError(task_id, f"the result is about task {result.task_id}")
        if result.status is not ExecutionStatus.SUCCEEDED:
            raise TaskEngineError(task_id, f"the result is {result.status}, not SUCCEEDED")
        return await self._apply(
            OPERATIONS["complete"],
            task_id,
            actor=self._actor,
            reason="",
            key=result.id,
            device_id=result.device_id,
            payload={"capability_id": result.capability_id, "tool_name": result.tool_name},
        )

    async def fail(self, task_id: TaskId, error: ErrorMetadata) -> Task:
        """PLANNING/EXECUTING → FAILED, with the error turned into information (§64)."""
        return await self._apply(
            OPERATIONS["fail"],
            task_id,
            actor=self._actor,
            reason=error.message,
            error=error,
            payload={"code": error.code},
        )

    async def cancel(
        self, task_id: TaskId, *, reason: str = "", actor: Actor | None = None
    ) -> Task:
        """→ CANCELLED from any live state, by the user (§65) or by ELA."""
        return await self._apply(
            OPERATIONS["cancel"],
            task_id,
            actor=self._actor if actor is None else actor,
            reason=reason,
        )

    async def expire(self, task_id: TaskId) -> Task:
        """→ EXPIRED from any live state, once ``deadline <= now`` (closed, ADR 0005 §2-bis)."""
        return await self._apply(
            OPERATIONS["expire"],
            task_id,
            actor=SYSTEM_ACTOR,
            reason="the deadline passed",
            guard=_require_deadline_passed,
        )

    # ----------------------------------------------------------------------------------
    # The one write path
    # ----------------------------------------------------------------------------------

    def _lock(self, task_id: TaskId) -> asyncio.Lock:
        return self._locks.setdefault(task_id, asyncio.Lock())

    def _now(self, task: Task, events: tuple[TaskEvent, ...]) -> datetime:
        """The clock, refused if it went backwards with respect to the task (ADR 0008 §7)."""
        now = self._clock.now()
        last_seen = _last_seen(task, events)
        if now < last_seen:
            raise ClockSkewError(task.id, now, last_seen)
        return now

    def _check_approval(self, task_id: TaskId, approval: Approval, status: ApprovalStatus) -> None:
        if approval.task_id != task_id:
            raise TaskEngineError(task_id, f"the approval is about task {approval.task_id}")
        if approval.status is not status:
            raise TaskEngineError(task_id, f"the approval is {approval.status}, not {status}")

    async def _apply(
        self,
        op: Operation,
        task_id: TaskId,
        *,
        actor: Actor,
        reason: str,
        key: UUID | None = None,
        payload: Payload | None = None,
        error: ErrorMetadata | None = None,
        decision_id: DecisionId | None = None,
        device_id: DeviceId | None = None,
        guard: Guard | None = None,
    ) -> Task:
        async with self._lock(task_id):
            task = await self._repository.get(task_id)
            events = await self._repository.events(task_id)
            if task.state is op.target:
                return self._already_applied(op, task, events, key)
            if task.state not in op.sources:
                if can_transition(task.state, op.target):
                    raise TaskEngineError(
                        task_id,
                        f"{op.name} does not apply from {task.state}: another operation does",
                    )
                raise IllegalTransitionError(task_id, task.state, op.target)
            now = self._now(task, events)
            if guard is not None:
                guard(task, now)
            keyed: dict[str, JsonValue] = {} if op.key is None else {op.key: str(key)}
            moved = transition(
                task,
                op.target,
                event_id=TaskEventId(self._ids.new_uuid()),
                now=now,
                message=reason,
                metadata={"operation": op.name, **keyed},
            )
            await self._repository.save(moved.task)
            await self._repository.append_event(moved.event)
            await self._audit_log.append(
                AuditEvent(
                    id=AuditEventId(self._ids.new_uuid()),
                    created_at=now,
                    event_type=op.audit_type,
                    actor=actor,
                    summary=f"{op.name}: {task.state.value} -> {op.target.value}"
                    + (f" ({reason})" if reason else ""),
                    task_id=task_id,
                    decision_id=decision_id,
                    device_id=device_id,
                    error=error,
                    payload={
                        "operation": op.name,
                        "previous_state": task.state.value,
                        "new_state": op.target.value,
                        "reason": reason,
                        **keyed,
                        **({} if payload is None else payload),
                    },
                )
            )
            return moved.task

    def _already_applied(
        self, op: Operation, task: Task, events: tuple[TaskEvent, ...], key: UUID | None
    ) -> Task:
        """The no-op of an already applied operation, unless it was applied with another key.

        Same operation *and* same key: a request and its grant share the approval id, so the
        key alone would mistake a task QUEUED by hand for one queued by that approval.
        """
        if op.key is None:
            return task
        recorded = _last_change(events)
        if recorded.get("operation") == op.name and recorded.get(op.key) == str(key):
            return task
        raise TaskEngineError(
            task.id,
            f"already {op.target.value} with {op.key} {recorded.get(op.key)!r} "
            f"(by {recorded.get('operation')}), not {key}",
        )


def _user_actor(task_id: TaskId, approval: Approval) -> Actor:
    """Who answered the approval; a resolved approval without a name is refused (§33)."""
    if not approval.responded_by:
        raise TaskEngineError(task_id, f"approval {approval.id} does not say who responded")
    return Actor(kind=ActorKind.USER, id=approval.responded_by)
