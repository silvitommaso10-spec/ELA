"""The STARTED protocol: a tool that cannot be run twice is never run twice (ADR 0021 §1–§2).

Crash window 7a of ADR 0015 §8 — the instant between the tool's effect and the insert of its
outcome — was repaired by *repeating* the tool, which is safe only while twice is once. For a
tool that says it is not, the executor writes an :class:`~ela.domain.ExecutionResult` with status
``STARTED`` before the call, and a retry that finds it with no outcome fails the step instead of
calling again.

The tests use a fake tool, not ``model.complete``: what is under test is the executor's protocol,
and it must hold for every non-idempotent tool, not for the one that happened to bring it. The
crash is a store that accepts the STARTED row and refuses the outcome — the narrowest simulation
of "the process died here" that does not need a process to die.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from ela.domain import (
    AuditEvent,
    AuditEventType,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    ProviderUsage,
    StepId,
    StepState,
    TaskId,
    TaskState,
)
from ela.executive import EXECUTION_INTERRUPTED, RECOVERED
from ela.ports import ExecutionResultStore
from ela.testing.fakes import FakeTool
from tests.executive.support import OK, World, fake_tools, world
from tests.permissions.support import ECHO

pytestmark = pytest.mark.anyio


class Crash(Exception):
    """The process dying between the tool's call and the insert of its outcome."""


class CrashingStore:
    """A store that accepts the ``STARTED`` record and dies on everything after it."""

    def __init__(self, inner: ExecutionResultStore) -> None:
        self.inner = inner
        self.armed = True

    async def add(self, result: ExecutionResult) -> None:
        if self.armed and result.status is not ExecutionStatus.STARTED:
            raise Crash
        await self.inner.add(result)

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        return await self.inner.get(result_id)

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        return await self.inner.for_step(task_id, step_id)


def a_world(*, idempotent: bool, usage: ProviderUsage | None = None) -> World:
    """A world whose ``core.echo`` tool declares ``idempotent`` and reports ``usage``."""
    built = world()
    tools = fake_tools(built.clock, built.ids)
    tools[ECHO.id] = FakeTool(
        ECHO.id,
        built.clock,
        built.ids,
        name=f"fake-{ECHO.id}",
        output={"ok": True},
        idempotent=idempotent,
        usage=usage,
    )
    fresh = world(tools=tools.values())
    fresh.fake_tools.update(tools)
    return fresh


async def running(w: World) -> tuple[TaskId, StepId]:
    task, step = await w.running(ECHO.id, conditions=(OK,))
    return task.id, step.id


# --------------------------------------------------------------------------------------
# The record is written before the call, and only for a tool that needs it
# --------------------------------------------------------------------------------------


async def test_a_non_idempotent_tool_leaves_a_started_record_before_its_outcome() -> None:
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)

    execution = await w.execute(task_id, step_id)

    started, outcome = await w.results.for_step(task_id, step_id)
    assert started.status is ExecutionStatus.STARTED
    assert outcome.status is ExecutionStatus.SUCCEEDED
    assert outcome is not None
    assert execution.result is not None
    assert execution.result.id == outcome.id
    assert outcome.metadata["started_id"] == str(started.id)
    assert await w.step_state(task_id, step_id) is StepState.COMPLETED


async def test_the_started_record_carries_the_decision_the_grant_and_the_node() -> None:
    """Everything the outcome will carry except the outcome (ADR 0021 §1)."""
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)

    execution = await w.execute(task_id, step_id)

    started, outcome = await w.results.for_step(task_id, step_id)
    assert execution.decision is not None
    assert started.decision_id == execution.decision.id == outcome.decision_id
    assert started.device_id == w.node.id == outcome.device_id
    assert started.task_id == task_id
    assert started.step_id == step_id
    assert started.tool_name == outcome.tool_name
    assert started.output == {}
    assert started.error is None
    assert started.usage is None


async def test_the_started_record_writes_no_audit_event() -> None:
    """Nothing has happened yet: ``TOOL_EXECUTED`` belongs to the outcome (ADR 0021 §1)."""
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)
    crashing = CrashingStore(w.results)
    w.executor._results = crashing  # noqa: SLF001

    with pytest.raises(Crash):
        await w.execute(task_id, step_id)

    assert AuditEventType.TOOL_EXECUTED not in await w.event_types(task_id)


async def test_an_idempotent_tool_leaves_no_started_record() -> None:
    """The old repair still applies to the old tools: nothing changes for them."""
    w = a_world(idempotent=True)
    task_id, step_id = await running(w)

    await w.execute(task_id, step_id)

    (only,) = await w.results.for_step(task_id, step_id)
    assert only.status is ExecutionStatus.SUCCEEDED
    assert "started_id" not in only.metadata


# --------------------------------------------------------------------------------------
# The retry does not call again (ADR 0021 §2)
# --------------------------------------------------------------------------------------


