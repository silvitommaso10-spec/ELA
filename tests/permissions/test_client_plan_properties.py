"""The property behind ``test_client_plan.py``: a client's step never loosens a decision.

    for any ``TaskStep`` a client can build and any ``CapabilitySpec`` it claims, the Guardian's
    outcome is never more permissive than the outcome of the same call with the registered
    specification and a step that declares nothing.

The named attacks are enumerated next door; this is the statement that covers the ones nobody
thought of. It is a *monotonicity* property, not an equality: a step is allowed to make a call
stricter — declaring ``requires_authorization`` on a SAFE capability is exactly what the field is
for — and forbidden to make it looser (ADR 0026 §7).

``arguments`` are generated too: they are the client's as much as the step is, and the scope
check reads them.
"""

from __future__ import annotations

from typing import Final

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    JsonMapping,
    PermissionOutcome,
    RiskLevel,
    StepId,
    TaskStep,
)
from tests.domain.examples import NOW, STEP_ID
from tests.permissions.support import ARGUMENTS, CATALOGUE, harness

PERMISSIVENESS: Final[dict[PermissionOutcome, int]] = {
    PermissionOutcome.DENIED: 0,
    PermissionOutcome.REQUIRES_APPROVAL: 1,
    PermissionOutcome.ALLOWED: 2,
}
"""How much each outcome lets happen: a call that would have asked the user and now runs has been
loosened, so ``REQUIRES_APPROVAL`` sits strictly between the two."""

REGISTERED: Final = tuple(CATALOGUE)

known_ids = st.sampled_from([spec.id for spec in REGISTERED])
invented_ids = st.from_regex(r"[a-z]{2,6}\.[a-z]{2,6}", fullmatch=True).map(CapabilityId)
paths = st.one_of(
    st.just("workspace/notes/briefing.md"),
    st.just("workspace/../etc/passwd"),
    st.just("/etc/passwd"),
    st.from_regex(r"[a-z]{1,6}(/[a-z]{1,6}){0,3}", fullmatch=True),
)


@st.composite
def client_steps(draw: st.DrawFn, capability_id: CapabilityId) -> TaskStep:
    """A step as it can arrive from ``StepIn`` (ADR 0023): every field the caller fills in."""
    declared = draw(
        st.one_of(
            st.just(()),
            st.just((capability_id,)),
            st.lists(st.one_of(known_ids, invented_ids), min_size=1, max_size=3).map(tuple),
        )
    )
    return TaskStep(
        id=StepId(draw(st.sampled_from([STEP_ID]))),
        created_at=NOW,
        goal=draw(st.text(min_size=0, max_size=20)),
        required_capabilities=declared,
        arguments={},  # replaced by the caller: the arguments are drawn once for both decisions
        preferred_device_traits=(),
        dependencies=(),
        risk=draw(st.sampled_from(list(RiskLevel))),
        expected_result="whatever the client wrote",
        success_conditions=(),
        requires_authorization=draw(st.booleans()),
    )


@st.composite
def claims(draw: st.DrawFn) -> tuple[CapabilitySpec, CapabilitySpec, TaskStep, JsonMapping]:
    """What the client claims, what the catalogue holds, the step, and the arguments.

    The claimed specification is the registered one with any subset of the fields a policy reads
    replaced — which is what a client could send if the API took a specification. It does not, and
    that is part of what is being asserted: check 1 compares the two.

    The ``id`` is **not** among the forged fields, and the reason is worth writing: changing it
    does not loosen a call, it asks a different one. "``system.shell`` dressed up as ``core.echo``
    is allowed" is true and says nothing — the caller asked for ``core.echo`` and got it. An id
    the catalogue does not hold has its own property below.
    """
    registered = draw(st.sampled_from(REGISTERED))
    claimed = registered.model_copy(
        update=draw(
            st.fixed_dictionaries(
                {},
                optional={
                    "risk": st.sampled_from(list(RiskLevel)),
                    "requires_authorization": st.booleans(),
                    "scope": st.one_of(st.just(()), st.just(("workspace",)), st.just(("/",))),
                    "input_schema": st.just({"type": "object"}),
                },
            )
        )
    )
    arguments = draw(
        st.one_of(
            st.just(ARGUMENTS.get(registered.id, {})),
            st.fixed_dictionaries({"path": paths, "body": st.text(max_size=8)}),
            st.just({}),
        )
    )
    return registered, claimed, draw(client_steps(registered.id)), arguments


