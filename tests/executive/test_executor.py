"""``Executor.execute`` (ADR 0013): one step, one decision, one tool call at most.

Every precondition that fails writes nothing; every outcome of the Guardian is a move of the
engine; the tool runs only under ``ALLOWED`` and the step never stays RUNNING after it ran.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any
from uuid import uuid5

import pytest

from ela.domain import (
    ActorKind,
    ApprovalId,
    ApprovalStatus,
    AuditEventType,
    AuthorizationId,
    CapabilityId,
    ErrorMetadata,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    PrivacyLevel,
    StepId,
    StepState,
    TaskState,
)
from ela.executive import (
    APPROVAL_NAMESPACE,
    AUTHORIZATION_NAMESPACE,
    DEFAULT_APPROVAL_TTL,
    GRANT_VANISHED,
    MAX_APPROVAL_TTL,
    TOOL_EXCEPTION,
    TOOL_REFUSED,
    VERIFICATION_EXCEPTION,
    VERIFICATION_FAILED,
    ExecutorError,
)
from ela.permissions import ApprovalMismatchError, Rule, authorization_from_approval
from ela.ports import (
    AuthorizationExhaustedError,
    NotAllowedError,
    NotFoundError,
)
from ela.tasks.errors import UnknownStepError
from ela.testing.fakes import (
    FakeAuthorizationStore,
    FakeClock,
    FakeIdGenerator,
    FakeTool,
    FakeVerifier,
)
from tests.executive.support import (
    BAD,
    BAD_FAILURE,
    OK,
    World,
    fake_verifier,
    grant_for,
    world,
)
from tests.permissions.support import (
    COMPLETE,
    ECHO,
    ECHO_ARGS,
    GUARDED_ECHO,
    GUARDED_NOTE,
    HIGH,
    NOTE,
    NOTE_ARGS,
    SENSING_ECHO,
    STATED_ECHO,
)
from tests.tasks.support import result_for

E = AuditEventType
SECRET_ARGS = {"path": "workspace/notes/briefing.md", "body": "SECRET-BODY"}


@pytest.fixture
def w() -> World:
    return world()


async def nothing_written(w: World, before: int) -> None:
    assert len(await w.events()) == before
    for tool in w.fake_tools.values():
        assert tool.calls == ()
    for verifier in w.fake_verifiers.values():
        assert verifier.calls == ()


# --------------------------------------------------------------------------------------
# Preconditions: refused before anything is written
# --------------------------------------------------------------------------------------


async def test_a_task_that_is_not_executing_is_refused(w: World) -> None:
    task, step = await w.running(ECHO.id)
    await w.engine.queue(task.id, reason="interrupted")
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="needs an EXECUTING task, not QUEUED"):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)


@pytest.mark.parametrize("state", [TaskState.CANCELLED, TaskState.COMPLETED, TaskState.FAILED])
async def test_a_terminal_task_is_refused(w: World, state: TaskState) -> None:
    task, step = await w.running(ECHO.id)
    if state is TaskState.CANCELLED:
        await w.engine.cancel(task.id)
    elif state is TaskState.FAILED:
        await w.engine.fail(task.id, ErrorMetadata(code="x", message="x"))
    else:
        await w.execute(task.id, step.id)
        await w.engine.complete(task.id, result_for(task.id))
    assert (await w.task(task.id)).state is state
    before = len(await w.events())
    calls = len(w.tool(ECHO.id).calls)
    with pytest.raises(ExecutorError, match=f"needs an EXECUTING task, not {state.value}"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert len(w.tool(ECHO.id).calls) == calls


async def test_an_unknown_step_is_refused(w: World) -> None:
    task, _ = await w.running(ECHO.id)
    before = len(await w.events())
    with pytest.raises(UnknownStepError):
        await w.execute(task.id, StepId(w.ids.new_uuid()))
    await nothing_written(w, before)


async def test_a_completed_step_is_refused(w: World) -> None:
    task, step = await w.running(ECHO.id)
    await w.execute(task.id, step.id)
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is COMPLETED, not RUNNING: start the step first"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert len(w.tool(ECHO.id).calls) == 1


async def test_a_pending_step_is_refused(w: World) -> None:
    task, first, second = await w.running_pair(ECHO.id)
    assert await w.step_state(task.id, second.id) is StepState.PENDING
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="is PENDING, not RUNNING: start the step first"):
        await w.execute(task.id, second.id)
    await nothing_written(w, before)
    assert await w.step_state(task.id, first.id) is StepState.RUNNING


@pytest.mark.parametrize("capabilities", [(), (ECHO.id, NOTE.id)], ids=["none", "two"])
async def test_a_step_without_exactly_one_capability_is_refused(
    w: World, capabilities: tuple[CapabilityId, ...]
) -> None:
    task, step = await w.running(ECHO.id, capabilities=capabilities)
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="declares exactly one"):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)


async def test_an_unknown_capability_is_refused(w: World) -> None:
    task, step = await w.running(CapabilityId("nobody.knows_this"))
    before = len(await w.events())
    with pytest.raises(NotFoundError):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)


async def test_a_capability_without_a_tool_is_refused_before_any_decision(w: World) -> None:
    task, step = await w.running(COMPLETE.id)
    before = len(await w.events())
    with pytest.raises(NotFoundError, match="tool"):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)
    assert (await w.task(task.id)).state is TaskState.EXECUTING


# --------------------------------------------------------------------------------------
# What cannot be verified is not executed (ADR 0014 §3, decisions A and B)
# --------------------------------------------------------------------------------------


async def test_a_step_without_a_success_condition_is_refused(w: World) -> None:
    task, step = await w.running(ECHO.id, conditions=())
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="declares no success condition"):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)
    assert (await w.task(task.id)).state is TaskState.EXECUTING


async def test_a_condition_outside_the_verifiers_vocabulary_is_refused(w: World) -> None:
    task, step = await w.running(ECHO.id, conditions=(OK, "made.up", "also.made_up"))
    before = len(await w.events())
    with pytest.raises(ExecutorError, match="made.up, also.made_up"):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)


async def test_a_capability_without_a_verifier_is_refused_before_any_decision() -> None:
    """The tool exists, the verifier does not: no decision, no grant spent, nothing run."""
    w = world(verifiers=(fake_verifier(NOTE.id),))  # no verifier for core.echo
    task, step = await w.running(GUARDED_ECHO.id)
    policy = grant_for(GUARDED_ECHO, created_at=w.now, max_uses=1)
    await w.store.grant(policy)
    before = len(await w.events())
    with pytest.raises(NotFoundError, match="verifier"):
        await w.execute(task.id, step.id)
    assert len(await w.events()) == before
    assert w.tool(GUARDED_ECHO.id).calls == ()
    assert await w.store.uses(policy.id) == 0
    assert E.PERMISSION_DECIDED not in await w.event_types(task.id)


async def test_the_tool_is_looked_up_before_the_verifier() -> None:
    w = world(tools=(), verifiers=())
    task, step = await w.running(ECHO.id)
    with pytest.raises(NotFoundError, match="tool"):
        await w.execute(task.id, step.id)


async def test_an_incoherent_approval_is_refused_before_anything(w: World) -> None:
    """A GRANTED request of this step that names another capability: the store was tampered
    with, or another executor's request landed here. Refused before any write."""
    task, step = await w.running(GUARDED_NOTE.id)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)
    foreign = asked.approval.model_copy(
        update={
            "id": ApprovalId(w.ids.new_uuid()),
            "capability_id": ECHO.id,
            "decision_id": asked.decision.id,
        }
    )
    await w.approvals.add(foreign)
    await w.answered(foreign)
    before = len(await w.events())
    with pytest.raises(ApprovalMismatchError):
        await w.execute(task.id, step.id)
    await nothing_written(w, before)
    assert await w.store.for_capability(GUARDED_NOTE.id) == ()


