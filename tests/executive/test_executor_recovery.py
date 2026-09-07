"""A retry resumes what a crash left unfinished (ADR 0015 §5–§8).

Every window of the table of ADR 0015 §8 that says **Riparato** has a test here that dies at
that write — a port refuses it, ``SimulatedCrash``, the process is gone — and retries the same
call: the tool never runs twice, the audit gets what it lacked, the step is closed. The windows
the table leaves declared have their tests too, so that what a retry does there is a fact and
not a guess. :data:`REPAIRED` is what ``tests/docs/test_adr_recovery.py`` compares with the ADR.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from ela.domain import (
    ApprovalStatus,
    AuditEventType,
    AuthorizationId,
    ExecutionResult,
    ExecutionStatus,
    PermissionOutcome,
    StepState,
    TaskEventType,
    TaskState,
)
from ela.executive import RECOVERED, VERIFICATION_FAILED, Executor, ExecutorError
from ela.ports import NotFoundError
from ela.testing.fakes import (
    FakeAuthorizationStore,
    FakeClock,
    FakeIdGenerator,
    FakeTool,
)
from tests.executive.support import (
    BAD,
    OK,
    SimulatedCrash,
    World,
    audit_of,
    count,
    crashing_world,
    grant_for,
    moved_to,
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
OUTSIDE_THE_SCOPE = {"path": "workspace/other/x.md", "body": "..."}
"""Arguments the Guardian denies: the note is outside ``workspace/notes`` (ADR 0011 §5)."""


# --------------------------------------------------------------------------------------
# Window 0: the crash that left nothing behind
# --------------------------------------------------------------------------------------


async def test_window_0_a_crash_before_the_first_write_leaves_nothing_to_repair() -> None:
    """The emptiest row of the table, and the only one whose repair is "start over".

    ``execute`` reads a great deal before it writes anything — the task, the graph, the
    placement, the results of the step, its requests, its grants — and the first write of the
    whole call is the Guardian's ``PERMISSION_DECIDED``. A crash anywhere before it must leave
    the world exactly as the call found it, so that the retry is a first attempt and not a
    resumption. It does, and this is what says so.
    """
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    before = await w.event_types(task.id)
    trail_before = await w.repository.events(task.id)

    crashes.audit.arm("append")  # the first write of the call, whichever it turns out to be
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    assert await w.event_types(task.id) == before
    assert await w.repository.events(task.id) == trail_before
    assert await w.results.for_step(task.id, step.id) == ()
    assert await w.approvals.for_task(task.id) == ()
    assert await w.store.for_capability(ECHO.id) == ()
    assert w.tool(ECHO.id).calls == ()
    assert (await w.task(task.id)).state is TaskState.EXECUTING
    assert await w.step_state(task.id, step.id) is StepState.RUNNING

    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(ECHO.id).calls) == 1
    assert await count(w, task.id, E.PERMISSION_DECIDED) == 1  # one attempt, one decision


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
# Windows 2 and 3: after a write that landed, before the step that reads it
# --------------------------------------------------------------------------------------


async def test_window_2_a_granted_authorization_without_its_decision_is_not_minted_again() -> None:
    """The grant and its audit agree; what never happened is the ``authorize`` that follows.

    Nothing is inconsistent here — which is the point of the row: the retry finds a grant it
    already owns, an audit that already names it, and asks the Guardian again. One grant, one
    ``AUTHORIZATION_GRANTED``, one more decision. No hole.
    """
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)
    decided = await count(w, task.id, E.PERMISSION_DECIDED)

    crashes.audit.arm("append", audit_of(E.AUTHORIZATION_GRANTED), after=True)
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    (minted,) = await w.store.for_capability(NOTE.id)
    assert await w.store.uses(minted.id) == 0
    assert await count(w, task.id, E.AUTHORIZATION_GRANTED) == 1
    assert await count(w, task.id, E.PERMISSION_DECIDED) == decided  # no decision followed it
    assert w.tool(NOTE.id).calls == ()

    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == minted
    assert await w.store.for_capability(NOTE.id) == (minted,)  # no second grant
    assert await count(w, task.id, E.AUTHORIZATION_GRANTED) == 1  # no second event
    assert await count(w, task.id, E.PERMISSION_DECIDED) == decided + 1  # a new decision
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(NOTE.id).calls) == 1


async def test_window_3_a_decision_that_never_came_back_is_taken_again() -> None:
    """The Guardian wrote ``PERMISSION_DECIDED`` and the process died before the answer arrived.

    Not repaired, and on purpose: every decision is an event (ADR 0011 §8), so the retry decides
    again and writes a *second* ``PERMISSION_DECIDED``. Two decisions in the log for one step is
    not a duplicate to be cleaned up — it is two times ELA asked itself the question. What must
    not have happened is anything else: no tool, no result, the step still RUNNING.
    """
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.PERMISSION_DECIDED), after=True)
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    assert await count(w, task.id, E.PERMISSION_DECIDED) == 1
    first = (await w.events(task.id))[-1].decision_id
    assert first is not None
    assert w.tool(ECHO.id).calls == ()
    assert await w.results.for_step(task.id, step.id) == ()
    assert await w.step_state(task.id, step.id) is StepState.RUNNING

    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is not None and execution.decision.id != first
    assert await count(w, task.id, E.PERMISSION_DECIDED) == 2
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(w.tool(ECHO.id).calls) == 1


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
    await w.alive()  # the node kept reporting itself; it is the *request* that expired, not it
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


async def test_window_5b_a_request_no_event_names_is_still_answerable() -> None:
    """The promise of the row, never observed until now: the "yes" still arrives.

    The engine saved the task as WAITING_APPROVAL and died before writing either the trail
    event or the audit one, so nothing in the log says the question was ever asked. The retry is
    refused — the task is not EXECUTING, which is the hole of ADR 0008 §4 and stays open — and
    the row claims something more than that: that the ``Approval`` is in the store and can be
    answered, so the user's "yes" reaches the step it was about. It does.
    """
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    crashes.repository.arm("append_event", moved_to(TaskState.WAITING_APPROVAL))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    (stored,) = await w.approvals.for_task(task.id)
    assert stored.status is ApprovalStatus.PENDING
    assert stored.step_id == step.id
    assert (await w.task(task.id)).state is TaskState.WAITING_APPROVAL  # the save landed
    trail = await w.repository.events(task.id)
    assert all(event.new_state is not TaskState.WAITING_APPROVAL for event in trail)
    assert E.APPROVAL_REQUESTED not in await w.event_types(task.id)

    crashes.disarm()
    with pytest.raises(ExecutorError, match="a tool needs an EXECUTING task, not WAITING_APPROVAL"):
        await w.execute(task.id, step.id)
    assert w.tool(NOTE.id).calls == ()

    answer = await w.answered(stored)
    await w.engine.approve(task.id, answer)
    await w.engine.start(task.id)
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert execution.authorization is not None
    assert execution.authorization.approval_id == stored.id
    assert len(w.tool(NOTE.id).calls) == 1
    assert await w.approvals.for_task(task.id) == (answer,)  # one question, one answer


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
# Window 4: the denial the log never heard about
# --------------------------------------------------------------------------------------


async def test_window_4_a_denied_task_without_its_events_refuses_the_retry() -> None:
    """The Guardian said no, the engine saved DENIED and died before saying so anywhere.

    The declared hole of ADR 0008 §4, seen from the executor's side: the state is terminal and
    neither the trail nor the audit carries the transition, so nothing can be replayed — the
    retry is refused because the task is not EXECUTING, and that refusal is the whole promise
    of the row. What matters is what it does *not* do: no tool runs, and the ``PERMISSION_DECIDED``
    that was already written is not written a second time.
    """
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, arguments=OUTSIDE_THE_SCOPE)
    crashes.repository.arm("append_event", moved_to(TaskState.DENIED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    assert (await w.task(task.id)).state is TaskState.DENIED  # the save landed
    types = await w.event_types(task.id)
    assert types[-1] is E.PERMISSION_DECIDED and E.TASK_DENIED not in types
    trail = await w.repository.events(task.id)
    assert all(event.new_state is not TaskState.DENIED for event in trail)

    crashes.disarm()
    with pytest.raises(ExecutorError, match="a tool needs an EXECUTING task, not DENIED"):
        await w.execute(task.id, step.id)
    assert await w.event_types(task.id) == types  # nothing was written by the refusal
    assert w.tool(NOTE.id).calls == ()
    assert await w.store.for_capability(NOTE.id) == ()
    assert await w.step_state(task.id, step.id) is StepState.RUNNING  # the task is terminal


# --------------------------------------------------------------------------------------
# Window 6: the grant spent, and the tool that never ran
# --------------------------------------------------------------------------------------


async def test_window_6_a_grant_spent_before_the_tool_costs_a_second_yes() -> None:
    """The grant is single-use and it is gone; the user is asked again. Accepted, not repaired.

    ADR 0012 §6 chose this on purpose: the alternative — reusing a grant whose use was already
    counted — would mean the executor deciding that the effect did not happen, which is exactly
    what it cannot know. So the price of this window is a second question to the user, and the
    row promises that the question is really asked: a **second** ``Approval`` for the same step,
    born from a **second** decision, with the tool still untouched.
    """
    w, crashes = crashing_world()
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    crashes.authorizations.arm("consume", after=True)
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    (minted,) = await w.store.for_capability(NOTE.id)
    assert await w.store.uses(minted.id) == 1  # spent, and nothing was bought with it
    assert w.tool(NOTE.id).calls == ()
    assert await w.results.for_step(task.id, step.id) == ()
    assert await w.step_state(task.id, step.id) is StepState.RUNNING

    crashes.disarm()
    execution = await w.execute(task.id, step.id)
    assert execution.decision is not None
    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None and execution.approval.id != asked.approval.id
    assert execution.approval.step_id == step.id
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert len(await w.approvals.for_task(task.id)) == 2  # one question, then another
    assert await w.store.for_capability(NOTE.id) == (minted,)  # no second grant either
    assert w.tool(NOTE.id).calls == ()


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


# --------------------------------------------------------------------------------------
# Window 10: the same hole as 9, reached by the two failures that are not the verifier's
# --------------------------------------------------------------------------------------


class VanishedGrants(FakeAuthorizationStore):
    """A store whose grant is gone by the time it is consumed (``grant_vanished``).

    Who deleted it is not modelled and does not matter: the row is about what the executor does
    when the thing it was authorised by is not there any more.
    """

    async def consume(self, authorization_id: AuthorizationId, *, now: datetime) -> int:
        raise NotFoundError("authorization", authorization_id)


async def test_window_10_a_vanished_grant_fails_the_step_into_the_same_hole_as_9() -> None:
    """``fail_step`` for ``grant_vanished``: the trail says FAILED, the audit never heard.

    Row 9 is the engine's hole seen after a failed verification; row 10 says the same hole is
    reached by the two failures the verifier has nothing to do with. This is the first of them,
    and it matters that it behaves identically: the executor refuses the retry rather than
    inventing a way to finish a step it cannot see the end of.
    """
    w, crashes = crashing_world(grants=VanishedGrants())
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    crashes.audit.arm("append", audit_of(E.STEP_FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    assert await w.step_state(task.id, step.id) is StepState.FAILED
    assert E.STEP_FAILED not in await w.event_types(task.id)
    assert w.tool(NOTE.id).calls == ()  # it never got as far as the tool

    crashes.disarm()
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is FAILED, not RUNNING"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert (await w.task(task.id)).state is TaskState.EXECUTING


async def test_window_10_a_refused_tool_fails_the_step_and_leaves_the_grant_spent() -> None:
    """``fail_step`` for ``tool.refused``, and the price the row names: the grant is gone.

    The tool said no to a decision it considered expired, so nothing was done — and yet the
    single use of the grant was already counted. Resuming this step is not a matter of trying
    again: it costs the user a new "yes", because the authorisation that paid for the first
    attempt is exhausted. That is the sentence of the row, and this is it as a fact.
    """
    late = FakeTool(NOTE.id, FakeClock(FakeClock().now() + timedelta(days=1)), FakeIdGenerator())
    w, crashes = crashing_world(tools=(late,))
    w.fake_tools = {NOTE.id: late}
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    crashes.audit.arm("append", audit_of(E.STEP_FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)

    assert await w.step_state(task.id, step.id) is StepState.FAILED
    assert E.STEP_FAILED not in await w.event_types(task.id)
    assert late.calls == ()  # it refused the decision before acting
    (minted,) = await w.store.for_capability(NOTE.id)
    assert minted.max_uses == 1 and await w.store.uses(minted.id) == 1

    crashes.disarm()
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is FAILED, not RUNNING"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert (await w.task(task.id)).state is TaskState.EXECUTING
