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

from ela.domain import ExecutionResult, JsonMapping, PermissionDecision, TaskState
from ela.executive import RunOutcome
from tests.executive.support import HEARTBEAT_TTL, World, world
from tests.permissions.support import ECHO, NOTE

PAST_THE_TTL = HEARTBEAT_TTL + timedelta(seconds=1)


def outlasting_the_heartbeat(w: World) -> None:
    """The echo of this world becomes a step that ends after ``local``'s heartbeat has expired."""
    tool = w.fake_tools[ECHO.id]
    ran = tool.execute

    async def long_step(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        result = await ran(decision, arguments)
        w.clock.advance(PAST_THE_TTL)
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