@pytest.mark.parametrize(
    "ttl", [timedelta(0), timedelta(seconds=-1), MAX_APPROVAL_TTL + timedelta(seconds=1)], ids=str
)
def test_an_approval_ttl_outside_the_cap_is_a_configuration_error(ttl: timedelta) -> None:
    """No TTL without a cap (review of M5.1): zero, negative or above seven days is refused."""
    with pytest.raises(ValueError, match="approval_ttl must be positive and at most"):
        world(approval_ttl=ttl)


def test_the_approval_ttl_cap_is_seven_days_and_inclusive() -> None:
    assert timedelta(days=7) == MAX_APPROVAL_TTL
    assert DEFAULT_APPROVAL_TTL <= MAX_APPROVAL_TTL
    world(approval_ttl=MAX_APPROVAL_TTL)


# --------------------------------------------------------------------------------------
# The four outcomes
# --------------------------------------------------------------------------------------


async def test_allowed_runs_the_tool_records_it_and_completes_the_step(w: World) -> None:
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.authorization is None
    assert execution.approval is None
    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.SUCCEEDED
    assert execution.result.output == {"ok": True}
    assert execution.task.state is TaskState.EXECUTING
    assert execution.step_id == step.id
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert w.tool(ECHO.id).calls[0].decision == execution.decision
    assert w.tool(ECHO.id).calls[0].arguments == ECHO_ARGS
    assert await w.event_types(task.id) == [
        E.TASK_CREATED,
        E.TASK_PLANNING_STARTED,
        E.PLAN_CREATED,
        E.TASK_QUEUED,
        E.TASK_STARTED,
        E.STEP_STARTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    executed = (await w.events(task.id))[-3]
    assert executed.actor.kind is ActorKind.ELA
    assert executed.decision_id == execution.decision.id
    assert executed.authorization_id is None
    assert executed.capability_id == ECHO.id
    assert (executed.task_id, executed.step_id) == (task.id, step.id)
    assert executed.tool_name == w.tool(ECHO.id).name
    assert executed.device_id == w.node.id
    assert executed.created_at == execution.result.created_at
    assert executed.error is None
    assert executed.summary == f"execute: SUCCEEDED core.echo by {w.tool(ECHO.id).name}"
    assert executed.payload == {
        "status": "SUCCEEDED",
        "result_id": str(execution.result.id),
        "targets": (),
        "duration_ms": 0,
        "device": str(w.node.id),
        "uses": None,
    }


async def test_denied_denies_the_task_and_runs_nothing(w: World) -> None:
    outside = {"path": "workspace/other/x.md", "body": "..."}
    task, step = await w.running(NOTE.id, arguments=outside)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.DENIED
    assert execution.result is None and execution.approval is None
    assert execution.task.state is TaskState.DENIED
    assert w.tool(NOTE.id).calls == ()
    assert (await w.event_types(task.id))[-2:] == [E.PERMISSION_DECIDED, E.TASK_DENIED]
    denied = (await w.events(task.id))[-1]
    assert denied.decision_id == execution.decision.id
    assert await w.step_state(task.id, step.id) is StepState.RUNNING  # the task is terminal


async def test_high_risk_is_denied_too(w: World) -> None:
    task, step = await w.running(HIGH.id)
    execution = await w.execute(task.id, step.id)
    assert execution.task.state is TaskState.DENIED
    assert w.tool(HIGH.id).calls == ()


async def test_requires_approval_builds_the_request_and_lets_the_task_wait(w: World) -> None:
    task, step = await w.running(NOTE.id, requires_authorization=True)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.result is None
    approval = execution.approval
    assert approval is not None
    assert approval.status is ApprovalStatus.PENDING
    assert (approval.task_id, approval.step_id) == (task.id, step.id)
    assert approval.capability_id == NOTE.id
    assert approval.targets == ("workspace/notes/briefing.md",)
    assert approval.targets == tuple(execution.decision.metadata["targets"])
    assert approval.decision_id == execution.decision.id
    assert approval.created_at == execution.decision.created_at
    assert approval.expires_at == execution.decision.created_at + DEFAULT_APPROVAL_TTL
    assert approval.responded_by is None and approval.responded_at is None
    assert approval.prompt == (
        f"workspace.write_note on workspace/notes/briefing.md for step {step.id} "
        f"({step.goal}): {execution.decision.reason}"
    )
    assert "SECRET-BODY" not in approval.prompt
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    assert w.tool(NOTE.id).calls == ()
    assert (await w.event_types(task.id))[-2:] == [E.PERMISSION_DECIDED, E.APPROVAL_REQUESTED]
    # stored before the task waited on it, under the id of its decision (ADR 0015 §6)
    assert approval.id == ApprovalId(uuid5(APPROVAL_NAMESPACE, str(execution.decision.id)))
    assert await w.approvals.get(approval.id) == approval
    assert await w.approvals.for_task(task.id) == (approval,)
    assert await w.approvals.pending() == (approval,)


async def test_the_question_carries_the_arguments_the_capability_declares(w: World) -> None:
    """§30, ADR 0029 §6: a "yes" is only worth something if the question was complete.

    ``core.echo_stated`` declares ``purpose``, so the request the user reads says what for. The
    value comes from the step's arguments — the same ones the tool will run on — so the question
    and the action cannot describe two different things.
    """
    task, step = await w.running(STATED_ECHO.id)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert "purpose: showing the reviewer the failing test" in execution.approval.prompt
    assert execution.approval.prompt == (
        f"core.echo_stated for step {step.id} ({step.goal}) — "
        f"purpose: showing the reviewer the failing test: {execution.decision.reason}"
    )


@pytest.mark.parametrize(
    "level", [PrivacyLevel.TRUSTED, PrivacyLevel.CLOUD_ALLOWED], ids=lambda one: one.value
)
async def test_the_question_says_where_a_wider_task_may_go(w: World, level: PrivacyLevel) -> None:
    """Criterion 31 (D20): dec. G2 of M11.2 with the place instead of the time.

    *How long the microphone stays open is half of what is being approved* becomes *where the
    content may go is half of what is being approved*: for a task declared wider than this machine,
    the question of every approval of its steps names the level. The whole question is compared,
    because a clause appended anywhere but there would be a different question.

    It names the **level and not the node**: the level is immutable, the placement is not — a
    released step is placed again — so a question naming the node could be false before the grant it
    asks for is spent.
    """
    task, step = await w.running(STATED_ECHO.id, max_privacy=level)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert execution.approval.prompt == (
        f"core.echo_stated for step {step.id} ({step.goal}) — "
        f"purpose: showing the reviewer the failing test; "
        f"this task may run on a {level.value} node: {execution.decision.reason}"
    )


async def test_the_question_of_a_task_nobody_declared_is_the_question_of_before(w: World) -> None:
    """And at the default the clause is **absent**: ``LOCAL_ONLY`` is what every task was, so its
    question is the one of before byte for byte — a default is not news. A clause that appeared here
    too would make every stored question of every task say something nobody declared."""
    task, step = await w.running(STATED_ECHO.id)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert "may run on" not in execution.approval.prompt
    assert execution.approval.prompt == (
        f"core.echo_stated for step {step.id} ({step.goal}) — "
        f"purpose: showing the reviewer the failing test: {execution.decision.reason}"
    )


async def test_a_capability_that_turns_a_sensor_on_says_so_before_it_runs(w: World) -> None:
    """``SENSOR_ACTIVATED``, and the order is the decision (M11.2 dec. L, ADR 0036 §11).

    Written **before** the tool. An event written afterwards would know the real duration and
    would be missing in exactly the worst case — ELA opens the microphone, something dies, and
    nothing says it was ever opened.

    And it carries the sensor, never the arguments: how long is an argument, and architecture
    rule 23 keeps those out of the audit.
    """
    task, step = await w.running(SENSING_ECHO.id)

    await w.execute(task.id, step.id)

    events = await w.audit.read()
    kinds = [event.event_type for event in events]
    activated = next(e for e in events if e.event_type is AuditEventType.SENSOR_ACTIVATED)
    assert kinds.index(AuditEventType.SENSOR_ACTIVATED) < kinds.index(AuditEventType.TOOL_EXECUTED)
    assert activated.summary == f"activate: MICROPHONE for {SENSING_ECHO.id}"
    assert activated.step_id == step.id
    assert "message" not in activated.summary


async def test_a_capability_that_turns_nothing_on_writes_no_sensor_event(w: World) -> None:
    """The declaration is what makes the event fire, so a capability without one is silent."""
    task, step = await w.running(ECHO.id)

    await w.execute(task.id, step.id)

    events = await w.audit.read()
    assert AuditEventType.SENSOR_ACTIVATED not in [e.event_type for e in events]


async def test_an_argument_the_capability_does_not_declare_stays_out_of_the_question(
    w: World,
) -> None:
    """The default is the defence (§57): ``model.complete`` takes ``input``, the user's content,
    and an ``Approval`` is stored. Nothing is shown unless the capability declared it."""
    task, step = await w.running(GUARDED_NOTE.id)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert "—" not in execution.approval.prompt
    assert "body" not in execution.approval.prompt


async def test_the_approval_ttl_is_the_executors(w: World) -> None:
    short = world(approval_ttl=timedelta(minutes=5))
    task, step = await short.running(GUARDED_ECHO.id)
    execution = await short.execute(task.id, step.id)
    assert execution.approval is not None
    assert execution.approval.expires_at == execution.decision.created_at + timedelta(minutes=5)
    assert execution.approval.targets == ()
    assert execution.approval.prompt.startswith(f"core.echo_guarded for step {step.id} (")


# --------------------------------------------------------------------------------------
# A grant from an approval: minted once, recorded once, consumed once
# --------------------------------------------------------------------------------------


async def approved_and_resumed(w: World, capability_id: CapabilityId, arguments: Any) -> Any:
    """Ask, let the user grant, resume: the task is EXECUTING again with the step RUNNING."""
    task, step = await w.running(capability_id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    w.clock.advance(timedelta(minutes=1))
    # A minute is the whole heartbeat TTL, so the node is stale exactly when the user answers.
    # In a running ELA the walk that resumes goes through the `run` route, which reports the
    # local node alive before it starts (ADR 0023 §5-bis); without that, the placement the
    # executor now checks would name a node nobody would place on today (ADR 0026 §3).
    await w.alive()
    approval = await w.answered(asked.approval)  # respond first, then the engine (ADR 0015 §6)
    await w.engine.approve(task.id, approval)
    await w.engine.start(task.id)
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
    return task, step, approval, asked.decision


async def test_a_granted_approval_becomes_a_grant_that_is_recorded_consumed_and_used(
    w: World,
) -> None:
    task, step, approval, asked = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    before = len(await w.events(task.id))
    execution = await w.execute(task.id, step.id)
    grant = execution.authorization
    assert grant is not None
    assert grant.id == AuthorizationId(uuid5(AUTHORIZATION_NAMESPACE, str(approval.id)))
    assert grant.approval_id == approval.id
    assert grant.scope == approval.targets
    assert grant.max_uses == 1
    assert await w.store.get(grant.id) == grant
    assert await w.store.uses(grant.id) == 1
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.metadata["rule"] == Rule.AUTHORIZATION_REQUIRED.value
    assert execution.decision.authorization_id == grant.id
    assert execution.result is not None
    assert execution.graph.states[step.id] is StepState.COMPLETED
    types = (await w.event_types(task.id))[before:]
    assert types == [
        E.AUTHORIZATION_GRANTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    recorded, _, executed, verified, _ = (await w.events(task.id))[before:]
    assert recorded.actor.kind is ActorKind.USER and recorded.actor.id == "tommaso"
    assert recorded.authorization_id == grant.id
    assert recorded.decision_id == asked.id
    assert (recorded.task_id, recorded.step_id, recorded.capability_id) == (
        task.id,
        step.id,
        NOTE.id,
    )
    assert recorded.created_at == grant.created_at
    assert grant.expires_at is not None
    assert recorded.payload == {
        "origin": "approval",
        "approval_id": str(approval.id),
        "expires_at": grant.expires_at.isoformat(),
        "max_uses": 1,
        "targets": ("workspace/notes/briefing.md",),
        "scope": ("workspace/notes/briefing.md",),
    }
    assert "prompt" not in json.dumps(recorded.model_dump(mode="json"))
    assert executed.authorization_id == grant.id
    assert executed.payload["uses"] == 1
    assert verified.authorization_id == grant.id  # the same grant the run rested on


async def test_the_grant_is_born_at_the_executors_now_and_consumed_at_the_decisions(
    w: World,
) -> None:
    task, step, approval, _ = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    seen: list[Any] = []
    original = w.store.consume

    async def spy(authorization_id: Any, *, now: Any) -> int:
        seen.append(now)
        return await original(authorization_id, now=now)

    w.store.consume = spy  # type: ignore[method-assign]
    execution = await w.execute(task.id, step.id)
    assert execution.authorization is not None
    assert execution.authorization.created_at == w.now
    assert seen == [execution.decision.created_at]


async def test_the_same_approval_never_mints_a_second_grant(w: World) -> None:
    """Retry after a crash between ``grant`` and its audit: the grant is reused, the audit
    completed, no duplicate."""
    task, step, approval, _ = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    minted = authorization_from_approval(
        approval,
        task=await w.task(task.id),
        step=step,
        capability=NOTE,
        now=w.now,
        authorization_id=AuthorizationId(uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))),
    )
    await w.store.grant(minted)  # stored, not recorded: the crash window of ADR 0013 §8
    before = len(await w.events(task.id))
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == minted
    assert len(await w.store.for_capability(NOTE.id)) == 1
    types = (await w.event_types(task.id))[before:]
    assert types.count(E.AUTHORIZATION_GRANTED) == 1
    assert execution.result is not None


async def test_a_grant_already_recorded_is_not_recorded_again(w: World) -> None:
    task, step, approval, _ = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    await w.execute(task.id, step.id)
    # the step is closed; a second call with the same approval on a fresh RUNNING step of
    # another task cannot reuse it (bound), but the grant lookup itself is what we probe:
    grants = await w.store.for_capability(NOTE.id)
    assert len(grants) == 1
    types = await w.event_types(task.id)
    assert types.count(E.AUTHORIZATION_GRANTED) == 1
    # replay the grant path directly: same approval, the store already holds it, audit has it
    before = len(await w.events(task.id))
    replayed = await w.executor._grant(  # noqa: SLF001
        approval, await w.task(task.id), step, NOTE, w.now
    )
    assert replayed == (grants[0], 1)
    assert len(await w.events(task.id)) == before


async def test_a_stored_grant_for_another_approval_under_the_same_id_is_refused(
    w: World,
) -> None:
    task, step, approval, _ = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    foreign = grant_for(
        NOTE,
        task=await w.task(task.id),
        step=step,
        created_at=w.now,
        id=AuthorizationId(uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))),
        approval_id=ApprovalId(w.ids.new_uuid()),
        max_uses=1,
    )
    await w.store.grant(foreign)
    before = len(await w.events(task.id))
    with pytest.raises(ExecutorError, match="exists for another approval"):
        await w.execute(task.id, step.id)
    assert len(await w.events(task.id)) == before
    assert w.tool(NOTE.id).calls == ()


