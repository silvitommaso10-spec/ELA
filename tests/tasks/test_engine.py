"""Every operation of the Task Engine: the legal case, the illegal states, the refused inputs.

The tests drive tasks through the engine itself (``support.py``). Where the engine refuses, the
task, its trail and the audit trail are checked to be exactly as before: refusing means writing
nothing (§33).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import product
from uuid import UUID, uuid5

import pytest

from ela.domain import (
    Actor,
    ActorKind,
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    PermissionOutcome,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.ports import NotFoundError
from ela.tasks.engine import OPERATIONS, SYSTEM_ACTOR, TASK_NAMESPACE, TaskEngine
from ela.tasks.errors import ClockSkewError, TaskEngineError, TaskError
from ela.tasks.state_machine import IllegalTransitionError
from ela.testing.fakes import FakeClock
from tests.domain.examples import DEVICE_ID, ELA_ACTOR, TASK_PLAN, USER_INTENT
from tests.tasks.support import (
    ERROR,
    HOUR,
    Harness,
    approval_for,
    created,
    dag_plan_for,
    decision_for,
    executing,
    h,
    plan_for,
    planning,
    queued,
    result_for,
    task_in,
    waiting_approval,
)

__all__ = ["h"]

S = TaskState
USER = Actor(kind=ActorKind.USER, id="tommaso")


async def last_change(h: Harness, task_id: TaskId) -> tuple[TaskState | None, TaskState | None]:
    event = (await h.repository.events(task_id))[-1]
    assert event.event_type is TaskEventType.STATE_CHANGED
    return event.previous_state, event.new_state


# --------------------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("orphan_after", [timedelta(0), timedelta(seconds=-1)])
def test_orphan_after_must_be_positive(h: Harness, orphan_after: timedelta) -> None:
    with pytest.raises(ValueError, match="positive"):
        TaskEngine(
            h.repository, h.audit, h.clock, h.ids, actor=ELA_ACTOR, orphan_after=orphan_after
        )


def test_engine_errors_are_task_errors() -> None:
    assert issubclass(TaskEngineError, TaskError)
    assert issubclass(ClockSkewError, TaskEngineError)


# --------------------------------------------------------------------------------------
# create
# --------------------------------------------------------------------------------------


async def test_create_stores_a_created_task_and_audits_it(h: Harness) -> None:
    task = await h.engine.create(USER_INTENT)
    assert task.id == TaskId(uuid5(TASK_NAMESPACE, str(USER_INTENT.id)))
    assert task.state is S.CREATED
    assert task.goal == USER_INTENT.text
    assert task.intent_id == USER_INTENT.id
    assert task.created_at == h.clock.now()
    assert task.deadline is None and task.plan_id is None
    assert await h.repository.get(task.id) == task
    assert await h.repository.events(task.id) == ()
    (audit,) = await h.audit.read()
    assert audit.event_type is AuditEventType.TASK_CREATED
    assert audit.actor == ELA_ACTOR
    assert audit.task_id == task.id
    assert audit.payload["intent_id"] == str(USER_INTENT.id)
    assert audit.payload["channel"] == USER_INTENT.channel.value


async def test_create_with_goal_and_deadline(h: Harness) -> None:
    deadline = h.clock.now() + HOUR
    task = await h.engine.create(USER_INTENT, goal="the meeting", deadline=deadline)
    assert task.goal == "the meeting"
    assert task.deadline == deadline
    assert (await h.audit.read())[0].payload["goal"] == "the meeting"


# --------------------------------------------------------------------------------------
# start_planning, plan
# --------------------------------------------------------------------------------------


async def test_start_planning_moves_and_audits(h: Harness) -> None:
    task = await created(h)
    moved = await h.engine.start_planning(task.id)
    assert moved.state is S.PLANNING
    assert await h.repository.get(task.id) == moved
    assert await last_change(h, task.id) == (S.CREATED, S.PLANNING)
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_PLANNING_STARTED
    assert audit.payload["previous_state"] == "CREATED"
    assert audit.payload["new_state"] == "PLANNING"
    assert audit.payload["operation"] == "start_planning"


async def test_plan_stores_the_plan_sets_plan_id_and_records_it(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    plan = dag_plan_for(task.id, TASK_PLAN.steps)  # the two-step DAG of the examples
    planned = await h.engine.plan(task.id, plan)
    assert planned.plan_id == plan.id
    assert planned.state is S.PLANNING
    assert await h.repository.get(task.id) == planned
    assert await h.repository.plan(task.id) == plan
    event = (await h.repository.events(task.id))[-1]
    assert event.event_type is TaskEventType.PLAN_ATTACHED
    assert event.metadata == {"operation": "plan", "plan_id": str(plan.id)}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.PLAN_CREATED
    assert audit.payload["plan_id"] == str(plan.id) and audit.payload["steps"] == 2


async def test_plan_refuses_a_plan_of_another_task(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    other = plan_for(TaskId(UUID(int=99)))
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="belongs to task"):
        await h.engine.plan(task.id, other)
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("state", [s for s in S if s is not S.PLANNING], ids=str)
async def test_plan_needs_a_planning_task(h: Harness, state: TaskState) -> None:
    task = await task_in(h, state)
    if task.plan_id is not None:
        # Already planned: the plan check comes first and says so.
        with pytest.raises(TaskEngineError, match="already has plan"):
            await h.engine.plan(task.id, plan_for(task.id, tail=901))
        return
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="needs a PLANNING task"):
        await h.engine.plan(task.id, plan_for(task.id))
    assert await h.snapshot(task.id) == before


# --------------------------------------------------------------------------------------
# request_approval, approve, deny
# --------------------------------------------------------------------------------------


async def test_request_approval_from_planning(h: Harness) -> None:
    task = await planning(h)
    approval = approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
    moved = await h.engine.request_approval(task.id, approval)
    assert moved.state is S.WAITING_APPROVAL
    event = (await h.repository.events(task.id))[-1]
    assert event.metadata == {"operation": "request_approval", "approval_id": str(approval.id)}
    assert event.message == approval.prompt
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.APPROVAL_REQUESTED
    assert audit.actor == ELA_ACTOR
    assert audit.payload["approval_id"] == str(approval.id)
    assert audit.payload["step_id"] == str(approval.step_id)
    assert audit.payload["reason"] == approval.prompt


async def test_request_approval_from_executing(h: Harness) -> None:
    task = await executing(h)
    moved = await h.engine.request_approval(
        task.id, approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
    )
    assert moved.state is S.WAITING_APPROVAL
    assert await last_change(h, task.id) == (S.EXECUTING, S.WAITING_APPROVAL)


async def test_request_approval_needs_a_plan(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="no plan"):
        await h.engine.request_approval(
            task.id, approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
        )
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize(
    ("status", "message"),
    [(ApprovalStatus.GRANTED, "not PENDING"), (ApprovalStatus.EXPIRED, "not PENDING")],
)
async def test_request_approval_needs_a_pending_approval(
    h: Harness, status: ApprovalStatus, message: str
) -> None:
    task = await planning(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=message):
        await h.engine.request_approval(task.id, approval_for(task.id, status))
    assert await h.snapshot(task.id) == before


async def test_request_approval_needs_an_approval_of_this_task(h: Harness) -> None:
    task = await planning(h)
    foreign = approval_for(TaskId(UUID(int=99)), ApprovalStatus.PENDING, responded_by=None)
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.request_approval(task.id, foreign)


async def test_approve_queues_the_task_as_the_user(h: Harness) -> None:
    task = await waiting_approval(h)
    approval = approval_for(task.id, ApprovalStatus.GRANTED)
    moved = await h.engine.approve(task.id, approval)
    assert moved.state is S.QUEUED
    assert await last_change(h, task.id) == (S.WAITING_APPROVAL, S.QUEUED)
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.APPROVAL_RESOLVED
    assert audit.actor == USER
    assert audit.payload["status"] == "GRANTED"
    assert audit.payload["responded_by"] == "tommaso"
    assert audit.payload["approval_id"] == str(approval.id)
    assert "approved by tommaso" in audit.summary


@pytest.mark.parametrize("status", [ApprovalStatus.PENDING, ApprovalStatus.REJECTED], ids=str)
async def test_approve_needs_a_granted_approval(h: Harness, status: ApprovalStatus) -> None:
    task = await waiting_approval(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="not GRANTED"):
        await h.engine.approve(task.id, approval_for(task.id, status))
    assert await h.snapshot(task.id) == before


async def test_approve_needs_to_know_who_responded(h: Harness) -> None:
    task = await waiting_approval(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="who responded"):
        await h.engine.approve(
            task.id, approval_for(task.id, ApprovalStatus.GRANTED, responded_by=None)
        )
    with pytest.raises(TaskEngineError, match="who responded"):
        await h.engine.approve(
            task.id, approval_for(task.id, ApprovalStatus.GRANTED, responded_by="")
        )
    assert await h.snapshot(task.id) == before


async def test_deny_by_approval_denies_as_the_user(h: Harness) -> None:
    task = await waiting_approval(h)
    approval = approval_for(task.id, ApprovalStatus.REJECTED)
    moved = await h.engine.deny(task.id, approval=approval)
    assert moved.state is S.DENIED
    event = (await h.repository.events(task.id))[-1]
    assert event.metadata == {"operation": "deny_by_approval", "approval_id": str(approval.id)}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.APPROVAL_RESOLVED
    assert audit.actor == USER
    assert audit.payload["status"] == "REJECTED"
    assert audit.decision_id is None


async def test_deny_by_approval_needs_a_rejected_one_of_this_task(h: Harness) -> None:
    task = await waiting_approval(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="not REJECTED"):
        await h.engine.deny(task.id, approval=approval_for(task.id, ApprovalStatus.GRANTED))
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.deny(
            task.id, approval=approval_for(TaskId(UUID(int=99)), ApprovalStatus.REJECTED)
        )
    with pytest.raises(TaskEngineError, match="who responded"):
        await h.engine.deny(
            task.id, approval=approval_for(task.id, ApprovalStatus.REJECTED, responded_by=None)
        )
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("source", [S.PLANNING, S.EXECUTING], ids=str)
async def test_deny_by_decision_denies_as_ela(h: Harness, source: TaskState) -> None:
    task = await task_in(h, source)
    decision = decision_for(task.id)
    moved = await h.engine.deny(task.id, decision=decision)
    assert moved.state is S.DENIED
    assert await last_change(h, task.id) == (source, S.DENIED)
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_DENIED
    assert audit.actor == ELA_ACTOR
    assert audit.decision_id == decision.id
    assert audit.payload["decision_id"] == str(decision.id)
    assert audit.payload["capability_id"] == decision.capability_id
    assert audit.payload["reason"] == decision.reason


@pytest.mark.parametrize(
    "outcome", [PermissionOutcome.ALLOWED, PermissionOutcome.REQUIRES_APPROVAL], ids=str
)
async def test_deny_by_decision_needs_a_denied_decision(
    h: Harness, outcome: PermissionOutcome
) -> None:
    task = await planning(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="not DENIED"):
        await h.engine.deny(task.id, decision=decision_for(task.id, outcome))
    assert await h.snapshot(task.id) == before


async def test_deny_by_decision_needs_a_decision_about_this_task(h: Harness) -> None:
    task = await planning(h)
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.deny(task.id, decision=decision_for(TaskId(UUID(int=99))))


async def test_deny_needs_exactly_one_reason(h: Harness) -> None:
    task = await waiting_approval(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="exactly one"):
        await h.engine.deny(task.id)
    with pytest.raises(TaskEngineError, match="exactly one"):
        await h.engine.deny(
            task.id,
            decision=decision_for(task.id),
            approval=approval_for(task.id, ApprovalStatus.REJECTED),
        )
    assert await h.snapshot(task.id) == before


async def test_deny_by_decision_from_waiting_approval_points_to_the_approval(h: Harness) -> None:
    """WAITING_APPROVAL -> DENIED is legal, but the user's answer is what denies it there."""
    task = await waiting_approval(h)
    with pytest.raises(TaskEngineError, match="another operation"):
        await h.engine.deny(task.id, decision=decision_for(task.id))


