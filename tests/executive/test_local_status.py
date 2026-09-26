"""The status of ``local``, observed by the Core (M13.3, decision 2 of the review; ADR 0048 §13).

A node says ``IDLE`` when it is about to ask and ``BUSY`` while a tool of its own runs; ``local``
said nothing, and scored 0 where an idle node scored 10 — the PC of block B won the measurement
because nobody observed the Mac. Since M13.3 the Core says it, in the same beat decision 7 asks for
before every placement: **``BUSY`` while a tool runs on ``local``, from its start to its result
stored, else ``IDLE``** — the user's correction after the manual test (2026-09-26): a step waiting
for a yes is ``RUNNING`` and occupies nothing. The fact is the executor's, the one module that runs
a tool here, and the beat is given the question as it is given the power reading: ``ela.devices``
does not import ``ela.executive``.
"""

from __future__ import annotations

import pytest

from ela.devices import LOCAL_DEVICE_ID
from ela.domain import (
    DeviceStatus,
    ExecutionResult,
    JsonMapping,
    PermissionDecision,
    PrivacyLevel,
    StepState,
)
from ela.executive import TOOL_REFUSED, RunOutcome
from ela.ports import NotAllowedError
from tests.executive.support import World, world
from tests.permissions.support import ECHO, GUARDED_ECHO


async def local_status(w: World) -> DeviceStatus:
    (found,) = [device for device in await w.devices.devices() if device.id == LOCAL_DEVICE_ID]
    return found.status


# ----------------------------------------------------------------------------------------
# The fact: a tool running here, from its start to its result stored
# ----------------------------------------------------------------------------------------


async def test_the_executor_says_a_tool_runs_here_from_its_start_to_its_stored_result() -> None:
    """``BUSY`` from the start of the tool to the result stored — the Core's observation, the
    executor's to make: the one module that runs a tool on this machine."""
    w = world()
    seen: list[bool] = []
    tool = w.fake_tools[ECHO.id]
    ran = tool.execute
    stored = w.results.add

    async def watched(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        seen.append(w.executor.running_here())
        return await ran(decision, arguments)

    async def storing(result: ExecutionResult) -> None:
        seen.append(w.executor.running_here())
        await stored(result)

    tool.execute = watched  # type: ignore[method-assign]
    w.results.add = storing  # type: ignore[method-assign]
    task, _ = await w.queued(ECHO.id)
    assert w.executor.running_here() is False

    await w.runner.run(task.id)

    assert seen == [True, True]
    assert w.executor.running_here() is False


async def test_a_tool_that_refuses_the_decision_occupies_nothing_after() -> None:
    w = world()

    async def refusing(decision: PermissionDecision, arguments: JsonMapping) -> ExecutionResult:
        raise NotAllowedError(ECHO.id, "the tool said no")

    w.fake_tools[ECHO.id].execute = refusing  # type: ignore[method-assign]
    task, (step,) = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)

    (execution,) = run.executions
    assert execution.graph.states[step.id] is StepState.FAILED
    assert run.outcome is RunOutcome.FAILED
    assert TOOL_REFUSED in (run.reason or "")
    assert w.executor.running_here() is False


async def test_a_result_the_store_did_not_take_occupies_nothing_after() -> None:
    """The count is of this process, so it must come back down whatever the run does: a Mac left
    ``BUSY`` by one failed write would lose every placement to the PC until ELA restarts."""
    w = world()

    async def falling(result: ExecutionResult) -> None:
        raise OSError("the database fell over")

    w.results.add = falling  # type: ignore[method-assign]
    task, _ = await w.queued(ECHO.id)

    with pytest.raises(OSError, match="fell over"):
        await w.runner.run(task.id)

    assert w.executor.running_here() is False


# ----------------------------------------------------------------------------------------
# The beat carries it
# ----------------------------------------------------------------------------------------


async def test_the_beat_says_busy_while_a_tool_runs_here_and_idle_after() -> None:
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


async def test_a_step_handed_to_a_node_leaves_local_idle() -> None:
    """The tool runs there: its ``BUSY`` is the node's to say, in its own heartbeat."""
    w = world()
    await w.remote()
    task, _ = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)

    run = await w.runner.run(task.id)
    await w.heartbeat.beat()

    assert run.outcome is RunOutcome.ASSIGNED
    assert await local_status(w) is DeviceStatus.IDLE