async def test_a_retry_after_the_crash_does_not_call_the_tool_again() -> None:
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)
    crashing = CrashingStore(w.results)
    w.executor._results = crashing  # noqa: SLF001
    with pytest.raises(Crash):
        await w.execute(task_id, step_id)
    assert len(w.tool(ECHO.id).calls) == 1
    crashing.armed = False

    execution = await w.execute(task_id, step_id)

    assert len(w.tool(ECHO.id).calls) == 1  # the tool is not run a second time
    assert await w.step_state(task_id, step_id) is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING  # the orchestrator decides about the task
    assert execution.decision is None  # no Guardian, no grant: the run is not restarted
    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.STARTED


async def test_the_interruption_is_audited_with_its_own_code_and_is_retryable() -> None:
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)
    crashing = CrashingStore(w.results)
    w.executor._results = crashing  # noqa: SLF001
    with pytest.raises(Crash):
        await w.execute(task_id, step_id)
    crashing.armed = False

    await w.execute(task_id, step_id)

    executed = next(
        e for e in await w.events(task_id) if e.event_type is AuditEventType.TOOL_EXECUTED
    )
    assert executed.error is not None
    assert executed.error.code == EXECUTION_INTERRUPTED
    assert executed.error.retryable is True  # the crash failed, not the request
    assert executed.error.tool_name == w.tool(ECHO.id).name
    assert executed.payload["status"] == ExecutionStatus.STARTED.value
    assert executed.payload[RECOVERED] is True
    failed = next(e for e in await w.events(task_id) if e.event_type is AuditEventType.STEP_FAILED)
    assert failed.error is not None
    assert failed.error.code == EXECUTION_INTERRUPTED


async def test_no_second_outcome_row_is_invented_for_an_interrupted_run() -> None:
    """What is known is that the tool was about to run, not that it ran and failed."""
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)
    crashing = CrashingStore(w.results)
    w.executor._results = crashing  # noqa: SLF001
    with pytest.raises(Crash):
        await w.execute(task_id, step_id)
    crashing.armed = False

    await w.execute(task_id, step_id)

    stored = await w.results.for_step(task_id, step_id)
    assert [r.status for r in stored] == [ExecutionStatus.STARTED]


async def test_the_audit_of_an_interruption_is_written_once() -> None:
    """Crash case 4 of ADR 0021 §12: between ``TOOL_EXECUTED`` and ``fail_step``.

    The step is still RUNNING, the STARTED record is still alone, and the retry must not write
    a second event for the same fact.
    """
    w = a_world(idempotent=False)
    task_id, step_id = await running(w)
    crashing = CrashingStore(w.results)
    w.executor._results = crashing  # noqa: SLF001
    with pytest.raises(Crash):
        await w.execute(task_id, step_id)
    crashing.armed = False
    started_record = (await w.results.for_step(task_id, step_id))[0]
    # the audit of the interruption, without the ``fail_step`` that follows it
    await w.executor._record_execution(  # noqa: SLF001
        w.tool(ECHO.id), started_record, (), None, recovered=True, error=_interruption(w)
    )
    before = _executions(await w.events(task_id))

    await w.execute(task_id, step_id)

    after = _executions(await w.events(task_id))
    assert before == after == 1
    assert await w.step_state(task_id, step_id) is StepState.FAILED


def _executions(events: Sequence[AuditEvent]) -> int:
    """How many ``TOOL_EXECUTED`` the trail holds: one per run, interrupted or not."""
    return len([e for e in events if e.event_type is AuditEventType.TOOL_EXECUTED])


def _interruption(w: World) -> ErrorMetadata:
    return ErrorMetadata(
        code=EXECUTION_INTERRUPTED, message="crash", tool_name=w.tool(ECHO.id).name
    )


# --------------------------------------------------------------------------------------
# What the call consumed reaches the audit trail (§32; ADR 0021 §3)
# --------------------------------------------------------------------------------------


USAGE = ProviderUsage(input_tokens=12, output_tokens=34, latency_ms=56)


async def test_the_usage_of_a_run_reaches_the_tool_executed_event() -> None:
    w = a_world(idempotent=False, usage=USAGE)
    task_id, step_id = await running(w)

    await w.execute(task_id, step_id)

    executed = next(
        e for e in await w.events(task_id) if e.event_type is AuditEventType.TOOL_EXECUTED
    )
    assert executed.usage == USAGE
    outcome = (await w.results.for_step(task_id, step_id))[1]
    assert outcome.usage == USAGE


async def test_a_tool_that_calls_no_provider_records_no_usage() -> None:
    """``None`` is not zero: a tool that made no call did not make a free one (ADR 0021 §3)."""
    w = a_world(idempotent=True)
    task_id, step_id = await running(w)

    await w.execute(task_id, step_id)

    executed = next(
        e for e in await w.events(task_id) if e.event_type is AuditEventType.TOOL_EXECUTED
    )
    assert executed.usage is None
