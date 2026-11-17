"""The executor and a policy of the login or of a file from the browser (M13.15, ADR 0071).

- **The five run without a question under a policy of their own** — the scope, the value named by
  value, on the Core —, and spend one use.
- **A policy is spent only on what would succeed now** (decision 13, answer 39): the executor asks
  the tool the prospect of a covered call **before** the use is spent, and a refusal fails the step
  with the tool's code — no use, no tool. Each row of the table of proposal 9, on both roads: under
  a policy the covered prospect refuses and spends nothing; without one the question's prospect
  refuses the same code and no question is composed.
- **A call without ``entry``, or with one the policy does not name, asks** (decision 4 (iii)), and
  the line «why I ask» names the argument, never a value.
- **A consent is not inherited** (decision 9): a policy of one of the five covers no other
  capability, and none of them is covered by a policy of a gesture or of a session.
- **The decision says which approval a grant rests on** (answer 38): a yes always carries it, a
  policy never.
- **The one sentence of the question names the policy that ended last** (decision 19, answer 53).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    Actor,
    ActorKind,
    ApprovalId,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    CapabilityId,
    ErrorMetadata,
    PermissionOutcome,
    StepState,
)
from ela.executive import ASKED
from ela.executive.executor import ended_at
from ela.permissions import short_id
from ela.ports import Prospect
from tests.executive.support import World, grant_for
from tests.executive.test_policy_high import high_world
from tests.permissions.catalogue_calls import CALLS, CATALOGUE
from tests.permissions.policy_support import BY_VALUE, policy_for

LOGIN = CapabilityId("browser.login")
FIVE: tuple[CapabilityId, ...] = (
    LOGIN,
    CapabilityId("browser.download"),
    CapabilityId("browser.download_as_you"),
    CapabilityId("browser.upload"),
    CapabilityId("browser.upload_as_you"),
)
EVERY = pytest.mark.parametrize("capability", FIVE)

REFUSALS: dict[CapabilityId, tuple[str, ...]] = {
    LOGIN: (
        "arguments.invalid",
        "browser.not_installed",
        "browser.unsupported_system",
        "browser.profile_undeclared",
        "browser.profile_unsafe",
        "browser.profile_busy",
        "browser.no_window",
        "vault.undeclared",
        "vault.no_program",
        "vault.program_gone",
        "vault.program_changed",
        "vault.program_is_a_script",
        "vault.locked",
        "vault.unauthenticated",
        "vault.timeout",
        "vault.failed",
        "vault.no_entry",
        "vault.entry_not_for_site",
        "vault.no_password",
    ),
    CapabilityId("browser.download"): (
        "arguments.invalid",
        "browser.site_not_declared",
        "browser.not_installed",
        "browser.unsupported_system",
        "fs.no_root",
        "path.invalid",
        "path.outside_root",
        "path.symlink",
        "path.is_directory",
        "path.ela_s_own",
        "path.hard_link",
        "fs.overwrite_mismatch",
    ),
    CapabilityId("browser.upload"): (
        "arguments.invalid",
        "browser.site_not_declared",
        "browser.not_installed",
        "browser.unsupported_system",
        "fs.no_root",
        "path.invalid",
        "path.outside_root",
        "path.symlink",
        "path.is_directory",
        "path.missing",
        "path.ela_s_own",
        "path.hard_link",
        "browser.file_too_large",
    ),
}
"""The table of proposal 9 of the SPEC of M13.15, by capability: what is refused before a spend.
The two «as you» add the profile's three to their twin's."""
PROFILE = ("browser.profile_undeclared", "browser.profile_unsafe", "browser.profile_busy")
REFUSALS[CapabilityId("browser.download_as_you")] = (
    *REFUSALS[CapabilityId("browser.download")],
    *PROFILE,
)
REFUSALS[CapabilityId("browser.upload_as_you")] = (
    *REFUSALS[CapabilityId("browser.upload")],
    *PROFILE,
)
ROWS = [(capability, code) for capability in FIVE for code in REFUSALS[capability]]


def five_world() -> World:
    return high_world(*(CATALOGUE.get(capability) for capability in FIVE))


async def a_policy(w: World, capability: CapabilityId, **changes: Any) -> Any:
    policy = policy_for(CATALOGUE.get(capability), created_at=w.now - timedelta(hours=1), **changes)
    await w.store.grant(policy)
    return policy


def refused(code: str, capability: CapabilityId) -> Prospect:
    return Prospect(
        refusal=ErrorMetadata(code=code, message=f"refused: {code}", tool_name=f"fake-{capability}")
    )


@EVERY
async def test_one_of_the_five_its_policy_covers_runs_without_a_question_and_spends_a_use(
    capability: CapabilityId,
) -> None:
    w = five_world()
    task, step = await w.running(capability, arguments=CALLS[capability])
    policy = await a_policy(w, capability)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED, execution.decision.reason
    assert execution.decision.reason == f"{capability} is covered by policy {policy.id}"
    assert execution.decision.approval_id is None
    assert execution.approval is None
    assert await w.store.uses(policy.id) == 1
    assert w.tool(capability).calls != ()
    assert w.tool(capability).covered_asks, "the prospect of a covered call was not asked"


@pytest.mark.parametrize(("capability", "code"), ROWS)
async def test_a_refusal_before_the_spend_fails_the_step_on_both_roads_and_spends_nothing(
    capability: CapabilityId, code: str
) -> None:
    """Answer 39: the same code for the same refusal — under a policy from the covered prospect,
    before the use; under no policy from the question's, before a question."""
    covered = five_world()
    task, step = await covered.running(capability, arguments=CALLS[capability])
    policy = await a_policy(covered, capability)
    covered.tool(capability).covered = refused(code, capability)

    under_a_policy = await covered.execute(task.id, step.id)

    asked = five_world()
    other, its_step = await asked.running(capability, arguments=CALLS[capability])
    asked.tool(capability).prospects = refused(code, capability)

    under_a_question = await asked.execute(other.id, its_step.id)

    assert under_a_policy.decision.outcome is PermissionOutcome.ALLOWED
    assert under_a_policy.approval is None
    assert await covered.store.uses(policy.id) == 0, "a use was spent on what would not succeed"
    assert covered.tool(capability).calls == (), "the tool ran"
    assert await covered.step_state(task.id, step.id) is StepState.FAILED
    for world_, failed_task in ((covered, task), (asked, other)):
        failed = [
            one
            for one in await world_.events(failed_task.id)
            if one.event_type is AuditEventType.STEP_FAILED
        ]
        assert failed[-1].error is not None and failed[-1].error.code == code
    assert under_a_question.approval is None, "a question was composed for what cannot succeed"
    assert asked.tool(capability).calls == ()


