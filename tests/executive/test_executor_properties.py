"""The invariants of the executor over every combination the fixtures can produce (ADR 0013,
ADR 0014).

The space is finite — a capability of each kind, a step that may require authorization, a grant
in each of the states :class:`Grant` lists, a tool that succeeds, fails or raises, a verifier that
passes, fails or raises — and hypothesis walks it: the tool runs if and only if the Guardian said
``ALLOWED`` and the grant, when spent, was spent; every run is recorded; a step never stays RUNNING
once the tool ran; a grant is consumed only when the decision rests on it — read from the Guardian,
not from ``CONSUMING_RULES`` (M13.1b); the verifier is consulted if and only if the tool ran and
said SUCCEEDED; the step is COMPLETED if and only if the verification passed; the task is FAILED
if and only if the verification did not pass; and the executor never raises past its
preconditions.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from enum import Enum
from typing import Any

from hypothesis import example, given, settings
from hypothesis import strategies as st

from ela.domain import (
    AuditEventType,
    ExecutionStatus,
    PermissionOutcome,
    StepState,
    TaskState,
)
from ela.permissions import Rule
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool, FakeVerifier
from tests.domain.examples import APPROVAL_ID
from tests.executive.support import BAD, OK, World, fake_verifier, grant_for, world
from tests.permissions.support import ECHO, ECHO_ARGS, GUARDED_NOTE, HIGH, NOTE, NOTE_ARGS

E = AuditEventType


class VerifierBehaviour(Enum):
    PASS = "pass"
    FAIL = "fail"
    RAISE = "raise"


class _RaisingVerifier(FakeVerifier):
    async def verify(self, conditions: Any, arguments: Any, result: Any) -> Any:
        self.calls = (*self.calls, (tuple(conditions), arguments, result))  # type: ignore[assignment]
        raise RuntimeError("boom")


class Grant(Enum):
    NONE = "none"
    USABLE = "usable"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    ELSEWHERE = "elsewhere"
    YES_USABLE = "yes-usable"
    YES_EXPIRED = "yes-expired"
    YES_EXHAUSTED = "yes-exhausted"
    """The last three are **born of a yes** (M13.1b): bound to the task and the step, single use,
    an ``approval_id``. The others are standing, and a standing grant never covers a row that asks
    at every use (M13.1 dec. D) — so until they were here no ``HIGH`` ever reached ``ALLOWED`` in
    this space, and the property could not see that an approved ``HIGH`` did not spend its yes."""


BORN_OF_A_YES = frozenset({Grant.YES_USABLE, Grant.YES_EXPIRED, Grant.YES_EXHAUSTED})


class ToolBehaviour(Enum):
    SUCCEED = "succeed"
    FAIL = "fail"
    RAISE = "raise"


class _RaisingTool(FakeTool):
    async def execute(self, decision: Any, arguments: Any) -> Any:
        raise RuntimeError("boom")


CAPABILITIES = {
    ECHO.id: (ECHO, ECHO_ARGS),
    NOTE.id: (NOTE, NOTE_ARGS),
    GUARDED_NOTE.id: (GUARDED_NOTE, NOTE_ARGS),
    HIGH.id: (HIGH, ECHO_ARGS),
}


async def run(
    capability_key: str,
    requires_authorization: bool,
    grant: Grant,
    behaviour: ToolBehaviour,
    verdict: VerifierBehaviour,
) -> None:
    spec, arguments = CAPABILITIES[capability_key]
    clock, ids = FakeClock(), FakeIdGenerator()
    if behaviour is ToolBehaviour.RAISE:
        tool: FakeTool = _RaisingTool(spec.id, clock, ids)
    else:
        status = (
            ExecutionStatus.SUCCEEDED
            if behaviour is ToolBehaviour.SUCCEED
            else ExecutionStatus.FAILED
        )
        tool = FakeTool(spec.id, clock, ids, status=status)
    verifier: FakeVerifier = (
        _RaisingVerifier(spec.id, conditions=(OK, BAD))
        if verdict is VerifierBehaviour.RAISE
        else fake_verifier(spec.id)
    )
    conditions = (OK,) if verdict is VerifierBehaviour.PASS else (OK, BAD)
    w: World = world(tools=(tool,), verifiers=(verifier,))
    w.fake_tools = {spec.id: tool}
    w.fake_verifiers = {spec.id: verifier}
    task, step = await w.running(
        spec.id, requires_authorization=requires_authorization, conditions=conditions
    )
    if grant is not Grant.NONE:
        changes: dict[str, Any] = {}
        if grant in (Grant.EXPIRED, Grant.YES_EXPIRED):
            changes["expires_at"] = w.now
        if grant is Grant.EXHAUSTED:
            changes["max_uses"] = 1
        if grant is Grant.ELSEWHERE:
            changes["scope"] = ("workspace/elsewhere",)
        if grant in BORN_OF_A_YES:
            changes |= {"approval_id": APPROVAL_ID, "max_uses": 1}
        bound = {"task": task, "step": step} if grant in BORN_OF_A_YES else {}
        stored = grant_for(spec, created_at=w.now - timedelta(minutes=1), **bound, **changes)
        await w.store.grant(stored)
        if grant in (Grant.EXHAUSTED, Grant.YES_EXHAUSTED):
            await w.store.consume(stored.id, now=w.now)
    # The oracle of the consumption (M13.1b dec. 1): the same call, decided with no grant at all.
    # ``decide`` writes nothing; if it would ask, then an ALLOWED with a grant rests on that grant.
    asked_without_a_grant = (
        w.guardian.decide(spec, arguments, task=task, step=step).outcome
        is PermissionOutcome.REQUIRES_APPROVAL
    )
    uses_before = {g.id: await w.store.uses(g.id) for g in await w.store.for_capability(spec.id)}

    execution = await w.execute(task.id, step.id)

    decision = execution.decision
    ran = tool.calls != () or (behaviour is ToolBehaviour.RAISE and execution.result is not None)
    types = await w.event_types(task.id)
    rule = Rule(str(decision.metadata["rule"]))
    uses_after = {g.id: await w.store.uses(g.id) for g in await w.store.for_capability(spec.id)}
    consumed = any(uses_after[gid] > uses_before[gid] for gid in uses_before)
    # the tool runs iff ALLOWED (the fake store never races: consume succeeds after ALLOWED)
    assert ran == (decision.outcome is PermissionOutcome.ALLOWED)
    assert (E.TOOL_EXECUTED in types) == ran
    assert (execution.result is not None) == ran
    # the verifier is consulted iff the tool ran and said SUCCEEDED (ADR 0014 §4)
    verified = ran and behaviour is ToolBehaviour.SUCCEED
    assert (verifier.calls != ()) == verified
    assert (E.EXECUTION_VERIFIED in types) == verified
    assert (execution.verification is not None) == verified
    passed = verified and verdict is VerifierBehaviour.PASS
    if ran:
        state = await w.step_state(task.id, step.id)
        assert state in (StepState.COMPLETED, StepState.FAILED)
        # the step is COMPLETED iff the verification passed: the tool's word is never enough
        assert (state is StepState.COMPLETED) == passed
        assert (E.STEP_COMPLETED in types) == passed
    # the task is FAILED iff a verification did not pass (decision C: a tool that reports its
    # own failure leaves the task EXECUTING)
    assert (execution.task.state is TaskState.FAILED) == (verified and not passed)
    assert (E.TASK_FAILED in types) == (verified and not passed)
    if verified and not passed:
        assert execution.verification is not None
        assert execution.verification.error is not None
        assert types[-4:] == [
            E.TOOL_EXECUTED,
            E.EXECUTION_VERIFIED,
            E.STEP_FAILED,
            E.TASK_FAILED,
        ]
    # a grant is consumed iff the decision rests on it: ALLOWED with a grant, and a question
    # without one — read from the Guardian, never from CONSUMING_RULES, which is what it checks
    assert consumed == (
        decision.outcome is PermissionOutcome.ALLOWED
        and execution.authorization is not None
        and asked_without_a_grant
    ), (
        f"{spec.id} under {rule.value}: consumed={consumed}, "
        f"asked without a grant={asked_without_a_grant}"
    )
    # and the grant is named where the action is recorded iff it was spent. True by construction
    # — the executor writes the id only after the consume — so this holds the shape, it repairs
    # nothing, and it cannot fail on the tree M13.1b found either
    if ran and execution.result is not None:
        spent = execution.authorization.id if consumed and execution.authorization else None
        assert execution.result.authorization_id == spent
        executed = [e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED]
        assert [e.authorization_id for e in executed] == [spent]
    # a grant that does not cover is never handed over
    if execution.authorization is not None:
        assert rule is not Rule.AUTHORIZATION_MISMATCH
    # every outcome is a move of the engine
    if decision.outcome is PermissionOutcome.DENIED:
        assert execution.task.state.value == "DENIED"
    if decision.outcome is PermissionOutcome.REQUIRES_APPROVAL:
        assert execution.task.state.value == "WAITING_APPROVAL"
        assert execution.approval is not None
        assert execution.approval.targets == tuple(
            t for t in decision.metadata["targets"] if isinstance(t, str)
        )
    if decision.outcome is PermissionOutcome.ALLOWED:
        assert execution.approval is None


@settings(max_examples=200, deadline=None)
@example(HIGH.id, False, Grant.YES_USABLE, ToolBehaviour.SUCCEED, VerifierBehaviour.PASS)
@example(HIGH.id, False, Grant.YES_EXPIRED, ToolBehaviour.SUCCEED, VerifierBehaviour.PASS)
@example(HIGH.id, False, Grant.YES_EXHAUSTED, ToolBehaviour.SUCCEED, VerifierBehaviour.PASS)
@given(
    capability_key=st.sampled_from(sorted(CAPABILITIES)),
    requires_authorization=st.booleans(),
    grant=st.sampled_from(list(Grant)),
    behaviour=st.sampled_from(list(ToolBehaviour)),
    verdict=st.sampled_from(list(VerifierBehaviour)),
)
def test_the_tool_runs_iff_allowed_and_every_run_is_recorded_and_verified(
    capability_key: str,
    requires_authorization: bool,
    grant: Grant,
    behaviour: ToolBehaviour,
    verdict: VerifierBehaviour,
) -> None:
    asyncio.run(run(capability_key, requires_authorization, grant, behaviour, verdict))
