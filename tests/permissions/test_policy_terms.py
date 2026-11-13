"""The declaration a capability makes about the policies of §59 (M13.12, ADR 0062; decisions 1, 2
and 16).

The catalogue refuses a declaration that would admit policies nobody could create, or that would
cover what they should not: on a capability that launches a program, on a row that does not ask or
that denies, with a limit that is not a number, with an argument nobody classified, on a ``HIGH``
without the words of its preview. Since M13.14 (ADR 0068) a declaration with no limit is admitted,
and so is a scoped argument that is one value: the three rows of ADR 0062 §1 revised.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ela.domain import CapabilityId, PolicyTerms, PolicyWords, RiskLevel
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_GUIDED,
    BROWSER_GUIDED_AS_YOU,
    FS_WRITE,
    GUIDED_ROUTE,
    RISK_POLICY,
    UNDECLARED_MODEL,
    CapabilityRegistry,
    InvalidCapabilityError,
    RiskNotAllowedError,
    Rule,
    browser_guided,
    production_catalogue,
    row_of,
)
from ela.routing import DEFAULT_ROUTES, Route, RoutePolicy
from tests.permissions.policy_support import MODEL, SITES, TERMED

GESTURE_TERMS = PolicyTerms(
    limits=(), free=("path", "fill", "click", "expect_text", "purpose", "continues")
)
"""The terms of a gesture, as proposal 3 of the SPEC of M13.14 writes them."""


def test_the_capabilities_that_declare_terms_are_these_and_no_other() -> None:
    """``browser.guided`` since M13.12, and ``browser.guided_as_you`` since M13.9 with the same
    limits — the limits are a session's, whatever browser it guides —, byte for byte as before.
    Since M13.14 (ADR 0068) ``fs.write``, ``browser.act`` and ``browser.act_as_you``, with the terms
    and the words of proposal 3. No single read, no login, no file from the browser and no
    terminal declares any."""
    catalogue = production_catalogue(sites=SITES, guided_model=MODEL)
    declared = {spec.id: spec.policy_terms for spec in catalogue.specs() if spec.policy_terms}
    words = {spec.id: spec.policy_words for spec in catalogue.specs() if spec.policy_words}

    assert set(declared) == {
        BROWSER_GUIDED,
        BROWSER_GUIDED_AS_YOU,
        FS_WRITE,
        BROWSER_ACT,
        BROWSER_ACT_AS_YOU,
    }
    assert set(words) == {FS_WRITE, BROWSER_ACT, BROWSER_ACT_AS_YOU}
    assert declared[FS_WRITE] == PolicyTerms(
        limits=(), free=("body", "overwrite", "purpose"), on_the_core=True
    )
    assert declared[BROWSER_ACT] == declared[BROWSER_ACT_AS_YOU] == GESTURE_TERMS
    assert words == {
        FS_WRITE: PolicyWords(
            does="writes and overwrites any file in these folders, on the Core",
            goes=(
                "what it writes goes into these folders, and wherever your system copies them; "
                "a file written there may be one your system runs"
            ),
        ),
        BROWSER_ACT: PolicyWords(
            does="makes any submission on these sites, in ELA's own empty browser",
            goes="what it sends goes to these sites, and is not taken back",
        ),
        BROWSER_ACT_AS_YOU: PolicyWords(
            does=(
                "makes any submission on these sites as you, in the browser that keeps your "
                "accounts"
            ),
            goes="what it sends goes to these sites in your name, and is not taken back",
        ),
    }
    assert declared[BROWSER_GUIDED_AS_YOU] == declared[BROWSER_GUIDED]
    assert {BROWSER_GUIDED: declared[BROWSER_GUIDED]} == {
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
        CapabilityId("browser.read_as_you"): RiskLevel.MEDIUM,
        CapabilityId("browser.act_as_you"): RiskLevel.HIGH,
        CapabilityId("browser.login"): RiskLevel.HIGH,
        CapabilityId("browser.guided_as_you"): RiskLevel.MEDIUM,
        # The files from the browser (M13.13, ADR 0066): four rows more, all ``HIGH`` — no row
        # of before moved.
        CapabilityId("browser.download"): RiskLevel.HIGH,
        CapabilityId("browser.download_as_you"): RiskLevel.HIGH,
        CapabilityId("browser.upload"): RiskLevel.HIGH,
        CapabilityId("browser.upload_as_you"): RiskLevel.HIGH,
    }


def refusal(**update: Any) -> str:
    with pytest.raises(InvalidCapabilityError) as caught:
        CapabilityRegistry((TERMED.model_copy(update=update),))
    return caught.value.reason


def terms(**update: Any) -> PolicyTerms:
    assert TERMED.policy_terms is not None
    return TERMED.policy_terms.model_copy(update=update)


WORDS = PolicyWords(does="does something of the tests", goes="nowhere")


def test_a_capability_that_launches_a_program_cannot_declare_terms() -> None:
    """The first defence of decision 2, aimed at what stays out (M13.14, ADR 0068; decision 5): a
    ``HIGH`` of :data:`LAUNCHES_A_PROGRAM` carrying a whole declaration, words included."""
    reason = refusal(id=CapabilityId("terminal.run"), risk=RiskLevel.HIGH, policy_words=WORDS)

    assert reason == (
        "terminal.run launches a program the plan chooses: a program can read the Core's token "
        "and create a policy, and only you create one"
    )


def test_a_high_capability_that_declares_terms_reads_its_own_row() -> None:
    """The first defence of decision 2, revised openly (ADR 0068): a ``HIGH`` that declares terms
    and its words is admitted, and its row is «approval unless policy» — its level does not
    move."""
    spec = TERMED.model_copy(update={"risk": RiskLevel.HIGH, "policy_words": WORDS})

    admitted = CapabilityRegistry((spec,)).get(spec.id)

    assert admitted.risk is RiskLevel.HIGH
    assert row_of(admitted) is Rule.APPROVAL_UNLESS_POLICY


def test_a_high_capability_with_terms_and_no_words_is_refused() -> None:
    """A preview that does not say what ELA will do without asking is not shown (proposal 13)."""
    assert refusal(risk=RiskLevel.HIGH) == (
        "a HIGH that declares policy terms says what it does and where it goes: policy_words"
    )


def test_words_without_terms_are_refused() -> None:
    """Words describe a policy: without terms nobody can create one."""
    assert refusal(policy_terms=None, policy_words=WORDS) == (
        "policy words without policy terms describe a policy nobody can create"
    )


@pytest.mark.parametrize("risk", [RiskLevel.SAFE, RiskLevel.LOW])
def test_a_capability_that_does_not_ask_cannot_declare_terms(risk: RiskLevel) -> None:
    assert refusal(risk=risk) == "test.termed does not ask: it needs no policy"


def test_a_critical_capability_with_terms_is_refused_by_the_cap_first() -> None:
    with pytest.raises(RiskNotAllowedError):
        CapabilityRegistry((TERMED.model_copy(update={"risk": RiskLevel.CRITICAL}),))


def test_a_declaration_that_bounds_nothing_is_admitted() -> None:
    """The row «non ha tetti» of ADR 0062 §1, removed (M13.14, ADR 0068; decision 8): what bounds
    a policy is its scope, its end, and its uses if the user sets them."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {
        name: value
        for name, value in dict(schema["properties"]).items()  # type: ignore[call-overload]
        if name not in ("budget", "count")
    }
    schema["required"] = ["text", "places"]
    spec = TERMED.model_copy(update={"input_schema": schema, "policy_terms": terms(limits=())})

    assert CapabilityRegistry((spec,)).get(spec.id) == spec