async def test_an_exhausted_grant_found_in_the_store_asks_again_and_names_it(w: World) -> None:
    """Window 6 of ADR 0013 §8: the grant of the GRANTED request was spent before the tool ran.
    The retry finds the request, reuses its grant, and the Guardian asks again — a second
    request for the step, born from a second decision (ADR 0015 §6)."""
    task, step, approval, _ = await approved_and_resumed(w, NOTE.id, NOTE_ARGS)
    minted = authorization_from_approval(
        approval,
        task=await w.task(task.id),
        step=step,
        capability=NOTE,
        now=w.now,
        authorization_id=AuthorizationId(uuid5(AUTHORIZATION_NAMESPACE, str(approval.id))),
    )
    await w.store.grant(minted)
    await w.store.consume(minted.id, now=w.now)
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == minted
    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.decision.authorization_id == minted.id
    assert execution.approval is not None
    assert "used 1 of 1 times" in execution.approval.prompt
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert w.tool(NOTE.id).calls == ()
    first, second = await w.approvals.for_task(task.id)
    assert (first.status, second.status) == (ApprovalStatus.GRANTED, ApprovalStatus.PENDING)
    assert first.id != second.id and first.decision_id != second.decision_id
    assert len(await w.store.for_capability(NOTE.id)) == 1  # no second grant from the first yes


