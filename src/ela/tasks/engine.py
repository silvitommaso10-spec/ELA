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
:data:`STEP_OPERATIONS` does the same for the steps of the plan (M3.2, ADR 0009): a step's state
is folded from the ``STEP_*`` events of the trail by :mod:`ela.tasks.graph`, and this module is
the only writer of those events (rule 11).

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
sign of life for ``orphan_after`` are failed with code :data:`ORPHANED`, and WAITING_APPROVAL
tasks whose request for consent has expired are EXPIRED (M5.3, ADR 0015 §6): the engine reads
the :class:`~ela.ports.ApprovalStore` for that and writes nothing to it — the request stays as
it was asked, the fact is ``TASK_EXPIRED``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
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
    StepId,
    StepState,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    UserIntent,
)
from ela.ports import (
    AlreadyExistsError,
    ApprovalStore,
    AuditLog,
    Clock,
    IdGenerator,
    TaskRepository,
)
from ela.tasks.errors import ClockSkewError, IllegalStepTransitionError, TaskEngineError
from ela.tasks.graph import STEP_EVENTS, GraphState, TaskGraph
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
    "STEP_OPERATIONS",
    "SYSTEM_ACTOR",
    "TASK_NAMESPACE",
    "Operation",
    "RecoverySummary",
    "StepOperation",
    "TaskEngine",
]

_S = TaskState
_P = StepState

TASK_NAMESPACE: Final = UUID("6f1c2a4e-3b7d-4d8a-9e21-5c0b7a1d2e33")
"""The UUID namespace of root task ids: ``TaskId = uuid5(TASK_NAMESPACE, str(intent.id))``.

Arbitrary and fixed forever: one intent gives one root task, however many times the request is
retried (ADR 0008 §8). Changing it would change the id of every root task.
"""

ORPHANED: Final = "orphaned"
"""The error code of a task failed by :meth:`TaskEngine.recover`."""

SYSTEM_ACTOR: Final = Actor(kind=ActorKind.SYSTEM, id="task-engine")
"""Who acts when nobody asked: expiries, recovery, the cancellation of dependent steps."""

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


class StepOperation(NamedTuple):
    """One row of :data:`STEP_OPERATIONS`: a move of one step of the plan (ADR 0009)."""

    name: str
    sources: frozenset[StepState]
    target: StepState
    event_type: TaskEventType
    audit_type: AuditEventType
    key: str | None


class RecoverySummary(NamedTuple):
    """What :meth:`TaskEngine.recover` did: the orphans it failed, the candidates it left alone,
    the tasks whose request for consent had expired (ADR 0015 §6)."""

    failed: tuple[Task, ...]
    skipped: tuple[Task, ...]
    """Candidates that had changed under the lock: no longer EXECUTING or WAITING_APPROVAL,
    alive again, or answered in the meantime."""
    expired: tuple[Task, ...] = ()
    """WAITING_APPROVAL tasks whose last PENDING request had expired: now EXPIRED."""


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

STEP_OPERATIONS: Final[Mapping[str, StepOperation]] = MappingProxyType(
    {
        op.name: op
        for op in (
            StepOperation(
                "start_step",
                frozenset({_P.PENDING}),
                _P.RUNNING,
                TaskEventType.STEP_STARTED,
                AuditEventType.STEP_STARTED,
                None,
            ),
            StepOperation(
                "complete_step",
                frozenset({_P.RUNNING}),
                _P.COMPLETED,
                TaskEventType.STEP_COMPLETED,
                AuditEventType.STEP_COMPLETED,
                "result_id",
            ),
            StepOperation(
                "fail_step",
                frozenset({_P.RUNNING}),
                _P.FAILED,
                TaskEventType.STEP_FAILED,
                AuditEventType.STEP_FAILED,
                None,
            ),
            StepOperation(
                "cancel_step",
                frozenset({_P.PENDING}),
                _P.CANCELLED,
                TaskEventType.STEP_CANCELLED,
                AuditEventType.STEP_CANCELLED,
                None,
            ),
        )
    }
)
"""The moves of one step of the plan, as decided in ADR 0009, in the order of its table.

``cancel_step`` has no public method: it is the propagation of ``fail_step`` to the PENDING
descendants of the failed step, written with the SYSTEM actor because nobody asked for it.
"""

