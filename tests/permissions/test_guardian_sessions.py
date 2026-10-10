"""A guided session covers the ``MEDIUM`` reads its own model writes (M13.9, decision 29).

Inside a session every gesture is a child task decided on the level of the catalogue, and a read
with the profile is ``MEDIUM``: it would ask at every look. What covers it is **the session**, when
the room attests that it is open — read at the moment of the decision, never from a copy — and the
capability of the session declares, in the catalogue, that the reads it makes are that capability.

No grant is born, and no grant is consumed: the decision names **a rule of its own**, and says
which session covered. What the Guardian is handed is a fact, and it checks every part of it
again — the catalogue is the first line and never the only one (ADR 0011):

* the plan was written by **that** session, and the task is its child;
* the capability of the session **declares** this one as what it covers;
* **the row asks unless authorized**: a session never covers a capability that asks at every use
  — the second of the two defences, for the day a declaration is written wrong;
* the target is one of the session's sites.

Anything else is the caller's incoherence, and is denied — as a grant that does not cover is.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    PermissionOutcome,
    PlanAuthor,
    PlanAuthorKind,
    RiskLevel,
    Task,
)
from ela.permissions import Rule
from ela.testing.fakes import FakeCapabilityRegistry
from tests.domain.examples import STEP_ID, TASK
from tests.permissions.policy_support import GUIDED, MODEL, policy_for
from tests.permissions.session_support import (
    ACT,
    ARGS,
    AUTHOR,
    CHILD,
    LOW_READ,
    READ,
    SESSION_STEP,
    SITES,
    cover,
    session_capability,
    step,
)
from tests.permissions.support import ECHO, Harness, born_of_a_yes, harness


def world(*specs: CapabilitySpec) -> Harness:
    return harness(registry=FakeCapabilityRegistry(specs))


@pytest.fixture
def h() -> Harness:
    return world(session_capability(READ), READ, ACT, LOW_READ, GUIDED, ECHO)


def decided(h: Harness, capability: CapabilitySpec = READ, **given: Any) -> Any:
    given.setdefault("task", CHILD)
    given.setdefault("step", step(capability))
    given.setdefault("author", AUTHOR)
    given.setdefault("session", cover())
    return h.guardian.decide(capability, ARGS, **given)


# ----------------------------------------------------------------------------------------
# It covers
# ----------------------------------------------------------------------------------------


def test_an_open_session_covers_the_read_its_model_wrote_and_the_decision_says_which(
    h: Harness,
) -> None:
    decision = decided(h)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.metadata["rule"] == Rule.SESSION.value == "SESSION"
    assert decision.reason == f"test.read_as_you is covered by the session of step {SESSION_STEP}"
    assert decision.metadata["session"] == str(SESSION_STEP)
    assert decision.authorization_id is None, "no grant is born, and none is used"
    assert decision.expires_at is not None and decision.expires_at > h.now


def test_the_rule_has_a_name_of_its_own_and_the_policy_changed_its_version() -> None:
    """The decision names its rule with a name that is not a grant's, and a Guardian that learnt a
    way to allow is not the Guardian of the version before."""
    from ela.permissions import POLICY_VERSION, RISK_POLICY

    assert Rule.SESSION not in set(RISK_POLICY.values()), "no row of the table is this rule"
    assert Rule.SESSION is not Rule.APPROVAL_UNLESS_AUTHORIZED
    assert POLICY_VERSION == "v0.3"


def test_without_the_room_s_word_the_same_read_asks(h: Harness) -> None:
    """A session that is over attests nothing: its child asks, as a ``MEDIUM`` always did. That
    the plan says «written by a session» is not what covers."""
    decision = decided(h, session=None)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_AUTHORIZED.value
    assert "session" not in decision.metadata


def test_a_decision_no_session_covered_says_nothing_of_a_session(h: Harness) -> None:
    decision = h.guardian.decide(ECHO, {"message": "hello"})

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert set(decision.metadata) == {"policy", "rule", "targets"}


# ----------------------------------------------------------------------------------------
# It does not cover: the fact the Guardian was handed is checked again, part by part
# ----------------------------------------------------------------------------------------


def denied(decision: Any) -> str:
    assert decision.outcome is PermissionOutcome.DENIED, decision.reason
    assert decision.metadata["rule"] == Rule.SESSION_MISMATCH.value == "SESSION_MISMATCH"
    assert "session" not in decision.metadata, "a session that did not cover is not named as one"
    return str(decision.reason)


@pytest.mark.parametrize(
    "author",
    [
        None,
        PlanAuthor(by=PlanAuthorKind.HAND),
        PlanAuthor(by=PlanAuthorKind.PLANNER),
        PlanAuthor(by=PlanAuthorKind.SESSION, session=STEP_ID, model=MODEL),
    ],
    ids=["nobody", "a hand", "the planner", "another session"],
)
def test_a_plan_that_session_did_not_write_is_not_covered_by_it(
    h: Harness, author: PlanAuthor | None
) -> None:
    said = denied(decided(h, author=author))

    assert "was not written by the session of step" in said


@pytest.mark.parametrize(
    "task",
    [None, TASK, TASK.model_copy(update={"parent_id": TASK.id})],
    ids=["no task", "nobody's child", "another task's child"],
)
def test_a_task_that_is_not_the_child_of_that_session_is_not_covered(
    h: Harness, task: Task | None
) -> None:
    said = denied(decided(h, task=task))

    assert "is not a child of the session's task" in said


def test_a_session_whose_capability_declares_nothing_covers_nothing(h: Harness) -> None:
    """``browser.guided`` declares no ``covers``: its reads are ``LOW`` and need none."""
    said = denied(decided(h, session=cover(capability_id=GUIDED.id)))

    assert "browser.guided declares no capability its sessions cover" in said


def test_a_session_covers_only_the_capability_it_declares() -> None:
    h = world(session_capability(LOW_READ), READ, LOW_READ)

    said = denied(decided(h))

    assert "test.session covers browser.read, not test.read_as_you" in said


def test_a_session_of_a_capability_the_catalogue_does_not_know_covers_nothing(h: Harness) -> None:
    said = denied(decided(h, session=cover(capability_id=CapabilityId("test.unknown"))))

    assert "test.unknown is not in the catalogue" in said


def test_a_declaration_made_for_another_schema_does_not_cover() -> None:
    """The declaration carries a copy of the schema it covers: one written for yesterday's
    arguments of the read is not a declaration for today's."""
    from ela.domain import Covered

    stale = Covered(capability_id=READ.id, input_schema={"type": "object", "properties": {}})
    h = world(session_capability(READ, covers=stale), READ)

    said = denied(decided(h))

    assert "declares it for another schema" in said


