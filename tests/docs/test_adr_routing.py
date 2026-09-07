"""The tables of ADR 0022 and ``ela.routing`` say the same thing.

Three tables, three row shapes, so none is mistaken for another: §4 (task type → provider,
profile), §5 (the routing error codes and whether they touch the network) and §8 (the two
variables and their defaults). The tool, verifier, port and capability tables of §2, §5, §9 and
§10 are checked where the other tables of their kind are — ``test_adr_executor.py``,
``test_adr_verification.py``, ``test_adr_ports.py``, ``test_adr_catalogue.py`` — and this module
would be a weaker copy of those.

What is left here is what only ADR 0022 says: the routing table, the codes it introduces, the
variables, the retired one, and the name architecture rule 26 is registered under.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from ela.ports import (
    PROVIDER_UNAVAILABLE,
    ROUTING_EMPTY_ROUTES,
    ROUTING_ERROR_CODES,
    ROUTING_UNKNOWN_PROVIDER,
    ROUTING_UNKNOWN_TASK_TYPE,
    RoutingError,
)
from ela.providers.anthropic.settings import RETIRED_SETTINGS
from ela.routing import DEFAULT_ROUTE, DEFAULT_ROUTES, RoutePolicy, RoutingSettings
from tests.architecture.rules import RULES

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0022-model-router.md"
ROUTE_ROW = re.compile(r"^\| (?:`(\w+)`|\*\(assente\)\*) \| `([\w-]+)` \| `(\w+)` \|$")
CODE_ROW = re.compile(r"^\| `([a-z_]+\.[a-z_]+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
SETTING_ROW = re.compile(r"^\| `(ELA_\w+)` \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
RETIRED_ROW = re.compile(r"^\| `(ELA_\w+)` \| (M[\d.]+) \| ([^|]+) \|$")
WRITTEN_ON = re.compile(r"^- \*\*Tabella scritta il:\*\* (\d{4}-\d{2}-\d{2})")
RULE_NAME = "tools-routing-isolation"
DEFAULT_KEY = None
"""How the §4 table writes the route of a call with no ``task_type``: *(assente)*."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §4 — the routing table
# ----------------------------------------------------------------------------------------


def documented_routes(text: str) -> dict[str | None, tuple[str, str]]:
    """task type (``None`` for the default route) → (provider, profile)."""
    rows = {
        (match.group(1) or DEFAULT_KEY): (match.group(2), match.group(3))
        for line in text.splitlines()
        if (match := ROUTE_ROW.match(line)) is not None
    }
    assert rows, "ADR 0022 §4 must contain the routing table"
    return rows


def coded_routes() -> dict[str | None, tuple[str, str]]:
    rows: dict[str | None, tuple[str, str]] = {
        task_type: (route.providers[0], route.profile)
        for task_type, route in DEFAULT_ROUTES.items()
    }
    rows[DEFAULT_KEY] = (DEFAULT_ROUTE.providers[0], DEFAULT_ROUTE.profile)
    return rows


def test_the_routing_table_matches_the_code() -> None:
    assert documented_routes(adr_text()) == coded_routes()


def test_the_table_is_the_two_lists_of_the_spec() -> None:
    """Four expensive, three cheap, one default: §25 read into a table (ADR 0022 §4)."""
    rows = documented_routes(adr_text())
    assert {t for t, (_, profile) in rows.items() if profile == "quality"} == {
        "planning",
        "coding",
        "reasoning",
        "analysis",
    }
    assert {t for t, (_, profile) in rows.items() if profile == "cheap"} == {
        "classification",
        "extraction",
        "routine",
    }
    assert rows[DEFAULT_KEY][1] == "balanced"


def test_the_reading_of_piccoli_task_is_written_down() -> None:
    """The one place §25 and the table do not line up word for word, argued in the ADR."""
    assert "«piccoli task» è letto come `routine`" in adr_text()
    assert "small_task" not in adr_text()
    assert "small_task" not in DEFAULT_ROUTES


def test_a_drifted_routing_table_is_detected() -> None:
    text = adr_text()
    for before, after in (
        ("| `coding` | `anthropic` | `quality` |", "| `coding` | `anthropic` | `cheap` |"),
        ("| `routine` | `anthropic` | `cheap` |", "| `routine` | `local` | `cheap` |"),
        (
            "| *(assente)* | `anthropic` | `balanced` |",
            "| *(assente)* | `anthropic` | `quality` |",
        ),
    ):
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_routes(drifted) != coded_routes(), before


def test_the_table_says_when_it_was_written() -> None:
    """Like the price list of ADR 0020 §6: an opinion with a date is an opinion somebody can
    revisit. No expiry gate here — a price is a fact about the world that changes without asking,
    a reading of §25 changes only when someone rereads §25."""
    match = next(
        (WRITTEN_ON.match(line) for line in adr_text().splitlines() if WRITTEN_ON.match(line)), None
    )
    assert match is not None, "ADR 0022 §4 must say when the table was written"
    assert date.fromisoformat(match.group(1)) <= date.today()


# ----------------------------------------------------------------------------------------
# §5 — the codes
# ----------------------------------------------------------------------------------------


def documented_codes(text: str) -> dict[str, tuple[str, str, str]]:
    """code → (when, network, where it is born), from the §5 table."""
    rows = {
        match.group(1): (match.group(2), match.group(3), match.group(4))
        for line in text.splitlines()
        if (match := CODE_ROW.match(line)) is not None
    }
    assert rows, "ADR 0022 §5 must contain the codes table"
    return rows