# --------------------------------------------------------------------------------------
# queue, start, heartbeat
# --------------------------------------------------------------------------------------


async def test_queue_from_planning(h: Harness) -> None:
    task = await planning(h)
    moved = await h.engine.queue(task.id)
    assert moved.state is S.QUEUED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_QUEUED
    assert audit.payload["reason"] == ""
    assert audit.summary == "queue: PLANNING -> QUEUED"


async def test_queue_from_executing_with_a_reason(h: Harness) -> None:
    task = await executing(h)
    moved = await h.engine.queue(task.id, reason="node went offline")
    assert moved.state is S.QUEUED
    assert await last_change(h, task.id) == (S.EXECUTING, S.QUEUED)
    audit = (await h.audit.read())[-1]
    assert audit.summary == "queue: EXECUTING -> QUEUED (node went offline)"
    assert (await h.repository.events(task.id))[-1].message == "node went offline"


async def test_queue_needs_a_plan(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="no plan"):
        await h.engine.queue(task.id)
    assert await h.snapshot(task.id) == before


async def test_queue_from_waiting_approval_points_to_approve(h: Harness) -> None:
    task = await waiting_approval(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="another operation"):
        await h.engine.queue(task.id)
    assert await h.snapshot(task.id) == before


async def test_start_records_the_device(h: Harness) -> None:
    task = await queued(h)
    moved = await h.engine.start(task.id, device_id=DEVICE_ID)
    assert moved.state is S.EXECUTING
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_STARTED
    assert audit.device_id == DEVICE_ID
    assert f"on device {DEVICE_ID}" in audit.summary


