"""The status of ``local``, observed by the Core (M13.3, decision 2 of the review; ADR 0048 §13).

A node says ``IDLE`` when it is about to ask and ``BUSY`` while a tool of its own runs; ``local``
said nothing, and scored 0 where an idle node scored 10 — the PC of block B won the measurement
because nobody observed the Mac. Since M13.3 the Core says it, in the same beat decision 7 asks for
before every placement: **``BUSY`` if a step is RUNNING on ``local``, else ``IDLE``**. The fact is
the Task Engine's — a step of a live task, started on ``local`` last and not ended — and the beat is
given the question as it is given the power reading: ``ela.devices`` does not import ``ela.tasks``.
"""

from __future__ import annotations

from uuid import uuid4

from ela.devices import LOCAL_DEVICE_ID
from ela.domain import (
    DeviceId,
    DeviceStatus,
    ExecutionResult,
    JsonMapping,
    PermissionDecision,
    PrivacyLevel,
)
from ela.executive import RunOutcome
from tests.executive.support import World, world
from tests.permissions.support import ECHO, GUARDED_ECHO


async def local_status(w: World) -> DeviceStatus:
    (found,) = [device for device in await w.devices.devices() if device.id == LOCAL_DEVICE_ID]
    return found.status


# ----------------------------------------------------------------------------------------
# The fact: a step RUNNING on a node, answered by the Task Engine
# ----------------------------------------------------------------------------------------


async def test_a_step_started_here_and_not_ended_is_running_here() -> None:
    w = world()
    await w.running(ECHO.id)

    assert await w.engine.running_on(LOCAL_DEVICE_ID) is True
    assert await w.engine.running_on(DeviceId(uuid4())) is False


async def test_a_step_that_ended_is_not_running_anywhere() -> None:
    w = world()
    task, step = await w.running(ECHO.id)

    await w.execute(task.id, step.id)

    assert await w.engine.running_on(LOCAL_DEVICE_ID) is False


async def test_a_step_running_on_a_node_is_that_node_s_and_not_this_machine_s() -> None:
    w = world()
    remote = await w.remote()
    task, step = await w.running(ECHO.id, start=False, max_privacy=PrivacyLevel.TRUSTED)
    await w.engine.start(task.id, device_id=remote.id)
    await w.engine.start_step(task.id, step.id, device_id=remote.id)

    assert await w.engine.running_on(remote.id) is True
    assert await w.engine.running_on(LOCAL_DEVICE_ID) is False


async def test_a_step_released_here_and_started_on_a_node_is_the_node_s() -> None:
    """The last start decides: a step handed back by an expiry and placed again elsewhere."""
    w = world()
    remote = await w.remote()
    task, step = await w.running(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)
    await w.engine.release_step(task.id, step.id, key=uuid4(), device_id=LOCAL_DEVICE_ID)
    await w.engine.start_step(task.id, step.id, device_id=remote.id)

    assert await w.engine.running_on(LOCAL_DEVICE_ID) is False
    assert await w.engine.running_on(remote.id) is True


async def test_with_no_live_task_nothing_is_running() -> None:
    assert await world().engine.running_on(LOCAL_DEVICE_ID) is False


# ----------------------------------------------------------------------------------------
# The beat carries it
# ----------------------------------------------------------------------------------------


async def test_the_beat_says_busy_while_a_step_runs_here_and_idle_after() -> None:
    """Criterion of decision 2: the beat asked while the echo is running here says ``BUSY``, and
    the one asked by the next placement, after the step ended, says ``IDLE``."""
    w = world()
    seen: list[DeviceStatus] = []
    tool = w.fake_tools[ECHO.id]
    ran = tool.execute

    async def watched(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        await w.heartbeat.beat()
        seen.append(await local_status(w))
        return await ran(decision, arguments)

    tool.execute = watched  # type: ignore[method-assign]
    task, _ = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)
    await w.heartbeat.beat()

    assert run.outcome is RunOutcome.COMPLETED
    assert seen == [DeviceStatus.BUSY]
    assert await local_status(w) is DeviceStatus.IDLE


# ----------------------------------------------------------------------------------------
# The correction of the manual test (2026-09-26): a question does not occupy the Mac
# ----------------------------------------------------------------------------------------


async def test_a_step_waiting_for_the_user_s_yes_leaves_local_idle() -> None:
    """The user's correction of decision 2, after the manual test: a step that waits for a yes is
    ``RUNNING`` and occupies nothing. A node is ``BUSY`` only while a tool of its own runs, and a
    question left open for hours would otherwise send every relocatable job to the PC with the Mac
    on the mains and idle."""
    w = world()
    task, _ = await w.queued(GUARDED_ECHO.id)

    run = await w.runner.run(task.id)
    await w.heartbeat.beat()

    assert run.outcome is RunOutcome.WAITING_APPROVAL
    assert await local_status(w) is DeviceStatus.IDLE


async def test_the_executor_says_a_tool_runs_here_from_its_start_to_its_stored_result() -> None:
    """``BUSY`` from the start of the tool to the result stored — the Core's observation, the
    executor's to make: the one module that runs a tool on this machine."""
    w = world()
    seen: list[bool] = []
    tool = w.fake_tools[ECHO.id]
    ran = tool.execute

    async def watched(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        seen.append(w.executor.running_here())
        return await ran(decision, arguments)

    tool.execute = watched  # type: ignore[method-assign]
    task, _ = await w.queued(ECHO.id)
    assert w.executor.running_here() is False

    await w.runner.run(task.id)

    assert seen == [True]
    assert w.executor.running_here() is False