def test_a_declaration_on_a_capability_without_a_scope_is_refused() -> None:
    schema = dict(TERMED.input_schema)
    properties = {k: v for k, v in dict(schema["properties"]).items() if k != "places"}  # type: ignore[call-overload]
    schema["properties"] = properties
    schema["required"] = ["text", "budget", "count"]
    reason = refusal(scope=(), scoped_arguments=(), input_schema=schema)
    assert "scope" in reason


def test_a_scoped_argument_that_is_one_value_is_admitted() -> None:
    """The second half of the row of ADR 0062 §1, removed (M13.14, ADR 0068): a scoped argument
    that is one value is a target per call, and the «partirebbe» of its policy asks the tool place
    by place."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {**dict(schema["properties"]), "places": {"type": "string"}}  # type: ignore[call-overload]
    spec = TERMED.model_copy(update={"input_schema": schema})

    assert CapabilityRegistry((spec,)).get(spec.id) == spec


def test_scoped_arguments_some_lists_and_some_one_value_are_refused() -> None:
    """The «partirebbe» is one call for lists and a question per place for one value: a capability
    that were both would have neither."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {**dict(schema["properties"]), "other": {"type": "string"}}  # type: ignore[call-overload]

    reason = refusal(input_schema=schema, scoped_arguments=("places", "other"))

    assert reason == (
        "the scoped arguments of a capability with policy terms are all lists or all one value"
    )


