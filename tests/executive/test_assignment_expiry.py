"""When the work expires: released, or closed where it stands (M12.2, dec. F; ADR 0038 §8).

The measure of D6, exactly: the STARTED record is born at the claim and only for a tool that cannot
be repeated, so

* **never claimed** ⇒ no record ⇒ the step is **released**, whatever its tool;
* **claimed and silent** ⇒ a repeatable tool has no record and is released; one that cannot be
  repeated has its record and is closed ``interrupted``.

Each case is driven through ``run``, because the point is what a *later call* does with work that
expired — nobody sweeps, and the expiry is derived on read (ADR 0016 §3). The node of these tests
stops reporting on purpose: for D6 the instant a node is gone is the expiry of its work, not a
belief about the node, and a step that went back in play must not wait on the silent one.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import (
    AuditEventType,
    PrivacyLevel,
    StepState,
    TaskEventType,
    TaskState,
)
from ela.executive import EXECUTION_INTERRUPTED, RunOutcome, Standing
from tests.domain.examples import ELA_ACTOR
from tests.executive.support import World, world
from tests.permissions.support import ECHO

E = AuditEventType
T = TaskEventType
INSTANT = timedelta(microseconds=1)


async def _never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the Core ran the tool of a step it had handed to a node")


@pytest.fixture
def w() -> World:
    return world()


async def handed_to_a_node(w: World, *, repeatable: bool = True) -> tuple[Any, Any, Any, Any]:
    """An offer of one step to a node that is not this machine; the tool never runs here yet."""
    w.tool(ECHO.id).idempotent = repeatable
    w.tool(ECHO.id).execute = _never  # type: ignore[method-assign]
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id)
    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    return task, step, stand.assignment, remote


async def only_this_machine_is_alive(w: World) -> None:
    """This machine reports, the node does not: what the Core knows when a node goes quiet."""
    await w.alive()


def restored(w: World) -> None:
    """Give the echo tool back, for the run that re-places the step on this machine."""
    w.tool(ECHO.id).execute = world().tool(ECHO.id).execute  # type: ignore[method-assign]


# ----------------------------------------------------------------------------------------
# Never claimed: the step goes back in play, whatever the tool (criterion 10)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("repeatable", [True, False], ids=["core-echo", "a-tool-that-cannot-be"])
async def test_an_unclaimed_assignment_is_placed_again_whatever_the_tool(
    w: World, repeatable: bool
) -> None:
    """Criterion 10. Nobody took the work, so nobody can have acted: the step is released with the
    assignment's id as the key, a new ``DEVICE_SELECTED`` places it, and **no**
    ``execution.interrupted`` is written — choosing by the tool's idempotency here would fail a
    step nothing ever started."""
    task, step, assignment, remote = await handed_to_a_node(w, repeatable=repeatable)
    w.clock.advance(assignment.expires_at - w.now)
    await only_this_machine_is_alive(w)
    restored(w)

    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    released = [e for e in await w.repository.events(task.id) if e.event_type is T.STEP_RELEASED]
    assert [e.metadata.get("assignment_id") for e in released] == [str(assignment.id)]
    assert len([e for e in await w.events(task.id) if e.event_type is E.DEVICE_SELECTED]) == 2
    assert EXECUTION_INTERRUPTED not in str(await w.events(task.id))
    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)  # it ran here, once


async def test_the_expiry_is_closed(w: World) -> None:
    """Criterion 13's other half: at ``expires_at`` exactly the work is over — the deadline is
    closed (ADR 0005 §2-bis), and ``<`` instead of ``<=`` would leave the step out one more TTL."""
    task, step, assignment, remote = await handed_to_a_node(w)
    w.clock.advance(assignment.expires_at - w.now - INSTANT)
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.LIVE

    w.clock.advance(INSTANT)

    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.LAPSED


# ----------------------------------------------------------------------------------------
# Claimed and silent: released, or closed interrupted (criterion 11)
# ----------------------------------------------------------------------------------------


async def test_a_claimed_assignment_of_a_repeatable_tool_is_placed_again(w: World) -> None:
    """``core.echo`` took the work and said nothing: there is no STARTED record to protect, so the
    step is released and runs here — once."""
    task, step, assignment, remote = await handed_to_a_node(w)
    await w.executor.begin(assignment.id, remote.id)
    w.clock.advance(assignment.expires_at - w.now)
    await only_this_machine_is_alive(w)
    restored(w)

    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED


async def test_a_claimed_assignment_that_expired_closes_interrupted_even_if_the_node_is_gone(
    w: World,
) -> None:
    """Criterion 11. A tool that cannot be repeated was started on the node and never reported:
    whether it acted is unknown, so the step is FAILED ``execution.interrupted`` with
    ``retryable`` — and the Core never calls the tool.

    The node is **gone from the registry's view** (it stopped reporting), which is the case that
    would go wrong through ``confirm``: the run would come back ``WAITING_DEVICE`` and the step
    would stay RUNNING for ever. An assignment is read, not confirmed (ADR 0038 §10).
    """
    task, step, assignment, remote = await handed_to_a_node(w, repeatable=False)
    await w.executor.begin(assignment.id, remote.id)
    (record,) = await w.results.for_step(task.id, step.id)
    w.clock.advance(assignment.expires_at - w.now)
    await only_this_machine_is_alive(w)

    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert await w.step_state(task.id, step.id) is StepState.FAILED
    failed = [e for e in await w.events(task.id) if e.event_type is E.STEP_FAILED][-1]
    assert failed.error is not None
    assert failed.error.code == EXECUTION_INTERRUPTED
    assert failed.error.retryable is True
    assert failed.error.device_id == remote.id  # the node of the record, not of the retry
    executed = [e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED][-1]
    assert executed.payload["result_id"] == str(record.id)
    assert executed.payload["device"] == str(remote.id)
    assert len([e for e in await w.events(task.id) if e.event_type is E.DEVICE_SELECTED]) == 1
    assert w.tool(ECHO.id).calls == ()  # the tool never ran in this process
    assert run.outcome is RunOutcome.FAILED
    assert (await w.task(task.id)).state is TaskState.FAILED


async def test_a_released_step_is_released_once(w: World) -> None:
    """Criterion 27: the release is idempotent **by key**, read from the trail and not from the
    state of the last assignment. A step released, placed here and left RUNNING by a crash has an
    ``EXPIRED`` assignment behind it — and must not be released a second time, which would undo the
    placement that followed the first release."""
    task, step, assignment, remote = await handed_to_a_node(w)
    w.clock.advance(assignment.expires_at - w.now)
    await only_this_machine_is_alive(w)
    restored(w)
    await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    released = [e for e in await w.repository.events(task.id) if e.event_type is T.STEP_RELEASED]

    again = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert again.outcome is RunOutcome.COMPLETED
    assert [e for e in await w.repository.events(task.id) if e.event_type is T.STEP_RELEASED] == (
        released
    )
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.NONE


# ----------------------------------------------------------------------------------------
# The revocation is an expiry (D17)
# ----------------------------------------------------------------------------------------


async def test_a_revocation_expires_the_work_of_that_node_at_once(w: World) -> None:
    """Criterion 18. The Core does not push (D4): what the revocation does to work already taken is
    bring its expiry to **now**, so the next ``run`` applies dec. F a second later instead of
    waiting out the TTL. The offers the node can no longer take go with it.

    The two writes in the order the route makes them — ``revoke``, then ``cut_short`` — because they
    are two halves of one answer: the secret opens nothing any more, and the work it held is over.
    A death between them is repaired by revoking again (window ``A14``), and the test of that order
    is here: with only the cut, the node would still be eligible and would simply win the step back.
    """
    task, step, assignment, remote = await handed_to_a_node(w)
    await w.executor.begin(assignment.id, remote.id)

    await w.devices.revoke(remote.id, by=ELA_ACTOR)
    cut = await w.assignments.cut_short(remote.id)
    w.clock.advance(timedelta(seconds=1))
    await only_this_machine_is_alive(w)
    restored(w)
    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert cut == 1
    assert w.now < assignment.expires_at  # a second later, and the TTL has not passed
    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)  # it came back here
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED
