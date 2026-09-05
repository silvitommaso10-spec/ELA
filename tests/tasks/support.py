"""A Task Engine on the fakes, plus the fixtures that drive a task into any state.

Every state is reached through the engine itself (never by writing the repository), so a test
that starts "from EXECUTING" exercises the same path production will. The one exception is the
crash-window tests, which write the repository on purpose and say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

import pytest

from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEvent,
    DecisionId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    IntentId,
    PermissionDecision,
    PermissionOutcome,
    PlanId,
    Task,
    TaskEvent,
    TaskId,
    TaskPlan,
    TaskState,
)
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeIdGenerator, FakeTaskRepository
from tests.domain.examples import (
    APPROVAL,
    ELA_ACTOR,
    ERROR_METADATA,
    EXECUTION_RESULT,
    PERMISSION_DECISION,
    TASK_PLAN,
    USER_INTENT,
)

ORPHAN_AFTER = timedelta(minutes=5)
HOUR = timedelta(hours=1)


@dataclass
class Harness:
    repository: FakeTaskRepository
    audit: FakeAuditLog
    clock: FakeClock
    ids: FakeIdGenerator
    engine: TaskEngine

    async def snapshot(self, task_id: TaskId) -> Snapshot:
        return Snapshot(
            await self.repository.get(task_id),
            await self.repository.events(task_id),
            await self.audit.read(),
        )


@dataclass(frozen=True)
class Snapshot:
    task: Task
    events: tuple[TaskEvent, ...]
    audit: tuple[AuditEvent, ...]


def make_harness(orphan_after: timedelta = ORPHAN_AFTER) -> Harness:
    repository = FakeTaskRepository()
    audit = FakeAuditLog()
    clock = FakeClock()
    ids = FakeIdGenerator()
    engine = TaskEngine(repository, audit, clock, ids, actor=ELA_ACTOR, orphan_after=orphan_after)
    return Harness(repository, audit, clock, ids, engine)


@pytest.fixture
def h() -> Harness:
    return make_harness()


# --------------------------------------------------------------------------------------
# Inputs bound to a task
# --------------------------------------------------------------------------------------


def _id(tail: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{tail:012d}")


def plan_for(task_id: TaskId, tail: int = 900) -> TaskPlan:
    return TASK_PLAN.model_copy(update={"task_id": task_id, "id": _id(tail)})


def approval_for(
    task_id: TaskId,
    status: ApprovalStatus,
    *,
    tail: int = 910,
    responded_by: str | None = "tommaso",
) -> Approval:
    return APPROVAL.model_copy(
        update={
            "task_id": task_id,
            "id": ApprovalId(_id(tail)),
            "status": status,
            "responded_by": responded_by,
        }
    )


def decision_for(
    task_id: TaskId, outcome: PermissionOutcome = PermissionOutcome.DENIED, *, tail: int = 920
) -> PermissionDecision:
    return PERMISSION_DECISION.model_copy(
        update={"task_id": task_id, "id": DecisionId(_id(tail)), "outcome": outcome}
    )


def result_for(
    task_id: TaskId, status: ExecutionStatus = ExecutionStatus.SUCCEEDED, *, tail: int = 930
) -> ExecutionResult:
    return EXECUTION_RESULT.model_copy(
        update={"task_id": task_id, "id": ExecutionId(_id(tail)), "status": status, "error": None}
    )


ERROR: ErrorMetadata = ERROR_METADATA


# --------------------------------------------------------------------------------------
# Driving a task into a state, through the engine
# --------------------------------------------------------------------------------------


async def created(h: Harness, *, deadline: datetime | None = None) -> Task:
    """A new task from a fresh intent: ``create`` is idempotent per intent (ADR 0008 §8)."""
    intent = USER_INTENT.model_copy(update={"id": IntentId(h.ids.new_uuid())})
    return await h.engine.create(intent, deadline=deadline)


async def planning(h: Harness, *, with_plan: bool = True) -> Task:
    task = await created(h)
    task = await h.engine.start_planning(task.id)
    if with_plan:
        plan = plan_for(task.id).model_copy(update={"id": PlanId(h.ids.new_uuid())})
        task = await h.engine.plan(task.id, plan)
    return task


async def waiting_approval(h: Harness) -> Task:
    task = await planning(h)
    return await h.engine.request_approval(
        task.id, approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
    )


async def queued(h: Harness) -> Task:
    task = await planning(h)
    return await h.engine.queue(task.id)


async def executing(h: Harness) -> Task:
    task = await queued(h)
    return await h.engine.start(task.id)


async def task_in(h: Harness, state: TaskState) -> Task:
    """A task in ``state``, reached through the engine; every state of §14 is reachable."""
    if state is TaskState.CREATED:
        return await created(h)
    if state is TaskState.PLANNING:
        return await planning(h)
    if state is TaskState.WAITING_APPROVAL:
        return await waiting_approval(h)
    if state is TaskState.QUEUED:
        return await queued(h)
    if state is TaskState.EXECUTING:
        return await executing(h)
    if state is TaskState.COMPLETED:
        task = await executing(h)
        return await h.engine.complete(task.id, result_for(task.id))
    if state is TaskState.FAILED:
        task = await executing(h)
        return await h.engine.fail(task.id, ERROR)
    if state is TaskState.CANCELLED:
        task = await created(h)
        return await h.engine.cancel(task.id)
    if state is TaskState.DENIED:
        task = await planning(h)
        return await h.engine.deny(task.id, decision=decision_for(task.id))
    assert state is TaskState.EXPIRED
    task = await created(h, deadline=h.clock.now() + HOUR)
    h.clock.advance(HOUR)
    return await h.engine.expire(task.id)
