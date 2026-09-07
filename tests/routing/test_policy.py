"""``RoutePolicy`` and the default table (spec §25; ADR 0022 §4, §6).

The table is the opinion of §25 written down, so the tests read like the spec: the four expensive
kinds of task, the three cheap ones, and what happens to everything else.
"""

from __future__ import annotations

import pytest

from ela.ports import ROUTING_UNKNOWN_TASK_TYPE, RoutingError
from ela.providers.anthropic.models import PROFILES
from ela.providers.anthropic.provider import PROVIDER_NAME
from ela.routing import BALANCED, CHEAP, DEFAULT_ROUTE, DEFAULT_ROUTES, QUALITY, Route, RoutePolicy

QUALITY_TASKS = ("planning", "coding", "reasoning", "analysis")
CHEAP_TASKS = ("classification", "extraction", "routine")


@pytest.fixture
def policy() -> RoutePolicy:
    return RoutePolicy()


@pytest.mark.parametrize("task_type", QUALITY_TASKS)
def test_the_expensive_list_of_the_spec(policy: RoutePolicy, task_type: str) -> None:
    """§25: «un modello molto potente può essere utilizzato per: pianificazione complessa;
    coding difficile; reasoning; analisi»."""
    assert policy.route_for(task_type).profile == QUALITY


@pytest.mark.parametrize("task_type", CHEAP_TASKS)
def test_the_cheap_list_of_the_spec(policy: RoutePolicy, task_type: str) -> None:
    """§25: «un modello più economico: classificazione; estrazione; piccoli task; routine».
    "Piccoli task" is ``routine``: a size is not a kind of task (ADR 0022 §4)."""
    assert policy.route_for(task_type).profile == CHEAP


def test_the_table_is_exactly_the_seven_task_types(policy: RoutePolicy) -> None:
    assert policy.task_types() == tuple(sorted(QUALITY_TASKS + CHEAP_TASKS))


def test_no_task_type_is_the_default_route(policy: RoutePolicy) -> None:
    """Not a safety net for a wrong type (§6): the route of whoever declares no type at all."""
    assert policy.route_for(None) is policy.default
    assert policy.default.profile == BALANCED


@pytest.mark.parametrize("task_type", ["telepathy", "", "Coding", "coding "])
def test_a_task_type_outside_the_table_is_refused(policy: RoutePolicy, task_type: str) -> None:
    """The vocabulary is closed, and closed means exactly: an empty string is not "no type",
    and a type that differs by a capital letter is another type."""
    with pytest.raises(RoutingError) as raised:
        policy.route_for(task_type)

    assert raised.value.code == ROUTING_UNKNOWN_TASK_TYPE
    assert "coding" in raised.value.message  # says what it does know


def test_every_profile_of_the_table_is_one_the_adapter_can_translate() -> None:
    """The Core names profiles and the adapter translates them (ADR 0020 §5). A table naming a
    profile no provider knows would fail every call it routed — before the network, but every
    time. The two vocabularies meet here, in a test, and nowhere in the code."""
    profiles = {route.profile for route in DEFAULT_ROUTES.values()} | {DEFAULT_ROUTE.profile}
    assert profiles <= set(PROFILES)


def test_the_table_names_the_provider_ela_actually_registers() -> None:
    """``ela.routing`` may not import ``ela.providers`` (contract 4), so the name in the table is
    a string. Here — in a test, where both sides are importable — the string is checked against
    the name the adapter registers under."""
    assert {name for route in DEFAULT_ROUTES.values() for name in route.providers} == {
        PROVIDER_NAME
    }
    assert DEFAULT_ROUTE.providers == (PROVIDER_NAME,)


def test_a_policy_reports_every_provider_it_names() -> None:
    """What the router checks at construction (ADR 0022 §7): the default route counts too."""
    policy = RoutePolicy(
        {"coding": Route(providers=("a", "b"), profile=QUALITY)},
        Route(providers=("c",), profile=BALANCED),
    )
    assert policy.provider_names() == ("a", "b", "c")


def test_the_table_of_a_policy_is_a_copy(policy: RoutePolicy) -> None:
    """A policy built from a mapping somebody else holds must not change when they change it:
    the routing of a running ELA is decided when the policy is built."""
    routes = dict(DEFAULT_ROUTES)
    built = RoutePolicy(routes, DEFAULT_ROUTE)
    routes["telepathy"] = Route(providers=("nobody",), profile=CHEAP)

    with pytest.raises(RoutingError):
        built.route_for("telepathy")


@pytest.mark.parametrize(
    ("providers", "profile"),
    [
        ((), QUALITY),
        (("a", "a"), QUALITY),
        (("a", ""), QUALITY),
        (("a", "   "), QUALITY),
        (("a",), ""),
        (("a",), "  "),
    ],
    ids=["empty", "repeated", "blank", "spaces", "no-profile", "blank-profile"],
)
def test_a_route_that_says_nothing_is_refused(providers: tuple[str, ...], profile: str) -> None:
    """A route with no provider routes nowhere, a repeated provider asks the same question twice
    (the status does not change in between), and a route with no profile is a choice not taken."""
    with pytest.raises(ValueError, match="route"):
        Route(providers=providers, profile=profile)


def test_a_route_is_frozen() -> None:
    route = Route(providers=("a",), profile=QUALITY)
    with pytest.raises(ValueError, match="frozen"):
        route.profile = CHEAP  # type: ignore[misc]