@pytest.mark.parametrize(
    "arguments",
    [
        {k: v for k, v in CALLS[LOGIN].items() if k != "entry"},
        {**CALLS[LOGIN], "entry": "an-entry-the-policy-does-not-name"},
    ],
    ids=["without entry", "another entry"],
)
async def test_a_login_without_its_entry_asks_and_the_line_names_no_value(
    arguments: dict[str, Any],
) -> None:
    w = five_world()
    task, step = await w.running(LOGIN, arguments=arguments)
    policy = await a_policy(w, LOGIN)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None
    why = list(execution.approval.metadata[ASKED]["why"])
    assert why == [f"a value of entry is not among those of policy {short_id(policy.id)}"]
    for value in (*BY_VALUE["entry"], str(arguments.get("entry"))):
        assert value not in execution.approval.prompt and value not in " ".join(why)
    assert await w.store.uses(policy.id) == 0


async def test_with_the_vault_locked_a_covered_login_writes_nothing_and_spends_no_use() -> None:
    """Decision 4 (iv): a yes would not open the vault — the refusal is born before any question,
    and under a policy before the spend."""
    w = five_world()
    task, step = await w.running(LOGIN, arguments=CALLS[LOGIN])
    policy = await a_policy(w, LOGIN)
    w.tool(LOGIN).covered = refused("vault.locked", LOGIN)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.reason == f"{LOGIN} is covered by policy {policy.id}"
    assert await w.store.uses(policy.id) == 0
    assert w.tool(LOGIN).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.FAILED


INHERITED = [
    ("browser.download", "browser.download_as_you"),
    ("browser.download_as_you", "browser.download"),
    ("browser.upload", "browser.upload_as_you"),
    ("browser.upload_as_you", "browser.upload"),
    ("browser.act", "browser.upload"),
    ("browser.act_as_you", "browser.login"),
    ("browser.guided", "browser.download"),
    ("browser.guided_as_you", "browser.upload_as_you"),
    ("browser.upload", "browser.act"),
    ("browser.login", "browser.act_as_you"),
    ("browser.download", "browser.guided"),
    ("browser.upload_as_you", "browser.guided_as_you"),
]
"""Decision 9: a consent is not inherited (ADR 0034) — between the five, and with the gestures and
the sessions, both ways."""


@pytest.mark.parametrize(("policy_of", "called"), INHERITED)
async def test_a_policy_of_one_capability_covers_no_other(policy_of: str, called: str) -> None:
    specs = {one: CATALOGUE.get(CapabilityId(one)) for one in (policy_of, called)}
    w = high_world(*specs.values())
    task, step = await w.running(CapabilityId(called), arguments=CALLS[called])
    policy = await a_policy(w, CapabilityId(policy_of))

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert execution.approval is not None
    assert f"no policy of yours for {called}" in list(execution.approval.metadata[ASKED]["why"])
    assert await w.store.uses(policy.id) == 0
    assert w.tool(CapabilityId(called)).calls == ()


