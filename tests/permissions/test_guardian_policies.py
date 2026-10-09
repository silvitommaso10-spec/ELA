"""The Guardian and the policies of §59 (M13.12, ADR 0062; decisions 2, 4, 9, 17).

A policy that covers allows, and says so; one that is revoked or expired is the normal «ask» of
§62; one that does not cover is the caller's incoherence, as every grant that does not cover
(ADR 0011 §6) — the executor never hands it over (``tests/executive/test_select_policies.py``).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from ela.domain import PermissionOutcome
from ela.permissions import Rule, browser_act, revoked, short_id
from ela.testing.fakes import FakeCapabilityRegistry
from tests.permissions.policy_support import (
    GUIDED,
    GUIDED_ARGS,
    GUIDED_LIMITS,
    SITES,
    TERMED,
    TERMED_ARGS,
    policy_for,
)
from tests.permissions.support import COMPLETE, ECHO, GUARDED_ECHO, NOTE, Harness, harness

ACT = browser_act(SITES)
ACT_ARGS: dict[str, Any] = {
    "site": "httpbin.org",
    "path": "/forms/post",
    "fill": [["#custname", "ELA"]],
    "click": "#submit",
    "expect_text": "ELA",
    "purpose": "inviare il modulo",
}


@pytest.fixture
def h() -> Harness:
    return harness(
        registry=FakeCapabilityRegistry((GUIDED, TERMED, ACT, ECHO, NOTE, COMPLETE, GUARDED_ECHO))
    )


def decide(h: Harness, spec: Any, arguments: Any, policy: Any) -> Any:
    return h.guardian.decide(spec, arguments, authorization=policy)


def test_a_policy_that_covers_allows_and_says_policy(h: Harness) -> None:
    policy = policy_for(GUIDED, scope=("www.youtube.com",), limits=GUIDED_LIMITS)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.ALLOWED
    assert decision.metadata["rule"] == Rule.APPROVAL_UNLESS_AUTHORIZED.value
    assert decision.reason == f"browser.guided is covered by policy {policy.id}"
    assert decision.authorization_id == policy.id


def test_the_decision_expires_no_later_than_the_policy(h: Harness) -> None:
    policy = policy_for(GUIDED, expires_at=h.now + timedelta(seconds=30))

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.expires_at == h.now + timedelta(seconds=30)


def test_a_revoked_policy_asks_and_names_the_revocation(h: Harness) -> None:
    policy = revoked(policy_for(GUIDED), h.now)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.reason == (
        f"browser.guided requires an authorization: policy {short_id(policy.id)} was revoked on "
        f"{h.now.date().isoformat()}"
    )


def test_an_expired_policy_asks(h: Harness) -> None:
    policy = policy_for(GUIDED, expires_at=h.now)

    decision = decide(h, GUIDED, GUIDED_ARGS, policy)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert "expired on" in decision.reason


@pytest.mark.parametrize(
    "arguments",
    [
        {**GUIDED_ARGS, "sites": ["example.com"]},
        {**GUIDED_ARGS, "max_cost_usd": "2.00"},
        {**GUIDED_ARGS, "task_type": "browsing"},
    ],
    ids=["site", "limit", "argument"],
)
def test_a_policy_handed_over_that_does_not_cover_is_an_incoherence(
    h: Harness, arguments: dict[str, Any]
) -> None:
    """ADR 0011 §6: the Guardian never ignores a fact it was handed."""
    policy = policy_for(GUIDED, scope=("www.youtube.com",), limits=GUIDED_LIMITS)

    decision = decide(h, GUIDED, arguments, policy)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert f"policy {short_id(policy.id)}" in decision.reason


def test_a_policy_fabricated_for_browser_act_is_denied_with_the_reason_that_names_the_row(
    h: Harness,
) -> None:
    """The second defence of decision 2, built: a standing grant for the HIGH that sends."""
    fabricated = policy_for(GUIDED, scope=SITES).model_copy(update={"capability_id": ACT.id})

    decision = decide(h, ACT, ACT_ARGS, fabricated)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert "is a standing policy (§59) and browser.act is HIGH" in decision.reason


@pytest.mark.parametrize(
    ("spec", "arguments"),
    [
        (COMPLETE, {"input": "riassumi"}),
        (GUARDED_ECHO, {"message": "ciao"}),
        (ECHO, {"message": "ciao"}),
        (NOTE, {"path": "workspace/notes/a.md", "body": "x"}),
    ],
    ids=["model.complete", "a-guarded-safe", "a-safe", "a-low"],
)
def test_a_standing_grant_on_a_capability_that_declares_no_terms_never_covers(
    h: Harness, spec: Any, arguments: dict[str, Any]
) -> None:
    """Decision 17 of the review: the predicate holds for every grant without ``approval_id``."""
    standing = policy_for(TERMED).model_copy(update={"capability_id": spec.id, "scope": spec.scope})

    decision = decide(h, spec, arguments, standing)

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.AUTHORIZATION_MISMATCH.value
    assert f"{spec.id} declares no terms for a policy" in decision.reason


def test_the_generic_capability_is_covered_like_browser_guided(h: Harness) -> None:
    decision = decide(h, TERMED, TERMED_ARGS, policy_for(TERMED))
    assert decision.outcome is PermissionOutcome.ALLOWED


def test_without_a_policy_a_session_asks(h: Harness) -> None:
    decision = h.guardian.decide(GUIDED, GUIDED_ARGS)

    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL
    assert decision.reason == "browser.guided requires an authorization: none was given"
