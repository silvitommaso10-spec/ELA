"""How ``build`` names the model a policy of ``browser.guided`` is born under (M13.12; decision 16).

The terms of ``browser.guided`` carry the model its default route reads today, and
:func:`~ela.composition.root.default_route_model` is what reads it: from the routing table and the
provider's profiles, without the network and without the key. A route the table does not know, or a
profile no model answers, is ``undeclared`` — no policy is born under it.
"""

from __future__ import annotations

from ela.composition import Ela
from ela.composition.root import default_route_model
from ela.permissions import BROWSER_GUIDED, GUIDED_ROUTE, UNDECLARED_MODEL
from ela.providers.anthropic.models import HAIKU_5_5
from ela.routing import DEFAULT_ROUTES, Route, RoutePolicy


async def test_the_built_catalogue_names_the_model_of_the_default_route(ela: Ela) -> None:
    terms = ela.capabilities.get(BROWSER_GUIDED).policy_terms

    assert terms is not None
    assert terms.route == GUIDED_ROUTE
    assert terms.model == HAIKU_5_5


def test_the_default_table_reads_the_cheap_profile() -> None:
    assert default_route_model(RoutePolicy(), GUIDED_ROUTE) == HAIKU_5_5


def test_a_route_the_table_does_not_know_is_undeclared() -> None:
    without = {name: route for name, route in DEFAULT_ROUTES.items() if name != GUIDED_ROUTE}

    assert default_route_model(RoutePolicy(without), GUIDED_ROUTE) == UNDECLARED_MODEL


def test_a_profile_no_model_answers_is_undeclared() -> None:
    nowhere = {**DEFAULT_ROUTES, GUIDED_ROUTE: Route(providers=("anthropic",), profile="telepathy")}

    assert default_route_model(RoutePolicy(nowhere), GUIDED_ROUTE) == UNDECLARED_MODEL
