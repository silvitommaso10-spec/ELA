"""A retry resumes what a crash left unfinished (ADR 0015 §5–§8).

Every window of the table of ADR 0015 §8 that says **Riparato** has a test here that dies at
that write — a port refuses it, ``SimulatedCrash``, the process is gone — and retries the same
call: the tool never runs twice, the audit gets what it lacked, the step is closed. The windows
the table leaves declared have their tests too, so that what a retry does there is a fact and
not a guess. :data:`REPAIRED` is what ``tests/docs/test_adr_recovery.py`` compares with the ADR.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from ela.domain import (
    ApprovalStatus,
    AuditEventType,
    ExecutionResult,
    ExecutionStatus,
    StepState,
    TaskEventType,
    TaskState,
)
from ela.executive import RECOVERED, VERIFICATION_FAILED, Executor, ExecutorError
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from tests.executive.support import (
    BAD,
    OK,
    SimulatedCrash,
    World,
    audit_of,
    count,
    crashing_world,
    grant_for,
    only_result,
    saved_as,
    trail_of,
    world,
)
from tests.permissions.support import ECHO, ECHO_ARGS, GUARDED_ECHO, NOTE
from tests.tasks.support import ORPHAN_AFTER

E = AuditEventType
REPAIRED = frozenset({"1", "5", "7b", "8", "8a", "8b", "8c", "9a"})
"""The windows of ADR 0015 §8 a retry repairs: one ``test_window_<n>_…`` each, below."""
SECRET_ARGS = {"path": "workspace/notes/briefing.md", "body": "SECRET-BODY"}


# --------------------------------------------------------------------------------------
# Window 1: the grant is stored, its audit is not (ADR 0013 §3, still true)
# --------------------------------------------------------------------------------------


async def test_window_1_a_stored_grant_without_its_audit_is_recorded_not_minted_again() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    answer = await w.answered(asked.approval)
    await w.engine.approve(task.id, answer)
    await w.engine.start(task.id)
    crashes.audit.arm("append", audit_of(E.AUTHORIZATION_GRANTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    (minted,) = await w.store.for_capability(NOTE.id)
    assert E.AUTHORIZATION_GRANTED not in await w.event_types(task.id)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == minted
    assert await w.store.for_capability(NOTE.id) == (minted,)
    assert await count(w, task.id, E.AUTHORIZATION_GRANTED) == 1
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(NOTE.id).calls) == 1


# --------------------------------------------------------------------------------------
# Window 5: the request is stored, the task never waited on it
# --------------------------------------------------------------------------------------


async def test_window_5_a_stored_request_is_asked_again_not_duplicated() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    crashes.repository.arm("save", saved_as(TaskState.WAITING_APPROVAL))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    (stored,) = await w.approvals.for_task(task.id)
    assert stored.status is ApprovalStatus.PENDING
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    assert E.APPROVAL_REQUESTED not in await w.event_types(task.id)
    decided = await count(w, task.id, E.PERMISSION_DECIDED)

    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.approval == stored
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert await w.approvals.for_task(task.id) == (stored,)
    assert await count(w, task.id, E.PERMISSION_DECIDED) == decided
    assert (await w.event_types(task.id))[-1] is E.APPROVAL_REQUESTED
    assert (await w.events(task.id))[-1].payload["approval_id"] == str(stored.id)
    assert w.tool(NOTE.id).calls == ()
    # the request was real: answered, it runs the step
    await w.engine.approve(task.id, await w.answered(stored))
    await w.engine.start(task.id)
    resumed = await w.execute(task.id, step.id)
    assert resumed.graph.states[step.id] is StepState.COMPLETED
    assert resumed.authorization is not None and resumed.authorization.approval_id == stored.id


async def test_an_expired_unanswered_request_is_never_asked_again() -> None:
    """Decision C: the request stays as it was asked, the retry is refused before any write,
    and the task — EXECUTING, silent — is the orphan rule's (ADR 0008 §6)."""
    w, crashes = crashing_world(approval_ttl=timedelta(minutes=5))
    task, step = await w.running(NOTE.id, requires_authorization=True)
    crashes.repository.arm("save", saved_as(TaskState.WAITING_APPROVAL))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    (stored,) = await w.approvals.for_task(task.id)
    assert stored.expires_at is not None
    w.clock.advance(stored.expires_at - w.now)  # the exact instant: closed bound
    before = len(await w.events())
    with pytest.raises(ExecutorError, match=f"approval {stored.id} for step {step.id} expired"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert await w.approvals.for_task(task.id) == (stored,)  # still PENDING, as asked
    assert w.tool(NOTE.id).calls == ()
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    w.clock.advance(ORPHAN_AFTER)
    summary = await w.engine.recover()
    assert [t.id for t in summary.failed] == [task.id]
    assert summary.expired == ()  # it never waited: an orphan, not an expired wait


async def test_window_5c_an_answer_the_engine_never_saw_is_the_callers_to_replay() -> None:
    """Declared, not the executor's: ``respond`` landed, ``approve`` died. The executor
    refuses (the task is not EXECUTING); ``approve`` again is what M8.1 does."""
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    answer = await w.answered(asked.approval)
    crashes.repository.arm("save", saved_as(TaskState.QUEUED))
    with pytest.raises(SimulatedCrash):
        await w.engine.approve(task.id, answer)
    assert (await w.task(task.id)).state is TaskState.WAITING_APPROVAL
    assert (await w.approvals.get(answer.id)).status is ApprovalStatus.GRANTED
    with pytest.raises(ExecutorError, match="not WAITING_APPROVAL"):
        await w.execute(task.id, step.id)
    crashes.disarm()
    await w.engine.approve(task.id, answer)
    await w.engine.start(task.id)
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert execution.authorization is not None
    assert execution.authorization.approval_id == answer.id


# --------------------------------------------------------------------------------------
# Windows 7a and 7b: around the tool
# --------------------------------------------------------------------------------------


async def test_window_7a_a_result_that_was_never_stored_means_the_tool_runs_again() -> None:
    """Declared: the effect and the insert are two systems. Narrowed to this instant."""
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    crashes.results.arm("add")
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    assert len(w.tool(ECHO.id).calls) == 1
    assert await w.results.for_step(task.id, step.id) == ()
    assert E.TOOL_EXECUTED not in await w.event_types(task.id)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is not None  # a whole new decision
    assert len(w.tool(ECHO.id).calls) == 2
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert await count(w, task.id, E.PERMISSION_DECIDED) == 2
    assert await count(w, task.id, E.TOOL_EXECUTED) == 1


async def test_window_7b_a_stored_result_without_its_audit_is_recorded_not_rerun() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    stored = await only_result(w, task.id, step.id)
    assert len(w.tool(ECHO.id).calls) == 1
    assert E.TOOL_EXECUTED not in await w.event_types(task.id)
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    decided = (await w.events(task.id))[-1]
    assert decided.event_type is E.PERMISSION_DECIDED
    assert stored.decision_id == decided.decision_id
    assert stored.authorization_id is None

    crashes.disarm()
    w.clock.advance(timedelta(seconds=30))
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.result == stored
    assert execution.verification is not None and execution.verification.passed
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(ECHO.id).calls) == 1
    assert len(w.verifier(ECHO.id).calls) == 1  # the crash came before any verification
    assert (await w.event_types(task.id))[-4:] == [
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    executed, verified = (await w.events(task.id))[-3:-1]
    assert executed.payload["result_id"] == str(stored.id)
    assert executed.decision_id == stored.decision_id
    assert executed.authorization_id is None
    assert executed.payload["uses"] is None
    assert executed.payload[RECOVERED] is True
    assert executed.created_at == w.now != stored.created_at
    assert executed.payload["targets"] == ()
    assert verified.payload[RECOVERED] is True
    assert verified.payload["result_id"] == str(stored.id)


async def test_window_7b_with_a_consumed_grant_names_it_and_reads_its_uses_now() -> None:
    """Decision E: ``uses`` is the store's count at the retry, and the payload says so."""
    w, crashes = crashing_world()
    task, step = await w.running(GUARDED_ECHO.id)
    policy = grant_for(GUARDED_ECHO, created_at=w.now, max_uses=3)
    await w.store.grant(policy)
    crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    stored = await only_result(w, task.id, step.id)
    assert stored.authorization_id == policy.id
    assert await w.store.uses(policy.id) == 1
    await w.store.consume(policy.id, now=w.now)  # someone else, meanwhile
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert await w.store.uses(policy.id) == 2  # the retry consumed nothing
    executed = next(e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED)
    assert executed.authorization_id == policy.id
    assert executed.payload["uses"] == 2
    assert executed.payload[RECOVERED] is True
    verified = next(e for e in await w.events(task.id) if e.event_type is E.EXECUTION_VERIFIED)
    assert verified.authorization_id == policy.id


async def test_window_7b_with_a_failed_result_records_it_and_fails_the_step() -> None:
    failing = FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=ExecutionStatus.FAILED)
    w, crashes = crashing_world(tools=(failing,))
    task, step = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.verification is None
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING
    assert (await w.event_types(task.id))[-2:] == [E.TOOL_EXECUTED, E.STEP_FAILED]
    executed, failed = (await w.events(task.id))[-2:]
    assert executed.payload["status"] == "FAILED" and executed.payload[RECOVERED] is True
    assert failed.error is not None and failed.error.code == "tool.failed"
    assert len(failing.calls) == 1
    assert w.verifier(ECHO.id).calls == ()