async def test_start_without_a_device(h: Harness) -> None:
    task = await queued(h)
    await h.engine.start(task.id)
    audit = (await h.audit.read())[-1]
    assert audit.device_id is None and audit.summary == "start: QUEUED -> EXECUTING"


async def test_heartbeat_appends_a_trail_event_and_no_audit(h: Harness) -> None:
    task = await executing(h)
    audits = len(await h.audit.read())
    h.clock.advance(timedelta(seconds=30))
    same = await h.engine.heartbeat(task.id)
    assert same == task
    event = (await h.repository.events(task.id))[-1]
    assert event.event_type is TaskEventType.HEARTBEAT
    assert event.created_at == h.clock.now()
    assert event.previous_state is None and event.new_state is None
    assert len(await h.audit.read()) == audits


@pytest.mark.parametrize("state", [s for s in S if s is not S.EXECUTING], ids=str)
async def test_heartbeat_needs_an_executing_task(h: Harness, state: TaskState) -> None:
    task = await task_in(h, state)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="EXECUTING"):
        await h.engine.heartbeat(task.id)
    assert await h.snapshot(task.id) == before


# --------------------------------------------------------------------------------------
# complete, fail, cancel, expire
# --------------------------------------------------------------------------------------


async def test_complete_on_a_succeeded_result(h: Harness) -> None:
    task = await executing(h)
    result = result_for(task.id)
    moved = await h.engine.complete(task.id, result)
    assert moved.state is S.COMPLETED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_COMPLETED
    assert audit.payload["result_id"] == str(result.id)
    assert audit.payload["capability_id"] == result.capability_id
    assert audit.device_id == result.device_id