def test_the_codes_table_is_exactly_the_routing_vocabulary() -> None:
    rows = documented_codes(adr_text())
    assert set(rows) == set(ROUTING_ERROR_CODES)
    assert set(rows) == {
        ROUTING_UNKNOWN_TASK_TYPE,
        ROUTING_UNKNOWN_PROVIDER,
        ROUTING_EMPTY_ROUTES,
        PROVIDER_UNAVAILABLE,
    }


def test_no_routing_failure_touches_the_network() -> None:
    """The whole point of reading a declared status (§7): every row says "mai toccata"."""
    rows = documented_codes(adr_text())
    assert all(network.strip() == "mai toccata" for _, network, _ in rows.values())


def test_one_code_is_borrowed_and_three_are_new() -> None:
    """``provider.unavailable`` is ADR 0020's: one wall, one name (ADR 0022 §5)."""
    assert PROVIDER_UNAVAILABLE in ROUTING_ERROR_CODES
    assert "Quattro codici e uno è **preso in prestito**" in adr_text()
    new = {ROUTING_UNKNOWN_TASK_TYPE, ROUTING_UNKNOWN_PROVIDER, ROUTING_EMPTY_ROUTES}
    assert new.isdisjoint({PROVIDER_UNAVAILABLE})
    assert new | {PROVIDER_UNAVAILABLE} == ROUTING_ERROR_CODES


def test_two_codes_are_born_before_a_step_exists() -> None:
    """The two configuration errors of §7 and §8 are caught where the composition root builds
    the policy and the router, not on the step that happens to need them."""
    rows = documented_codes(adr_text())
    assert rows[ROUTING_UNKNOWN_PROVIDER][2].strip() == "costruzione del router"
    assert rows[ROUTING_EMPTY_ROUTES][2].strip() == "costruzione della politica"


def test_an_empty_table_is_refused_and_the_adr_says_where_to_look() -> None:
    """The review of M7.3: replacing the table with one route is legitimate, with nothing is not
    — and the refusal points back at the default table (ADR 0022 §8)."""
    assert "`ELA_MODEL_ROUTES={}` è rifiutata con `routing.empty_routes`" in adr_text()
    with pytest.raises(RoutingError) as raised:
        RoutePolicy({}, DEFAULT_ROUTE)
    assert raised.value.code == ROUTING_EMPTY_ROUTES
    assert "ELA_MODEL_ROUTES" in raised.value.message


def test_an_absent_provider_and_an_unavailable_one_are_not_the_same_code() -> None:
    """The answer to question 3 of the SPEC, in the document and in the vocabulary."""
    assert ROUTING_UNKNOWN_PROVIDER != PROVIDER_UNAVAILABLE
    assert "**Assente è diverso da `UNAVAILABLE`.**" in adr_text()


# ----------------------------------------------------------------------------------------
# §8 — the variables
# ----------------------------------------------------------------------------------------


def documented_settings(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := SETTING_ROW.match(line)) is not None
    }
    assert rows, "ADR 0022 §8 must contain the settings table"
    return rows


def test_the_settings_table_is_the_fields_of_the_settings() -> None:
    rows = documented_settings(adr_text())
    assert set(rows) == {"ELA_MODEL_ROUTES", "ELA_MODEL_DEFAULT_ROUTE"}
    assert set(rows) == {f"ELA_{name.upper()}" for name in RoutingSettings.model_fields}


def test_the_defaults_of_the_table_are_the_defaults_of_the_code() -> None:
    rows = documented_settings(adr_text())
    settings = RoutingSettings(_env_file=None)
    assert "la tabella di §4" in rows["ELA_MODEL_ROUTES"]
    assert settings.model_routes == dict(DEFAULT_ROUTES)
    assert rows["ELA_MODEL_DEFAULT_ROUTE"] == "`anthropic`, `balanced`"
    assert settings.model_default_route == DEFAULT_ROUTE
    assert DEFAULT_ROUTE.providers == ("anthropic",) and DEFAULT_ROUTE.profile == "balanced"


def documented_retirements(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := RETIRED_ROW.match(line)) is not None
    }


def test_the_retired_variable_of_the_adr_is_the_one_the_code_refuses() -> None:
    rows = documented_retirements(adr_text())
    assert set(rows) == set(RETIRED_SETTINGS) == {"ELA_ANTHROPIC_MODEL"}
    for variable, replacement in rows.items():
        for name in re.findall(r"`(ELA_\w+)`", replacement):
            assert name in RETIRED_SETTINGS[variable]


def test_the_migration_is_written_down() -> None:
    """A retired variable with no instructions is a wall; ADR 0022 §8 says what to write."""
    assert "ELA_MODEL_DEFAULT_ROUTE={" in adr_text()
    assert "un bottone morto" in adr_text()


# ----------------------------------------------------------------------------------------
# Rule 26
# ----------------------------------------------------------------------------------------


def test_rule_26_is_registered_under_the_name_the_adr_gives_it() -> None:
    assert f"(`{RULE_NAME}`)" in adr_text()
    assert RULE_NAME in RULES


def test_a_missing_table_is_detected() -> None:
    """The negative case of every reader above: a document without its table fails loudly."""
    for reader in (documented_routes, documented_codes, documented_settings):
        with pytest.raises(AssertionError, match="must contain"):
            reader("# 0022. Un ADR senza tabelle\n")
