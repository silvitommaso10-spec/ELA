"""The executor and a policy of a ``HIGH`` (M13.14, ADR 0068; decisions 9, 10, 24 of the review).

A ``HIGH`` that declares terms runs without a question under a policy of its own, and spends one
use — **but only on what would succeed now**: no question was composed, so the tool's prospect, the
one ADR 0045 §6-bis reads before a question, is read before the use is spent, and a refusal fails
the step with the tool's code, no use spent and no tool called. A yes is not touched by this, nor
is a ``MEDIUM`` under its policy. A policy whose uses are spent asks, and the line «why I ask» says
so; a policy of the Core is never handed over for a step on a node, which asks.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from ela.domain import (
    ApprovalId,
    AuditEventType,
    CapabilityId,
    ErrorMetadata,
    PermissionOutcome,
    PolicyTerms,
    PolicyWords,
    PrivacyLevel,
    RiskLevel,
    StepState,
)
from ela.executive import ASKED
from ela.permissions import Rule, short_id
from ela.ports import Prospect
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeTool
from tests.executive.support import World, fake_verifier, grant_for, world
from tests.permissions.policy_support import TERMED, TERMED_ARGS, policy_for
from tests.permissions.support import CATALOGUE

HIGH_TERMED = TERMED.model_copy(
    update={
        "id": CapabilityId("test.high_termed"),
        "risk": RiskLevel.HIGH,
        "policy_terms": PolicyTerms(
            limits=("budget", "count"),
            uncovered=("route",),
            free=("text",),
            model="test-model",
            on_the_core=True,
        ),
        "policy_words": PolicyWords(does="does something of the tests", goes="nowhere"),
    }
)
"""A ``HIGH`` that declares terms, covered only on the Core — the shape of ``fs.write``."""

REFUSED = ErrorMetadata(
    code="path.symlink",
    message="'ELA/prova/uno/fuori/x.md' passes through a link",
    tool_name="fake-test.high_termed",
)


def high_world(*specs: Any) -> World:
    clock, ids = FakeClock(), FakeIdGenerator()
    capabilities = specs or (HIGH_TERMED,)
    tools = [
        FakeTool(spec.id, clock, ids, name=f"fake-{spec.id}", output={"ok": True})
        for spec in capabilities
    ]
    verifiers = [fake_verifier(spec.id) for spec in capabilities]
    added = tuple(spec for spec in capabilities if spec not in CATALOGUE)
    w = world(tools=tools, verifiers=verifiers, catalogue=(*CATALOGUE, *added))
    w.fake_tools = {tool.capability_id: tool for tool in tools}
    w.fake_verifiers = {verifier.capability_id: verifier for verifier in verifiers}
    return w


async def a_policy(w: World, spec: Any = HIGH_TERMED, **changes: Any) -> Any:
    policy = policy_for(spec, created_at=w.now - timedelta(hours=1), **changes)
    await w.store.grant(policy)
    return policy


async def test_a_high_its_policy_covers_runs_without_a_question_and_spends_a_use() -> None:
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value
    assert execution.decision.reason == f"test.high_termed is covered by policy {policy.id}"
    assert execution.approval is None
    assert await w.store.uses(policy.id) == 1
    assert w.tool(HIGH_TERMED.id).calls != ()


async def test_a_refused_prospect_under_a_policy_fails_the_step_and_spends_nothing() -> None:
    """Answer 24 of the review: the step fails with the tool's code — no use spent, no tool
    called, nothing written; it is not a question."""
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w)
    w.tool(HIGH_TERMED.id).prospects = Prospect(refusal=REFUSED)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.approval is None
    assert await w.store.uses(policy.id) == 0
    assert w.tool(HIGH_TERMED.id).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    failed = [e for e in await w.events(task.id) if e.event_type is AuditEventType.STEP_FAILED]
    assert failed[-1].error is not None and failed[-1].error.code == "path.symlink"


async def test_a_yes_to_the_same_high_is_not_read_again_before_its_spend() -> None:
    """Only a policy: a yes was given to a question composed on the prospect already — its grant
    is spent and the tool runs, and the tool's own run refuses whatever moved since."""
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    yes = grant_for(
        HIGH_TERMED,
        task=task,
        step=step,
        tail=701,
        created_at=w.now,
        max_uses=1,
        approval_id=ApprovalId(w.ids.new_uuid()),
        bounds=None,
    )
    await w.store.grant(yes)
    w.tool(HIGH_TERMED.id).prospects = Prospect(refusal=REFUSED)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert await w.store.uses(yes.id) == 1
    assert w.tool(HIGH_TERMED.id).calls != ()


async def test_a_medium_under_its_policy_is_not_read_again_before_its_spend() -> None:
    """Only for a ``HIGH`` (answer 24): a session under its policy stays as M13.12 made it."""
    w = high_world(TERMED)
    task, step = await w.running(TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w, TERMED)
    w.tool(TERMED.id).prospects = Prospect(refusal=REFUSED)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert await w.store.uses(policy.id) == 1
    assert w.tool(TERMED.id).calls != ()


async def test_a_spent_policy_asks_and_the_question_says_its_uses() -> None:
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w, max_uses=1)
    await w.store.consume(policy.id, now=w.now)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.decision.metadata["rule"] == Rule.APPROVAL_UNLESS_POLICY.value
    assert execution.approval is not None
    assert list(execution.approval.metadata[ASKED]["why"]) == [
        f"policy {short_id(policy.id)} was used 1 of its 1 times"
    ]
    assert await w.store.uses(policy.id) == 1
    assert w.tool(HIGH_TERMED.id).calls == ()


async def test_a_step_on_a_node_asks_and_the_question_says_the_policy_is_of_the_core() -> None:
    """Decision 10: the policy is never handed over for a step on a node — the step asks, as
    ADR 0048 §8 asks, and the line says why."""
    w = high_world()
    elsewhere = await w.remote()
    task, step = await w.running(
        HIGH_TERMED.id, arguments=TERMED_ARGS, max_privacy=PrivacyLevel.TRUSTED
    )
    policy = await a_policy(w)

    placement = await w.placement(
        task.id, step.id, device_id=elsewhere.id, max_privacy=PrivacyLevel.TRUSTED
    )

    execution = await w.execute(task.id, step.id, placement=placement)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.authorization is None
    assert execution.approval is not None
    assert list(execution.approval.metadata[ASKED]["why"]) == [
        f"policy {short_id(policy.id)} covers only a step that runs on the Core, and this step "
        "is not one"
    ]
    assert await w.store.uses(policy.id) == 0
