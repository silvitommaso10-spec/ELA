"""Whether a step can be acted on, said once for the executor, the Planner and the hand route.

M14.2, ADR 0058 (decision B, and decision 8 of the review). The check that decides whether the
executor acts on a step — exactly one capability, in the catalogue, with a tool and a verifier, at
least one success condition, all in the verifier's vocabulary (ADR 0013 §2, ADR 0014 §3) — lived
inline in ``Executor._prepared``. It is one function now: what decides whether a step runs is what
decides whether a plan comes in, and a second copy is how the two would stop agreeing.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import CapabilityId, TaskStep
from ela.executive import executor as executor_module
from ela.executive import planner as planner_module
from ela.executive.readiness import Ready, Unready, readiness
from ela.permissions import CapabilityRegistry
from ela.permissions.errors import CapabilityNotFound
from ela.ports import NotFoundError
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from tests.domain.examples import TASK_STEP
from tests.permissions.support import ECHO, NOTE

KNOWN = "fake.ok"


def registries(*, tools: bool = True, verifiers: bool = True) -> dict[str, Any]:
    clock, ids = FakeClock(), FakeIdGenerator()
    return {
        "capabilities": CapabilityRegistry((ECHO, NOTE)),
        "tools": FakeToolRegistry([FakeTool(ECHO.id, clock, ids)] if tools else []),
        "verifiers": FakeVerifierRegistry(
            [FakeVerifier(ECHO.id, name="echo-checker", conditions=(KNOWN,))] if verifiers else []
        ),
    }


def step(**changed: Any) -> TaskStep:
    fields = {"required_capabilities": (ECHO.id,), "success_conditions": (KNOWN,), **changed}
    return TASK_STEP.model_copy(update=fields)


def test_a_step_with_its_capability_its_tool_and_its_verifier_is_ready() -> None:
    world = registries()

    ready = readiness(step(), **world)

    assert isinstance(ready, Ready)
    assert ready.spec == ECHO
    assert ready.tool is world["tools"].get(ECHO.id)
    assert ready.verifier is world["verifiers"].get(ECHO.id)


@pytest.mark.parametrize("declared", [(), (ECHO.id, NOTE.id)], ids=["none", "two"])
def test_a_step_declares_exactly_one_capability(declared: tuple[CapabilityId, ...]) -> None:
    unready = readiness(step(required_capabilities=declared), **registries())

    assert isinstance(unready, Unready)
    assert unready.code == "capabilities"
    assert unready.said == (
        f"declares {len(declared)} capabilities; an executable step declares exactly one"
    )
    assert unready.error is None


def test_a_step_declares_a_success_condition() -> None:
    unready = readiness(step(success_conditions=()), **registries())

    assert isinstance(unready, Unready)
    assert unready.code == "no_condition"
    assert unready.said == (
        "declares no success condition; an action that cannot be verified is not executed"
    )


def test_a_capability_outside_the_catalogue_carries_the_registry_s_own_error() -> None:
    unready = readiness(step(required_capabilities=(CapabilityId("made.up"),)), **registries())

    assert isinstance(unready, Unready)
    assert unready.code == "unknown_capability"
    assert isinstance(unready.error, CapabilityNotFound)
    assert "made.up" not in unready.said


@pytest.mark.parametrize(("missing", "code"), [("tools", "no_tool"), ("verifiers", "no_verifier")])
def test_a_capability_without_its_tool_or_its_verifier_carries_the_registry_s_error(
    missing: str, code: str
) -> None:
    unready = readiness(step(), **registries(**{missing: False}))

    assert isinstance(unready, Unready)
    assert unready.code == code
    assert isinstance(unready.error, NotFoundError)
    assert ECHO.id in unready.said


def test_conditions_outside_the_vocabulary_are_counted_and_not_echoed() -> None:
    """What the Planner and the route say goes back to a caller, and to the audit when the plan
    was the model's: the count and the verifier's name, never the words the plan wrote."""
    unready = readiness(step(success_conditions=(KNOWN, "made.up", "other.one")), **registries())

    assert isinstance(unready, Unready)
    assert unready.code == "outside"
    assert unready.outside == ("made.up", "other.one")
    assert unready.said == (
        "names 2 success conditions echo-checker cannot check; an action that cannot be verified "
        "is not executed"
    )
    assert "made.up" not in unready.said


def test_the_checks_come_in_the_executor_s_order() -> None:
    """Two capabilities and no condition: the count first, as ``Executor._prepared`` always did."""
    unready = readiness(
        step(required_capabilities=(ECHO.id, NOTE.id), success_conditions=()), **registries()
    )

    assert isinstance(unready, Unready)
    assert unready.code == "capabilities"


def test_the_executor_and_the_planner_call_this_very_function() -> None:
    """The call graph and not a result (criterion 5): each module holds the same object."""
    assert executor_module.readiness is readiness
    assert planner_module.readiness is readiness
