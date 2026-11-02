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

import re
from datetime import date, timedelta

import pytest

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
from tests.docs import test_adr_provider as price_list

ACCOUNTS_PATH = price_list.PRICELIST_PATH.with_name("0063-browser-with-your-accounts.md")
DUE = re.compile(r"una persona,? entro il \**(\d{4}-\d{2}-\d{2})")
"""How the two ADRs write the day: «una persona entro il …» in ADR 0061, «una persona, entro il
**…**» in ADR 0063 §6. A dated note that keeps a day gone by says it otherwise."""

NAMED_HERE = "claude-haiku-5-5"
"""The model of the route, **written here and not read from the provider's own constant**: a
model renamed in place would pass a comparison with the constant, and nobody would be told to
read the policy again (the re-read of the round)."""


def due_by(pricelist: str) -> date:
    """The day the price list — and the provider's policy with it — is read again by: the date of
    ADR 0061 §1 plus the days after which the reminder of ``test_adr_provider`` fails, both read
    where they are kept and neither copied here (2026-10-29)."""
    return price_list.documented_price_check(pricelist) + timedelta(
        days=price_list.MAX_PRICE_AGE_DAYS
    )


def reread(due: date) -> str:
    """What the two tests below fail with (M13.9, decision 75), naming the day it is due by."""
    return (
        "the model of the route a guided session runs on is not the one this test names. Whoever "
        "changes it re-reads the provider's policy for that model — how long it keeps what a "
        "session sends, and who may read it — and dates it in ADR 0063 §6; then names the new "
        f"model here. The re-reading goes with the price list's (ADR 0061): a person, by {due}"
    )


REREAD = reread(due_by(price_list.pricelist_text()))
"""The message, with the day derived from the price list as it is: written by hand until
2026-10-29, it said a day the two ADRs kept in their dated notes after a re-reading had moved it."""


def places(pricelist: str, accounts: str) -> dict[str, str]:
    """The three places that name the day: §1 and the consequences of ADR 0061, §6 of ADR 0063."""
    return {
        "ADR 0061 §1": pricelist.split("### 1.", 1)[1].split("### 2.", 1)[0],
        "ADR 0061, «Conseguenze»": pricelist.split("## Conseguenze", 1)[1],
        "ADR 0063 §6": accounts.split("### 6.", 1)[1].split("### 7.", 1)[0],
    }


def due_problem(pricelist: str, accounts: str) -> str | None:
    """Which place does not name the derived day, once and alone, or ``None`` if each does."""
    due = due_by(pricelist).isoformat()
    for where, text in places(pricelist, accounts).items():
        named = DUE.findall(text)
        if named != [due]:
            return f"{where} names {named or 'no day'} for the re-reading, which is due by {due}"
    return None


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
    re-reading goes with the price list's, and the day both are due by — which the two ADRs name
    too. The day is derived from the date of the price list (2026-10-29): written by hand here and
    looked for in the ADRs, it stayed true after a re-reading, because the dated notes keep it."""
    pricelist = price_list.pricelist_text()
    accounts = ACCOUNTS_PATH.read_text(encoding="utf-8")

    assert "ADR 0063 §6" in REREAD and "ADR 0061" in REREAD
    assert "provider's policy" in REREAD
    assert REREAD.endswith(f"by {due_by(pricelist)}")
    assert due_problem(pricelist, accounts) is None


def test_a_day_the_adrs_do_not_derive_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """The negative case, with a price list checked on a day of its own: the day moves with that
    date and with the days of the reminder, and a place that names the day before, or none, or
    two, is found."""
    pricelist = (
        "### 1. Il listino\n- **Listino verificato il:** 2027-01-01 (fonte: un'altra)\n"
        "lo rilegge una persona entro il 2027-01-31.\n### 2. La fascia\n"
        "## Conseguenze\n- lo rilegge una persona entro il 2027-01-31.\n"
    )
    accounts = "### 6. La sessione\nuna persona, entro il **2027-01-31**.\n### 7. Il resto\n"

    assert due_by(pricelist) == date(2027, 1, 31)
    assert reread(due_by(pricelist)).endswith("a person, by 2027-01-31")
    assert due_problem(pricelist, accounts) is None

    in_section_1 = pricelist.replace("2027-01-31.\n### 2.", "2026-11-07.\n### 2.")
    assert (due_problem(in_section_1, accounts) or "").startswith(
        "ADR 0061 §1 names ['2026-11-07']"
    )
    consequences = "## Conseguenze\n- lo rilegge una persona entro il "
    in_the_consequences = pricelist.replace(
        f"{consequences}2027-01-31", f"{consequences}2026-11-07"
    )
    assert (due_problem(in_the_consequences, accounts) or "").startswith(
        "ADR 0061, «Conseguenze» names ['2026-11-07']"
    )
    gone_by = accounts.replace("2027-01-31", "2026-11-07")
    assert (due_problem(pricelist, gone_by) or "").startswith("ADR 0063 §6 names ['2026-11-07']")
    none = accounts.replace(", entro il **2027-01-31**", "")
    assert (due_problem(pricelist, none) or "").startswith("ADR 0063 §6 names no day")
    two = accounts.replace("**.\n", "**, una persona, entro il **2027-01-31**.\n")
    assert (due_problem(pricelist, two) or "").startswith("ADR 0063 §6 names ['2027-01-31', '2027")

    monkeypatch.setattr(price_list, "MAX_PRICE_AGE_DAYS", 10)
    assert due_by(pricelist) == date(2027, 1, 11)
    assert (due_problem(pricelist, accounts) or "").startswith("ADR 0061 §1 names ['2027-01-31']")


def test_a_route_the_table_does_not_know_is_undeclared() -> None:
    without = {name: route for name, route in DEFAULT_ROUTES.items() if name != GUIDED_ROUTE}

    assert default_route_model(RoutePolicy(without), GUIDED_ROUTE) == UNDECLARED_MODEL


def test_a_profile_no_model_answers_is_undeclared() -> None:
    nowhere = {**DEFAULT_ROUTES, GUIDED_ROUTE: Route(providers=("anthropic",), profile="telepathy")}

    assert default_route_model(RoutePolicy(nowhere), GUIDED_ROUTE) == UNDECLARED_MODEL
