"""The scope of a guided session (M14.3, ADR 0060): a list of sites, each a target, and a step that
narrows the scope of the capability it asks for and never widens it.

``targets_of`` gives one target per element of a scoped argument that is a list, and none for an
empty list — which a non-empty scope then denies, «a doubt». The catalogue admits a scoped argument
that is an array of strings. The Guardian denies with ``Rule.SCOPE`` a target the capability's scope
covers but the step's ``within`` does not: the property of ADR 0026 §7, extended to the scope.
"""

from __future__ import annotations

import pytest

from ela.domain import CapabilitySpec, PermissionOutcome, RiskLevel
from ela.permissions import (
    BROWSER_GUIDED,
    BROWSER_READ,
    CapabilityRegistry,
    InvalidCapabilityError,
    PermissionGuardian,
    browser_guided,
    browser_read,
    check_capability,
    production_catalogue,
)
from ela.permissions.capabilities import DECLARES_AN_EMPTY_SCOPE, LOOKS_MAX, SECONDS_MAX
from ela.permissions.guardian import Rule
from ela.permissions.scope import scope_covers, targets_of
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeIdGenerator
from tests.domain.examples import TASK_STEP

SITES = ("www.youtube.com", "example.com")


def test_a_list_gives_one_target_per_site() -> None:
    spec = browser_guided(SITES)
    assert targets_of(spec, {"sites": ["www.youtube.com", "example.com"]}) == SITES
    assert targets_of(spec, {"sites": ("example.com",)}) == ("example.com",)


def test_an_empty_list_gives_no_target_and_a_scope_denies_it() -> None:
    spec = browser_guided(SITES)
    assert targets_of(spec, {"sites": []}) == ()
    assert not scope_covers(spec.scope, targets_of(spec, {"sites": []}))


def test_a_string_is_still_one_target_and_a_missing_argument_is_none() -> None:
    spec = browser_read(SITES)
    assert targets_of(spec, {"site": "example.com"}) == ("example.com",)
    assert targets_of(spec, {}) == (None,)


def test_the_capability_is_the_one_the_spec_writes() -> None:
    spec = browser_guided(SITES)
    assert (spec.id, spec.risk, spec.requires_authorization) == (
        BROWSER_GUIDED,
        RiskLevel.MEDIUM,
        True,
    )
    assert spec.scope == SITES and spec.scoped_arguments == ("sites",)
    assert BROWSER_GUIDED in DECLARES_AN_EMPTY_SCOPE
    assert tuple(spec.input_schema["required"]) == (
        "goal",
        "sites",
        "max_cost_usd",
        "looks",
        "seconds",
    )
    properties = spec.input_schema["properties"]
    assert (
        properties["looks"]["maximum"] == LOOKS_MAX
        and properties["seconds"]["maximum"] == SECONDS_MAX
    )
    assert [one.id for one in production_catalogue().specs()][-1] == BROWSER_GUIDED


def test_an_empty_list_of_sites_is_an_answer_for_the_session_too() -> None:
    """``ELA_BROWSER_SITES=[]`` is «no site», for the browser's three capabilities (M13.4)."""
    check_capability(browser_guided(()))


def test_a_scoped_argument_is_a_string_or_an_array_of_strings_and_nothing_else() -> None:
    def with_sites(declared: object) -> CapabilitySpec:
        spec = browser_guided(SITES)
        schema = {
            **spec.input_schema,
            "properties": {**spec.input_schema["properties"], "sites": declared},
        }
        return spec.model_copy(update={"input_schema": schema})

    check_capability(with_sites({"type": "array", "items": {"type": "string"}}))
    for wrong in (
        {"type": "array", "items": {"type": "integer"}},
        {"type": "array"},
        {"type": "integer"},
    ):
        with pytest.raises(InvalidCapabilityError, match="string or an array of strings"):
            check_capability(with_sites(wrong))
    spec = browser_guided(SITES)
    without = {
        **spec.input_schema,
        "properties": {
            name: value
            for name, value in spec.input_schema["properties"].items()
            if name != "sites"
        },
        "required": ["goal"],
    }
    with pytest.raises(InvalidCapabilityError, match="string or an array of strings"):
        check_capability(spec.model_copy(update={"input_schema": without}))


def guardian() -> PermissionGuardian:
    registry = CapabilityRegistry((browser_read(SITES), browser_guided(SITES)))
    return PermissionGuardian(registry, FakeClock(), FakeIdGenerator(), FakeAuditLog())


READ = {"site": "example.com", "path": "/", "purpose": "a gesture"}


def test_a_step_within_the_session_s_sites_is_decided_as_without_it() -> None:
    step = TASK_STEP.model_copy(
        update={"required_capabilities": (BROWSER_READ,), "within": ("example.com",)}
    )
    decision = guardian().decide(browser_read(SITES), READ, step=step)
    assert decision.outcome is PermissionOutcome.ALLOWED


def test_a_site_the_capability_covers_and_the_session_does_not_is_denied_by_scope() -> None:
    step = TASK_STEP.model_copy(
        update={"required_capabilities": (BROWSER_READ,), "within": ("www.youtube.com",)}
    )
    decision = guardian().decide(browser_read(SITES), READ, step=step)
    assert decision.outcome is PermissionOutcome.DENIED
    assert decision.metadata["rule"] == Rule.SCOPE.value
    assert "not within the step's scope" in decision.reason


def test_an_empty_within_covers_nothing() -> None:
    step = TASK_STEP.model_copy(update={"required_capabilities": (BROWSER_READ,), "within": ()})
    decision = guardian().decide(browser_read(SITES), READ, step=step)
    assert decision.outcome is PermissionOutcome.DENIED
