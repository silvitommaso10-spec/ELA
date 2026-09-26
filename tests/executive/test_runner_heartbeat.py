"""``local`` is alive whenever the runner is about to choose it (M13.3, C6 and form H; T-H1).

Until M13.3 ``local`` beat at start-up and at the start of every ``POST /tasks/{id}/run``, and the
runner placed every step of a walk without beating. A local step that lasted longer than the
heartbeat's TTL left ``local`` expired for the next step **of the same walk**: a ``LOCAL_ONLY`` task
went back to ``QUEUED`` with ``WAITING_DEVICE`` while the Mac was right there, and a ``TRUSTED`` one
sent its next step to another machine. ADR 0044 §8 put that case in the future — «un ``local``
scaduto […] diventerebbe un lavoro mandato altrove» —, and it was already here.

The precondition is built, not waited for: the first step's tool moves the Core's clock past the TTL
as it finishes. An event — the end of the step — and not a duration (ADR 0006 §13).
"""

from __future__ import annotations

from datetime import timedelta

from ela.devices import POWER_POINTS
from ela.domain import (
    AuditEventType,
    ExecutionResult,
    JsonMapping,
    PermissionDecision,
    PowerSource,
    TaskState,
)
from ela.executive import RunOutcome
from ela.testing.fakes import FakeLocalBeat
from tests.executive.support import HEARTBEAT_TTL, World, world
from tests.permissions.support import ECHO, GUARDED_ECHO, NOTE

PAST_THE_TTL = HEARTBEAT_TTL + timedelta(seconds=1)


def outlasting_the_heartbeat(w: World) -> None:
    """The echo of this world becomes a step that ends after ``local``'s heartbeat has expired —
    and, as it ends, the machine it ran on is unplugged: two facts the next placement has to see."""
    tool = w.fake_tools[ECHO.id]
    ran = tool.execute

    async def long_step(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        result = await ran(decision, arguments)
        w.clock.advance(PAST_THE_TTL)
        w.power.source = PowerSource.BATTERY
        return result

    tool.execute = long_step  # type: ignore[method-assign]


async def test_a_local_plan_whose_first_step_outlasts_the_heartbeat_is_walked_in_one_run() -> None:
    w = world()
    outlasting_the_heartbeat(w)
    task, steps = await w.queued(ECHO.id, NOTE.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED, run.reason
    assert run.task.state is TaskState.COMPLETED
    assert run.steps == tuple(step.id for step in steps)


async def test_the_second_step_is_placed_on_the_power_read_after_the_first_one_ended() -> None:
    """Decision 7 of the review: a fresh beat before **every** placement, not only the first.

    With a beat only at the start of the walk — or only from the loop, twenty seconds apart — the
    second step would be placed on the power source of a reading older than the end of the first,
    the periodic belief that ADR 0029 §7 forbids to decide an action. The machine is on the wall
    when the walk starts and on battery when the first step ends; the second placement says so.
    """
    w = world()
    w.power.source = PowerSource.AC
    outlasting_the_heartbeat(w)
    task, steps = await w.queued(ECHO.id, NOTE.id)

    await w.runner.run(task.id)

    placed = [e for e in await w.events(task.id) if e.event_type is AuditEventType.DEVICE_SELECTED]
    power = [e.payload["candidates"][0]["components"]["power"] for e in placed]
    assert power == [POWER_POINTS[PowerSource.AC], POWER_POINTS[PowerSource.BATTERY]]


async def test_the_runner_asks_for_a_beat_before_every_place_and_every_confirm() -> None:
    """A step placed and asked about, then confirmed on the next walk: a beat before each."""
    beat = FakeLocalBeat()
    w = world(beat=beat)
    task, _ = await w.queued(GUARDED_ECHO.id)

    asked = await w.runner.run(task.id)  # place, then the question
    assert beat.beats == 1
    (request,) = await w.approvals.for_task(task.id)
    await w.engine.approve(task.id, await w.answered(request))
    await w.alive()  # the quiet beat writes nothing: the node is kept alive by hand
    await w.runner.run(task.id)  # confirm the node of the RUNNING step

    assert asked.outcome is RunOutcome.WAITING_APPROVAL
    assert beat.beats == 2
