"""A crash at any write, then a retry, ends where the uninterrupted run ends (ADR 0015 §5–§8).

Hypothesis picks a capability, a grant, a tool and a verifier as ``test_executor_properties``
does, plus the write that dies. The same call is made twice in a world whose write died and once
in a world where nothing died; the two worlds must agree on the step's state, the task's state
and the number of ``TOOL_EXECUTED`` and ``EXECUTION_VERIFIED`` events — and the tool must have
run once, except when the crash came before its result was stored (window 7a), where it runs
again by declared limit. Every ``TOOL_EXECUTED`` names a result the store holds.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    AuditEventType,
    ExecutionId,
    ExecutionStatus,
    StepState,
    TaskEventType,
    TaskState,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool, FakeVerifier
from tests.executive.support import (
    BAD,
    OK,
    Crashes,
    SimulatedCrash,
    World,
    audit_of,
    crashing_world,
    fake_verifier,
    grant_for,
    saved_as,
    trail_of,
)
from tests.permissions.support import ECHO, ECHO_ARGS, GUARDED_NOTE, HIGH, NOTE, NOTE_ARGS

E = AuditEventType


class Crash(Enum):
    NONE = "none"
    RESULT_STORED = "results.add"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    TASK_FAILED = "fail: save"


def arm(crashes: Crashes, crash: Crash) -> None:
    if crash is Crash.RESULT_STORED:
        crashes.results.arm("add")
    elif crash is Crash.TOOL_EXECUTED:
        crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    elif crash is Crash.EXECUTION_VERIFIED:
        crashes.audit.arm("append", audit_of(E.EXECUTION_VERIFIED))
    elif crash is Crash.STEP_COMPLETED:
        crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_COMPLETED))
    elif crash is Crash.STEP_FAILED:
        crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_FAILED))
    elif crash is Crash.TASK_FAILED:
        crashes.repository.arm("save", saved_as(TaskState.FAILED))


class Grant(Enum):
    NONE = "none"
    USABLE = "usable"
    EXHAUSTED = "exhausted"


CAPABILITIES = {
    ECHO.id: (ECHO, ECHO_ARGS),
    NOTE.id: (NOTE, NOTE_ARGS),
    GUARDED_NOTE.id: (GUARDED_NOTE, NOTE_ARGS),
    HIGH.id: (HIGH, ECHO_ARGS),
}


async def prepared(
    capability_key: str, grant: Grant, tool_status: ExecutionStatus, verdict: bool
) -> tuple[World, Crashes, FakeTool, FakeVerifier, Any, Any, Any]:
    spec, arguments = CAPABILITIES[capability_key]
    tool = FakeTool(spec.id, FakeClock(), FakeIdGenerator(), status=tool_status)
    verifier = fake_verifier(spec.id)
    w, crashes = crashing_world(tools=(tool,), verifiers=(verifier,))
    w.fake_tools, w.fake_verifiers = {spec.id: tool}, {spec.id: verifier}
    task, step = await w.running(spec.id, conditions=(OK,) if verdict else (OK, BAD))
    if grant is not Grant.NONE:
        stored = grant_for(spec, created_at=w.now, max_uses=1)
        await w.store.grant(stored)
        if grant is Grant.EXHAUSTED:
            await w.store.consume(stored.id, now=w.now)
    return w, crashes, tool, verifier, task, step, arguments


async def outcome(w: World, task: Any, step: Any) -> tuple[StepState, TaskState, int, int]:
    types = await w.event_types(task.id)
    return (
        await w.step_state(task.id, step.id),
        (await w.task(task.id)).state,
        types.count(E.TOOL_EXECUTED),
        types.count(E.EXECUTION_VERIFIED),
    )


async def run(
    capability_key: str,
    grant: Grant,
    tool_status: ExecutionStatus,
    verdict: bool,
    crash: Crash,
) -> None:
    reference, _, tool_ref, _, task_ref, step_ref, arguments = await prepared(
        capability_key, grant, tool_status, verdict
    )
    baseline = await reference.executor.execute(task_ref.id, step_ref.id, arguments)
    expected = await outcome(reference, task_ref, step_ref)

    w, crashes, tool, verifier, task, step, arguments = await prepared(
        capability_key, grant, tool_status, verdict
    )
    arm(crashes, crash)
    crashed = False
    try:
        await w.executor.execute(task.id, step.id, arguments)
    except SimulatedCrash:
        crashed = True
    crashes.disarm()
    if crashed:
        await w.executor.execute(task.id, step.id, arguments)

    ran = tool_ref.calls != ()
    spent = baseline.result is not None and baseline.result.authorization_id is not None
    if crashed and crash is Crash.RESULT_STORED:
        # window 7a, declared: nothing was stored, the retry is a whole new decision — and a
        # single-use grant the first run spent makes it a question to the user (ADR 0013 §8)
        assert len(tool.calls) == 2 if not spent else 1
        if spent:
            assert (await w.task(task.id)).state is TaskState.WAITING_APPROVAL
        else:
            assert await outcome(w, task, step) == expected
    else:
        assert await outcome(w, task, step) == expected
        assert len(tool.calls) == (1 if ran else 0)
    assert len(verifier.calls) <= 2  # at most once per call that reached the verifier
    for event in await w.events(task.id):
        if event.event_type in (E.TOOL_EXECUTED, E.EXECUTION_VERIFIED):
            stored = await w.results.get(ExecutionId(UUID(str(event.payload["result_id"]))))
            assert stored.step_id == step.id
    if ran and not (crashed and crash is Crash.RESULT_STORED and spent):
        assert await w.step_state(task.id, step.id) is not StepState.RUNNING


@settings(max_examples=150, deadline=None)
@given(
    capability_key=st.sampled_from(sorted(CAPABILITIES)),
    grant=st.sampled_from(list(Grant)),
    tool_status=st.sampled_from([ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED]),
    verdict=st.booleans(),
    crash=st.sampled_from(list(Crash)),
)
def test_a_crash_and_a_retry_end_where_the_uninterrupted_run_ends(
    capability_key: str,
    grant: Grant,
    tool_status: ExecutionStatus,
    verdict: bool,
    crash: Crash,
) -> None:
    asyncio.run(run(capability_key, grant, tool_status, verdict, crash))


@pytest.mark.parametrize("crash", [c for c in Crash if c is not Crash.NONE], ids=lambda c: c.value)
def test_every_crash_point_is_reachable(crash: Crash) -> None:
    """The property would hold vacuously on a crash that never fires: each one does, on the
    run that reaches it (a SUCCEEDED echo with a failing verification reaches them all)."""

    async def reach() -> bool:
        verdict = crash not in (Crash.STEP_FAILED, Crash.TASK_FAILED)
        w, crashes, _, _, task, step, arguments = await prepared(
            ECHO.id, Grant.NONE, ExecutionStatus.SUCCEEDED, verdict
        )
        arm(crashes, crash)
        try:
            await w.executor.execute(task.id, step.id, arguments)
        except SimulatedCrash:
            return True
        return False

    assert asyncio.run(reach())
