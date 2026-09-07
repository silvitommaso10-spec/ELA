"""The Task Runner: choose a step, choose a node, execute, close (M6.3, ADR 0019).

The world is the one of the executor tests, with the node, the registry, the orchestrator and
the runner wired in ``world()``. Every plan here is built through the engine and nothing writes
the repository by hand: what a test asserts is what a real walk produces.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.devices import Refusal
from ela.domain import (
    ApprovalStatus,
    AuditEventType,
    ErrorMetadata,
    PrivacyLevel,
    StepState,
    TaskState,
)
from ela.executive import RunnerError, RunOutcome
from tests.executive.support import BAD, HEARTBEAT_TTL, OK, World, world
from tests.permissions.support import CRITICAL, ECHO, GUARDED_ECHO, NOTE, grant
from tests.tasks.support import result_for

E = AuditEventType


@pytest.fixture
def w() -> World:
    return world()


async def unavailable(w: World) -> None:
    """The one node goes quiet: nothing is eligible any more (ADR 0016 §3)."""
    await w.devices.update(w.node.model_copy(update={"last_seen_at": None}))


# --------------------------------------------------------------------------------------
# The walk itself
# --------------------------------------------------------------------------------------


async def test_a_chain_of_three_steps_is_walked_to_completed_by_one_call(w: World) -> None:
    """The acceptance criterion of M6.3: one call, topological order, the task closed."""
    task, steps = await w.queued(ECHO.id, NOTE.id, ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.task.state is TaskState.COMPLETED
    assert run.steps == tuple(step.id for step in steps)
    assert len(run.executions) == 3
    graph = await w.engine.graph(task.id)
    assert all(graph.states[step.id] is StepState.COMPLETED for step in steps)


async def test_the_walk_starts_the_task_once_and_each_step_on_the_chosen_node(w: World) -> None:
    task, steps = await w.queued(ECHO.id, NOTE.id)

    await w.runner.run(task.id)

    types = await w.event_types(task.id)
    assert types.count(E.TASK_STARTED) == 1
    assert types.count(E.DEVICE_SELECTED) == 2  # one placement per step, none for the task
    assert types.count(E.TASK_COMPLETED) == 1
    started = [e for e in await w.events(task.id) if e.event_type is E.STEP_STARTED]
    assert [e.device_id for e in started] == [w.node.id, w.node.id]
    assert [e.step_id for e in started] == [step.id for step in steps]


async def test_every_result_carries_the_node_the_orchestrator_chose(w: World) -> None:
    task, steps = await w.queued(ECHO.id, NOTE.id)

    run = await w.runner.run(task.id)

    for execution in run.executions:
        assert execution.result is not None
        assert execution.result.device_id == w.node.id
    for step in steps:
        (stored,) = await w.results.for_step(task.id, step.id)
        assert stored.device_id == w.node.id


async def test_the_task_is_closed_on_the_result_of_the_last_step_in_topological_order(
    w: World,
) -> None:
    """ADR 0019 §6: a deterministic rule, so that a retry uses the same idempotency key."""
    task, steps = await w.queued(ECHO.id, NOTE.id)

    await w.runner.run(task.id)

    (last,) = await w.results.for_step(task.id, steps[-1].id)
    completed = next(e for e in await w.events(task.id) if e.event_type is E.TASK_COMPLETED)
    assert completed.payload["result_id"] == str(last.id)


async def test_independent_steps_are_walked_in_the_order_of_the_plan(w: World) -> None:
    """With no dependencies ``ready()`` names them all; the runner takes the first, in order."""
    task, steps = await w.queued(ECHO.id, NOTE.id, GUARDED_ECHO.id, chain=False)
    await w.store.grant(grant(GUARDED_ECHO, max_uses=None, expires_at=None))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == tuple(step.id for step in steps)


async def test_the_runner_writes_no_audit_event_of_its_own(w: World) -> None:
    """Every fact of a walk is someone else's event (ADR 0019 §2): ``place``, the engine, the
    executor. A type nobody else writes would mean the runner started narrating."""
    task, _ = await w.queued(ECHO.id, NOTE.id)

    await w.runner.run(task.id)

    assert set(await w.event_types(task.id)) == {
        E.TASK_CREATED,
        E.TASK_PLANNING_STARTED,
        E.PLAN_CREATED,
        E.TASK_QUEUED,
        E.DEVICE_SELECTED,
        E.TASK_STARTED,
        E.STEP_STARTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    }


async def test_the_decision_names_the_node_it_was_taken_about(w: World) -> None:
    """ADR 0019 §4: the node reaches ``PERMISSION_DECIDED``, and no rule of the Guardian."""
    task, _ = await w.queued(ECHO.id)

    await w.runner.run(task.id)

    decided = [e for e in await w.events(task.id) if e.event_type is E.PERMISSION_DECIDED]
    assert [e.device_id for e in decided] == [w.node.id]


async def test_the_conditions_of_every_step_are_the_ones_the_verifier_checked(w: World) -> None:
    task, steps = await w.queued(ECHO.id, NOTE.id, conditions=(OK,))

    run = await w.runner.run(task.id)

    for execution, step in zip(run.executions, steps, strict=True):
        assert execution.verification is not None
        assert execution.verification.conditions == step.success_conditions
        assert execution.verification.passed


# --------------------------------------------------------------------------------------
# A step that fails takes the task down with it (ADR 0014 §4, applied here)
# --------------------------------------------------------------------------------------


async def test_a_failed_step_fails_the_task_and_cancels_its_descendants() -> None:
    w = world(failing=frozenset({NOTE.id}))
    task, steps = await w.queued(ECHO.id, NOTE.id, ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.task.state is TaskState.FAILED
    assert run.steps == (steps[0].id, steps[1].id)  # the third was never attempted
    graph = await w.engine.graph(task.id)
    assert graph.states[steps[0].id] is StepState.COMPLETED
    assert graph.states[steps[1].id] is StepState.FAILED
    assert graph.states[steps[2].id] is StepState.CANCELLED


async def test_the_task_fails_with_the_very_error_of_the_step() -> None:
    """Not a second description of the same failure (ADR 0019 §7): the same metadata."""
    w = world(failing=frozenset({NOTE.id}))
    task, _ = await w.queued(ECHO.id, NOTE.id)

    await w.runner.run(task.id)

    events = await w.events(task.id)
    step_failed = next(e for e in reversed(events) if e.event_type is E.STEP_FAILED)
    task_failed = next(e for e in reversed(events) if e.event_type is E.TASK_FAILED)
    assert step_failed.error is not None
    assert task_failed.error == step_failed.error


async def test_a_failed_verification_closes_the_task_before_the_runner_looks(w: World) -> None:
    """The executor closes this one itself (ADR 0014 §4): the runner reports what it finds, and
    does not write a second ``TASK_FAILED``."""
    task, _ = await w.queued(ECHO.id, conditions=(BAD,))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.task.state is TaskState.FAILED
    assert (await w.event_types(task.id)).count(E.TASK_FAILED) == 1


async def test_a_denied_step_stops_the_walk_with_the_task_denied(w: World) -> None:
    task, steps = await w.queued(ECHO.id, CRITICAL.id, ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.DENIED
    assert run.task.state is TaskState.DENIED
    assert run.steps == (steps[0].id, steps[1].id)
    assert w.tool(CRITICAL.id).calls == ()


# --------------------------------------------------------------------------------------
# No eligible node: the task waits (ADR 0017 §6)
# --------------------------------------------------------------------------------------


async def test_no_eligible_node_leaves_the_task_queued_without_failing_it(w: World) -> None:
    """The acceptance criterion of M6.3: QUEUED, no ``TASK_FAILED``, one ``DEVICE_UNAVAILABLE``."""
    task, steps = await w.queued(ECHO.id)
    await unavailable(w)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.WAITING_DEVICE
    assert run.task.state is TaskState.QUEUED
    assert run.steps == ()
    assert (await w.engine.graph(task.id)).states[steps[0].id] is StepState.PENDING
    types = await w.event_types(task.id)
    assert E.TASK_FAILED not in types
    assert types.count(E.DEVICE_UNAVAILABLE) == 1  # the one ``place`` wrote, and no other


async def test_a_node_that_disappears_mid_plan_puts_the_task_back_to_queued(w: World) -> None:
    task, steps = await w.queued(ECHO.id, NOTE.id)
    first = await w.runner.run(task.id, max_privacy=PrivacyLevel.LOCAL_ONLY)
    assert first.outcome is RunOutcome.COMPLETED

    later, steps = await w.queued(ECHO.id, NOTE.id)
    await w.engine.start(later.id, device_id=w.node.id)
    await w.engine.start_step(later.id, steps[0].id, device_id=w.node.id)
    await w.execute(later.id, steps[0].id)  # the first step is done, the task EXECUTING
    await unavailable(w)

    run = await w.runner.run(later.id)

    assert run.outcome is RunOutcome.WAITING_DEVICE
    assert run.task.state is TaskState.QUEUED
    assert (await w.engine.graph(later.id)).states[steps[1].id] is StepState.PENDING
    assert E.TASK_FAILED not in await w.event_types(later.id)


async def test_every_retry_records_its_own_wait(w: World) -> None:
    """ADR 0017 §6.4: each call is a decision taken at a different instant, on a registry that
    may have changed, so each one writes its own event."""
    task, _ = await w.queued(ECHO.id)
    await unavailable(w)

    await w.runner.run(task.id)
    await w.runner.run(task.id)

    assert (await w.event_types(task.id)).count(E.DEVICE_UNAVAILABLE) == 2


async def test_the_wait_records_why_every_candidate_lost(w: World) -> None:
    task, _ = await w.queued(ECHO.id)
    await unavailable(w)

    await w.runner.run(task.id)

    waited = next(e for e in await w.events(task.id) if e.event_type is E.DEVICE_UNAVAILABLE)
    (candidate,) = waited.payload["candidates"]
    assert candidate["device_id"] == str(w.node.id)
    assert candidate["refusals"] == (Refusal.UNAVAILABLE.value,)


async def test_a_node_the_caller_will_not_tolerate_is_not_eligible(w: World) -> None:
    """``max_privacy`` is the runner's word and the default is the most restrictive level."""
    await w.devices.update(w.node.model_copy(update={"privacy": PrivacyLevel.CLOUD_ALLOWED}))
    task, _ = await w.queued(ECHO.id)

    assert (await w.runner.run(task.id)).outcome is RunOutcome.WAITING_DEVICE
    allowed = await w.runner.run(task.id, max_privacy=PrivacyLevel.CLOUD_ALLOWED)
    assert allowed.outcome is RunOutcome.COMPLETED