Guard = Callable[[Task, tuple[TaskEvent, ...], datetime], Awaitable[None]]
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


def _last_step_change(events: tuple[TaskEvent, ...], step_id: StepId) -> Mapping[str, JsonValue]:
    """The metadata of the last ``STEP_*`` event of one step: which operation, with which key.

    Only asked about a step that is no longer PENDING, and a step leaves PENDING through one of
    these events only: the event exists, so there is no default.
    """
    return next(
        event.metadata
        for event in reversed(events)
        if event.step_id == step_id and event.event_type in STEP_EVENTS
    )


async def _require_plan(task: Task, _events: tuple[TaskEvent, ...], _now: datetime) -> None:
    if task.plan_id is None:
        raise TaskEngineError(task.id, "the task has no plan: nothing to queue or approve")


async def _require_deadline_passed(
    task: Task, _events: tuple[TaskEvent, ...], now: datetime
) -> None:
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
    how long an EXECUTING task may stay silent before :meth:`recover` fails it. ``approvals`` is
    where :meth:`recover` reads whether the request a WAITING_APPROVAL task waits on has expired
    (ADR 0015 §6): mandatory, because an engine that cannot see the requests cannot close them.
    """

    def __init__(
        self,
        repository: TaskRepository,
        audit_log: AuditLog,
        clock: Clock,
        ids: IdGenerator,
        *,
        approvals: ApprovalStore,
        actor: Actor,
        orphan_after: timedelta,
    ) -> None:
        if orphan_after <= timedelta(0):
            raise ValueError(f"orphan_after must be positive, not {orphan_after}")
        self._repository = repository
        self._audit_log = audit_log
        self._clock = clock
        self._ids = ids
        self._approvals = approvals
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
        """Attach ``plan`` to a PLANNING task: store it, set ``plan_id``, record and audit it.

        The steps must form a DAG (ADR 0009): a cycle, a dependency on a step outside the plan or
        a duplicate id is refused before anything is written.
        """
        if plan.task_id != task_id:
            raise TaskEngineError(task_id, f"the plan belongs to task {plan.task_id}")
        TaskGraph.from_plan(plan)
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

    async def recover(self) -> RecoverySummary:
        """Fail every EXECUTING task silent for ``orphan_after`` or longer (§14, closed bound),
        then expire every WAITING_APPROVAL task whose request has expired (ADR 0015 §6).

        Safe to call at any time, not only at start-up: each candidate is re-read under its own
        lock, and one that is no longer EXECUTING — or alive again — is skipped, never failed,
        while the others proceed (ADR 0008 §6). Likewise a task answered between the read and
        the lock is skipped: its answer is in the store and whoever resumes it moves it.
        """
        now = self._clock.now()
        failed: list[Task] = []
        skipped: list[Task] = []
        for candidate in await self._repository.tasks(states=frozenset({TaskState.EXECUTING})):
            if not self._is_orphan(now, candidate, await self._repository.events(candidate.id)):
                continue
            async with self._lock(candidate.id):
                task = await self._repository.get(candidate.id)
                events = await self._repository.events(candidate.id)
                if task.state is not TaskState.EXECUTING or not self._is_orphan(now, task, events):
                    skipped.append(task)
                    continue
                last_seen = _last_seen(task, events)
                error = ErrorMetadata(
                    code=ORPHANED,
                    message=f"no sign of life since {last_seen.isoformat()}",
                    retryable=True,
                    details={
                        "last_seen_at": last_seen.isoformat(),
                        "orphan_after_seconds": self._orphan_after.total_seconds(),
                    },
                )
                failed.append(
                    await self._apply_loaded(
                        OPERATIONS["recover"],
                        task,
                        events,
                        actor=SYSTEM_ACTOR,
                        reason=error.message,
                        error=error,
                        payload={"code": ORPHANED},
                    )
                )
        expired: list[Task] = []
        waiting = frozenset({TaskState.WAITING_APPROVAL})
        for candidate in await self._repository.tasks(states=waiting):
            if await self._expired_request(candidate.id, now) is None:
                continue
            async with self._lock(candidate.id):
                task = await self._repository.get(candidate.id)
                request = await self._expired_request(candidate.id, now)
                if task.state is not TaskState.WAITING_APPROVAL or request is None:
                    skipped.append(task)
                    continue
                events = await self._repository.events(candidate.id)
                assert request.expires_at is not None
                expired.append(
                    await self._apply_loaded(
                        OPERATIONS["expire"],
                        task,
                        events,
                        actor=SYSTEM_ACTOR,
                        reason=(
                            f"approval {request.id} expired at {request.expires_at.isoformat()}"
                        ),
                        payload={
                            "approval_id": str(request.id),
                            "expires_at": request.expires_at.isoformat(),
                        },
                    )
                )
        return RecoverySummary(tuple(failed), tuple(skipped), tuple(expired))

    async def _expired_request(self, task_id: TaskId, now: datetime) -> Approval | None:
        """The request the task waits on — its last PENDING one — if it has expired at ``now``
        (closed bound); ``None`` if there is none, or it can still be answered."""
        pending = [
            a for a in await self._approvals.for_task(task_id) if a.status is ApprovalStatus.PENDING
        ]
        if not pending:
            return None
        last = pending[-1]
        if last.expires_at is None or last.expires_at > now:
            return None
        return last

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
        """EXECUTING → COMPLETED, on a result that says SUCCEEDED (§63) and a plan whose every
        step is COMPLETED (ADR 0004 P7 "tutti gli step eseguiti"; ADR 0009)."""
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
            guard=self._require_graph_complete,
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
    # The Task Graph: the steps of the plan (§15, ADR 0009)
    # ----------------------------------------------------------------------------------

    async def graph(self, task_id: TaskId) -> GraphState:
        """The plan of the task as a graph, with where every step stands: read, never written.

        ``NotFoundError`` of the repository if the task is unknown or has no plan.
        """
        async with self._lock(task_id):
            await self._repository.get(task_id)
            return await self._graph(task_id, await self._repository.events(task_id))

    async def start_step(
        self, task_id: TaskId, step_id: StepId, *, device_id: DeviceId | None = None
    ) -> GraphState:
        """PENDING → RUNNING for a step whose every dependency is COMPLETED (§13)."""
        return await self._apply_step(
            STEP_OPERATIONS["start_step"],
            task_id,
            step_id,
            reason="" if device_id is None else f"on device {device_id}",
            device_id=device_id,
            must_be_ready=True,
        )

    async def complete_step(
        self, task_id: TaskId, step_id: StepId, result: ExecutionResult
    ) -> GraphState:
        """RUNNING → COMPLETED, on a result that says SUCCEEDED for this task and this step."""
        if result.task_id != task_id:
            raise TaskEngineError(task_id, f"the result is about task {result.task_id}")
        if result.step_id != step_id:
            raise TaskEngineError(task_id, f"the result is about step {result.step_id}")
        if result.status is not ExecutionStatus.SUCCEEDED:
            raise TaskEngineError(task_id, f"the result is {result.status}, not SUCCEEDED")
        return await self._apply_step(
            STEP_OPERATIONS["complete_step"],
            task_id,
            step_id,
            reason="",
            key=result.id,
            device_id=result.device_id,
            payload={"capability_id": result.capability_id, "tool_name": result.tool_name},
        )

    async def fail_step(self, task_id: TaskId, step_id: StepId, error: ErrorMetadata) -> GraphState:
        """RUNNING → FAILED, then every PENDING descendant → CANCELLED with the reason (§15).

        A retry on a step already FAILED writes no second failure but completes the cascade a
        crash may have cut short (ADR 0009: idempotent by outcome).
        """
        return await self._apply_step(
            STEP_OPERATIONS["fail_step"],
            task_id,
            step_id,
            reason=error.message,
            error=error,
            payload={"code": error.code},
            cascade=error,
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

    def _is_orphan(self, now: datetime, task: Task, events: tuple[TaskEvent, ...]) -> bool:
        """Silent for ``orphan_after`` or longer: the bound is closed (ADR 0005 §2-bis)."""
        return now - _last_seen(task, events) >= self._orphan_after

    def _check_approval(self, task_id: TaskId, approval: Approval, status: ApprovalStatus) -> None:
        if approval.task_id != task_id:
            raise TaskEngineError(task_id, f"the approval is about task {approval.task_id}")
        if approval.status is not status:
            raise TaskEngineError(task_id, f"the approval is {approval.status}, not {status}")

    async def _graph(self, task_id: TaskId, events: tuple[TaskEvent, ...]) -> GraphState:
        graph = TaskGraph.from_plan(await self._repository.plan(task_id))
        return GraphState(graph, graph.states(events))

    async def _require_graph_complete(
        self, task: Task, events: tuple[TaskEvent, ...], _now: datetime
    ) -> None:
        """Every step of the plan is COMPLETED: executing is not succeeding (§63, P7)."""
        state = await self._graph(task.id, events)
        pending = [str(s) for s in state.graph.order if state.states[s] is not StepState.COMPLETED]
        if pending:
            raise TaskEngineError(
                task.id, f"{len(pending)} step(s) not COMPLETED: {', '.join(pending)}"
            )

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
            return await self._apply_loaded(
                op,
                task,
                events,
                actor=actor,
                reason=reason,
                key=key,
                payload=payload,
                error=error,
                decision_id=decision_id,
                device_id=device_id,
                guard=guard,
            )

    async def _apply_loaded(
        self,
        op: Operation,
        task: Task,
        events: tuple[TaskEvent, ...],
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
        """The write path proper, on a task already read under its lock by the caller."""
        task_id = task.id
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
            await guard(task, events, now)
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

    # ----------------------------------------------------------------------------------
    # The write path of a step (ADR 0009): event, then audit; the task itself is not saved
    # ----------------------------------------------------------------------------------

    async def _apply_step(
        self,
        op: StepOperation,
        task_id: TaskId,
        step_id: StepId,
        *,
        reason: str,
        key: UUID | None = None,
        payload: Payload | None = None,
        error: ErrorMetadata | None = None,
        device_id: DeviceId | None = None,
        must_be_ready: bool = False,
        cascade: ErrorMetadata | None = None,
    ) -> GraphState:
        async with self._lock(task_id):
            task = await self._repository.get(task_id)
            events = await self._repository.events(task_id)
            if task.state is not TaskState.EXECUTING:
                raise TaskEngineError(
                    task_id, f"{op.name} needs an EXECUTING task, not {task.state}"
                )
            graph, states = await self._graph(task_id, events)
            graph.step(step_id)
            current = states[step_id]
            if current is op.target:
                self._step_already_applied(op, task_id, events, step_id, key)
            elif current not in op.sources:
                raise IllegalStepTransitionError(step_id, current.value, op.target.value)
            else:
                now = self._now(task, events)
                if must_be_ready and step_id not in graph.ready(states):
                    waiting = sorted(
                        str(d) for d in graph.dependencies(step_id) if states[d] is not _P.COMPLETED
                    )
                    raise TaskEngineError(
                        task_id, f"step {step_id} is not ready: waiting for {', '.join(waiting)}"
                    )
                keyed: dict[str, JsonValue] = {} if op.key is None else {op.key: str(key)}
                events = await self._write_step(
                    op,
                    task_id,
                    step_id,
                    events,
                    now=now,
                    actor=self._actor,
                    previous=current,
                    reason=reason,
                    keyed=keyed,
                    payload=payload,
                    error=error,
                    device_id=device_id,
                )
            if cascade is not None:
                events = await self._cancel_dependents(graph, task, events, step_id, cascade)
            return GraphState(graph, graph.states(events))

    def _step_already_applied(
        self,
        op: StepOperation,
        task_id: TaskId,
        events: tuple[TaskEvent, ...],
        step_id: StepId,
        key: UUID | None,
    ) -> None:
        """Same rule as for the task (ADR 0008 §8): same operation and same key, or refused."""
        if op.key is None:
            return
        recorded = _last_step_change(events, step_id)
        if recorded.get("operation") == op.name and recorded.get(op.key) == str(key):
            return
        raise TaskEngineError(
            task_id,
            f"step {step_id} already {op.target.value} with {op.key} {recorded.get(op.key)!r} "
            f"(by {recorded.get('operation')}), not {key}",
        )

    async def _cancel_dependents(
        self,
        graph: TaskGraph,
        task: Task,
        events: tuple[TaskEvent, ...],
        failed: StepId,
        error: ErrorMetadata,
    ) -> tuple[TaskEvent, ...]:
        """PENDING → CANCELLED for every descendant of ``failed`` still PENDING, in order.

        Called on the first failure and on every retry, so a cascade cut short by a crash is
        completed by the next call; steps already CANCELLED are left alone.
        """
        op = STEP_OPERATIONS["cancel_step"]
        reason = f"dependency {failed} failed: {error.message}"
        for step_id in graph.to_cancel(failed, graph.states(events)):
            events = await self._write_step(
                op,
                task.id,
                step_id,
                events,
                now=self._now(task, events),
                actor=SYSTEM_ACTOR,
                previous=StepState.PENDING,
                reason=reason,
                keyed={"cause_step_id": str(failed)},
                payload=None,
                error=None,
                device_id=None,
            )
        return events

    async def _write_step(
        self,
        op: StepOperation,
        task_id: TaskId,
        step_id: StepId,
        events: tuple[TaskEvent, ...],
        *,
        now: datetime,
        actor: Actor,
        previous: StepState,
        reason: str,
        keyed: Mapping[str, JsonValue],
        payload: Payload | None,
        error: ErrorMetadata | None,
        device_id: DeviceId | None,
    ) -> tuple[TaskEvent, ...]:
        """Event, then audit (ADR 0008 §4); returns the trail with the new event appended."""
        event = TaskEvent(
            id=TaskEventId(self._ids.new_uuid()),
            created_at=now,
            task_id=task_id,
            event_type=op.event_type,
            step_id=step_id,
            message=reason,
            metadata={"operation": op.name, **keyed},
        )
        await self._repository.append_event(event)
        await self._audit_log.append(
            AuditEvent(
                id=AuditEventId(self._ids.new_uuid()),
                created_at=now,
                event_type=op.audit_type,
                actor=actor,
                summary=f"{op.name}: step {step_id} {previous.value} -> {op.target.value}"
                + (f" ({reason})" if reason else ""),
                task_id=task_id,
                step_id=step_id,
                device_id=device_id,
                error=error,
                payload={
                    "operation": op.name,
                    "step_id": str(step_id),
                    "previous_step_state": previous.value,
                    "new_step_state": op.target.value,
                    "reason": reason,
                    **keyed,
                    **({} if payload is None else payload),
                },
            )
        )
        return (*events, event)


def _user_actor(task_id: TaskId, approval: Approval) -> Actor:
    """Who answered the approval; a resolved approval without a name is refused (§33)."""
    if not approval.responded_by:
        raise TaskEngineError(task_id, f"approval {approval.id} does not say who responded")
    return Actor(kind=ActorKind.USER, id=approval.responded_by)
