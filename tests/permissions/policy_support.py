"""What the tests of the policies of §59 share (M13.12, ADR 0062): a declared capability, the real
``browser.guided`` with its sites and its model, and a policy built as the route would build it.

**Built here, in the tests**, where no architecture rule applies: in production a policy is born
only from the route of its creation (rule 66), through
:func:`~ela.permissions.authorization_from_policy`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Final
from uuid import UUID

from ela.domain import (
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    PolicyBounds,
    PolicyTerms,
    RiskLevel,
)
from ela.permissions import COST_PATTERN, browser_guided
from tests.domain.examples import NOW

SITES: Final = ("www.youtube.com", "example.com", "httpbin.org")
"""The sites of the guide's sections 26 and 27: ``ELA_BROWSER_SITES`` of the proofs."""

MODEL: Final = "claude-haiku-5-5"
"""The model of the route ``browsing`` today: the cheap profile (M14.6)."""

GUIDED: Final = browser_guided(SITES, model=MODEL)
"""``browser.guided`` as the composition root builds it: the sites of the ``.env``, and the model of
the default route in its terms."""

TERMED: Final = CapabilitySpec(
    id=CapabilityId("test.termed"),
    created_at=NOW,
    description="A MEDIUM capability of the tests that declares what a policy must bound.",
    risk=RiskLevel.MEDIUM,
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1},
            "places": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "budget": {"type": "string", "pattern": COST_PATTERN},
            "count": {"type": "integer", "minimum": 1, "maximum": 30},
            "route": {"type": "string", "minLength": 1},
        },
        "required": ["text", "places", "budget", "count"],
        "additionalProperties": False,
    },
    scope=("alpha.example", "beta.example"),
    scoped_arguments=("places",),
    policy_terms=PolicyTerms(
        limits=("budget", "count"), uncovered=("route",), free=("text",), model="test-model"
    ),
    requires_authorization=True,
)
"""The generic capability of the Guardian's and the executor's tests: what ``model.complete`` was
for them before M13.12, when a standing grant covered any MEDIUM (decision 17 of the review)."""

TERMED_ARGS: Final[dict[str, Any]] = {
    "text": "anything",
    "places": ["alpha.example"],
    "budget": "1.10",
    "count": 5,
}

GUIDED_ARGS: Final[dict[str, Any]] = {
    "goal": "Apri YouTube e cerca il canale di MrBeast.",
    "sites": ["www.youtube.com"],
    "max_cost_usd": "1.10",
    "looks": 8,
    "seconds": 300,
}
"""A session inside the policy of the proof: the plan ``policy-youtube.json``."""

GUIDED_LIMITS: Final = {"max_cost_usd": "1.10", "looks": "10", "seconds": "300"}
"""The policy of the proof's step 4: 1,10 $, ten looks, five minutes."""


WIDEST: Final = {
    "max_cost_usd": "999999",
    "looks": "30",
    "seconds": "1800",
    "budget": "999",
    "count": "30",
}
"""The widest value of every limit the declarations of the tests name."""


def policy_for(
    spec: CapabilitySpec,
    *,
    scope: tuple[str, ...] | None = None,
    limits: dict[str, str] | None = None,
    created_at: datetime = NOW,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    terms: PolicyTerms | None = None,
    tail: int = 900,
    **changes: Any,
) -> Authorization:
    """A standing policy for ``spec``: the capability's whole scope, limits at their widest unless
    given, a day of life, the terms of today — then ``changes``."""
    declared = spec.policy_terms if terms is None else terms
    assert declared is not None, f"{spec.id} declares no terms"
    chosen = {name: WIDEST[name] for name in declared.limits} if limits is None else limits
    base = Authorization(
        id=AuthorizationId(UUID(f"{tail:08x}-0000-4000-8000-{tail:012d}")),
        created_at=created_at,
        capability_id=spec.id,
        scope=spec.scope if scope is None else scope,
        granted_by="tommaso",
        expires_at=created_at + timedelta(days=1) if expires_at is None else expires_at,
        revoked_at=revoked_at,
        bounds=PolicyBounds(terms=declared, limits=chosen),
        metadata={"origin": "policy"},
    )
    return base.model_copy(update=changes)


def revoked(policy: Authorization, at: datetime) -> Authorization:
    """``policy`` revoked at ``at``, as the store writes it: in the tests a copy is enough — in
    production only the store's ``revoke`` writes the field (rule 66)."""
    return policy.model_copy(update={"revoked_at": at})
