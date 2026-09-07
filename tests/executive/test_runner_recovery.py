"""A crashed walk is resumed by calling ``run`` again (M6.3, ADR 0019 §8).

Same shape as ``test_executor_recovery.py``: each window of the table of ADR 0019 §8 has a test
that dies at that write and then repeats **the same call**, because that is what resuming is —
the runner keeps nothing between two iterations, so a new process and a new iteration are the
same thing. The windows the table leaves declared have their tests too, so that what a retry does
there is a fact and not a guess. :data:`REPAIRED` is what ``tests/docs/test_adr_runner.py``
compares with the ADR.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ela.domain import AuditEvent, AuditEventType, StepState, TaskEventType, TaskState
from ela.executive import RunnerError, RunOutcome, TaskRunner
from tests.executive.support import (
    SimulatedCrash,
    World,
    audit_of,
    crashing_world,
    saved_as,
    trail_of,
)
from tests.permissions.support import ECHO, NOTE

E = AuditEventType
REPAIRED = frozenset({"R2", "R3", "R4", "R5", "R6", "R8"})
"""The windows of ADR 0019 §8 a second ``run`` repairs: one ``test_window_<n>_…`` each, below."""


def nth(event_type: AuditEventType, after: int) -> Callable[[AuditEvent], bool]:
    """A predicate that lets the first ``after`` events of this type through and kills the next."""
    seen = 0

    def when(event: AuditEvent) -> bool:
        nonlocal seen
        if event.event_type is not event_type:
            return False
        seen += 1
        return seen > after

    return when


async def unavailable(w: World) -> None:
    await w.devices.update(w.node.model_copy(update={"last_seen_at": None}))


# --------------------------------------------------------------------------------------
# R1: the placement is written, nobody used it. Not repaired, and deliberately so.
# --------------------------------------------------------------------------------------


async def test_window_r1_a_placement_nobody_used_is_taken_again_not_reused() -> None:
    """A placement is advice, and stale advice must not be acted on: the retry asks again, and
    the second ``DEVICE_SELECTED`` is the honest record of a second decision (ADR 0017 §6.4)."""
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id)
    crashes.repository.arm("save", saved_as(TaskState.EXECUTING))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 1
    assert (await w.task(task.id)).state is TaskState.QUEUED
    assert (await w.engine.graph(task.id)).states[steps[0].id] is StepState.PENDING

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 2


# --------------------------------------------------------------------------------------
# R2: the task started, the step did not
# --------------------------------------------------------------------------------------


async def test_window_r2_a_started_task_whose_step_is_still_pending_is_picked_up() -> None:
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id)
    crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_STARTED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert (await w.task(task.id)).state is TaskState.EXECUTING
    assert (await w.engine.graph(task.id)).states[steps[0].id] is StepState.PENDING

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert (await w.event_types(task.id)).count(E.TASK_STARTED) == 1  # ``start`` is a no-op now
    assert len(w.tool(ECHO.id).calls) == 1


# --------------------------------------------------------------------------------------
# R3: the step is RUNNING and nothing else happened — ``ready()`` will never name it
# --------------------------------------------------------------------------------------


async def test_window_r3_a_step_left_running_is_picked_before_any_ready_one() -> None:
    """The property that makes the loop re-entrant (ADR 0019 §5). Without it the plan stalls:
    ``ready()`` returns PENDING steps only, so nobody would ever finish this one."""
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id, NOTE.id)
    crashes.audit.arm("append", audit_of(E.PERMISSION_DECIDED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    graph = await w.engine.graph(task.id)
    assert graph.states[steps[0].id] is StepState.RUNNING
    assert graph.ready() == (), "a RUNNING step is not ready: only the runner can pick it up"
    assert await w.results.for_step(task.id, steps[0].id) == ()

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == tuple(step.id for step in steps)


async def test_window_r3_the_resumed_step_keeps_the_node_it_was_started_on() -> None:
    """The second property (ADR 0019 §5): a RUNNING step is **not** placed again. Its node is a
    fact in ``STEP_STARTED``, and asking again could name another one."""
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id)
    crashes.audit.arm("append", audit_of(E.PERMISSION_DECIDED))
    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)
    crashes.disarm()
    placed = (await w.event_types(task.id)).count(E.DEVICE_SELECTED)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == placed == 1
    (stored,) = await w.results.for_step(task.id, steps[0].id)
    assert stored.device_id == w.node.id


# --------------------------------------------------------------------------------------
# R4: between two steps
# --------------------------------------------------------------------------------------


async def test_window_r4_a_crash_between_two_steps_loses_nothing() -> None:
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id, NOTE.id)
    crashes.audit.arm("append", nth(E.DEVICE_SELECTED, 1))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    graph = await w.engine.graph(task.id)
    assert graph.states[steps[0].id] is StepState.COMPLETED
    assert graph.states[steps[1].id] is StepState.PENDING

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (steps[1].id,)  # the first was already done
    assert len(w.tool(ECHO.id).calls) == 1
    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 2


# --------------------------------------------------------------------------------------
# R5: every step is COMPLETED, the task is not
# --------------------------------------------------------------------------------------


async def test_window_r5_a_finished_plan_whose_task_is_open_is_closed_by_the_retry() -> None:
    """And it is closed on the **same** result, so ``complete`` is a no-op if it already ran:
    the rule of ADR 0019 §6 is what makes the idempotency key stable across a crash."""
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id, NOTE.id)
    crashes.repository.arm("save", saved_as(TaskState.COMPLETED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    graph = await w.engine.graph(task.id)
    assert all(graph.states[step.id] is StepState.COMPLETED for step in steps)
    assert (await w.task(task.id)).state is TaskState.EXECUTING

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == ()  # nothing was executed again
    assert len(w.tool(NOTE.id).calls) == 1
    (last,) = await w.results.for_step(task.id, steps[-1].id)
    completed = next(e for e in await w.events(task.id) if e.event_type is E.TASK_COMPLETED)
    assert completed.payload["result_id"] == str(last.id)
    assert (await w.event_types(task.id)).count(E.TASK_COMPLETED) == 1


# --------------------------------------------------------------------------------------
# R6: the step failed, the task did not
# --------------------------------------------------------------------------------------


async def test_window_r6_a_blocked_plan_whose_task_is_open_is_failed_by_the_retry() -> None:
    w, crashes = crashing_world(failing=frozenset({ECHO.id}))
    task, steps = await w.queued(ECHO.id, NOTE.id)
    crashes.repository.arm("save", saved_as(TaskState.FAILED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    graph = await w.engine.graph(task.id)
    assert graph.states[steps[0].id] is StepState.FAILED
    assert graph.states[steps[1].id] is StepState.CANCELLED  # the cascade ran with ``fail_step``
    assert (await w.task(task.id)).state is TaskState.EXECUTING

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.steps == ()
    events = await w.events(task.id)
    step_failed = next(e for e in reversed(events) if e.event_type is E.STEP_FAILED)
    task_failed = next(e for e in reversed(events) if e.event_type is E.TASK_FAILED)
    assert task_failed.error == step_failed.error
    assert [e.event_type for e in events].count(E.TASK_FAILED) == 1


async def test_a_second_fail_on_an_already_failed_task_is_a_silent_no_op() -> None:
    """``fail`` has no idempotency key (engine ``OPERATIONS``), which is what lets the retry of
    R6 be safe even when the crash came *after* the task was failed."""
    w = crashing_world(failing=frozenset({ECHO.id}))[0]
    task, _ = await w.queued(ECHO.id)
    first = await w.runner.run(task.id)
    assert first.outcome is RunOutcome.FAILED
    before = len(await w.events(task.id))

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.FAILED
    assert len(await w.events(task.id)) == before


# --------------------------------------------------------------------------------------
# R7 and R9: the engine's holes, declared and not repaired (as windows 4, 5b and 9)
# --------------------------------------------------------------------------------------


async def test_window_r7_a_wait_saved_without_its_audit_is_the_engines_hole() -> None:
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id, NOTE.id)
    await w.runner.run(task.id)  # the first step goes through, the task is EXECUTING
    assert (await w.task(task.id)).state is TaskState.COMPLETED

    later, steps = await w.queued(ECHO.id, NOTE.id)
    await w.engine.start(later.id, device_id=w.node.id)
    await w.engine.start_step(later.id, steps[0].id, device_id=w.node.id)
    await w.execute(later.id, steps[0].id)
    await unavailable(w)
    crashes.audit.arm("append", audit_of(E.TASK_QUEUED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(later.id)

    assert (await w.task(later.id)).state is TaskState.QUEUED  # saved
    assert (await w.event_types(later.id)).count(E.TASK_QUEUED) == 1  # only the plan's, not this
    crashes.disarm()

    run = await w.runner.run(later.id)

    assert run.outcome is RunOutcome.WAITING_DEVICE  # the walk goes on; the event stays missing
    assert (await w.event_types(later.id)).count(E.TASK_QUEUED) == 1


async def test_window_r9_a_completed_task_without_its_audit_is_the_engines_hole() -> None:
    w, crashes = crashing_world()
    task, _ = await w.queued(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TASK_COMPLETED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert (await w.task(task.id)).state is TaskState.COMPLETED
    assert E.TASK_COMPLETED not in await w.event_types(task.id)

    crashes.disarm()
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED  # reported at the door, nothing written
    assert E.TASK_COMPLETED not in await w.event_types(task.id)


# --------------------------------------------------------------------------------------
# R8: the process dies while the user thinks
# --------------------------------------------------------------------------------------


async def test_window_r8_a_run_resumes_a_waiting_task_in_a_process_that_never_saw_it() -> None:
    """A new ``TaskRunner`` over the same stores finishes what another one started: the loop
    keeps nothing in memory between two iterations, so a restart is just the next call."""
    w = crashing_world()[0]
    task, steps = await w.queued(ECHO.id, NOTE.id)
    await w.engine.start(task.id, device_id=w.node.id)
    await w.engine.start_step(task.id, steps[0].id, device_id=w.node.id)

    reborn = TaskRunner(
        engine=w.engine,
        orchestrator=w.orchestrator,
        executor=w.executor,
        repository=w.repository,
        results=w.results,
        audit=w.audit,
    )
    run = await reborn.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == tuple(step.id for step in steps)
    assert (await w.event_types(task.id)).count(E.DEVICE_SELECTED) == 1  # only for the 2nd step


# --------------------------------------------------------------------------------------
# Window 9 of ADR 0015 seen from up here: a STEP_* in the trail with no audit event
# --------------------------------------------------------------------------------------


async def test_a_step_started_only_in_the_trail_cannot_be_resumed() -> None:
    """The engine's hole (ADR 0008 §4, ADR 0015 window 9) reaches the runner as a step that is
    RUNNING with nothing in the audit to say where. The node is not guessed (§33)."""
    w, crashes = crashing_world()
    task, steps = await w.queued(ECHO.id)
    crashes.audit.arm("append", audit_of(E.STEP_STARTED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert (await w.engine.graph(task.id)).states[steps[0].id] is StepState.RUNNING
    assert E.STEP_STARTED not in await w.event_types(task.id)

    crashes.disarm()
    with pytest.raises(RunnerError, match="no STEP_STARTED names the node"):
        await w.runner.run(task.id)


async def test_a_step_failed_only_in_the_trail_cannot_close_the_task() -> None:
    """Same hole on the other side: the plan is blocked and no recorded error says why, so the
    task is not failed on an error nobody wrote down."""
    w, crashes = crashing_world(failing=frozenset({ECHO.id}))
    task, steps = await w.queued(ECHO.id)
    crashes.audit.arm("append", audit_of(E.STEP_FAILED))

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert (await w.engine.graph(task.id)).states[steps[0].id] is StepState.FAILED
    assert E.STEP_FAILED not in await w.event_types(task.id)

    crashes.disarm()
    with pytest.raises(RunnerError, match="no STEP_FAILED in the audit carries the error"):
        await w.runner.run(task.id)