def test_every_property_of_the_schema_is_in_exactly_one_class() -> None:
    """B1 of the critical re-read: an argument nobody classified would be covered in silence."""
    assert "route" in refusal(policy_terms=terms(uncovered=()))
    assert "budget" in refusal(policy_terms=terms(free=("text", "budget")))
    assert "ghost" in refusal(policy_terms=terms(free=("text", "ghost")))
    assert "places" in refusal(policy_terms=terms(free=("text", "places")))


def test_a_limit_must_be_required_and_a_number() -> None:
    schema = dict(TERMED.input_schema)
    schema["required"] = ["text", "places", "count"]
    assert "budget" in refusal(input_schema=schema)
    words = dict(TERMED.input_schema)
    words["properties"] = {**dict(words["properties"]), "budget": {"type": "string"}}  # type: ignore[call-overload]
    assert "budget" in refusal(input_schema=words)


def test_an_integer_limit_must_have_its_minimum_and_maximum() -> None:
    """Decision 25: the form of a policy shows the range of an integer limit, and the catalogue
    refuses one without it — built with a capability whose ``count`` has no ``maximum``."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {
        **dict(schema["properties"]),
        "count": {"type": "integer", "minimum": 1},
    }  # type: ignore[call-overload]
    assert "the integer limit 'count' has no minimum and maximum" in refusal(input_schema=schema)
    unbounded = dict(TERMED.input_schema)
    unbounded["properties"] = {**dict(unbounded["properties"]), "count": {"type": "integer"}}  # type: ignore[call-overload]
    assert "'count'" in refusal(input_schema=unbounded)


def test_the_integer_limits_of_browser_guided_have_their_range() -> None:
    properties = browser_guided(SITES, model=MODEL).input_schema["properties"]
    assert isinstance(properties, Mapping)
    for name in ("looks", "seconds"):
        declared = properties[name]
        assert declared["type"] == "integer", name
        assert {"minimum", "maximum"} <= set(declared), name


def test_an_uncovered_argument_must_be_optional() -> None:
    schema = dict(TERMED.input_schema)
    schema["required"] = ["text", "places", "budget", "count", "route"]
    assert "route" in refusal(input_schema=schema)


def test_a_free_required_argument_must_be_a_string() -> None:
    """For a capability whose scope is a list, whose prospect is a call built with ELA's sentence
    in every required free argument."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {**dict(schema["properties"]), "text": {"type": "integer"}}  # type: ignore[call-overload]
    assert refusal(input_schema=schema) == "the free argument 'text' is required and not a string"


def test_a_free_required_argument_need_not_be_a_string_for_a_scope_of_one_value() -> None:
    """The row of ADR 0062 §1 on free arguments holds only where a call is built (M13.14, ADR
    0068): ``fill`` (an array) and ``overwrite`` (a boolean) are free for the gestures and the
    writes, which are asked about place by place."""
    schema = dict(TERMED.input_schema)
    schema["properties"] = {
        **dict(schema["properties"]),  # type: ignore[call-overload]
        "text": {"type": "integer"},
        "places": {"type": "string"},
    }
    spec = TERMED.model_copy(update={"input_schema": schema})

    assert CapabilityRegistry((spec,)).get(spec.id) == spec


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

    assert found == [
        ONE_MODEL.format(capability=BROWSER_GUIDED, count=2),
        ONE_MODEL.format(capability=BROWSER_GUIDED_AS_YOU, count=2),
    ]