@pytest.mark.parametrize(
    "status", [s for s in ExecutionStatus if s is not ExecutionStatus.SUCCEEDED], ids=str
)
async def test_complete_needs_success(h: Harness, status: ExecutionStatus) -> None:
    """Ending is not succeeding (§63): a FAILED result does not complete a task."""
    task = await executing(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="not SUCCEEDED"):
        await h.engine.complete(task.id, result_for(task.id, status))
    assert await h.snapshot(task.id) == before


async def test_complete_needs_a_result_of_this_task(h: Harness) -> None:
    task = await executing(h)
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.complete(task.id, result_for(TaskId(UUID(int=99))))
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.complete(task.id, result_for(task.id).model_copy(update={"task_id": None}))


@pytest.mark.parametrize("source", [S.PLANNING, S.EXECUTING], ids=str)
async def test_fail_records_the_error(h: Harness, source: TaskState) -> None:
    task = await task_in(h, source)
    moved = await h.engine.fail(task.id, ERROR)
    assert moved.state is S.FAILED
    assert await last_change(h, task.id) == (source, S.FAILED)
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_FAILED
    assert audit.error == ERROR
    assert audit.payload["code"] == ERROR.code
    assert audit.payload["reason"] == ERROR.message


@pytest.mark.parametrize(
    "state", [S.CREATED, S.PLANNING, S.WAITING_APPROVAL, S.QUEUED, S.EXECUTING]
)
async def test_cancel_from_every_live_state(h: Harness, state: TaskState) -> None:
    task = await task_in(h, state)
    moved = await h.engine.cancel(task.id, reason="changed my mind", actor=USER)
    assert moved.state is S.CANCELLED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_CANCELLED
    assert audit.actor == USER
    assert audit.payload["reason"] == "changed my mind"


