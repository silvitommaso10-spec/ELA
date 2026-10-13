"""How ``build`` names the model a policy of ``browser.guided`` is born under (M13.12; decision 16).

The terms of ``browser.guided`` carry the model its default route reads today, and
:func:`~ela.composition.root.default_route_model` is what reads it: from the routing table and the
provider's profiles, without the network and without the key. A route the table does not know, or a
profile no model answers, is ``undeclared`` — no policy is born under it.

**Whoever changes the model of that route re-reads the provider's policy** (M13.9, decision 75):
what a session with the user's accounts sends is the user's own content, and how long the
provider keeps it — and who may read it — is said per model, on a page that changes. No list of
those models is written in ELA; the two tests that hold the model fail with the sentence that
says what to do.
"""

from __future__ import annotations

from ela.composition import Ela
from ela.composition.root import default_route_model
from ela.permissions import (
    BROWSER_GUIDED,
    BROWSER_GUIDED_AS_YOU,
    GUIDED_ROUTE,
    UNDECLARED_MODEL,
)
from ela.providers.anthropic.models import HAIKU_5_5
from ela.routing import DEFAULT_ROUTES, Route, RoutePolicy

NAMED_HERE = "claude-haiku-5-5"
"""The model of the route, **written here and not read from the provider's own constant**: a
model renamed in place would pass a comparison with the constant, and nobody would be told to
read the policy again (the re-read of the round)."""

REREAD = (
    "the model of the route a guided session runs on is not the one this test names. Whoever "
    "changes it re-reads the provider's policy for that model — how long it keeps what a "
    "session sends, and who may read it — and dates it in ADR 0063 §6; then names the new model "
    "here. The re-reading goes with the price list's (ADR 0061): a person, by 2026-11-07"
)
"""What the two tests below fail with (M13.9, decision 75)."""


async def test_the_built_catalogue_names_the_model_of_the_default_route(ela: Ela) -> None:
    for capability in (BROWSER_GUIDED, BROWSER_GUIDED_AS_YOU):
        terms = ela.capabilities.get(capability).policy_terms

        assert terms is not None
        assert terms.route == GUIDED_ROUTE
        assert terms.model == HAIKU_5_5 == NAMED_HERE, REREAD


def test_the_default_table_reads_the_cheap_profile() -> None:
    assert default_route_model(RoutePolicy(), GUIDED_ROUTE) == NAMED_HERE, REREAD


def test_the_sentence_says_where_the_policy_is_dated_and_by_when_it_is_read_again() -> None:
    """The message is the instruction: the ADR where the provider's policy is dated, that the
    re-reading goes with the price list's, and the date both are due — which the two ADRs name
    too."""
    from pathlib import Path

    adrs = Path(__file__).resolve().parents[2] / "docs" / "adr"
    accounts = (adrs / "0063-browser-with-your-accounts.md").read_text(encoding="utf-8")
    prices = (adrs / "0061-haiku-5-5.md").read_text(encoding="utf-8")

    assert "ADR 0063 §6" in REREAD and "ADR 0061" in REREAD and "2026-11-07" in REREAD
    assert "provider's policy" in REREAD
    assert (
        "2026-11-07" in prices and "2026-11-07" in accounts.split("### 6.", 1)[1].split("### 7.")[0]
    )


def test_a_route_the_table_does_not_know_is_undeclared() -> None:
    without = {name: route for name, route in DEFAULT_ROUTES.items() if name != GUIDED_ROUTE}

    assert default_route_model(RoutePolicy(without), GUIDED_ROUTE) == UNDECLARED_MODEL


def test_a_profile_no_model_answers_is_undeclared() -> None:
    nowhere = {**DEFAULT_ROUTES, GUIDED_ROUTE: Route(providers=("anthropic",), profile="telepathy")}

    assert default_route_model(RoutePolicy(nowhere), GUIDED_ROUTE) == UNDECLARED_MODEL