async def test_a_node_that_comes_back_lets_the_next_run_finish_the_plan(w: World) -> None:
    task, _ = await w.queued(ECHO.id, NOTE.id)
    await unavailable(w)
    assert (await w.runner.run(task.id)).outcome is RunOutcome.WAITING_DEVICE

    await w.devices.heartbeat(w.node.id)

    assert (await w.runner.run(task.id)).outcome is RunOutcome.COMPLETED


# --------------------------------------------------------------------------------------
# The approval: the walk stops, and the next one resumes it
# --------------------------------------------------------------------------------------


async def test_a_step_that_needs_consent_stops_the_walk_and_the_next_run_finishes_it(
    w: World,
) -> None:
    task, steps = await w.queued(GUARDED_ECHO.id, ECHO.id)

    asked = await w.runner.run(task.id)

    assert asked.outcome is RunOutcome.WAITING_APPROVAL
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.steps == (steps[0].id,)
    (request,) = await w.approvals.for_task(task.id)
    assert request.status is ApprovalStatus.PENDING

    await w.engine.approve(task.id, await w.answered(request))
    resumed = await w.runner.run(task.id)

    assert resumed.outcome is RunOutcome.COMPLETED
    assert resumed.steps == (steps[0].id, steps[1].id)
    types = await w.event_types(task.id)
    assert types.count(E.APPROVAL_REQUESTED) == 1  # no second request, no second decision
    assert len(await w.approvals.for_task(task.id)) == 1