async def test_a_usable_grant_found_in_the_store_is_consumed_and_used(w: World) -> None:
    task, step = await w.running(GUARDED_ECHO.id)
    policy = grant_for(GUARDED_ECHO, created_at=w.now, max_uses=3)
    await w.store.grant(policy)
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == policy
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert await w.store.uses(policy.id) == 1
    assert execution.result is not None
    executed = next(e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED)
    assert executed.authorization_id == policy.id
    assert executed.payload["uses"] == 1


async def test_a_grant_the_decision_does_not_rest_on_is_not_consumed(w: World) -> None:
    task, step = await w.running(ECHO.id)
    policy = grant_for(ECHO, created_at=w.now, max_uses=1)
    await w.store.grant(policy)
    execution = await w.execute(task.id, step.id)
    assert execution.authorization == policy
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.metadata["rule"] == Rule.ALLOW.value
    assert await w.store.uses(policy.id) == 0
    executed = next(e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED)
    assert executed.authorization_id is None
    assert executed.payload["uses"] is None


async def test_a_grant_expiring_at_the_decisions_instant_is_not_consumed(w: World) -> None:
    task, step = await w.running(GUARDED_ECHO.id)
    at_now = grant_for(GUARDED_ECHO, created_at=w.now, expires_at=w.now)
    await w.store.grant(at_now)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert await w.store.uses(at_now.id) == 0
    assert w.tool(GUARDED_ECHO.id).calls == ()


