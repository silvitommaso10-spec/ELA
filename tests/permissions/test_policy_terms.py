"""The declaration a capability makes about the policies of §59 (M13.12, ADR 0062; decisions 1, 2
and 16).

The catalogue refuses a declaration that would admit policies nobody could create, or that would
cover what they should not: on a row that does not ask unless authorized, with nothing to bound,
with a limit that is not a number, with an argument nobody classified.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import CapabilityId, PolicyTerms, RiskLevel
from ela.permissions import (
    BROWSER_GUIDED,
    GUIDED_ROUTE,
    RISK_POLICY,
    UNDECLARED_MODEL,
    CapabilityRegistry,
    InvalidCapabilityError,
    RiskNotAllowedError,
    Rule,
    browser_guided,
    production_catalogue,
)
from ela.routing import DEFAULT_ROUTES, Route, RoutePolicy
from tests.permissions.policy_support import MODEL, SITES, TERMED


def test_browser_guided_declares_its_terms_and_it_is_the_only_one() -> None:
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)
    declared = {spec.id: spec.policy_terms for spec in catalogue.specs() if spec.policy_terms}

    assert declared == {
        BROWSER_GUIDED: PolicyTerms(
            limits=("max_cost_usd", "looks", "seconds"),
            uncovered=("task_type",),
            free=("goal",),
            route=GUIDED_ROUTE,
            model=MODEL,
        )
    }


def test_the_catalogue_built_without_settings_declares_no_model_anybody_runs() -> None:
    guided = production_catalogue().get(BROWSER_GUIDED)
    assert guided.policy_terms is not None
    assert guided.policy_terms.model == UNDECLARED_MODEL


def test_the_levels_did_not_move() -> None:
    """Decision 2: the row of each level is the one of ``155550d``."""
    assert dict(RISK_POLICY) == {
        RiskLevel.SAFE: Rule.ALLOW,
        RiskLevel.LOW: Rule.ALLOW_WITHIN_SCOPE,
        RiskLevel.MEDIUM: Rule.APPROVAL_UNLESS_AUTHORIZED,
        RiskLevel.HIGH: Rule.APPROVAL_EVERY_USE,
        RiskLevel.CRITICAL: Rule.DENY,
    }
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)
    risks = {spec.id: spec.risk for spec in catalogue.specs() if spec.id.startswith("browser.")}
    assert risks == {
        CapabilityId("browser.read"): RiskLevel.LOW,
        CapabilityId("browser.act"): RiskLevel.HIGH,
        CapabilityId("browser.guided"): RiskLevel.MEDIUM,
    }


def refusal(**update: Any) -> str:
    with pytest.raises(InvalidCapabilityError) as caught:
        CapabilityRegistry((TERMED.model_copy(update=update),))
    return caught.value.reason


def terms(**update: Any) -> PolicyTerms:
    assert TERMED.policy_terms is not None
    return TERMED.policy_terms.model_copy(update=update)


def test_a_high_capability_that_declares_terms_is_refused() -> None:
    """The first defence of decision 2, built: a fake HIGH carrying the declaration."""
    assert refusal(risk=RiskLevel.HIGH) == "no policy reaches a HIGH (ADR 0045 §3)"


@pytest.mark.parametrize("risk", [RiskLevel.SAFE, RiskLevel.LOW])
def test_a_capability_that_does_not_ask_cannot_declare_terms(risk: RiskLevel) -> None:
    assert refusal(risk=risk) == "test.termed does not ask: it needs no policy"


def test_a_critical_capability_with_terms_is_refused_by_the_cap_first() -> None:
    with pytest.raises(RiskNotAllowedError):
        CapabilityRegistry((TERMED.model_copy(update={"risk": RiskLevel.CRITICAL}),))


def test_a_declaration_that_bounds_nothing_is_refused() -> None:
    assert "bounds nothing" in refusal(policy_terms=terms(limits=()))


def test_a_declaration_on_a_capability_without_a_scope_is_refused() -> None:
    schema = dict(TERMED.input_schema)
    properties = {k: v for k, v in dict(schema["properties"]).items() if k != "places"}  # type: ignore[call-overload]
    schema["properties"] = properties
    schema["required"] = ["text", "budget", "count"]
    reason = refusal(scope=(), scoped_arguments=(), input_schema=schema)
    assert "scope" in reason


def test_a_scoped_argument_that_is_not_a_list_is_refused() -> None:
    schema = dict(TERMED.input_schema)
    schema["properties"] = {**dict(schema["properties"]), "places": {"type": "string"}}  # type: ignore[call-overload]
    assert "places" in refusal(input_schema=schema)


def test_every_property_of_the_schema_is_in_exactly_one_class() -> None:
    """B1 of the critical re-read: an argument nobody classified would be covered in silence."""
    assert "route" in refusal(policy_terms=terms(uncovered=()))
    assert "text" in refusal(policy_terms=terms(free=("text", "budget")))
    assert "ghost" in refusal(policy_terms=terms(free=("text", "ghost")))
    assert "places" in refusal(policy_terms=terms(free=("text", "places")))


def test_a_limit_must_be_required_and_a_number() -> None:
    schema = dict(TERMED.input_schema)
    schema["required"] = ["text", "places", "count"]
    assert "budget" in refusal(input_schema=schema)
    words = dict(TERMED.input_schema)
    words["properties"] = {**dict(words["properties"]), "budget": {"type": "string"}}  # type: ignore[call-overload]
    assert "budget" in refusal(input_schema=words)


def test_an_uncovered_argument_must_be_optional() -> None:
    schema = dict(TERMED.input_schema)
    schema["required"] = ["text", "places", "budget", "count", "route"]
    assert "route" in refusal(input_schema=schema)


def test_a_free_required_argument_must_be_a_string() -> None:
    schema = dict(TERMED.input_schema)
    schema["properties"] = {**dict(schema["properties"]), "text": {"type": "integer"}}  # type: ignore[call-overload]
    assert "text" in refusal(input_schema=schema)


def test_the_generic_capability_of_the_tests_is_admitted() -> None:
    assert CapabilityRegistry((TERMED,)).get(TERMED.id) == TERMED


def test_browser_guided_with_a_real_model_is_admitted() -> None:
    spec = browser_guided(SITES, model=MODEL)
    assert CapabilityRegistry((spec,)).get(spec.id) == spec


# ----------------------------------------------------------------------------------------
# Decision 16: a policy names one model, and the default route has one provider
# ----------------------------------------------------------------------------------------

ONE_MODEL = (
    "a policy names one model: the default route of {capability} has {count} providers, and the "
    "second could answer with a model no policy named. Whoever adds a provider decides with an ADR "
    "whether to pass to (b) of question 16 of M13.12 — the model as a fact of the call"
)


def routes_with_more_than_one_provider(policy: RoutePolicy) -> list[str]:
    """The capabilities with ``policy_terms`` whose default route has more than one provider."""
    found = []
    for spec in production_catalogue(sites=SITES, guided_model=MODEL).specs():
        if spec.policy_terms is None or spec.policy_terms.route is None:
            continue
        route = policy.route_for(spec.policy_terms.route)
        if len(route.providers) > 1:
            found.append(ONE_MODEL.format(capability=spec.id, count=len(route.providers)))
    return found


def test_the_default_route_of_a_capability_with_terms_has_one_provider() -> None:
    """The form of ADR 0045 §13: an appunto that fails when the world moves."""
    assert routes_with_more_than_one_provider(RoutePolicy(DEFAULT_ROUTES)) == []


def test_a_second_provider_on_the_route_would_be_found() -> None:
    """The negative case: a router with two providers on ``browsing``."""
    two = dict(DEFAULT_ROUTES)
    two[GUIDED_ROUTE] = Route(providers=("anthropic", "another"), profile="cheap")

    found = routes_with_more_than_one_provider(RoutePolicy(two))

    assert found == [ONE_MODEL.format(capability=BROWSER_GUIDED, count=2)]