async def test_cancel_defaults_to_ela(h: Harness) -> None:
    task = await created(h)
    await h.engine.cancel(task.id)
    assert (await h.audit.read())[-1].actor == ELA_ACTOR


@pytest.mark.parametrize(
    "state", [S.CREATED, S.PLANNING, S.WAITING_APPROVAL, S.QUEUED, S.EXECUTING]
)
async def test_expire_once_the_deadline_passed(h: Harness, state: TaskState) -> None:
    deadline = h.clock.now() + HOUR
    h.engine = TaskEngine(h.repository, h.audit, h.clock, h.ids, actor=ELA_ACTOR, orphan_after=HOUR)
    task = await created(h, deadline=deadline)
    if state is not S.CREATED:
        task = await h.engine.start_planning(task.id)
        task = await h.engine.plan(task.id, plan_for(task.id))
    if state is S.WAITING_APPROVAL:
        task = await h.engine.request_approval(
            task.id, approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
        )
    if state in (S.QUEUED, S.EXECUTING):
        task = await h.engine.queue(task.id)
    if state is S.EXECUTING:
        task = await h.engine.start(task.id)
    assert task.state is state
    h.clock.advance(HOUR)  # exactly the deadline: closed bound, already expired
    moved = await h.engine.expire(task.id)
    assert moved.state is S.EXPIRED
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_EXPIRED
    assert audit.actor == SYSTEM_ACTOR


async def test_expire_needs_a_deadline(h: Harness) -> None:
    task = await created(h)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="no deadline"):
        await h.engine.expire(task.id)
    assert await h.snapshot(task.id) == before


async def test_expire_before_the_deadline_is_refused(h: Harness) -> None:
    task = await created(h, deadline=h.clock.now() + HOUR)
    h.clock.advance(HOUR - timedelta(seconds=1))
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="has not passed"):
        await h.engine.expire(task.id)
    assert await h.snapshot(task.id) == before


# --------------------------------------------------------------------------------------
# The illegal pairs of ADR 0004, through the engine
# --------------------------------------------------------------------------------------

BY_TARGET = {
    S.PLANNING: "start_planning",
    S.WAITING_APPROVAL: "request_approval",
    S.QUEUED: "queue",
    S.EXECUTING: "start",
    S.COMPLETED: "complete",
    S.FAILED: "fail",
    S.CANCELLED: "cancel",
    S.DENIED: "deny",
    S.EXPIRED: "expire",
}
LEGAL_BUT_ANOTHER_OPERATION = {(S.WAITING_APPROVAL, S.QUEUED), (S.WAITING_APPROVAL, S.DENIED)}
ILLEGAL = [
    (a, b)
    for a, b in product(S, S)
    if b in BY_TARGET
    and a is not b
    and b not in OPERATIONS[BY_TARGET[b].replace("deny", "deny_by_decision")].sources
    and a not in OPERATIONS[BY_TARGET[b].replace("deny", "deny_by_decision")].sources
]