def test_a_target_outside_the_sites_of_the_session_is_not_covered(h: Harness) -> None:
    """The step's own narrowing would deny it first; this is the Guardian's own look at the sites
    the room attests, for a step that carries none."""
    said = denied(decided(h, step=step(within=None), session=cover(sites=("video.example",))))

    assert "is not among the sites of the session" in said


def test_a_grant_and_a_session_together_are_two_facts_too_many(h: Harness) -> None:
    grant = born_of_a_yes(READ, scope=SITES)

    said = denied(decided(h, authorization=grant))

    assert "an authorization and a session" in said


# ----------------------------------------------------------------------------------------
# The second defence: no session covers a row that asks at every use
# ----------------------------------------------------------------------------------------


def test_the_guardian_denies_a_session_presented_for_a_high_whatever_the_catalogue_says() -> None:
    """The catalogue refuses a ``covers`` towards a row that is not «approval unless authorized»
    (``tests/permissions/test_covers.py``). This is the day that refusal is got round — here by a
    registry that checks nothing —: the Guardian denies on its own."""
    h = world(session_capability(ACT), ACT)
    arguments: dict[str, Any] = {
        "site": "posta.example",
        "path": "/send",
        "fill": [["#to", "x"]],
        "click": "#send",
        "expect_text": "sent",
        "purpose": "mandare",
    }

    decision = h.guardian.decide(
        ACT,
        arguments,
        task=CHILD,
        step=step(ACT, arguments=arguments),
        author=AUTHOR,
        session=cover(),
    )

    said = denied(decision)
    assert "browser.act is HIGH: a session covers only a row that asks unless authorized" in said


def test_nor_one_presented_for_a_row_that_does_not_ask() -> None:
    h = world(session_capability(LOW_READ), LOW_READ)

    said = denied(decided(h, LOW_READ))

    assert "browser.read is LOW: a session covers only a row that asks unless authorized" in said


def test_a_session_whose_own_capability_does_not_ask_covers_nothing() -> None:
    """What makes the cover worth something is that the session itself was asked for: a yes, or a
    policy. A session's capability on a row that asks nobody would open the reads to no yes."""
    h = world(session_capability(READ, risk=RiskLevel.LOW, requires_authorization=False), READ)

    said = denied(decided(h))

    assert "test.session is LOW: only a session that was asked for covers" in said


def test_a_policy_of_the_session_is_not_a_grant_for_its_reads(h: Harness) -> None:
    """A policy of ``browser.guided`` never covered a gesture, and a policy of a session with the
    profile does not either: presented for the read, it is a grant for another capability."""
    policy = policy_for(GUIDED, scope=SITES)

    decision = decided(h, session=None, authorization=policy)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value


# ----------------------------------------------------------------------------------------
# The audit says which session covered
# ----------------------------------------------------------------------------------------


async def test_the_audit_names_the_session_that_covered(h: Harness) -> None:
    decision = await h.guardian.authorize(
        READ, ARGS, task=CHILD, step=step(), author=AUTHOR, session=cover()
    )

    (event,) = await h.audit.read()
    assert event.payload["rule"] == "SESSION"
    assert event.payload["session"] == str(SESSION_STEP)
    assert event.payload["policy"] == "v0.3"
    assert event.decision_id == decision.id and event.authorization_id is None


async def test_the_audit_of_any_other_decision_has_no_session(h: Harness) -> None:
    await h.guardian.authorize(READ, ARGS, task=CHILD, step=step(), author=AUTHOR)

    (event,) = await h.audit.read()
    assert "session" not in event.payload
