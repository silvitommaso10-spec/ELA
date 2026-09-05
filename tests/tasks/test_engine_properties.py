"""Property tests: random walks through the engine keep the task, its trail and the audit coherent.

Whatever the sequence of operations — on the task and, since M3.2, on the steps of its plan — the
stored state is the ``new_state`` of the last STATE_CHANGED, consecutive state changes differ,
instants never go backwards, every applied transition and every step move is one audit event, the
folded step states are always legal, and a refused operation leaves everything as it was.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    ApprovalStatus,
    AuditEventType,
    StepId,
    StepState,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.ports import NotFoundError
from ela.tasks.errors import GraphError, TaskEngineError
from ela.tasks.graph import STEP_EVENTS, GraphState, TaskGraph
from ela.tasks.state_machine import IllegalTransitionError
from tests.domain.examples import USER_INTENT
from tests.tasks.graphs import diamond, sid
from tests.tasks.support import (
    ERROR,
    Harness,
    approval_for,
    dag_plan_for,
    decision_for,
    make_harness,
    result_for,
    step_result_for,
)

S = TaskState
Step = Callable[[Harness, TaskId, int], Awaitable[object]]


async def _start_planning(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.start_planning(t)


async def _plan(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.plan(t, dag_plan_for(t, diamond(), tail=900 + n))


async def _request(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.request_approval(
        t, approval_for(t, ApprovalStatus.PENDING, tail=910 + n, responded_by=None)
    )


async def _approve(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.approve(t, approval_for(t, ApprovalStatus.GRANTED, tail=910 + n))


async def _deny_approval(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.deny(t, approval=approval_for(t, ApprovalStatus.REJECTED, tail=910 + n))


async def _deny_decision(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.deny(t, decision=decision_for(t, tail=920 + n))


async def _queue(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.queue(t, reason=f"step {n}")


async def _start(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.start(t)


async def _heartbeat(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.heartbeat(t)


async def _complete(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.complete(t, result_for(t, tail=930 + n))


async def _fail(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.fail(t, ERROR)


async def _cancel(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.cancel(t)


async def _expire(h: Harness, t: TaskId, n: int) -> object:
    return await h.engine.expire(t)


async def _tick(h: Harness, t: TaskId, n: int) -> object:
    h.clock.advance(timedelta(seconds=n + 1))
    return await h.repository.get(t)


def _start_step(step_id: StepId) -> Step:
    async def op(h: Harness, t: TaskId, n: int) -> object:
        return await h.engine.start_step(t, step_id)

    return op


def _complete_step(step_id: StepId) -> Step:
    async def op(h: Harness, t: TaskId, n: int) -> object:
        return await h.engine.complete_step(t, step_id, step_result_for(t, step_id, tail=940 + n))

    return op


def _fail_step(step_id: StepId) -> Step:
    async def op(h: Harness, t: TaskId, n: int) -> object:
        return await h.engine.fail_step(t, step_id, ERROR)

    return op


async def _run_steps(h: Harness, t: TaskId, n: int) -> object:
    """Start and complete every ready step until nothing is ready: the way to COMPLETED."""
    state = await h.engine.graph(t)
    while ready := state.ready():
        for k, step_id in enumerate(ready):
            await h.engine.start_step(t, step_id)
            state = await h.engine.complete_step(
                t, step_id, step_result_for(t, step_id, tail=950 + 10 * n + k)
            )
    return state


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
    "run_steps": _run_steps,
    **{f"start_step_{i}": _start_step(sid(i)) for i in range(4)},
    **{f"complete_step_{i}": _complete_step(sid(i)) for i in range(4)},
    **{f"fail_step_{i}": _fail_step(sid(i)) for i in range(4)},
}
NOT_TRANSITIONS = {"plan", "heartbeat", "tick", "run_steps"} | {
    name for name in STEPS if "_step_" in name
}
STEP_OPS = {name for name in STEPS if "_step" in name}

walks = st.lists(st.sampled_from(sorted(STEPS)), min_size=1, max_size=30)


async def _walk(names: list[str], with_deadline: bool) -> None:
    h = make_harness()
    deadline = h.clock.now() + timedelta(seconds=10) if with_deadline else None
    task = await h.engine.create(USER_INTENT, deadline=deadline)
    transitions = 0
    plans = 0
    graph = TaskGraph(diamond())
    for n, name in enumerate(names):
        before = await h.snapshot(task.id)
        try:
            result = await STEPS[name](h, task.id, n)
        except (TaskEngineError, IllegalTransitionError, GraphError, NotFoundError):
            # NotFoundError: ``run_steps`` reads the graph of a task that has no plan yet.
            assert await h.snapshot(task.id) == before
            continue
        after = await h.snapshot(task.id)
        if name in STEP_OPS:
            assert isinstance(result, GraphState)
            assert result.states == graph.states(after.events)
            assert after.task == before.task
        else:
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
        # Invariants of the graph: the trail always folds, and every step move is one audit
        step_moves = [e for e in after.events if e.event_type in STEP_EVENTS]
        states = graph.states(after.events)
        if step_moves:
            assert after.task.plan_id is not None
        for step_id in graph.order:
            if states[step_id] in (StepState.RUNNING, StepState.COMPLETED):
                assert all(states[d] is StepState.COMPLETED for d in graph.dependencies(step_id))
            if states[step_id] in (StepState.FAILED, StepState.CANCELLED):
                assert all(states[d] is StepState.CANCELLED for d in graph.descendants(step_id))
        for e in step_moves:
            assert e.step_id is not None and e.step_id in graph
        if after.task.state is S.COMPLETED:
            assert graph.is_complete(states)
        types = [a.event_type for a in after.audit]
        assert types[0] is AuditEventType.TASK_CREATED
        assert len(types) == 1 + transitions + plans + len(step_moves)
        assert AuditEventType.TASK_CREATED not in types[1:]
        step_audits = [t for t in types if t.name.startswith("STEP_")]
        assert [t.name for t in step_audits] == [e.event_type.name for e in step_moves]


@given(names=walks, with_deadline=st.booleans())
@settings(max_examples=150, deadline=None)
def test_random_walks_keep_task_trail_and_audit_coherent(
    names: list[str], with_deadline: bool
) -> None:
    asyncio.run(_walk(names, with_deadline))
