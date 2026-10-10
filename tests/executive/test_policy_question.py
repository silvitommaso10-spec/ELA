"""The executor and the policies of §59 (M13.12, ADR 0062; decisions 4, 5, 8, 11, 20).

A step a policy covers runs without a question and spends one use; a step it does not cover asks,
and the question says why, with the predicate's first reason; a policy revoked between the
Guardian's yes and the spend asks again; and a store of the authorizations that does not answer
stops the run with its error, before the Guardian and before any tool.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import AuditEventType, PermissionOutcome, TaskState
from ela.executive import ASKED
from ela.permissions import short_id
from ela.ports import AuthorizationRevokedError
from ela.testing.fakes import FakeAuthorizationStore, FakeClock, FakeIdGenerator, FakeTool
from tests.executive.support import World, fake_verifier, world
from tests.permissions.policy_support import TERMED, TERMED_ARGS, policy_for, revoked
from tests.permissions.support import CATALOGUE, GUARDED_ECHO


def termed_world(*, store: Any = None) -> World:
    clock, ids = FakeClock(), FakeIdGenerator()
    tool = FakeTool(TERMED.id, clock, ids, name="fake-test.termed", output={"ok": True})
    verifier = fake_verifier(TERMED.id)
    w = world(
        tools=(tool,),
        verifiers=(verifier,),
        catalogue=CATALOGUE,
        store=store,
    )
    w.fake_tools = {TERMED.id: tool}
    w.fake_verifiers = {TERMED.id: verifier}
    return w


async def running(w: World, **arguments: Any) -> Any:
    return await w.running(TERMED.id, arguments={**TERMED_ARGS, **arguments})


async def test_a_step_a_policy_covers_runs_without_a_question_and_spends_a_use() -> None:
    w = termed_world()
    task, step = await running(w)
    policy = policy_for(TERMED, created_at=w.now - timedelta(hours=1))
    await w.store.grant(policy)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.reason == f"test.termed is covered by policy {policy.id}"
    assert execution.approval is None
    assert await w.store.uses(policy.id) == 1
    assert execution.result is not None and execution.result.authorization_id == policy.id
    assert w.tool(TERMED.id).calls != ()


async def test_a_step_no_policy_covers_asks_and_the_question_says_why() -> None:
    w = termed_world()
    task, step = await running(w, budget="5")
    policy = policy_for(
        TERMED, limits={"budget": "1.10", "count": "30"}, created_at=w.now - timedelta(hours=1)
    )
    await w.store.grant(policy)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None
    asked = execution.approval.metadata[ASKED]
    assert list(asked["why"]) == [f"budget 5 is above the 1.10 of policy {short_id(policy.id)}"]
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert await w.store.uses(policy.id) == 0
    assert w.tool(TERMED.id).calls == ()


async def test_with_no_policy_the_question_says_so() -> None:
    w = termed_world()
    task, step = await running(w)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert list(execution.approval.metadata[ASKED]["why"]) == ["no policy of yours for test.termed"]


async def test_a_capability_without_terms_has_no_line_why() -> None:
    w = world()
    task, step = await w.running(GUARDED_ECHO.id)

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    assert "why" not in execution.approval.metadata[ASKED]


async def test_a_revoked_policy_asks_and_the_question_says_revoked() -> None:
    w = termed_world()
    task, step = await running(w)
    policy = revoked(
        policy_for(TERMED, created_at=w.now - timedelta(hours=2)), w.now - timedelta(hours=1)
    )
    await w.store.grant(policy)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None
    assert list(execution.approval.metadata[ASKED]["why"]) == [
        f"policy {short_id(policy.id)} was revoked on "
        f"{(w.now - timedelta(hours=1)).date().isoformat()}"
    ]


class _RevokedBetween(FakeAuthorizationStore):
    """A store where the policy is revoked between the Guardian's yes and the spend (ADR 0046
    §3)."""

    async def consume(self, authorization_id: Any, *, now: Any) -> int:
        grant = await self.get(authorization_id)
        raise AuthorizationRevokedError(
            authorization_id, now if grant.revoked_at is None else grant.revoked_at
        )


async def test_a_policy_revoked_between_the_decision_and_the_spend_asks_and_runs_nothing() -> None:
    w = termed_world(store=_RevokedBetween())
    task, step = await running(w)
    policy = policy_for(TERMED, created_at=w.now - timedelta(hours=1))
    await w.store.grant(policy)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.approval is not None
    assert "revoked" in execution.approval.prompt
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert w.tool(TERMED.id).calls == ()


class _RevokedAfterTheRead(FakeAuthorizationStore):
    """The executor reads the policy **before** it is revoked: the copy it holds in memory, and
    hands the Guardian, has ``revoked_at=None``; the revocation is written in the store right after
    that read — between the decision and the spend. Nothing here fakes ``consume``: the store's own
    rereads the row (decision 27 of the review of the summary)."""

    def __init__(self, at: Any) -> None:
        super().__init__()
        self.at = at
        self.handed: list[Any] = []

    async def for_capability(self, capability_id: Any) -> Any:
        found = await super().for_capability(capability_id)
        self.handed.extend(found)
        for one in found:
            if one.approval_id is None and one.revoked_at is None:
                await self.revoke(one.id, at=self.at)
        return found


async def test_a_copy_in_memory_from_before_the_revocation_is_not_spent_and_the_step_asks() -> None:
    """Rule 66 says who may revoke; it does not stop a copy read before the revocation from
    reaching the Guardian, which says yes to it. What stops the spend is ``consume``, which rereads
    the row in its conditional ``UPDATE`` (``revoked_at IS NULL``, ADR 0062 §2): the step asks,
    and the tool is never called."""
    store = _RevokedAfterTheRead(at=FakeClock().now())
    w = termed_world(store=store)
    task, step = await running(w)
    policy = policy_for(TERMED, created_at=w.now - timedelta(hours=1))
    await w.store.grant(policy)

    execution = await w.execute(task.id, step.id)

    copy = next(one for one in store.handed if one.id == policy.id)
    assert copy.revoked_at is None, "the copy handed over is from before the revocation"
    assert (await w.store.get(policy.id)).revoked_at is not None
    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.decision.authorization_id == policy.id
    assert execution.approval is not None
    assert "revoked" in execution.approval.prompt
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert await w.store.uses(policy.id) == 0
    assert w.tool(TERMED.id).calls == ()


class _Unanswering(FakeAuthorizationStore):
    """A store of the authorizations that does not answer (decision 20)."""

    async def for_capability(self, capability_id: Any) -> Any:
        raise OSError("the store of the authorizations does not answer")


async def test_a_store_that_does_not_answer_stops_the_run_before_the_guardian_and_any_tool() -> (
    None
):
    """Decision 20: the rule is «never an execution»."""
    w = termed_world(store=_Unanswering())
    task, step = await running(w)

    with pytest.raises(OSError, match="does not answer"):
        await w.execute(task.id, step.id)

    assert w.tool(TERMED.id).calls == ()
    types = await w.event_types(task.id)
    assert AuditEventType.PERMISSION_DECIDED not in types
    assert AuditEventType.TOOL_EXECUTED not in types
