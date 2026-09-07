"""A step written by the client can only make a decision stricter, never looser (ADR 0026 §7).

``POST /tasks/{id}/plan`` is public surface until the Planner exists (ADR 0023), so
``required_capabilities``, ``requires_authorization``, ``risk`` and ``arguments`` of every step
arrive from outside. It is the first thing an attacker tries, and until M9.1 the property that
stops them lived in two boolean expressions with no test that named it.

The property, with an explicit order on outcomes (:data:`PERMISSIVENESS`):

    for any ``TaskStep`` a client can build and any ``CapabilitySpec`` it claims, the Guardian's
    outcome is never **more permissive** than the outcome of the same call with the registered
    specification and a step that declares nothing.

It holds because everything the policy reads comes from the catalogue — ``registered.risk``,
``registered.scope``, ``registered.input_schema`` — and a step can only add: check 3 denies when
the step names capabilities and not this one, and check 5b reads
``registered.requires_authorization or step.requires_authorization``. The property test is in
``test_client_plan_properties.py``; these are the named attacks, one by one.
"""

from __future__ import annotations

from typing import Final

import pytest

from ela.devices import UNGUARDED_RISK
from ela.domain import (
    CapabilityId,
    CapabilitySpec,
    PermissionOutcome,
    RiskLevel,
    TaskStep,
)
from ela.permissions import MAX_RISK
from ela.permissions.guardian import Rule
from tests.permissions.support import (
    ARGUMENTS,
    COMPLETE,
    ECHO,
    GUARDED_NOTE,
    NOTE,
    Harness,
    harness,
    step_for,
)

PERMISSIVENESS: Final[dict[PermissionOutcome, int]] = {
    PermissionOutcome.DENIED: 0,
    PermissionOutcome.REQUIRES_APPROVAL: 1,
    PermissionOutcome.ALLOWED: 2,
}
"""How much each outcome lets happen. DENIED lets nothing, ALLOWED lets everything, and asking
the user sits between the two: a call that would have asked and now runs has been loosened."""


@pytest.fixture
def h() -> Harness:
    return harness()


def decide(h: Harness, spec: CapabilitySpec, step: TaskStep | None) -> PermissionOutcome:
    return h.guardian.decide(spec, ARGUMENTS.get(spec.id, {}), step=step).outcome


# --------------------------------------------------------------------------------------
# The four fields a client fills in
# --------------------------------------------------------------------------------------


def test_a_step_cannot_switch_off_the_approval_a_capability_requires(h: Harness) -> None:
    """``requires_authorization=False`` on a MEDIUM capability buys nothing: the ``or``
    only ever adds."""
    assert COMPLETE.risk is RiskLevel.MEDIUM

    honest = decide(h, COMPLETE, step_for(COMPLETE.id, requires_authorization=True))
    hostile = decide(h, COMPLETE, step_for(COMPLETE.id, requires_authorization=False))

    assert honest is PermissionOutcome.REQUIRES_APPROVAL
    assert hostile is PermissionOutcome.REQUIRES_APPROVAL


def test_a_step_can_only_add_an_approval_never_remove_one(h: Harness) -> None:
    """The other direction is allowed, and is the point of the field: SAFE plus a step that asks."""
    assert decide(h, ECHO, step_for(ECHO.id)) is PermissionOutcome.ALLOWED

    asked = decide(h, ECHO, step_for(ECHO.id, requires_authorization=True))

    assert asked is PermissionOutcome.REQUIRES_APPROVAL


def test_declaring_no_capability_only_gives_up_a_check_that_could_deny(h: Harness) -> None:
    """An empty ``required_capabilities`` is *no declaration*, not a permission (ADR 0011 §15).

    Skipping check 3 can never turn a DENIED into an ALLOWED: the check has no allowing branch.
    """
    silent = decide(h, NOTE, step_for())
    declared = decide(h, NOTE, step_for(NOTE.id))
    lying = h.guardian.decide(NOTE, ARGUMENTS[NOTE.id], step=step_for(ECHO.id))

    assert silent is declared is PermissionOutcome.ALLOWED
    assert lying.outcome is PermissionOutcome.DENIED
    assert lying.metadata["rule"] == Rule.STEP_MISMATCH.value


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk", RiskLevel.SAFE),
        ("scope", ("workspace", "..", "/etc")),
        ("requires_authorization", False),
        ("input_schema", {"type": "object"}),
    ],
)
def test_a_specification_the_client_dressed_up_is_refused_by_name(
    h: Harness, field: str, value: object
) -> None:
    """Check 1 compares with the **registered** specification, so a forged one never gets used.

    This is what makes the rest of the property hold: the client can name a capability, it cannot
    describe one. The base is ``GUARDED_NOTE`` so that every one of the four edits is a real
    change: forging a field to the value it already had is not a forgery.
    """
    forged = GUARDED_NOTE.model_copy(update={field: value})
    assert forged != GUARDED_NOTE, "this case forges nothing"
    decision = h.guardian.decide(forged, ARGUMENTS[GUARDED_NOTE.id], step=step_for(GUARDED_NOTE.id))

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.CATALOGUE.value


def test_a_capability_the_catalogue_does_not_hold_is_refused(h: Harness) -> None:
    invented = NOTE.model_copy(update={"id": CapabilityId("workspace.write_anywhere")})

    decision = h.guardian.decide(invented, ARGUMENTS[NOTE.id], step=step_for(invented.id))

    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.CATALOGUE.value


# --------------------------------------------------------------------------------------
# The one client field the Guardian does not read — and the filter that reads it
# --------------------------------------------------------------------------------------


def test_the_guardian_reads_the_registered_risk_and_not_the_steps(h: Harness) -> None:
    """``step.risk`` exists and the Guardian never consults it: the risk is the catalogue's."""
    lowered = step_for(COMPLETE.id).model_copy(update={"risk": RiskLevel.SAFE})

    decision = h.guardian.decide(COMPLETE, ARGUMENTS[COMPLETE.id], step=lowered)

    assert decision.risk is RiskLevel.MEDIUM
    assert decision.outcome is PermissionOutcome.REQUIRES_APPROVAL


def test_the_degraded_filter_is_vacuous_today_and_this_says_so() -> None:
    """The one place ``step.risk`` is read is a filter no real capability can trigger.

    ``refusals`` discards a DEGRADED node from ``UNGUARDED_RISK`` (HIGH) up, and the catalogue
    stops at :data:`~ela.permissions.MAX_RISK` (MEDIUM), so declaring a lower risk loosens nothing
    — there was nothing tight — and declaring a higher one can only tighten.

    Written down rather than left to look like a defence: **a defence that appears active and
    cannot fire is worse than an absent one, because whoever reads it stops looking for a real
    one.** It comes alive the day the catalogue admits HIGH, and that is the day the provenance
    of ``step.risk`` has to be looked at again (ADR 0026 §7).
    """
    assert UNGUARDED_RISK > MAX_RISK, (
        "the DEGRADED filter is no longer vacuous: a registrable capability can now reach "
        "UNGUARDED_RISK, so where step.risk comes from starts to matter (ADR 0026 §7)"
    )
