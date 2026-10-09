"""Which grant the executor hands the Guardian when policies of §59 are among the candidates
(M13.12, ADR 0062; decision 4). Pure, and held by a property in three parts.

The oracle of the property is **not** ``shortfall``: it would be the note that adapts to the value
it should defend (ADR 0045 §13, ADR 0046 §2). It is a reading of its own, written here, of what the
strategy built — the sites a subset of the policy's, every value at most its limit, no
``task_type``, alive and not revoked, the terms of today.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    Authorization,
    AuthorizationId,
    PermissionOutcome,
    PolicyTerms,
    RiskLevel,
    TaskStep,
)
from ela.executive import select_authorization
from ela.permissions import PermissionGuardian, Rule, targets_of
from ela.testing.fakes import FakeAuditLog, FakeCapabilityRegistry, FakeClock, FakeIdGenerator
from tests.domain.examples import APPROVAL_ID, NOW, TASK, TASK_STEP
from tests.permissions.policy_support import (
    GUIDED,
    GUIDED_ARGS,
    GUIDED_LIMITS,
    MODEL,
    SITES,
    policy_for,
    revoked,
)

STEP: TaskStep = TASK_STEP.model_copy(
    update={"required_capabilities": (GUIDED.id,), "arguments": GUIDED_ARGS}
)
OLD_TERMS = PolicyTerms(
    limits=("max_cost_usd", "looks"),
    uncovered=("task_type",),
    free=("goal",),
    route="browsing",
    model=MODEL,
)


def select(*candidates: tuple[Authorization, int], arguments: dict[str, Any] = GUIDED_ARGS) -> Any:
    return select_authorization(
        candidates,
        task=TASK,
        step=STEP,
        capability=GUIDED,
        arguments=arguments,
        targets=targets_of(GUIDED, arguments),
        now=NOW,
    )


def yes(**changes: Any) -> Authorization:
    return Authorization(
        id=AuthorizationId(APPROVAL_ID),
        created_at=NOW,
        capability_id=GUIDED.id,
        scope=GUIDED.scope,
        granted_by="tommaso",
        approval_id=APPROVAL_ID,
        task_id=TASK.id,
        step_id=STEP.id,
        expires_at=NOW + timedelta(hours=1),
        max_uses=1,
    ).model_copy(update=changes)


def test_a_policy_that_covers_is_handed_over() -> None:
    policy = policy_for(GUIDED, scope=("www.youtube.com",), limits=GUIDED_LIMITS)
    assert select((policy, 0)) == (policy, 0)


def test_a_policy_that_does_not_cover_is_never_handed_over() -> None:
    narrow = policy_for(GUIDED, scope=("httpbin.org",))
    tight = policy_for(GUIDED, limits={**GUIDED_LIMITS, "looks": "1"})
    for policy in (narrow, tight):
        assert select((policy, 0)) is None
    assert (
        select((policy_for(GUIDED), 0), arguments={**GUIDED_ARGS, "task_type": "browsing"}) is None
    )


def test_a_revoked_or_expired_policy_that_covers_is_handed_over_so_the_question_says_why() -> None:
    gone = revoked(policy_for(GUIDED), NOW)
    over = policy_for(GUIDED, expires_at=NOW)
    assert select((gone, 0)) == (gone, 0)
    assert select((over, 0)) == (over, 0)


def test_a_usable_policy_beats_a_revoked_one() -> None:
    gone = revoked(policy_for(GUIDED, tail=901), NOW)
    alive = policy_for(GUIDED, tail=902)
    assert select((gone, 0), (alive, 0)) == (alive, 0)


def test_the_step_s_own_yes_comes_first() -> None:
    assert select((policy_for(GUIDED), 0), (yes(), 0)) == (yes(), 0)


def test_a_policy_for_a_row_that_asks_at_every_use_is_never_handed_over() -> None:
    high = GUIDED.model_copy(update={"risk": RiskLevel.HIGH})
    found = select_authorization(
        ((policy_for(GUIDED), 0),),
        task=TASK,
        step=STEP,
        capability=high,
        arguments=GUIDED_ARGS,
        targets=targets_of(GUIDED, GUIDED_ARGS),
        now=NOW,
    )
    assert found is None


# ----------------------------------------------------------------------------------------
# The property, in three parts (decision 4)
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Built:
    """A candidate and what the strategy knows about it, read without the predicate."""

    grant: Authorization
    uses: int
    covers: bool
    usable: bool


def _number(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except ArithmeticError:
        return None
    return number if number.is_finite() else None


def _covers_by_hand(grant: Authorization, arguments: dict[str, Any]) -> bool:
    if grant.approval_id is not None:
        return grant.step_id == STEP.id and grant.task_id == TASK.id
    bounds = grant.bounds
    if bounds is None or bounds.terms != GUIDED.policy_terms:
        return False
    if not set(arguments["sites"]) <= set(grant.scope):
        return False
    if "task_type" in arguments:
        return False
    for name in ("max_cost_usd", "looks", "seconds"):
        limit, value = _number(bounds.limits[name]), _number(arguments[name])
        if limit is None or value is None or value > limit:
            return False
    return True


def _usable_by_hand(grant: Authorization, uses: int) -> bool:
    if grant.revoked_at is not None:
        return False
    if grant.expires_at is not None and grant.expires_at <= NOW:
        return False
    return grant.max_uses is None or uses < grant.max_uses


sites_ = st.lists(st.sampled_from(SITES), min_size=1, max_size=3, unique=True)


@st.composite
def candidates(draw: st.DrawFn, arguments: dict[str, Any]) -> Built:
    if draw(st.booleans()):
        grant = yes(expires_at=NOW + timedelta(seconds=draw(st.sampled_from([-1, 0, 60]))))
        uses = draw(st.sampled_from([0, 1]))
    else:
        tail = draw(st.integers(min_value=900, max_value=999))
        limits = {
            "max_cost_usd": draw(st.sampled_from(["0.5", "1.10", "2", "uno"])),
            "looks": draw(st.sampled_from(["5", "10", "30"])),
            "seconds": draw(st.sampled_from(["60", "300", "1800"])),
        }
        old = draw(st.booleans()) and draw(st.booleans())
        grant = policy_for(
            GUIDED,
            scope=tuple(draw(sites_)),
            limits={k: v for k, v in limits.items() if not old or k != "seconds"},
            terms=OLD_TERMS if old else None,
            expires_at=NOW + timedelta(seconds=draw(st.sampled_from([-1, 0, 60]))),
            tail=tail,
        )
        if draw(st.booleans()) and draw(st.booleans()):
            grant = revoked(grant, NOW)
        uses = draw(st.integers(min_value=0, max_value=5))
    return Built(grant, uses, _covers_by_hand(grant, arguments), _usable_by_hand(grant, uses))


@st.composite
def worlds(draw: st.DrawFn) -> tuple[dict[str, Any], list[Built]]:
    arguments: dict[str, Any] = {
        "goal": "una frase",
        "sites": draw(sites_),
        "max_cost_usd": draw(st.sampled_from(["0.6", "1.10", "2.00"])),
        "looks": draw(st.sampled_from([1, 8, 10, 30])),
        "seconds": draw(st.sampled_from([30, 300, 1800])),
    }
    if draw(st.booleans()) and draw(st.booleans()):
        arguments["task_type"] = "browsing"
    built = draw(st.lists(candidates(arguments), max_size=4))
    unique = {one.grant.id: one for one in built}
    return arguments, list(unique.values())


@settings(max_examples=300, deadline=None)
@given(worlds())
def test_the_executor_hands_over_what_the_guardian_accepts_and_a_covering_policy_if_any(
    world: tuple[dict[str, Any], list[Built]],
) -> None:
    arguments, built = world
    guardian = PermissionGuardian(
        FakeCapabilityRegistry((GUIDED,)), FakeClock(NOW), FakeIdGenerator(), FakeAuditLog()
    )
    step = STEP.model_copy(update={"arguments": arguments})
    chosen = select_authorization(
        [(one.grant, one.uses) for one in built],
        task=TASK,
        step=step,
        capability=GUIDED,
        arguments=arguments,
        targets=targets_of(GUIDED, arguments),
        now=NOW,
    )
    decision = guardian.decide(
        GUIDED,
        arguments,
        task=TASK,
        step=step,
        authorization=None if chosen is None else chosen[0],
        authorization_uses=0 if chosen is None else chosen[1],
    )

    # (1) never a grant the Guardian would call the caller's incoherence
    assert decision.metadata["rule"] != Rule.AUTHORIZATION_MISMATCH.value, decision.reason
    # (2) a covering, usable candidate is found when there is one
    if any(one.covers and one.usable for one in built):
        assert decision.outcome is PermissionOutcome.ALLOWED, decision.reason
    # (3) failing that, a covering one is handed over, so the question says why
    elif any(one.covers for one in built):
        assert chosen is not None
        assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
        assert decision.authorization_id == chosen[0].id
    else:
        assert chosen is None
        assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
