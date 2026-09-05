"""Property tests: random walks through the engine keep the task, its trail and the audit coherent.

Whatever the sequence of operations, the stored state is the ``new_state`` of the last
STATE_CHANGED, consecutive state changes differ, instants never go backwards, every applied
transition is one audit event, and a refused operation leaves everything as it was.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import ApprovalStatus, AuditEventType, Task, TaskEventType, TaskId, TaskState
from ela.tasks.errors import TaskEngineError
from ela.tasks.state_machine import IllegalTransitionError
from tests.domain.examples import USER_INTENT
from tests.tasks.support import (
    ERROR,
    Harness,
    approval_for,
    decision_for,
    make_harness,
    plan_for,
    result_for,
)

S = TaskState
Step = Callable[[Harness, TaskId, int], Awaitable[Task]]


async def _start_planning(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.start_planning(t)


async def _plan(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.plan(t, plan_for(t, tail=900 + n))


async def _request(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.request_approval(
        t, approval_for(t, ApprovalStatus.PENDING, tail=910 + n, responded_by=None)
    )


async def _approve(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.approve(t, approval_for(t, ApprovalStatus.GRANTED, tail=910 + n))


async def _deny_approval(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.deny(t, approval=approval_for(t, ApprovalStatus.REJECTED, tail=910 + n))


async def _deny_decision(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.deny(t, decision=decision_for(t, tail=920 + n))


async def _queue(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.queue(t, reason=f"step {n}")


async def _start(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.start(t)


async def _heartbeat(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.heartbeat(t)


async def _complete(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.complete(t, result_for(t, tail=930 + n))


async def _fail(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.fail(t, ERROR)


async def _cancel(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.cancel(t)


async def _expire(h: Harness, t: TaskId, n: int) -> Task:
    return await h.engine.expire(t)


async def _tick(h: Harness, t: TaskId, n: int) -> Task:
    h.clock.advance(timedelta(seconds=n + 1))
    return await h.repository.get(t)


STEPS: dict[str, Step] = {
    "start_planning": _start_planning,
    "plan": _plan,
    "request_approval": _request,
    "approve": _approve,
    "deny_by_approval": _deny_approval,
    "deny_by_decision": _deny_decision,
    "queue": _queue,
    "start": _start,
    "heartbeat": _heartbeat,
    "complete": _complete,
    "fail": _fail,
    "cancel": _cancel,
    "expire": _expire,
    "tick": _tick,
}
NOT_TRANSITIONS = {"plan", "heartbeat", "tick"}

walks = st.lists(st.sampled_from(sorted(STEPS)), min_size=1, max_size=25)


async def _walk(names: list[str], with_deadline: bool) -> None:
    h = make_harness()
    deadline = h.clock.now() + timedelta(seconds=10) if with_deadline else None
    task = await h.engine.create(USER_INTENT, deadline=deadline)
    transitions = 0
    plans = 0
    for n, name in enumerate(names):
        before = await h.snapshot(task.id)
        try:
            result = await STEPS[name](h, task.id, n)
        except (TaskEngineError, IllegalTransitionError):
            assert await h.snapshot(task.id) == before
            continue
        after = await h.snapshot(task.id)
        assert result == after.task
        if name in NOT_TRANSITIONS:
            assert after.task.state is before.task.state
            plans += int(name == "plan" and after.task.plan_id != before.task.plan_id)
        elif after.task.state is not before.task.state:
            transitions += 1
        # Invariants of the trail
        changes = [e for e in after.events if e.event_type is TaskEventType.STATE_CHANGED]
        expected = changes[-1].new_state if changes else S.CREATED
        assert after.task.state is expected
        for previous, current in zip(changes, changes[1:], strict=False):
            assert previous.new_state is current.previous_state
            assert current.previous_state is not current.new_state
        instants = [task.created_at, *(e.created_at for e in after.events)]
        assert instants == sorted(instants)
        assert len(changes) == transitions
        types = [a.event_type for a in after.audit]
        assert types[0] is AuditEventType.TASK_CREATED
        assert len(types) == 1 + transitions + plans
        assert AuditEventType.TASK_CREATED not in types[1:]


@given(names=walks, with_deadline=st.booleans())
@settings(max_examples=150, deadline=None)
def test_random_walks_keep_task_trail_and_audit_coherent(
    names: list[str], with_deadline: bool
) -> None:
    asyncio.run(_walk(names, with_deadline))