@given(claims())
@settings(deadline=None, max_examples=400)
def test_a_client_step_is_never_more_permissive_than_no_step_at_all(
    case: tuple[CapabilitySpec, CapabilitySpec, TaskStep, JsonMapping],
) -> None:
    registered, claimed, step, arguments = case
    h = harness()

    baseline = h.guardian.decide(registered, arguments, step=None).outcome
    reached = h.guardian.decide(claimed, arguments, step=step).outcome

    assert PERMISSIVENESS[reached] <= PERMISSIVENESS[baseline], (
        f"a client's step loosened {registered.id}: {baseline.value} -> {reached.value}"
    )


@given(claims())
@settings(deadline=None, max_examples=400)
def test_the_decision_always_carries_the_registered_risk_not_the_claimed_one(
    case: tuple[CapabilitySpec, CapabilitySpec, TaskStep, JsonMapping],
) -> None:
    """Whatever the client says the risk is, the decision records the catalogue's — or denies.

    The exception is the denial on check 1 itself, which is reached *because* the two disagree
    and has no registered specification to speak for.
    """
    registered, claimed, step, arguments = case
    h = harness()

    decision = h.guardian.decide(claimed, arguments, step=step)

    if decision.metadata["rule"] != "CATALOGUE":
        assert decision.risk is registered.risk


@given(claims(), st.one_of(known_ids, invented_ids))
@settings(deadline=None, max_examples=200)
def test_a_capability_the_catalogue_does_not_hold_is_always_denied(
    case: tuple[CapabilitySpec, CapabilitySpec, TaskStep, JsonMapping],
    capability_id: CapabilityId,
) -> None:
    """Renaming a specification asks a different question; asking an unknown one is refused.

    The counterpart of the ``id`` left out of :func:`claims`: whatever else the client sends, a
    capability the catalogue never registered gets nothing.
    """
    _, claimed, step, arguments = case
    h = harness()
    renamed = claimed.model_copy(update={"id": capability_id})
    registered_ids = {spec.id for spec in REGISTERED}

    decision = h.guardian.decide(renamed, arguments, step=step)

    if capability_id not in registered_ids:
        assert decision.outcome is PermissionOutcome.DENIED
        assert decision.metadata["rule"] == "CATALOGUE"


@given(claims())
@settings(deadline=None, max_examples=200)
def test_declaring_an_approval_on_the_step_never_removes_the_need_for_one(
    case: tuple[CapabilitySpec, CapabilitySpec, TaskStep, JsonMapping],
) -> None:
    """The ``or`` of check 5b, as a property: turning the step's flag on cannot allow more."""
    registered, _, step, arguments = case
    h = harness()

    off = h.guardian.decide(
        registered, arguments, step=step.model_copy(update={"requires_authorization": False})
    ).outcome
    on = h.guardian.decide(
        registered, arguments, step=step.model_copy(update={"requires_authorization": True})
    ).outcome

    assert PERMISSIVENESS[on] <= PERMISSIVENESS[off]


def test_the_property_is_not_vacuous() -> None:
    """A monotonicity property whose baseline is always DENIED would hold and mean nothing.

    So the three outcomes are pinned as reachable, with the catalogue this harness uses: a SAFE
    capability runs, a MEDIUM one asks, and one above the cap is refused. Deterministic on
    purpose — a statistic over generated cases would be a second thing that can go quiet.
    """
    h = harness()
    by_id = {spec.id: spec for spec in REGISTERED}
    reached = {
        h.guardian.decide(spec, ARGUMENTS.get(spec.id, {}), step=None).outcome
        for spec in (
            by_id[CapabilityId("core.echo")],
            by_id[CapabilityId("model.complete")],
            by_id[CapabilityId("system.shell")],
        )
    }

    assert reached == set(PERMISSIVENESS)
