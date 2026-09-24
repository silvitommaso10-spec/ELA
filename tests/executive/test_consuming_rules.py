"""``CONSUMING_RULES`` follows the Guardian, for every value of ``Rule`` (M13.1b dec. 1).

The set says which decisions rest on the grant they were handed, and so which ones spend it. Until
M13.1b it was written by hand in the executor, and it missed the one row that asks at every use:
an approved ``HIGH`` never spent its yes. It is now derived — ``ASKING_RULES`` plus
``AUTHORIZATION_REQUIRED`` — and this file is what keeps the derivation honest without reading it.

For each member of :class:`~ela.permissions.Rule` there is one **scenario**: a capability, its
arguments, a step, a task and a grant. The Guardian decides the same call **with that grant and
without it**. If the decision is ``ALLOWED`` with the grant and not without, the ``ALLOWED`` rests
on the grant, and the rule must be in ``CONSUMING_RULES``; otherwise it must not be.

The scenarios are written by hand, and they are **preconditions, not expectations**: what is
asserted comes from the Guardian's answer. Each scenario must also really produce its rule in one
of the two decisions, so the table cannot lie about which rule it exercises. The world is closed
over ``Rule``: a member added tomorrow without a scenario fails here, and one whose ``ALLOWED``
rests on a grant fails until it consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pytest

from ela.domain import (
    Authorization,
    CapabilityId,
    CapabilitySpec,
    JsonMapping,
    PermissionOutcome,
    RiskLevel,
    Task,
    TaskStep,
)
from ela.executive import CONSUMING_RULES
from ela.permissions import ASKING_RULES, Rule
from ela.ports import CapabilityRegistryPort
from ela.testing.fakes import FakeCapabilityRegistry
from tests.domain.examples import TASK
from tests.permissions.support import (
    CATALOGUE,
    CRITICAL,
    ECHO,
    ECHO_ARGS,
    GUARDED_ECHO,
    HIGH,
    NOTE,
    NOTE_ARGS,
    born_of_a_yes,
    grant,
    harness,
    step_for,
)

MEDIUM_ECHO: Final = ECHO.model_copy(
    update={"id": CapabilityId("core.echo_medium"), "risk": RiskLevel.MEDIUM}
)
"""The ``MEDIUM`` row, which the shared test catalogue has no capability for."""


class _BrokenRegistry:
    """A catalogue that raises: the only way ``INTERNAL_ERROR`` is born (§33)."""

    def get(self, capability_id: CapabilityId) -> CapabilitySpec:
        raise RuntimeError("the catalogue is on fire")

    def specs(self) -> tuple[CapabilitySpec, ...]:
        return ()


@dataclass(frozen=True)
class Scenario:
    """One call, decided twice: with ``grant`` and without it."""

    spec: CapabilitySpec
    arguments: JsonMapping
    grant: Authorization
    step: TaskStep | None = None
    task: Task | None = None
    registry: CapabilityRegistryPort | None = None


REGISTRY: Final = FakeCapabilityRegistry((*CATALOGUE, MEDIUM_ECHO))

SCENARIOS: Final[dict[Rule, Scenario]] = {
    Rule.ALLOW: Scenario(ECHO, ECHO_ARGS, grant(ECHO), step_for(ECHO.id)),
    Rule.ALLOW_WITHIN_SCOPE: Scenario(NOTE, NOTE_ARGS, grant(NOTE), step_for(NOTE.id)),
    Rule.APPROVAL_UNLESS_AUTHORIZED: Scenario(
        MEDIUM_ECHO, ECHO_ARGS, grant(MEDIUM_ECHO), step_for(MEDIUM_ECHO.id)
    ),
    Rule.APPROVAL_EVERY_USE: Scenario(
        HIGH, ECHO_ARGS, born_of_a_yes(HIGH), step_for(HIGH.id), task=TASK
    ),
    Rule.AUTHORIZATION_REQUIRED: Scenario(
        GUARDED_ECHO, ECHO_ARGS, grant(GUARDED_ECHO), step_for(GUARDED_ECHO.id)
    ),
    Rule.DENY: Scenario(
        CRITICAL, ECHO_ARGS, born_of_a_yes(CRITICAL), step_for(CRITICAL.id), task=TASK
    ),
    Rule.SCOPE: Scenario(
        NOTE, {**NOTE_ARGS, "path": "workspace/other/x.md"}, grant(NOTE), step_for(NOTE.id)
    ),
    Rule.CATALOGUE: Scenario(
        ECHO.model_copy(update={"description": "a specification the catalogue never held"}),
        ECHO_ARGS,
        grant(ECHO),
    ),
    Rule.ARGUMENTS: Scenario(ECHO, {"message": 42}, grant(ECHO), step_for(ECHO.id)),
    Rule.STEP_MISMATCH: Scenario(ECHO, ECHO_ARGS, grant(ECHO), step_for(NOTE.id)),
    # The one rule a *valid* grant cannot produce: it is born of a grant that does not cover.
    Rule.AUTHORIZATION_MISMATCH: Scenario(ECHO, ECHO_ARGS, grant(NOTE), step_for(ECHO.id)),
    Rule.INTERNAL_ERROR: Scenario(
        ECHO, ECHO_ARGS, grant(ECHO), step_for(ECHO.id), registry=_BrokenRegistry()
    ),
}


def missing_scenarios(scenarios: dict[Rule, Scenario]) -> list[str]:
    return sorted(rule.value for rule in set(Rule) - set(scenarios))


def drift(rule: Rule, scenario: Scenario, consuming: frozenset[Rule]) -> str | None:
    """Why ``consuming`` is wrong about ``rule``, read from the Guardian; ``None`` if right."""
    h = harness(registry=REGISTRY if scenario.registry is None else scenario.registry)

    def decide(authorization: Authorization | None) -> tuple[PermissionOutcome, str]:
        decision = h.guardian.decide(
            scenario.spec,
            scenario.arguments,
            task=scenario.task,
            step=scenario.step,
            authorization=authorization,
        )
        return decision.outcome, str(decision.metadata["rule"])

    with_grant = decide(scenario.grant)
    without = decide(None)
    if rule.value not in {with_grant[1], without[1]}:
        return (
            f"the scenario of {rule.value} is settled by {with_grant[1]} and {without[1]}: it does "
            "not exercise the rule it is filed under"
        )
    rests_on_the_grant = (
        with_grant[0] is PermissionOutcome.ALLOWED and without[0] is not PermissionOutcome.ALLOWED
    )
    if (rule in consuming) is rests_on_the_grant:
        return None
    seen = f"{rule.value}: with the grant {with_grant[0].value}, without it {without[0].value}. "
    return seen + (
        "The ALLOWED rests on the grant, so the grant must be spent: the rule belongs in "
        "CONSUMING_RULES."
        if rests_on_the_grant
        else "The outcome does not rest on the grant, so spending it would take a use nobody "
        "used: the rule does not belong in CONSUMING_RULES."
    )


def test_every_rule_has_a_scenario() -> None:
    """The closed world: a ``Rule`` nobody wrote a scenario for is a rule nobody checked."""
    missing = missing_scenarios(SCENARIOS)
    assert not missing, (
        f"write a scenario for {missing} in SCENARIOS: a call the Guardian settles under that "
        "rule, with a grant and without, so whether it spends the grant is read from its behaviour"
    )


@pytest.mark.parametrize("rule", list(Rule), ids=lambda rule: rule.value)
def test_a_rule_consumes_exactly_when_an_allowed_rests_on_the_grant(rule: Rule) -> None:
    scenario = SCENARIOS.get(rule)
    if scenario is None:
        pytest.fail(f"Rule.{rule.name} has no scenario: see test_every_rule_has_a_scenario")
    problem = drift(rule, scenario, CONSUMING_RULES)
    assert problem is None, problem


def test_a_drifted_set_is_caught_in_both_directions() -> None:
    """The check fails when the set is wrong, whichever way: a rule that should spend and does not
    — the defect M13.1b repairs — and a rule that spends a grant it did not rest on."""
    every_use = SCENARIOS[Rule.APPROVAL_EVERY_USE]
    assert drift(Rule.APPROVAL_EVERY_USE, every_use, ASKING_RULES - {Rule.APPROVAL_EVERY_USE})
    assert drift(Rule.ALLOW, SCENARIOS[Rule.ALLOW], ASKING_RULES | {Rule.ALLOW})


def test_a_rule_without_a_scenario_is_caught() -> None:
    fewer = {rule: scenario for rule, scenario in SCENARIOS.items() if rule is not Rule.SCOPE}
    assert missing_scenarios(fewer) == [Rule.SCOPE.value]


def test_a_scenario_filed_under_the_wrong_rule_is_caught() -> None:
    problem = drift(Rule.DENY, SCENARIOS[Rule.ALLOW], CONSUMING_RULES)
    assert problem is not None and "does not exercise the rule" in problem
