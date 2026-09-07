"""What must hold for *every* plan a runner walks, not only for the examples (ADR 0019).

The example tests fix the behaviour; these fix the shape of a walk. Two of them are the reason
the loop has no counter guarding it: termination is a property of the code — every iteration that
does not return closes a step — and a property is asserted, not defended with a branch nobody can
reach.
"""

from __future__ import annotations

import asyncio

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ela.domain import AuditEventType, StepState, TaskState
from ela.executive import OUTCOMES, RunOutcome
from tests.executive.support import OK, World, world
from tests.permissions.support import CRITICAL, ECHO, GUARDED_ECHO, NOTE

E = AuditEventType

#: Capabilities a generated plan may ask for: two that go through, one that asks the user, one
#: the Guardian denies. Enough for a walk to end in each of the ways it can end.
CAPABILITIES = st.sampled_from([ECHO.id, NOTE.id, GUARDED_ECHO.id, CRITICAL.id])
PLANS = st.lists(CAPABILITIES, min_size=1, max_size=5)
CHAINED = st.booleans()

SETTINGS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


async def walk(capabilities: list[str], chain: bool) -> tuple[World, object, tuple[object, ...]]:
    w = world()
    task, steps = await w.queued(*capabilities, conditions=(OK,), chain=chain)
    run = await w.runner.run(task.id)
    return w, run, steps


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_a_run_executes_each_step_at_most_once(capabilities: list[str], chain: bool) -> None:
    """The invariant that makes the loop terminate without a counter (ADR 0019 §3): a step runs
    once, so a walk cannot iterate more times than the plan has steps."""
    _, run, steps = asyncio.run(walk(capabilities, chain))
    assert len(set(run.steps)) == len(run.steps)
    assert len(run.steps) <= len(steps)
    assert set(run.steps) <= {step.id for step in steps}


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_a_walk_ends_in_a_state_that_explains_its_outcome(
    capabilities: list[str], chain: bool
) -> None:
    """The outcome is never a story the runner tells: it is read off the task, or it is the one
    state — QUEUED — in which the task is waiting for a node."""
    _, run, _ = asyncio.run(walk(capabilities, chain))
    if run.outcome is RunOutcome.WAITING_DEVICE:
        assert run.task.state is TaskState.QUEUED
    else:
        assert OUTCOMES[run.task.state] is run.outcome


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_every_executed_step_was_placed_and_started_on_the_same_node(
    capabilities: list[str], chain: bool
) -> None:
    """The node an execution records is the node the orchestrator chose for that step, and the
    one ``STEP_STARTED`` names: no execution attributes an effect to a node nobody picked."""
    w, run, _ = asyncio.run(walk(capabilities, chain))
    events = asyncio.run(w.events(run.task.id))
    for execution in run.executions:
        started = [
            e for e in events if e.event_type is E.STEP_STARTED and e.step_id == execution.step_id
        ]
        assert [e.device_id for e in started] == [w.node.id]
        if execution.result is not None:
            assert execution.result.device_id == w.node.id


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_a_walk_never_leaves_a_completed_plan_on_an_open_task(
    capabilities: list[str], chain: bool
) -> None:
    """If every step is COMPLETED when ``run`` returns, the task is COMPLETED too: the loop does
    not stop one write short of closing what it finished."""
    w, run, steps = asyncio.run(walk(capabilities, chain))
    graph = asyncio.run(w.engine.graph(run.task.id))
    if all(graph.states[step.id] is StepState.COMPLETED for step in steps):
        assert run.task.state is TaskState.COMPLETED


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_a_walk_never_leaves_a_blocked_plan_on_an_executing_task(
    capabilities: list[str], chain: bool
) -> None:
    """A plan that can never complete never leaves its task EXECUTING: somebody has decided, and
    since ADR 0014 §4 left that decision to whoever orchestrates, that somebody is the runner."""
    w, run, _ = asyncio.run(walk(capabilities, chain))
    graph = asyncio.run(w.engine.graph(run.task.id))
    if graph.is_blocked:
        assert run.task.state is not TaskState.EXECUTING


@given(capabilities=PLANS, chain=CHAINED)
@SETTINGS
def test_a_walk_writes_no_audit_event_type_of_its_own(capabilities: list[str], chain: bool) -> None:
    """Whatever the plan, the runner adds no kind of fact to the chain of §32 (ADR 0019 §2)."""
    w, run, _ = asyncio.run(walk(capabilities, chain))
    written = set(asyncio.run(w.event_types(run.task.id)))
    assert written <= {
        E.TASK_CREATED,
        E.TASK_PLANNING_STARTED,
        E.PLAN_CREATED,
        E.TASK_QUEUED,
        E.DEVICE_SELECTED,
        E.DEVICE_UNAVAILABLE,
        E.TASK_STARTED,
        E.STEP_STARTED,
        E.PERMISSION_DECIDED,
        E.APPROVAL_REQUESTED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
        E.STEP_FAILED,
        E.STEP_CANCELLED,
        E.TASK_COMPLETED,
        E.TASK_FAILED,
        E.TASK_DENIED,
    }