# --------------------------------------------------------------------------------------
# Windows 8, 8a, 8b, 8c: after the audit of the run
# --------------------------------------------------------------------------------------


async def test_window_8_a_recorded_failure_closes_the_step_without_a_rerun() -> None:
    failing = FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=ExecutionStatus.FAILED)
    w, crashes = crashing_world(tools=(failing,))
    task, step = await w.running(ECHO.id)
    crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    assert (await w.event_types(task.id))[-1] is E.TOOL_EXECUTED
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING
    assert len(failing.calls) == 1
    assert await count(w, task.id, E.TOOL_EXECUTED) == 1
    assert (await w.event_types(task.id))[-2:] == [E.TOOL_EXECUTED, E.STEP_FAILED]
    executed, failed = (await w.events(task.id))[-2:]
    assert RECOVERED not in executed.payload  # written with the run, not at the retry
    assert failed.error is not None and failed.error.code == "tool.failed"


async def test_window_8a_an_executed_unverified_result_is_verified_again_not_rerun() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.EXECUTION_VERIFIED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    assert (await w.event_types(task.id))[-1] is E.TOOL_EXECUTED
    calls = len(w.verifier(ECHO.id).calls)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.verification is not None and execution.verification.passed
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(ECHO.id).calls) == 1
    assert len(w.verifier(ECHO.id).calls) == calls + 1
    assert w.verifier(ECHO.id).calls[-1].result == execution.result
    assert (await w.event_types(task.id))[-3:] == [
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    executed, verified, _ = (await w.events(task.id))[-3:]
    assert RECOVERED not in executed.payload
    assert verified.payload[RECOVERED] is True
    assert verified.payload["result_id"] == executed.payload["result_id"]
    assert verified.decision_id == executed.decision_id
    assert verified.authorization_id == executed.authorization_id


async def test_window_8a_a_verification_that_fails_at_the_retry_fails_the_task() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    crashes.audit.arm("append", audit_of(E.EXECUTION_VERIFIED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.task.state is TaskState.FAILED
    assert execution.graph.states[step.id] is StepState.FAILED
    assert (await w.event_types(task.id))[-4:] == [
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_FAILED,
        E.TASK_FAILED,
    ]
    _, verified, step_failed, task_failed = (await w.events(task.id))[-4:]
    assert verified.error == step_failed.error == task_failed.error
    assert verified.error is not None and verified.error.code == VERIFICATION_FAILED
    assert verified.payload[RECOVERED] is True
    assert len(w.tool(ECHO.id).calls) == 1


async def test_window_8b_a_passed_verification_completes_the_step_without_verifying_again() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_COMPLETED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    assert (await w.event_types(task.id))[-1] is E.EXECUTION_VERIFIED
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert execution.verification is not None
    assert execution.verification.passed and execution.verification.failures == ()
    assert execution.verification.conditions == (OK,)
    assert len(w.tool(ECHO.id).calls) == 1
    assert len(w.verifier(ECHO.id).calls) == 1
    assert await count(w, task.id, E.EXECUTION_VERIFIED) == 1
    assert (await w.event_types(task.id))[-2:] == [E.EXECUTION_VERIFIED, E.STEP_COMPLETED]


async def test_window_8c_a_failed_verification_fails_step_and_task_without_a_second_look() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    crashes.repository.arm("append_event", trail_of(TaskEventType.STEP_FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    verified = (await w.events(task.id))[-1]
    assert verified.event_type is E.EXECUTION_VERIFIED and verified.error is not None
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is None
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.FAILED
    assert execution.verification is not None
    assert execution.verification.error == verified.error
    assert execution.verification.failures == ()  # not rebuilt: the error carries them
    assert execution.verification.error is not None
    assert [f["condition"] for f in execution.verification.error.details["failures"]] == [BAD]
    assert len(w.verifier(ECHO.id).calls) == 1
    assert await count(w, task.id, E.EXECUTION_VERIFIED) == 1
    assert (await w.event_types(task.id))[-3:] == [
        E.EXECUTION_VERIFIED,
        E.STEP_FAILED,
        E.TASK_FAILED,
    ]
    _, step_failed, task_failed = (await w.events(task.id))[-3:]
    assert step_failed.error == task_failed.error == verified.error


# --------------------------------------------------------------------------------------
# Window 9a: the step is FAILED by a verification, the task was to follow
# --------------------------------------------------------------------------------------


async def test_window_9a_a_step_failed_by_a_verification_fails_its_executing_task() -> None:
    w, crashes = crashing_world()
    task, first, second = await w.running_pair(ECHO.id, conditions=(BAD,))
    crashes.repository.arm("save", saved_as(TaskState.FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, first.id)
    graph = await w.engine.graph(task.id)
    assert graph.states[first.id] is StepState.FAILED
    assert graph.states[second.id] is StepState.CANCELLED
    assert graph.is_blocked
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    step_failed, cancelled = (await w.events(task.id))[-2:]
    assert step_failed.event_type is E.STEP_FAILED and step_failed.step_id == first.id
    assert cancelled.event_type is E.STEP_CANCELLED and cancelled.step_id == second.id

    crashes.disarm()
    execution = await w.execute(task.id, first.id)
    assert execution.decision is None and execution.result is None
    assert execution.task.state is TaskState.FAILED
    assert execution.graph.states[first.id] is StepState.FAILED
    task_failed = (await w.events(task.id))[-1]
    assert task_failed.event_type is E.TASK_FAILED
    assert task_failed.error == step_failed.error
    assert task_failed.error is not None and task_failed.error.code == VERIFICATION_FAILED
    assert len(w.tool(ECHO.id).calls) == 1
    assert len(w.verifier(ECHO.id).calls) == 1


async def test_a_step_failed_for_another_reason_leaves_the_task_to_the_orchestrator() -> None:
    """The asymmetry of ADR 0014 §4 holds on a retry too: a tool's own failure closed the step,
    not the task; the executor has nothing to finish and refuses as before."""
    failing = FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=ExecutionStatus.FAILED)
    w = world(tools=(failing,))
    task, step = await w.running(ECHO.id)
    await w.execute(task.id, step.id)
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is FAILED, not RUNNING"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert (await w.task(task.id)).state is TaskState.EXECUTING


# --------------------------------------------------------------------------------------
# The answer from the store
# --------------------------------------------------------------------------------------


async def test_a_rejected_request_denies_the_task_through_the_store(w: World) -> None:
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    answer = await w.answered(asked.approval, status=ApprovalStatus.REJECTED)
    denied = await w.engine.deny(task.id, approval=answer)
    assert denied.state is TaskState.DENIED
    assert (await w.event_types(task.id))[-1] is E.APPROVAL_RESOLVED
    assert await w.store.for_capability(NOTE.id) == ()
    assert w.tool(NOTE.id).calls == ()


async def test_the_last_granted_request_of_the_step_is_the_one_that_grants(w: World) -> None:
    """Window 6 end to end: the first yes was spent, the second yes runs the step."""
    task, step = await w.running(NOTE.id, requires_authorization=True)
    first_ask = await w.execute(task.id, step.id)
    assert first_ask.approval is not None
    first = await w.answered(first_ask.approval)
    await w.engine.approve(task.id, first)
    await w.engine.start(task.id)
    minted = await w.executor._grant(  # noqa: SLF001 — the grant of the first yes, spent
        first, await w.task(task.id), step, NOTE, w.now
    )
    await w.store.consume(minted[0].id, now=w.now)
    second_ask = await w.execute(task.id, step.id)
    assert second_ask.approval is not None and second_ask.approval.id != first.id
    assert second_ask.task.state is TaskState.WAITING_APPROVAL
    second = await w.answered(second_ask.approval)
    await w.engine.approve(task.id, second)
    await w.engine.start(task.id)
    execution = await w.execute(task.id, step.id)
    assert execution.authorization is not None
    assert execution.authorization.approval_id == second.id
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert [a.status for a in await w.approvals.for_task(task.id)] == [
        ApprovalStatus.GRANTED,
        ApprovalStatus.GRANTED,
    ]
    assert len(await w.store.for_capability(NOTE.id)) == 2
    assert len(w.tool(NOTE.id).calls) == 1


async def test_a_granted_request_of_another_step_is_not_seen(w: World) -> None:
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    other_task, other_step = await w.running(NOTE.id, requires_authorization=True)
    execution = await w.execute(other_task.id, other_step.id)
    assert execution.authorization is None
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert execution.approval is not None and execution.approval.task_id == other_task.id


# --------------------------------------------------------------------------------------
# Incoherences, the signature, privacy across a retry
# --------------------------------------------------------------------------------------


async def test_two_results_for_one_step_are_refused_before_anything(w: World) -> None:
    task, step = await w.running(ECHO.id)
    for tail in (1, 2):
        await w.results.add(
            ExecutionResult(
                id=w.ids.new_uuid(),  # type: ignore[arg-type]
                created_at=w.now,
                capability_id=ECHO.id,
                status=ExecutionStatus.SUCCEEDED,
                task_id=task.id,
                step_id=step.id,
                metadata={"tail": tail},
            )
        )
    before = len(await w.events())
    with pytest.raises(
        ExecutorError, match="has 2 results and 0 started records; a step runs once"
    ):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert w.tool(ECHO.id).calls == ()


async def test_the_approval_and_arguments_parameters_and_the_optional_stores_are_gone(
    w: World,
) -> None:
    task, step = await w.running(ECHO.id)
    with pytest.raises(TypeError):  # ``approval`` went in ADR 0015 §4
        await w.executor.execute(task.id, step.id, device_id=w.node.id, approval=None)  # type: ignore[call-arg]
    with pytest.raises(TypeError):  # ``arguments`` went in ADR 0018: they are the step's
        await w.executor.execute(task.id, step.id, ECHO_ARGS, device_id=w.node.id)  # type: ignore[call-arg]
    with pytest.raises(TypeError):  # and the node is mandatory (ADR 0019 §4)
        await w.executor.execute(task.id, step.id)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        Executor(  # type: ignore[call-arg]
            registry=w.registry,
            tools=w.tools,
            verifiers=w.verifiers,
            guardian=w.guardian,
            engine=w.engine,
            repository=w.repository,
            authorizations=w.store,
            audit=w.audit,
            clock=w.clock,
            ids=w.ids,
            actor=w.executor._actor,  # noqa: SLF001
        )


async def test_nothing_of_the_user_enters_the_audit_on_a_retry_either() -> None:
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id)
    crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    serialized = json.dumps([e.model_dump(mode="json") for e in await w.events()])
    assert "SECRET-BODY" not in serialized
    assert "workspace/notes/briefing.md" in serialized
    assert "SECRET-BODY" not in json.dumps(
        [a.model_dump(mode="json") for a in await w.approvals.for_task(task.id)]
    )


@pytest.fixture
def w() -> World:
    return world()


async def test_window_9_a_step_failed_in_the_trail_without_its_audit_is_the_engines_hole() -> None:
    """Declared (ADR 0013 §8 row 9): the trail says FAILED, the audit lacks ``STEP_FAILED``;
    the executor finds nothing of its own to finish and refuses as before."""
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    crashes.audit.arm("append", audit_of(E.STEP_FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    assert (await w.event_types(task.id))[-1] is E.EXECUTION_VERIFIED
    crashes.disarm()
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is FAILED, not RUNNING"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert (await w.task(task.id)).state is TaskState.EXECUTING