# --------------------------------------------------------------------------------------
# consume that fails after ALLOWED: ask again, or fail the step
# --------------------------------------------------------------------------------------


class _RacingStore(FakeAuthorizationStore):
    """A store where someone else spends the grant between ``authorize`` and ``consume``."""

    async def consume(self, authorization_id: Any, *, now: Any) -> int:
        raise AuthorizationExhaustedError(authorization_id, 1, 1)


class _ForgetfulStore(FakeAuthorizationStore):
    async def consume(self, authorization_id: Any, *, now: Any) -> int:
        raise NotFoundError("authorization", authorization_id)


async def test_a_grant_spent_by_someone_else_asks_again() -> None:
    w = world(store=_RacingStore())
    task, step = await w.running(GUARDED_ECHO.id)
    policy = grant_for(GUARDED_ECHO, created_at=w.now, max_uses=1)
    await w.store.grant(policy)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.approval is not None
    assert execution.approval.decision_id == execution.decision.id
    assert "was used 1 of 1 times" in execution.approval.prompt
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert execution.result is None
    assert w.tool(GUARDED_ECHO.id).calls == ()
    assert (await w.event_types(task.id))[-2:] == [E.PERMISSION_DECIDED, E.APPROVAL_REQUESTED]


async def test_a_grant_that_vanished_fails_the_step_and_runs_nothing() -> None:
    w = world(store=_ForgetfulStore())
    task, step = await w.running(GUARDED_ECHO.id)
    policy = grant_for(GUARDED_ECHO, created_at=w.now)
    await w.store.grant(policy)
    execution = await w.execute(task.id, step.id)
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.result is None and execution.approval is None
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING
    assert w.tool(GUARDED_ECHO.id).calls == ()
    assert (await w.event_types(task.id))[-2:] == [E.PERMISSION_DECIDED, E.STEP_FAILED]
    failed = (await w.events(task.id))[-1]
    assert failed.error is not None
    assert failed.error.code == GRANT_VANISHED
    assert str(policy.id) in failed.error.message


