"""How far a task may travel, and what that changes (M12.2, D18, D20; ADR 0038 §16).

Before this the answer was always "nowhere": ``run`` never passed ``max_privacy``, the default was
the strictest level, and the filter refused every node wider than it. That was the **safe default**
and not the defect — the defect was that nobody *could* declare anything else, which is a field
with no writer. Here it has one, and the two halves of criterion 4 are the two tasks below: one
nobody declared stays on this machine, one declared ``TRUSTED`` goes to the node that won it.

The last test is the **guard of criterion 32**, the commit order made executable: it fails if the
sensitivity of a task arrives before the remote branch. With the field and without the branch, a
declared task would simply run the winning node's work *here*, in this process — green everywhere
else, and exactly the silent divergence dec. O asks to be caught.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.devices import LOCAL_DEVICE_ID
from ela.domain import AuditEventType, PrivacyLevel, StepState, TaskState
from ela.executive import RunOutcome, Standing
from tests.executive.support import World, world
from tests.permissions.support import ECHO

E = AuditEventType


async def _never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the Core ran the work of a node that had won the step")


@pytest.fixture
def w() -> World:
    """A world with a node that is not this machine, built to win on points."""
    return world()


async def test_a_task_nobody_declared_stays_on_this_machine(w: World) -> None:
    """Criterion 4, the half that was already true and must stay true: the default is the strictest
    level, so a task created without a word about it is refused every node but ``local`` — and the
    reason each candidate was refused is ``PRIVACY``, written where whoever waits can read it."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert (await w.task(task.id)).max_privacy is PrivacyLevel.LOCAL_ONLY
    (selected,) = [e for e in await w.events(task.id) if e.event_type is E.DEVICE_SELECTED]
    assert selected.device_id == LOCAL_DEVICE_ID
    refusals = {c["device_id"]: c["refusals"] for c in selected.payload["candidates"]}
    assert "PRIVACY" in refusals[str(remote.id)]
    assert selected.payload["max_privacy"] == PrivacyLevel.LOCAL_ONLY.value


async def test_a_declared_task_reaches_the_node_that_won_it(w: World) -> None:
    """Criterion 4, the half M12.2 adds: the same plan and the same node, with the level declared at
    creation — and the step is handed out instead of being run here. The level is the task's, so the
    audit of the placement carries it: two policies of the user, compared in one place."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.ASSIGNED
    (selected,) = [e for e in await w.events(task.id) if e.event_type is E.DEVICE_SELECTED]
    assert selected.device_id == remote.id
    assert selected.payload["max_privacy"] == PrivacyLevel.TRUSTED.value
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.standing is Standing.LIVE
    assert stand.assignment is not None
    assert stand.assignment.device_id == remote.id


async def test_the_level_is_written_once_and_read_by_every_placement(w: World) -> None:
    """Immutable (D20): there is no operation that widens it, and every placement of that task reads
    the same value — which is what an argument of ``run`` could not promise, because a second call
    with nothing would judge the same task at the strictest level again."""
    await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    assert (await w.runner.run(task.id)).outcome is RunOutcome.ASSIGNED
    assert (await w.runner.run(task.id)).outcome is RunOutcome.ASSIGNED  # still TRUSTED
    assert (await w.task(task.id)).max_privacy is PrivacyLevel.TRUSTED
    created = [e for e in await w.events(task.id) if e.event_type is E.TASK_CREATED]
    assert [e.payload["max_privacy"] for e in created] == [PrivacyLevel.TRUSTED.value]


async def test_a_declared_task_never_runs_here_for_a_remote_node(w: World) -> None:
    """The guard of criterion 32 (dec. O): **the order of the commits, as a test.**

    The spy is the whole of it — the Core's echo tool raises if anything calls it. With the remote
    branch in place the node's work is handed out and the tool is never called here, so the spy
    stays quiet. Had the sensitivity arrived first, ``execute`` would have run the winning node's
    step in this process: the task would have completed, every other test would have passed, and
    the one thing that changed — *which machine ran the user's content* — would have changed in
    silence. That is the divergence this test refuses to let through.
    """
    w.tool(ECHO.id).execute = _never  # type: ignore[method-assign]
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.ASSIGNED
    assert w.tool(ECHO.id).calls == ()  # nothing ran in this process
    assert await w.results.for_step(task.id, step.id) == ()  # not even a STARTED record (D14)
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None and stand.assignment.device_id == remote.id