@EVERY
async def test_a_decision_on_a_yes_carries_its_approval_and_one_on_a_policy_none(
    capability: CapabilityId,
) -> None:
    """Answer 38: the Guardian copies the grant's ``approval_id`` into the decision — the road the
    executor mints from a yes —, and a policy, minted by the route, has none to copy."""
    w = five_world()
    task, step = await w.running(capability, arguments=CALLS[capability])
    approval = ApprovalId(UUID("00000000-0000-4000-8000-0000000a9971"))
    yes = grant_for(
        CATALOGUE.get(capability),
        task=task,
        step=step,
        tail=702,
        created_at=w.now,
        max_uses=1,
        approval_id=approval,
        bounds=None,
    )
    await w.store.grant(yes)

    on_a_yes = await w.execute(task.id, step.id)

    covered = five_world()
    other, its_step = await covered.running(capability, arguments=CALLS[capability])
    await a_policy(covered, capability)
    on_a_policy = await covered.execute(other.id, its_step.id)

    assert on_a_yes.decision.outcome is PermissionOutcome.ALLOWED
    assert on_a_yes.decision.approval_id == approval
    assert on_a_policy.decision.approval_id is None
    assert on_a_policy.decision.authorization_id is not None


async def test_a_question_answered_yes_mints_a_grant_whose_decision_names_its_approval() -> None:
    """The executor's own road (rule 66): asked, answered, and run — the decision of the run
    carries the approval the user answered."""
    w = five_world()
    task, step = await w.running(LOGIN, arguments=CALLS[LOGIN])
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    ran = await w.execute(task.id, step.id)

    assert ran.decision.outcome is PermissionOutcome.ALLOWED
    assert ran.decision.approval_id == asked.approval.id


# ----------------------------------------------------------------------------------------
# The one sentence of the question: the policy that ended last (decision 19, answer 53)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("revoked_first", [True, False], ids=["revoked first", "spent first"])
async def test_the_one_sentence_names_the_policy_that_ended_last(revoked_first: bool) -> None:
    w = five_world()
    capability = CapabilityId("browser.upload")
    task, step = await w.running(capability, arguments=CALLS[capability])
    early, late = w.now - timedelta(minutes=30), w.now - timedelta(minutes=5)
    revoked = await a_policy(w, capability, tail=901)
    spent = await a_policy(w, capability, tail=902, max_uses=1)
    await w.store.revoke(revoked.id, at=early if revoked_first else late)
    await w.store.consume(spent.id, now=w.now - timedelta(minutes=40))
    await w.audit.append(
        AuditEvent(
            id=AuditEventId(UUID("00000000-0000-4000-8000-0000000e0e01")),
            created_at=late if revoked_first else early,
            event_type=AuditEventType.TOOL_EXECUTED,
            actor=Actor(kind=ActorKind.SYSTEM, id="executor"),
            summary="the last use of the spent policy",
            capability_id=capability,
            authorization_id=spent.id,
            payload={"status": "SUCCEEDED"},
        )
    )

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    last = spent if revoked_first else revoked
    said = (
        f"policy {short_id(spent.id)} was used 1 of its 1 use"
        if revoked_first
        else f"policy {short_id(revoked.id)} was revoked on"
    )
    assert said in execution.approval.prompt, execution.approval.prompt
    assert execution.authorization is not None and execution.authorization.id == last.id
    assert len(list(execution.approval.metadata[ASKED]["why"])) == 2, "the lines say them all"


def test_when_a_policy_ended_is_derived_from_its_data() -> None:
    """The first of its revocation, its past expiry, the instant of its last use if its uses are
    spent — or, with no instant of a use, its birth: the nearest the data give."""
    spec = CATALOGUE.get(CapabilityId("browser.upload"))
    now = policy_for(spec).created_at + timedelta(hours=2)
    born = policy_for(spec, max_uses=1)
    used = born.created_at + timedelta(minutes=10)
    revoked = born.model_copy(update={"revoked_at": born.created_at + timedelta(minutes=20)})

    assert ended_at(born, 0, now=now, last_used={}) == now
    assert ended_at(born, 1, now=now, last_used={born.id: used}) == used
    assert ended_at(born, 1, now=now, last_used={}) == born.created_at
    assert ended_at(revoked, 1, now=now, last_used={born.id: used}) == used
    assert ended_at(revoked, 0, now=now, last_used={}) == revoked.revoked_at
    expired = born.model_copy(update={"expires_at": born.created_at + timedelta(minutes=5)})
    assert ended_at(expired, 0, now=now, last_used={}) == expired.expires_at