async def test_the_resumed_step_is_not_placed_a_second_time(w: World) -> None:
    """ADR 0019 §5: a RUNNING step keeps the node it was started on. The node of a started step
    is a fact, not a decision to retake — re-placing could name a second one."""
    task, steps = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)
    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 1

    (request,) = await w.approvals.for_task(task.id)
    await w.engine.approve(task.id, await w.answered(request))
    await w.runner.run(task.id)

    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 1
    (stored,) = await w.results.for_step(task.id, steps[0].id)
    assert stored.device_id == w.node.id


async def test_a_rejected_request_leaves_the_task_denied_and_the_next_run_says_so(
    w: World,
) -> None:
    task, _ = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)
    (request,) = await w.approvals.for_task(task.id)
    answer = await w.answered(request, status=ApprovalStatus.REJECTED)
    await w.engine.deny(task.id, approval=answer)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.DENIED
    assert run.steps == ()


async def test_a_standing_grant_lets_a_guarded_step_run_without_asking(w: World) -> None:
    await w.store.grant(grant(GUARDED_ECHO, max_uses=None, expires_at=None))
    task, _ = await w.queued(GUARDED_ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert await w.approvals.for_task(task.id) == ()


# --------------------------------------------------------------------------------------
# The door: what a runner refuses, and what it finds already closed
# --------------------------------------------------------------------------------------


async def test_a_completed_task_is_reported_and_nothing_is_written(w: World) -> None:
    task, _ = await w.queued(ECHO.id)
    await w.runner.run(task.id)
    before = len(await w.events(task.id))

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.COMPLETED
    assert again.steps == () and again.executions == ()
    assert len(await w.events(task.id)) == before


async def test_a_cancelled_task_says_cancelled_and_a_run_touches_nothing(w: World) -> None:
    task, _ = await w.queued(ECHO.id)
    await w.engine.cancel(task.id, reason="the user changed their mind")
    before = len(await w.events(task.id))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.CANCELLED
    assert run.task.state is TaskState.CANCELLED
    assert len(await w.events(task.id)) == before


async def test_an_expired_task_says_expired_and_not_cancelled(w: World) -> None:
    """Two facts, two outcomes: somebody stopped this one, or time did (review of M6.3)."""
    task, _ = await w.queued(ECHO.id, deadline=w.now + timedelta(minutes=1))
    w.clock.advance(timedelta(minutes=2))
    await w.engine.expire(task.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.EXPIRED
    assert run.outcome is not RunOutcome.CANCELLED
    assert run.task.state is TaskState.EXPIRED


async def test_a_failed_task_is_reported_as_failed(w: World) -> None:
    task, _ = await w.queued(ECHO.id)
    await w.engine.start(task.id, device_id=w.node.id)
    await w.engine.fail(task.id, ErrorMetadata(code="x", message="something else failed it"))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.steps == ()


async def test_a_task_that_is_not_queued_or_executing_cannot_be_walked(w: World) -> None:
    fresh = await w.engine.create(w.intent())

    with pytest.raises(RunnerError, match="QUEUED or EXECUTING"):
        await w.runner.run(fresh.id)


async def test_a_plan_with_no_steps_cannot_close_a_task_and_is_refused(w: World) -> None:
    task, _ = await w.queued()

    with pytest.raises(RunnerError, match="no steps"):
        await w.runner.run(task.id)


async def test_two_running_steps_are_an_incoherence_the_runner_refuses(w: World) -> None:
    """A sequential runner leaves at most one; two means somebody else moved the trail (§33)."""
    task, steps = await w.queued(ECHO.id, ECHO.id, chain=False)
    await w.engine.start(task.id, device_id=w.node.id)
    await w.engine.start_step(task.id, steps[0].id, device_id=w.node.id)
    await w.engine.start_step(task.id, steps[1].id, device_id=w.node.id)

    with pytest.raises(RunnerError, match="2 steps are RUNNING"):
        await w.runner.run(task.id)


async def test_a_running_step_without_a_node_in_the_audit_is_refused(w: World) -> None:
    """The node is not invented: a step started without one cannot be resumed (§33)."""
    task, steps = await w.queued(ECHO.id)
    await w.engine.start(task.id, device_id=w.node.id)
    await w.engine.start_step(task.id, steps[0].id)  # the shape of before M6.3

    with pytest.raises(RunnerError, match="no STEP_STARTED names the node"):
        await w.runner.run(task.id)


async def test_a_completed_plan_whose_result_is_missing_cannot_close_the_task(w: World) -> None:
    task, steps = await w.queued(ECHO.id)
    await w.engine.start(task.id, device_id=w.node.id)
    await w.engine.start_step(task.id, steps[0].id, device_id=w.node.id)
    await w.engine.complete_step(  # a result the store never saw
        task.id,
        steps[0].id,
        result_for(task.id).model_copy(update={"step_id": steps[0].id}),
    )

    with pytest.raises(RunnerError, match="0 stored results"):
        await w.runner.run(task.id)


# --------------------------------------------------------------------------------------
# Time passing: a node is available because it keeps saying so, not because it once did
# --------------------------------------------------------------------------------------


async def test_a_walk_resumed_after_the_user_took_their_time_needs_a_node_still_alive(
    w: World,
) -> None:
    """The shape a long task really has (review of M6.3): the walk stops for a consent, the user
    thinks for longer than a heartbeat lasts, and the node has to still be there afterwards.

    The step already RUNNING resumes on the node it was started on — that is a fact in the audit,
    not a placement to retake — but the **next** step needs a placement, and there is nothing to
    place it on until the node says it is alive.
    """
    task, steps = await w.queued(GUARDED_ECHO.id, ECHO.id)
    asked = await w.runner.run(task.id)
    assert asked.outcome is RunOutcome.WAITING_APPROVAL

    (request,) = await w.approvals.for_task(task.id)
    w.clock.advance(HEARTBEAT_TTL * 5)  # the user thinks; the node says nothing
    await w.engine.approve(task.id, await w.answered(request))

    stalled = await w.runner.run(task.id)

    assert stalled.outcome is RunOutcome.WAITING_DEVICE
    assert stalled.steps == (steps[0].id,)  # the RUNNING one finished on its own node
    assert stalled.task.state is TaskState.QUEUED
    graph = await w.engine.graph(task.id)
    assert graph.states[steps[0].id] is StepState.COMPLETED
    assert graph.states[steps[1].id] is StepState.PENDING
    assert E.TASK_FAILED not in await w.event_types(task.id)

    await w.alive()
    finished = await w.runner.run(task.id)

    assert finished.outcome is RunOutcome.COMPLETED
    assert finished.steps == (steps[1].id,)


async def test_a_node_that_keeps_beating_carries_a_walk_across_the_deadline(w: World) -> None:
    task, steps = await w.queued(GUARDED_ECHO.id, ECHO.id)
    await w.runner.run(task.id)
    (request,) = await w.approvals.for_task(task.id)
    w.clock.advance(HEARTBEAT_TTL * 5)
    await w.alive()  # what a real node does while a task is open
    await w.engine.approve(task.id, await w.answered(request))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == tuple(step.id for step in steps)