async def call(h: Harness, task_id: TaskId, target: TaskState) -> None:
    engine = h.engine
    name = BY_TARGET[target]
    if name == "request_approval":
        await engine.request_approval(
            task_id, approval_for(task_id, ApprovalStatus.PENDING, responded_by=None)
        )
    elif name == "complete":
        await engine.complete(task_id, result_for(task_id))
    elif name == "fail":
        await engine.fail(task_id, ERROR)
    elif name == "deny":
        await engine.deny(task_id, decision=decision_for(task_id))
    else:
        await getattr(engine, name)(task_id)


@pytest.mark.parametrize(("source", "target"), ILLEGAL, ids=lambda s: s.value)
async def test_illegal_pairs_are_refused_and_write_nothing(
    h: Harness, source: TaskState, target: TaskState
) -> None:
    task = await task_in(h, source)
    before = await h.snapshot(task.id)
    expected = (
        TaskEngineError
        if (source, target) in LEGAL_BUT_ANOTHER_OPERATION
        else IllegalTransitionError
    )
    with pytest.raises(expected) as excinfo:
        await call(h, task.id, target)
    if isinstance(excinfo.value, IllegalTransitionError):
        assert (excinfo.value.current, excinfo.value.requested) == (source, target)
    assert await h.snapshot(task.id) == before


def test_the_illegal_pairs_cover_the_table() -> None:
    """67 pairs with an operation as target that are not that operation's, minus the no-ops."""
    assert len(ILLEGAL) == 90 - 9 - 21


# --------------------------------------------------------------------------------------
# Unknown task, clock skew
# --------------------------------------------------------------------------------------


async def test_unknown_task_is_not_found(h: Harness) -> None:
    unknown = TaskId(UUID(int=7))
    with pytest.raises(NotFoundError):
        await h.engine.queue(unknown)
    with pytest.raises(NotFoundError):
        await h.engine.plan(unknown, plan_for(unknown))
    with pytest.raises(NotFoundError):
        await h.engine.heartbeat(unknown)


async def test_a_clock_that_went_backwards_is_refused(h: Harness) -> None:
    task = await queued(h)
    before = await h.snapshot(task.id)
    behind = TaskEngine(
        h.repository,
        h.audit,
        FakeClock(h.clock.now() - timedelta(seconds=1)),
        h.ids,
        actor=ELA_ACTOR,
        orphan_after=HOUR,
    )
    with pytest.raises(ClockSkewError) as excinfo:
        await behind.start(task.id)
    assert excinfo.value.last_seen == h.clock.now()
    assert excinfo.value.now == h.clock.now() - timedelta(seconds=1)
    assert await h.snapshot(task.id) == before


async def test_the_same_instant_is_not_skew(h: Harness) -> None:
    task = await queued(h)
    assert (await h.engine.start(task.id)).state is S.EXECUTING


async def test_skew_is_measured_against_heartbeats_too(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(timedelta(minutes=1))
    await h.engine.heartbeat(task.id)
    behind = TaskEngine(
        h.repository,
        h.audit,
        FakeClock(h.clock.now() - timedelta(seconds=1)),
        h.ids,
        actor=ELA_ACTOR,
        orphan_after=HOUR,
    )
    with pytest.raises(ClockSkewError):
        await behind.heartbeat(task.id)
    with pytest.raises(ClockSkewError):
        await behind.complete(task.id, result_for(task.id))


async def test_skew_before_a_plan_is_refused(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    behind = TaskEngine(
        h.repository,
        h.audit,
        FakeClock(datetime(2020, 1, 1, tzinfo=UTC)),
        h.ids,
        actor=ELA_ACTOR,
        orphan_after=HOUR,
    )
    with pytest.raises(ClockSkewError):
        await behind.plan(task.id, plan_for(task.id))
    with pytest.raises(NotFoundError):
        await h.repository.plan(task.id)