# --------------------------------------------------------------------------------------
# The tool: what it returns, what it raises
# --------------------------------------------------------------------------------------


class _RaisingTool(FakeTool):
    async def execute(self, decision: PermissionDecision, arguments: Any) -> Any:
        raise RuntimeError("the disk caught fire")


def _world_with(tool: FakeTool) -> World:
    w = world(tools=(tool,))
    w.fake_tools = {tool.capability_id: tool}
    return w


async def test_a_tool_that_raises_is_a_failed_result_recorded_then_the_step_fails() -> None:
    w = _world_with(_RaisingTool(ECHO.id, FakeClock(), FakeIdGenerator(), name="fire"))
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.result.error is not None
    assert execution.result.error.code == TOOL_EXCEPTION
    assert execution.result.error.message == "RuntimeError"
    assert execution.result.tool_name == "fire"
    assert (execution.result.task_id, execution.result.step_id) == (task.id, step.id)
    assert execution.graph.states[step.id] is StepState.FAILED
    assert (await w.event_types(task.id))[-2:] == [E.TOOL_EXECUTED, E.STEP_FAILED]
    executed, failed = (await w.events(task.id))[-2:]
    assert executed.error == execution.result.error == failed.error
    assert executed.payload["status"] == "FAILED"
    assert "caught fire" not in json.dumps(executed.model_dump(mode="json"))


async def test_a_failed_result_fails_the_step_with_the_tools_error() -> None:
    error = ErrorMetadata(code="notes.locked", message="the workspace is locked")
    tool = FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=ExecutionStatus.FAILED)
    w = _world_with(tool)
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.result is not None and execution.result.error is None
    failed = (await w.events(task.id))[-1]
    assert failed.event_type is E.STEP_FAILED
    assert failed.error is not None
    assert failed.error.code == "tool.failed"
    assert failed.error.tool_name == tool.name
    assert error.code != failed.error.code  # the synthesised one, since the tool gave none


@pytest.mark.parametrize(
    "status", [ExecutionStatus.TIMED_OUT, ExecutionStatus.CANCELLED, ExecutionStatus.SKIPPED]
)
async def test_any_status_but_succeeded_fails_the_step(status: ExecutionStatus) -> None:
    w = _world_with(FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=status))
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.graph.states[step.id] is StepState.FAILED
    failed = (await w.events(task.id))[-1]
    assert failed.error is not None
    assert failed.error.code == f"tool.{status.value.lower()}"


async def test_a_tool_that_refuses_the_decision_fails_the_step_without_a_run() -> None:
    ahead = FakeClock(FakeClock().now() + timedelta(days=1))
    w = _world_with(FakeTool(ECHO.id, ahead, FakeIdGenerator(), name="late"))
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.result is None
    assert execution.graph.states[step.id] is StepState.FAILED
    types = await w.event_types(task.id)
    assert E.TOOL_EXECUTED not in types
    assert types[-2:] == [E.PERMISSION_DECIDED, E.STEP_FAILED]
    failed = (await w.events(task.id))[-1]
    assert failed.error is not None
    assert failed.error.code == TOOL_REFUSED
    assert str(execution.decision.id) in failed.error.message
    assert w.tool(ECHO.id).calls == ()


async def test_the_executor_calls_the_tool_only_with_an_allowed_decision(w: World) -> None:
    for capability in (ECHO, NOTE, HIGH):
        task, step = await w.running(capability.id)
        await w.execute(task.id, step.id)
    for tool in w.fake_tools.values():
        for call in tool.calls:
            assert call.decision.outcome is PermissionOutcome.ALLOWED
            assert call.decision.capability_id == tool.capability_id
    assert w.tool(HIGH.id).calls == ()
    assert len(w.tool(ECHO.id).calls) == len(w.tool(NOTE.id).calls) == 1


async def test_neither_arguments_nor_output_ever_enter_the_audit(w: World) -> None:
    secret_tool = FakeTool(NOTE.id, w.clock, w.ids, name="notes", output={"echo": "SECRET-OUTPUT"})
    w = _world_with(secret_tool)
    task, step = await w.running(NOTE.id)
    execution = await w.execute(task.id, step.id)
    assert execution.result is not None
    assert execution.result.output == {"echo": "SECRET-OUTPUT"}
    serialized = json.dumps([event.model_dump(mode="json") for event in await w.events()])
    assert "SECRET-BODY" not in serialized
    assert "SECRET-OUTPUT" not in serialized
    assert "workspace/notes/briefing.md" in serialized  # the targets, yes (ADR 0011 §8)


