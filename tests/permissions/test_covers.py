"""What a session's capability may declare it covers (M13.9, decision 29): the first defence.

``covers`` is a fact of the catalogue, **outside** the terms of a policy: the capability of a
session names the capability its reads are, with a copy of that capability's schema — so the day
the schema grows the declaration is another one, and a policy born before stops covering by
itself (the closed world of ADR 0062 §1, extended).

**The catalogue refuses a cover towards a row that is not «approval unless authorized»**: no
session covers a capability that asks at every use, and none has a use for covering one that asks
nobody. It is the first of two defences; the second is the Guardian's
(``test_guardian_sessions.py``), for the day this one is got round.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import CapabilityId, CapabilitySpec, RiskLevel
from ela.permissions import CapabilityRegistry, InvalidCapabilityError, browser_act, browser_read
from tests.permissions.policy_support import GUIDED

SITES = ("posta.example", "video.example")
READ: CapabilitySpec = browser_read(SITES).model_copy(
    update={
        "id": CapabilityId("test.read_as_you"),
        "risk": RiskLevel.MEDIUM,
        "requires_authorization": True,
    }
)
ACT: CapabilitySpec = browser_act(SITES)
LOW_READ: CapabilitySpec = browser_read(SITES)


def session(covered: CapabilitySpec | None, **changes: Any) -> CapabilitySpec:
    """A session's capability declaring ``covers`` — validated, as a factory of the catalogue
    builds one: ``model_copy`` would let anything through."""
    from ela.domain import Covered

    declared = None
    if covered is not None:
        declared = Covered(capability_id=covered.id, input_schema=covered.input_schema)
    fields = GUIDED.model_dump() | {"id": "test.session", "covers": declared} | changes
    return CapabilitySpec.model_validate(fields)


def refused(*specs: CapabilitySpec) -> str:
    with pytest.raises(InvalidCapabilityError) as caught:
        CapabilityRegistry(specs)
    return caught.value.reason


def test_a_session_s_capability_declares_the_medium_its_reads_are() -> None:
    made = session(READ)

    for order in ((made, READ), (READ, made)):
        catalogue = CapabilityRegistry(order)
        declared = catalogue.get(CapabilityId("test.session")).covers
        assert declared is not None
        assert declared.capability_id == READ.id and declared.input_schema == READ.input_schema


def test_a_capability_that_declares_nothing_covers_nothing() -> None:
    assert GUIDED.covers is None and READ.covers is None
    CapabilityRegistry((GUIDED, READ))


def test_the_catalogue_refuses_a_cover_of_a_row_that_asks_at_every_use() -> None:
    said = refused(session(ACT), ACT)

    assert "test.session covers browser.act, which is HIGH" in said
    assert "only a row that asks unless authorized" in said


def test_and_of_a_row_that_does_not_ask() -> None:
    said = refused(session(LOW_READ), LOW_READ)

    assert "test.session covers browser.read, which is LOW" in said


def test_and_of_a_capability_that_is_not_in_the_catalogue() -> None:
    said = refused(session(READ))

    assert "test.session covers test.read_as_you, which is not in the catalogue" in said


def test_and_of_itself() -> None:
    from ela.domain import Covered

    itself = session(None)
    itself = CapabilitySpec.model_validate(
        itself.model_dump()
        | {"covers": Covered(capability_id=itself.id, input_schema=itself.input_schema)}
    )

    assert "test.session covers itself" in refused(itself)


def test_and_a_declaration_whose_copy_of_the_schema_is_not_the_schema() -> None:
    """The copy is what lets an old policy stop covering: one that could drift from the schema it
    copies would be a copy of nothing."""
    from ela.domain import Covered

    stale = Covered(capability_id=READ.id, input_schema={"type": "object", "properties": {}})

    said = refused(session(READ, covers=stale), READ)

    assert (
        "test.session covers test.read_as_you with a schema that is not test.read_as_you's" in said
    )


def test_and_a_cover_declared_by_a_capability_whose_own_row_does_not_ask() -> None:
    """A session covers because somebody said yes to it, or wrote a policy for it. A session
    nobody is asked for would cover with nobody's yes."""
    unasked = session(READ, risk=RiskLevel.LOW, requires_authorization=False, policy_terms=None)

    said = refused(unasked, READ)

    assert "test.session is LOW: only a capability that asks may cover another" in said


