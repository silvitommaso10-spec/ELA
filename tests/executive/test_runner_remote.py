"""A step whose node is not this machine is handed out, not run here (M12.2, ADR 0038 §2, §10).

The world's own node **is** ``local``, so these tests add a node built to win on points and then
check what the runner does: the work goes out, the call returns ``ASSIGNED`` with the assignment's
own sentence, and nothing of the step ran in this process. The spy is the whole defence of
criterion 2 — a tool that raises if the Core calls it — because "it was assigned" and "it was
assigned *and also executed*" would otherwise look the same from outside.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import AuditEventType, PrivacyLevel, StepState, TaskState
from ela.executive import RunOutcome, Standing
from tests.executive.support import World, world
from tests.permissions.support import ECHO

E = AuditEventType
INSTANT = timedelta(microseconds=1)


async def _never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the Core ran the tool of a step it had handed to a node")


@pytest.fixture
def w() -> World:
    """A world whose echo tool must not be called here: the step of these tests goes out."""
    built = world()
    built.tool(ECHO.id).execute = _never  # type: ignore[method-assign]
    return built


async def test_a_step_placed_on_a_remote_node_is_assigned_not_executed(w: World) -> None:
    """Criterion 2. The task stays EXECUTING, the step RUNNING, and the reason names the node,
    the work and the deadline — what a person deciding whether to wait has to read."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.ASSIGNED
    assert run.steps == () and run.executions == ()  # this call executed nothing
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.standing is Standing.LIVE
    assert stand.assignment is not None
    assert run.reason is not None
    assert remote.name in run.reason
    assert str(stand.assignment.id) in run.reason
    assert stand.assignment.expires_at.isoformat() in run.reason
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    assert await w.results.for_step(task.id, step.id) == ()  # no STARTED until the claim (D14)


async def test_the_node_that_wins_is_the_node_that_works(w: World) -> None:
    """Criterion 3, at the runner: the node ``DEVICE_SELECTED`` names is the node the work is
    handed to. Before M12.2 the two could differ in silence — the step ran here whatever was
    chosen."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    await w.runner.run(task.id)

    (selected,) = [e for e in await w.events(task.id) if e.event_type is E.DEVICE_SELECTED]
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    assert selected.device_id == remote.id == stand.assignment.device_id


async def test_a_second_run_finds_the_work_still_out_and_writes_nothing(w: World) -> None:
    """Criterion 13's live half: at ``expires_at - 1µs`` the work is alive, so the run says so and
    touches nothing — no trail event, no audit event, no second assignment. The deadline is closed,
    and this is the side of it where the Core keeps its hands off."""
    await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)
    await w.runner.run(task.id)
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    before = (
        len(await w.repository.events(task.id)),
        len(await w.events()),
        len(await w.results.for_step(task.id, step.id)),
    )
    w.clock.advance(stand.assignment.expires_at - w.now - INSTANT)

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.ASSIGNED
    assert again.reason == await w.assignments.describe(stand.assignment)
    assert (
        len(await w.repository.events(task.id)),
        len(await w.events()),
        len(await w.results.for_step(task.id, step.id)),
    ) == before


async def test_a_step_of_this_machine_still_runs_here(w: World) -> None:
    """Dec. A, as a test beside the remote one: with no node but ``local`` the plan runs in this
    process, which is why the spy has to be taken off for this one."""
    w.tool(ECHO.id).execute = world().tool(ECHO.id).execute  # type: ignore[method-assign]
    task, (step,) = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)
    assert await w.assignments.standing(task.id, step.id) == (Standing.NONE, None)