async def test_a_tool_refusal_and_a_raise_are_told_apart_from_a_denial(w: World) -> None:
    """Sanity on the names: five different codes for five different facts."""
    assert (
        len(
            {
                TOOL_EXCEPTION,
                TOOL_REFUSED,
                GRANT_VANISHED,
                VERIFICATION_FAILED,
                VERIFICATION_EXCEPTION,
            }
        )
        == 5
    )
    assert NotAllowedError is not RuntimeError


# --------------------------------------------------------------------------------------
# Verification: the tool's word is not enough (ADR 0014 §4–§8)
# --------------------------------------------------------------------------------------


async def test_a_passed_verification_completes_the_step_and_is_recorded(w: World) -> None:
    task, step = await w.running(ECHO.id, conditions=(OK,))
    execution = await w.execute(task.id, step.id)
    assert execution.verification is not None
    assert execution.verification.passed
    assert execution.verification.conditions == (OK,)
    assert execution.verification.failures == ()
    assert execution.verification.error is None
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert execution.task.state is TaskState.EXECUTING
    verifier = w.verifier(ECHO.id)
    assert len(verifier.calls) == 1
    assert verifier.calls[0].conditions == (OK,)
    assert verifier.calls[0].arguments == ECHO_ARGS
    assert verifier.calls[0].result == execution.result
    executed, verified, completed = (await w.events(task.id))[-3:]
    assert verified.event_type is E.EXECUTION_VERIFIED
    assert completed.event_type is E.STEP_COMPLETED
    assert verified.actor.kind is ActorKind.ELA
    assert verified.decision_id == executed.decision_id == execution.decision.id
    assert verified.authorization_id == executed.authorization_id is None
    assert (verified.task_id, verified.step_id, verified.capability_id) == (
        task.id,
        step.id,
        ECHO.id,
    )
    assert verified.tool_name == w.tool(ECHO.id).name
    assert verified.device_id == w.node.id
    assert verified.error is None
    assert verified.summary == f"verify: passed core.echo by {verifier.name}"
    assert execution.result is not None
    assert verified.payload == {
        "passed": True,
        "result_id": str(execution.result.id),
        "verifier": verifier.name,
        "conditions": (OK,),
        "failed": (),
        "device": str(w.node.id),
    }


async def test_a_failed_verification_fails_the_step_and_the_task_with_the_metadata(
    w: World,
) -> None:
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    execution = await w.execute(task.id, step.id)
    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.SUCCEEDED  # the tool's word
    assert len(w.tool(ECHO.id).calls) == 1
    verification = execution.verification
    assert verification is not None
    assert not verification.passed
    assert verification.conditions == (BAD,)
    assert [f.code for f in verification.failures] == [BAD_FAILURE.code]
    assert verification.failures[0].details["condition"] == BAD
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.FAILED
    assert (await w.task(task.id)).state is TaskState.FAILED
    assert (await w.event_types(task.id))[-4:] == [
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_FAILED,
        E.TASK_FAILED,
    ]
    executed, verified, step_failed, task_failed = (await w.events(task.id))[-4:]
    assert executed.payload["status"] == "SUCCEEDED"
    error = verification.error
    assert error is not None
    assert verified.error == step_failed.error == task_failed.error == error
    assert verified.payload["passed"] is False
    assert verified.payload["failed"] == (BAD,)
    assert verified.payload["conditions"] == (BAD,)
    # §64, field by field
    assert error.code == VERIFICATION_FAILED
    assert error.message == (
        f"1 of 1 success conditions failed for core.echo: {BAD} ({BAD_FAILURE.code})"
    )
    assert error.cause == BAD_FAILURE.message
    assert error.tool_name == w.tool(ECHO.id).name
    assert error.model is None
    assert error.device_id == w.node.id
    assert error.details["device"] == str(w.node.id)
    assert error.attempted_fix is None
    assert error.successful_fix is None
    assert error.retryable is BAD_FAILURE.retryable
    assert error.details["conditions"] == (BAD,)
    assert error.details["result_id"] == str(execution.result.id)
    assert error.details["verifier"] == w.verifier(ECHO.id).name
    (failure,) = error.details["failures"]
    assert failure == {
        "condition": BAD,
        "code": BAD_FAILURE.code,
        "message": BAD_FAILURE.message,
        "retryable": True,
        "details": {"expected_bytes": 3, "actual_bytes": 0},
    }


async def test_every_failed_condition_is_named_and_a_passed_one_is_not(w: World) -> None:
    task, step = await w.running(ECHO.id, conditions=(OK, BAD))
    execution = await w.execute(task.id, step.id)
    assert execution.verification is not None
    error = execution.verification.error
    assert error is not None
    assert error.message.startswith("1 of 2 success conditions failed for core.echo: ")
    assert error.details["conditions"] == (OK, BAD)
    assert [f["condition"] for f in error.details["failures"]] == [BAD]
    verified = next(e for e in await w.events(task.id) if e.event_type is E.EXECUTION_VERIFIED)
    assert verified.payload["failed"] == (BAD,)


async def test_two_failed_conditions_make_one_error_with_two_failures() -> None:
    worse = ErrorMetadata(code="fake.worse", message="and so does the sky", retryable=False)
    verifier = FakeVerifier(
        ECHO.id, conditions=(BAD, "fake.worse"), failures={BAD: BAD_FAILURE, "fake.worse": worse}
    )
    w = world(verifiers=(verifier,))
    task, step = await w.running(ECHO.id, conditions=(BAD, "fake.worse"))
    execution = await w.execute(task.id, step.id)
    assert execution.verification is not None
    error = execution.verification.error
    assert error is not None
    assert error.message.startswith("2 of 2 success conditions failed")
    assert error.cause == f"{BAD_FAILURE.message}; {worse.message}"
    assert error.retryable is False  # retryable only if every failure is
    assert [f["condition"] for f in error.details["failures"]] == [BAD, "fake.worse"]
    assert execution.task.state is TaskState.FAILED


