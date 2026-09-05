"""Re-running an operation that was already applied does not duplicate (§14, ADR 0008 §8).

Idempotent by state (the target is the stored state), and by key where the operation carries
one: the same approval twice is a no-op, another approval on a task already QUEUED is refused.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

import pytest

from ela.domain import (
    ApprovalStatus,
    AuditEventType,
    Task,
    TaskEvent,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
)
from ela.ports import AlreadyExistsError, NotFoundError
from ela.tasks.errors import TaskEngineError
from ela.testing.fakes import FakeTaskRepository
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.tasks.support import (
    ERROR,
    Harness,
    approval_for,
    created,
    decision_for,
    executing,
    h,
    make_harness,
    plan_for,
    planning,
    queued,
    result_for,
    waiting_approval,
)

__all__ = ["h"]

S = TaskState
Step = Callable[[Harness, TaskId], Awaitable[Task]]


async def _pending(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.request_approval(
        task_id, approval_for(task_id, ApprovalStatus.PENDING, responded_by=None)
    )


async def _approve(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.approve(task_id, approval_for(task_id, ApprovalStatus.GRANTED))


async def _deny_approval(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.deny(task_id, approval=approval_for(task_id, ApprovalStatus.REJECTED))


async def _deny_decision(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.deny(task_id, decision=decision_for(task_id))


async def _complete(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.complete(task_id, result_for(task_id))


async def _fail(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.fail(task_id, ERROR)


async def _expire(h: Harness, task_id: TaskId) -> Task:
    return await h.engine.expire(task_id)


TWICE: list[tuple[str, TaskState, Step]] = [
    ("start_planning", S.CREATED, lambda h, t: h.engine.start_planning(t)),
    ("request_approval", S.PLANNING, _pending),
    ("approve", S.WAITING_APPROVAL, _approve),
    ("deny_by_approval", S.WAITING_APPROVAL, _deny_approval),
    ("deny_by_decision", S.PLANNING, _deny_decision),
    ("queue", S.PLANNING, lambda h, t: h.engine.queue(t)),
    ("start", S.QUEUED, lambda h, t: h.engine.start(t)),
    ("complete", S.EXECUTING, _complete),
    ("fail", S.EXECUTING, _fail),
    ("cancel", S.EXECUTING, lambda h, t: h.engine.cancel(t)),
]


async def _in(h: Harness, state: TaskState) -> Task:
    if state is S.CREATED:
        return await created(h)
    if state is S.PLANNING:
        return await planning(h)
    if state is S.WAITING_APPROVAL:
        return await waiting_approval(h)
    if state is S.QUEUED:
        return await queued(h)
    return await executing(h)


@pytest.mark.parametrize(("name", "source", "step"), TWICE, ids=[row[0] for row in TWICE])
async def test_the_same_operation_twice_writes_once(
    h: Harness, name: str, source: TaskState, step: Step
) -> None:
    task = await _in(h, source)
    first = await step(h, task.id)
    after_first = await h.snapshot(task.id)
    second = await step(h, task.id)
    assert second == first
    assert await h.snapshot(task.id) == after_first
    changes = [e for e in after_first.events if e.event_type is TaskEventType.STATE_CHANGED]
    assert changes[-1].previous_state is source and changes[-1].new_state is first.state
    assert sum(1 for e in changes if e.new_state is first.state) == 1


async def test_expire_twice_writes_once(h: Harness) -> None:
    task = await created(h, deadline=h.clock.now())
    first = await h.engine.expire(task.id)
    after_first = await h.snapshot(task.id)
    assert await h.engine.expire(task.id) == first
    assert await h.snapshot(task.id) == after_first


async def test_another_key_on_the_same_state_is_refused(h: Harness) -> None:
    task = await waiting_approval(h)
    await h.engine.approve(task.id, approval_for(task.id, ApprovalStatus.GRANTED))
    after = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="already QUEUED with approval_id"):
        await h.engine.approve(task.id, approval_for(task.id, ApprovalStatus.GRANTED, tail=911))
    assert await h.snapshot(task.id) == after


async def test_another_approval_request_on_a_waiting_task_is_refused(h: Harness) -> None:
    task = await waiting_approval(h)
    after = await h.snapshot(task.id)
    other = approval_for(task.id, ApprovalStatus.PENDING, tail=911, responded_by=None)
    with pytest.raises(TaskEngineError, match="already WAITING_APPROVAL with approval_id"):
        await h.engine.request_approval(task.id, other)
    assert await h.snapshot(task.id) == after


async def test_another_result_on_a_completed_task_is_refused(h: Harness) -> None:
    task = await executing(h)
    await h.engine.complete(task.id, result_for(task.id))
    with pytest.raises(TaskEngineError, match="already COMPLETED with result_id"):
        await h.engine.complete(task.id, result_for(task.id, tail=931))


async def test_another_decision_on_a_denied_task_is_refused(h: Harness) -> None:
    task = await planning(h)
    await h.engine.deny(task.id, decision=decision_for(task.id))
    with pytest.raises(TaskEngineError, match="already DENIED with decision_id"):
        await h.engine.deny(task.id, decision=decision_for(task.id, tail=921))


async def test_a_denied_by_decision_task_refuses_a_rejected_approval(h: Harness) -> None:
    """Same target, different fact: the trail has a decision id, not an approval id."""
    task = await planning(h)
    await h.engine.deny(task.id, decision=decision_for(task.id))
    with pytest.raises(TaskEngineError, match="already DENIED with approval_id None"):
        await h.engine.deny(task.id, approval=approval_for(task.id, ApprovalStatus.REJECTED))


async def test_a_keyed_no_op_reads_past_heartbeats(h: Harness) -> None:
    """The key lives on the last STATE_CHANGED, not on the last event of any type."""
    task = await waiting_approval(h)
    approval = approval_for(task.id, ApprovalStatus.GRANTED)
    await h.engine.approve(task.id, approval)
    await h.engine.start(task.id)
    await h.engine.heartbeat(task.id)
    await h.engine.heartbeat(task.id)
    await h.engine.queue(task.id, reason="interrupted")
    after = await h.snapshot(task.id)
    # QUEUED again, this time by ``queue``: the recorded key is not the approval's.
    with pytest.raises(TaskEngineError, match="already QUEUED with approval_id None"):
        await h.engine.approve(task.id, approval)
    assert await h.snapshot(task.id) == after


# --------------------------------------------------------------------------------------
# create and plan
# --------------------------------------------------------------------------------------


async def test_create_twice_is_one_task_and_one_audit_event(h: Harness) -> None:
    first = await h.engine.create(USER_INTENT)
    h.clock.advance(timedelta(minutes=1))
    second = await h.engine.create(USER_INTENT, goal="another goal")
    assert second == first
    assert await h.repository.tasks() == (first,)
    audits = await h.audit.read()
    assert [a.event_type for a in audits] == [AuditEventType.TASK_CREATED]


async def test_two_intents_are_two_tasks(h: Harness) -> None:
    first = await h.engine.create(USER_INTENT)
    other = USER_INTENT.model_copy(update={"id": USER_INTENT.id.__class__(int=42)})
    second = await h.engine.create(other)
    assert second.id != first.id
    assert len(await h.repository.tasks()) == 2


async def test_the_same_plan_twice_is_a_no_op(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    plan = plan_for(task.id)
    first = await h.engine.plan(task.id, plan)
    after = await h.snapshot(task.id)
    assert await h.engine.plan(task.id, plan) == first
    assert await h.snapshot(task.id) == after


async def test_another_plan_is_refused(h: Harness) -> None:
    task = await planning(h)
    after = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="already has plan"):
        await h.engine.plan(task.id, plan_for(task.id, tail=901))
    assert await h.snapshot(task.id) == after
    assert (await h.repository.plan(task.id)).id == task.plan_id


# --------------------------------------------------------------------------------------
# Crash windows (ADR 0008 §4): the repository is written by hand, on purpose
# --------------------------------------------------------------------------------------


async def test_state_saved_but_no_event_a_keyless_retry_is_a_no_op(h: Harness) -> None:
    task = await planning(h)
    await h.repository.save(task.model_copy(update={"state": S.QUEUED}))  # crash after save
    before = await h.snapshot(task.id)
    assert (await h.engine.queue(task.id)).state is S.QUEUED
    assert await h.snapshot(task.id) == before


async def test_state_saved_but_no_event_a_keyed_retry_is_refused(h: Harness) -> None:
    """The trail cannot vouch for the key: the safe side is to refuse (ADR 0008 risks)."""
    task = await waiting_approval(h)
    await h.repository.save(task.model_copy(update={"state": S.QUEUED}))
    # The last STATE_CHANGED is the request, with the same approval id: not the same operation.
    with pytest.raises(TaskEngineError, match=r"already QUEUED .*\(by request_approval\)"):
        await h.engine.approve(task.id, approval_for(task.id, ApprovalStatus.GRANTED))


async def test_plan_stored_but_task_not_saved_the_retry_continues(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    plan = plan_for(task.id)
    await h.repository.add_plan(plan)  # crash between add_plan and save
    planned = await h.engine.plan(task.id, plan)
    assert planned.plan_id == plan.id
    assert (await h.repository.events(task.id))[-1].event_type is TaskEventType.PLAN_ATTACHED


async def test_another_plan_stored_but_task_not_saved_is_refused(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    await h.repository.add_plan(plan_for(task.id, tail=901))
    with pytest.raises(TaskEngineError, match="is stored"):
        await h.engine.plan(task.id, plan_for(task.id))
    assert (await h.repository.get(task.id)).plan_id is None


# --------------------------------------------------------------------------------------
# Concurrency (ADR 0008 §11): the per-task lock serialises interleaved operations
# --------------------------------------------------------------------------------------


class YieldingRepository(FakeTaskRepository):
    """A fake whose every call yields to the loop first, as a real adapter would."""

    async def get(self, task_id: TaskId) -> Task:
        await asyncio.sleep(0)
        return await super().get(task_id)

    async def save(self, task: Task) -> None:
        await asyncio.sleep(0)
        await super().save(task)

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        await asyncio.sleep(0)
        return await super().events(task_id)

    async def append_event(self, event: TaskEvent) -> None:
        await asyncio.sleep(0)
        await super().append_event(event)

    async def add_plan(self, plan: TaskPlan) -> None:
        await asyncio.sleep(0)
        await super().add_plan(plan)


async def test_concurrent_queues_write_one_event() -> None:
    h = make_harness()
    h.repository = YieldingRepository()
    h.engine = h.engine.__class__(
        h.repository, h.audit, h.clock, h.ids, actor=ELA_ACTOR, orphan_after=timedelta(minutes=5)
    )
    task = await planning(h)
    results = await asyncio.gather(*(h.engine.queue(task.id) for _ in range(5)))
    assert all(result.state is S.QUEUED for result in results)
    changes = [
        e for e in await h.repository.events(task.id) if e.event_type is TaskEventType.STATE_CHANGED
    ]
    assert [e.new_state for e in changes] == [S.PLANNING, S.QUEUED]
    assert [a.event_type for a in await h.audit.read()].count(AuditEventType.TASK_QUEUED) == 1


async def test_without_the_lock_interleaving_would_duplicate() -> None:
    """Negative case: the same interleaving on a repository alone applies the move twice."""
    from ela.tasks.state_machine import transition

    repository = YieldingRepository()
    h = make_harness()
    h.repository = repository
    h.engine = h.engine.__class__(
        repository, h.audit, h.clock, h.ids, actor=ELA_ACTOR, orphan_after=timedelta(minutes=5)
    )
    task = await planning(h)

    async def unguarded(tail: int) -> None:
        stored = await repository.get(task.id)
        moved = transition(
            stored, S.QUEUED, event_id=stored.id.__class__(int=tail), now=h.clock.now()
        )
        await repository.save(moved.task)
        await repository.append_event(moved.event)

    await asyncio.gather(unguarded(1), unguarded(2))
    queued_events = [e for e in await repository.events(task.id) if e.new_state is S.QUEUED]
    assert len(queued_events) == 2


async def test_repository_errors_pass_through_unchanged(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    other = TaskId(task.id.__class__(int=5))
    with pytest.raises(NotFoundError):
        await h.repository.add_plan(plan_for(other))
    with pytest.raises(AlreadyExistsError):
        await h.repository.add(task)


async def test_a_keyed_check_on_a_trail_without_state_changes_is_refused(h: Harness) -> None:
    """A task written by hand, in the target state, with only heartbeats: nothing vouches."""
    from ela.domain import TaskEvent, TaskEventId

    stranded = Task(
        id=TaskId(USER_INTENT.id.__class__(int=78)),
        created_at=h.clock.now(),
        goal="stranded",
        state=S.COMPLETED,
    )
    await h.repository.add(stranded)
    await h.repository.append_event(
        TaskEvent(
            id=TaskEventId(h.ids.new_uuid()),
            created_at=h.clock.now(),
            task_id=stranded.id,
            event_type=TaskEventType.HEARTBEAT,
        )
    )
    with pytest.raises(TaskEngineError, match=r"already COMPLETED with result_id None \(by None\)"):
        await h.engine.complete(stranded.id, result_for(stranded.id))
