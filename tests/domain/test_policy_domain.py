"""The shape of a policy of §59 in the domain (M13.12, ADR 0062; decision 3d, proposal 2).

Two invariants beside the one of ADR 0012 §1, in the same validator: a grant without
``approval_id`` always ends, and a grant born from a yes has no bounds.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from ela.domain import (
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilityId,
    PolicyBounds,
    PolicyTerms,
)
from tests.domain.examples import APPROVAL_ID, NOW, STEP_ID, TASK_ID

TERMS = PolicyTerms(
    limits=("budget",), uncovered=("route",), free=("text",), route="browsing", model="m"
)
BOUNDS = PolicyBounds(terms=TERMS, limits={"budget": "1.10"})


def standing(**fields: object) -> Authorization:
    return Authorization.model_validate(
        {
            "id": AuthorizationId(TASK_ID),
            "created_at": NOW,
            "capability_id": CapabilityId("test.termed"),
            "scope": ("alpha.example",),
            "granted_by": "local",
            "expires_at": NOW + timedelta(days=1),
            "bounds": BOUNDS,
            **fields,
        }
    )


def test_a_policy_carries_its_bounds_and_its_end() -> None:
    policy = standing()

    assert policy.bounds == BOUNDS
    assert policy.expires_at == NOW + timedelta(days=1)
    assert policy.revoked_at is None


def test_a_grant_without_approval_id_and_without_an_end_is_refused() -> None:
    """Decision 3d: a policy always ends; the type refuses one that does not."""
    with pytest.raises(ValidationError, match="expires"):
        standing(expires_at=None)


def test_a_grant_born_from_a_yes_has_no_bounds() -> None:
    with pytest.raises(ValidationError, match="bounds"):
        standing(approval_id=APPROVAL_ID, task_id=TASK_ID, step_id=STEP_ID, max_uses=1)


def test_a_grant_born_from_a_yes_may_still_have_no_end_written() -> None:
    """The invariant of decision 3d is about grants without ``approval_id``; ADR 0012 §1 is
    unchanged for the others."""
    yes = standing(
        approval_id=APPROVAL_ID,
        task_id=TASK_ID,
        step_id=STEP_ID,
        max_uses=1,
        bounds=None,
        expires_at=None,
    )
    assert yes.expires_at is None


def test_the_values_of_the_limits_are_kept_as_words_and_never_validated() -> None:
    """Proposal 15: a row the type refused would stop every grant of the capability; a value that
    is not a number is the predicate's «does not cover», not the type's refusal."""
    odd = PolicyBounds(terms=TERMS, limits={"budget": "uno"})
    assert odd.limits["budget"] == "uno"


def test_terms_and_bounds_are_frozen() -> None:
    with pytest.raises(ValidationError):
        TERMS.limits = ("other",)  # type: ignore[misc]
    with pytest.raises(TypeError):
        BOUNDS.limits["budget"] = "2"  # type: ignore[index]


def test_the_revocation_has_its_event() -> None:
    assert AuditEventType.AUTHORIZATION_REVOKED.value == "AUTHORIZATION_REVOKED"