async def test_a_failed_verification_cancels_the_dependent_steps(w: World) -> None:
    task, first, second = await w.running_pair(ECHO.id, conditions=(BAD,))
    execution = await w.execute(task.id, first.id)
    assert execution.graph.states[first.id] is StepState.FAILED
    assert execution.graph.states[second.id] is StepState.CANCELLED
    assert execution.graph.is_blocked
    assert execution.task.state is TaskState.FAILED


class _CrashingVerifier(FakeVerifier):
    async def verify(self, conditions: Any, arguments: Any, result: Any) -> Any:
        self.calls = (*self.calls, (tuple(conditions), arguments, result))  # type: ignore[assignment]
        raise RuntimeError("SECRET-REASON: the disk went away")


async def test_a_verifier_that_raises_fails_the_step_and_the_task_without_the_message() -> None:
    verifier = _CrashingVerifier(ECHO.id, name="crashing")
    w = world(verifiers=(verifier,))
    task, step = await w.running(ECHO.id, conditions=(OK,))
    execution = await w.execute(task.id, step.id)
    assert len(verifier.calls) == 1
    assert execution.verification is not None
    assert not execution.verification.passed
    (failure,) = execution.verification.failures
    assert failure.code == VERIFICATION_EXCEPTION
    assert failure.message == "RuntimeError"
    assert failure.details["condition"] is None
    error = execution.verification.error
    assert error is not None
    assert error.code == VERIFICATION_FAILED
    assert error.cause == "RuntimeError"
    assert error.message == (
        "1 of 1 success conditions failed for core.echo: "
        f"{VERIFICATION_EXCEPTION} ({VERIFICATION_EXCEPTION})"
    )
    assert error.retryable is False
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.FAILED
    types = await w.event_types(task.id)
    assert types[-4:] == [E.TOOL_EXECUTED, E.EXECUTION_VERIFIED, E.STEP_FAILED, E.TASK_FAILED]
    verified = (await w.events(task.id))[-3]
    assert verified.payload["failed"] == (VERIFICATION_EXCEPTION,)
    assert "SECRET-REASON" not in json.dumps([e.model_dump(mode="json") for e in await w.events()])


@pytest.mark.parametrize(
    "status",
    [
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMED_OUT,
        ExecutionStatus.CANCELLED,
        ExecutionStatus.SKIPPED,
    ],
)
async def test_a_result_that_did_not_succeed_is_not_verified(status: ExecutionStatus) -> None:
    """The tool reported its own failure: the step fails, the task stays EXECUTING, and the
    verifier is not consulted (ADR 0014 §4, decision C)."""
    w = _world_with(FakeTool(ECHO.id, FakeClock(), FakeIdGenerator(), status=status))
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    execution = await w.execute(task.id, step.id)
    assert execution.verification is None
    assert w.verifier(ECHO.id).calls == ()
    types = await w.event_types(task.id)
    assert E.EXECUTION_VERIFIED not in types
    assert types[-2:] == [E.TOOL_EXECUTED, E.STEP_FAILED]
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING


async def test_a_tool_that_raises_is_not_verified_either() -> None:
    w = _world_with(_RaisingTool(ECHO.id, FakeClock(), FakeIdGenerator(), name="fire"))
    task, step = await w.running(ECHO.id)
    execution = await w.execute(task.id, step.id)
    assert execution.verification is None
    assert w.verifier(ECHO.id).calls == ()
    assert execution.task.state is TaskState.EXECUTING


async def test_the_verifier_is_consulted_only_after_a_run_and_with_the_runs_result(
    w: World,
) -> None:
    for capability in (ECHO, NOTE, HIGH):
        task, step = await w.running(capability.id)
        await w.execute(task.id, step.id)
    for capability_id, verifier in w.fake_verifiers.items():
        tool = w.tool(capability_id)
        assert len(verifier.calls) == len(tool.calls)
        for call in verifier.calls:
            assert call.result.status is ExecutionStatus.SUCCEEDED
            assert call.result.capability_id == capability_id
    assert w.verifier(HIGH.id).calls == ()


async def test_neither_arguments_output_nor_compared_content_enter_the_verification_audit(
    w: World,
) -> None:
    leaky = ErrorMetadata(
        code="fake.mismatch", message="the file differs", details={"expected_bytes": 11}
    )
    verifier = FakeVerifier(
        NOTE.id, name="notes-verifier", conditions=(BAD,), failures={BAD: leaky}
    )
    secret_tool = FakeTool(NOTE.id, w.clock, w.ids, name="notes", output={"echo": "SECRET-OUTPUT"})
    w = world(tools=(secret_tool,), verifiers=(verifier,))
    w.fake_tools = {NOTE.id: secret_tool}
    task, step = await w.running(NOTE.id, conditions=(BAD,))
    execution = await w.execute(task.id, step.id)
    assert execution.task.state is TaskState.FAILED
    serialized = json.dumps([event.model_dump(mode="json") for event in await w.events()])
    assert "SECRET-BODY" not in serialized
    assert "SECRET-OUTPUT" not in serialized
    assert "expected_bytes" in serialized  # sizes, yes (decision F)