# ----------------------------------------------------------------------------------------
# The closed world of ADR 0062 §1, extended to what a session covers
# ----------------------------------------------------------------------------------------


def a_policy_of(spec: CapabilitySpec) -> Any:
    """The policy Tommaso writes for a session's capability, born under today's declaration."""
    from uuid import UUID

    from ela.domain import AuthorizationId
    from ela.permissions.policies import PolicyRequest, authorization_from_policy
    from tests.domain.examples import NOW
    from tests.permissions.policy_support import GUIDED_LIMITS

    return authorization_from_policy(
        PolicyRequest(spec.id, ("example.com",), GUIDED_LIMITS, 30),
        catalogue=CapabilityRegistry((spec, READ, GROWN)),
        granted_by="tommaso",
        now=NOW,
        authorization_id=AuthorizationId(UUID("00000000-0000-4000-8000-000000000c0e")),
    )


GROWN: CapabilitySpec = READ.model_copy(
    update={
        "id": CapabilityId("test.read_grown"),
        "input_schema": {
            **READ.input_schema,
            "properties": {**READ.input_schema["properties"], "lang": {"type": "string"}},  # type: ignore[dict-item]
        },
    }
)
"""The read of tomorrow: one argument more."""
SESSION_ARGS: dict[str, Any] = {
    "goal": "Leggi la posta di oggi.",
    "sites": ["example.com"],
    "max_cost_usd": "1.10",
    "looks": 8,
    "seconds": 300,
}


def test_a_policy_carries_a_copy_of_what_its_session_covered_the_day_it_was_born() -> None:
    made = session(READ)

    policy = a_policy_of(made)

    assert policy.bounds is not None
    assert policy.bounds.covers == made.covers
    assert policy.bounds.terms == made.policy_terms, "and the terms, as before"


def test_a_policy_born_before_the_covered_schema_changed_stops_covering_by_itself() -> None:
    """Decision 29: the terms copied on a grant do not carry the schema of the capability the
    session covers, so without this an old policy would go on opening sessions whose reads are no
    longer the reads it was written for. The copy of the declaration is compared with today's,
    and the reason is the one of terms that changed: the session asks."""
    from ela.permissions.policies import GAPS, Gap, shortfall
    from tests.domain.examples import NOW

    born = session(READ)
    policy = a_policy_of(born)
    assert shortfall(policy, born, SESSION_ARGS, now=NOW, gaps=GAPS) is None, "the control"

    today = session(GROWN)
    found = shortfall(policy, today, SESSION_ARGS, now=NOW, gaps=GAPS)

    assert found is not None and found.gap is Gap.TERMS
    assert "declares other terms than those policy" in found.reason


def test_a_policy_of_a_capability_that_covers_nothing_is_what_it_was() -> None:
    """``browser.guided`` covers nothing, and a policy born with M13.12 — stored before the field
    existed — reads as it was written and covers what it covered."""
    from ela.domain import PolicyBounds
    from ela.permissions.policies import GAPS, shortfall
    from tests.domain.examples import NOW
    from tests.permissions.policy_support import GUIDED_ARGS, policy_for

    policy = policy_for(GUIDED)
    assert policy.bounds is not None
    stored = policy.bounds.model_dump(mode="json")
    stored.pop("covers", None)

    read_back = PolicyBounds.model_validate(stored)

    assert read_back == policy.bounds and read_back.covers is None
    assert shortfall(policy, GUIDED, GUIDED_ARGS, now=NOW, gaps=GAPS) is None
