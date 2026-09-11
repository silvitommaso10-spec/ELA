"""The tables of ADR 0023 — and what ADR 0024 and ADR 0025 add to them — say what the code says.

Three tables, three shapes: §3 (the variables), §6 (the routes) and §10 (which exception becomes
which status). Plus the name architecture rule 27 is registered under.

An ADR is immutable, so the two routes and the one failure that M8.2 added are repeated in
ADR 0024, and the route and the two variables that M8.3 added are repeated in ADR 0025, each
under its own label ("Rotte aggiunte", "Errori aggiunti", "Variabili aggiunte") in the same row
shapes; the tests below read all three documents, and what the application serves is the union.

What is *not* here is checked where the other tables of its kind are: the ports in
``test_adr_ports.py``, the capabilities in ``test_adr_catalogue.py``, the commands and the exit
codes of the CLI in ``test_adr_cli.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.api.app import FAILURES
from ela.api.tasks import PLAN_IS_TEMPORARY
from ela.composition.settings import ApiSettings, CoreSettings
from ela.tombstones import (
    RETIRED_SETTINGS,
)
from tests.api.routers import api_routers, routes_of
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0023-composition-root-and-api.md"
CLI_ADR_PATH = ADR_DIR / "0024-cli.md"
DEBTS_ADR_PATH = ADR_DIR / "0025-phase-8-debts.md"
PERCEPTION_ADR_PATH = ADR_DIR / "0028-perception-core.md"
CONTEXT_ADR_PATH = ADR_DIR / "0032-context-core.md"
VOICE_ADR_PATH = ADR_DIR / "0034-voice-online.md"
SETTING_ROW = re.compile(r"^\| `(ELA_\w+)` \| `([^`]+)` \| (?:`([^`]+)`|\*\(([^)]+)\)\*) \|")
ROUTE_ROW = re.compile(r"^\| `(GET|POST)` \| `(/[\w{}/]*)` \| ([^|]+) \|$")
NODE_ROUTE_ROW = re.compile(r"^\| `(GET|POST|PUT)` \| `(/[\w{}/]*)` \| ([^|]+) \| ([^|]+) \|$")
"""ADR 0037 §4: the five routes of the nodes, with the identity that may call each."""
ERROR_ROW = re.compile(r"^\| ([^|]+) \| (?:`(\w+)`|\*\(([^)]+)\)\*) \| `(\d{3})` \|$")
RULE_NAME = "concretes-named-only-by-the-composition-root"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def cli_adr_text() -> str:
    """ADR 0024, read whole: its added rows keep the shapes of the tables they extend."""
    return CLI_ADR_PATH.read_text(encoding="utf-8")


def debts_adr_text() -> str:
    """ADR 0025, read the same way: one route added, two variables added (§10 of that ADR)."""
    return DEBTS_ADR_PATH.read_text(encoding="utf-8")


def perception_adr_text() -> str:
    """ADR 0028, read the same way: one route added (§12)."""
    return PERCEPTION_ADR_PATH.read_text(encoding="utf-8")


def context_adr_text() -> str:
    """ADR 0032, read the same way: one route added (§13)."""
    return CONTEXT_ADR_PATH.read_text(encoding="utf-8")


def voice_adr_text() -> str:
    """ADR 0034, read the same way: three routes added (§9)."""
    return VOICE_ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §3 — the seven variables
# ----------------------------------------------------------------------------------------


def documented_settings(text: str) -> dict[str, str | None]:
    """variable → its documented default, ``None`` where the ADR says it is required."""
    rows = {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := SETTING_ROW.match(line)) is not None
    }
    assert rows, "ADR 0023 §3 must contain the table of the new variables"
    return rows


def coded_settings() -> dict[str, str | None]:
    fields = {**ApiSettings.model_fields, **CoreSettings.model_fields}
    return {
        f"ELA_{name.upper()}": None if field.default is None else str(field.default)
        for name, field in fields.items()
    }


def test_the_nine_variables_are_the_ones_the_settings_declare() -> None:
    """Every variable of the two tables is declared, with its default — except a retired one,
    which stays declared as a tombstone with no default (``ELA_USER_NAME``, ADR 0037 §15)."""
    documented = (
        documented_settings(adr_text())
        | documented_settings(debts_adr_text())
        | documented_settings(nodes_adr_text())
        | documented_settings(work_adr_text())
    )
    coded = coded_settings()

    assert documented.keys() == coded.keys()
    for variable, default in documented.items():
        assert coded[variable] == (None if variable in RETIRED_SETTINGS else default), variable


def test_the_two_variables_of_m8_3_are_the_ones_adr_0025_adds() -> None:
    """Added, never replacing: the seven of ADR 0023 §3 keep their rows there."""
    added = documented_settings(debts_adr_text())

    assert set(added) == {"ELA_DECISION_TTL_SECONDS", "ELA_NOTES_SCOPE"}
    assert not set(added) & set(documented_settings(adr_text()))


def test_every_ttl_in_the_tables_names_its_ceiling() -> None:
    """No TTL without a ceiling (ADR 0012, ADR 0013, ADR 0025 §6): the constraint column says so.

    Three now: a grant, a request for consent, and a decision. The rule is the reason the test
    reads both documents instead of counting the rows of one — a fourth TTL added to a third ADR
    without a ``MAX_`` beside it is what this must catch."""
    rows = [
        line
        for text in (adr_text(), debts_adr_text())
        for line in text.splitlines()
        if SETTING_ROW.match(line)
    ]
    ttls = [row for row in rows if "TTL_SECONDS" in row]

    assert len(ttls) == 3
    assert all("MAX_" in row for row in ttls)


# ----------------------------------------------------------------------------------------
# §6 — the routes: twelve here, two more in ADR 0024 §5
# ----------------------------------------------------------------------------------------


def documented_routes(text: str) -> set[tuple[str, str]]:
    rows = {
        (match.group(1), match.group(2))
        for line in text.splitlines()
        if (match := ROUTE_ROW.match(line)) is not None
    }
    assert rows, "ADR 0023 §6 must contain the table of the routes"
    return rows


def coded_routes() -> set[tuple[str, str]]:
    """Every route of every router module of ``ela.api``, **found** and not listed (M12.1).

    This used to walk a tuple of nine imported routers, so a tenth module would have been
    invisible both to the count below and to the comparison with the ADRs — green, and false.
    """
    return routes_of(api_routers().values())


def nodes_adr_text() -> str:
    """ADR 0037, which adds the routes of the nodes in a table with one more column."""
    return ADR_PATH.with_name("0037-node-identity.md").read_text(encoding="utf-8")


def work_adr_text() -> str:
    """ADR 0038, which adds the variables of the assignments, and later the routes of the work."""
    return ADR_PATH.with_name("0038-work-protocol.md").read_text(encoding="utf-8")


def documented_node_routes(text: str | None = None) -> set[tuple[str, str]]:
    """The routes of a node, from the ADR that documents them — ADR 0037 §4 by default.

    ADR 0038 §11 adds the three of the work in the same four-column shape, and the two are read in
    union: ADR 0037 is immutable, so a route added later lives in the ADR that added it.
    """
    rows = {
        (match.group(1), match.group(2))
        for line in (nodes_adr_text() if text is None else text).splitlines()
        if (match := NODE_ROUTE_ROW.match(line)) is not None
    }
    assert rows, "the ADR must contain the table of the routes of the nodes"
    return rows


def test_the_routes_of_the_adrs_are_the_routes_of_the_code() -> None:
    documented = (
        documented_node_routes()
        | documented_node_routes(work_adr_text())
        | (
            documented_routes(adr_text())
            | documented_routes(cli_adr_text())
            | documented_routes(debts_adr_text())
            | documented_routes(perception_adr_text())
            | documented_routes(context_adr_text())
            | documented_routes(voice_adr_text())
        )
    )
    assert documented == coded_routes()


def test_the_route_of_m8_3_is_the_one_adr_0025_adds() -> None:
    """The one route that returns what a tool produced (ADR 0025 §4)."""
    added = documented_routes(debts_adr_text())

    assert added == {("GET", "/tasks/{task_id}/results")}
    assert not added & (documented_routes(adr_text()) | documented_routes(cli_adr_text()))


def test_the_two_routes_of_m8_2_are_the_ones_adr_0024_adds() -> None:
    """Added, never replacing: what ADR 0023 documented is still served, unchanged."""
    added = documented_routes(cli_adr_text())

    assert added == {("GET", "/devices"), ("GET", "/audit/verify")}
    assert not added & documented_routes(adr_text())


def test_there_are_twenty_eight_of_them() -> None:
    """Twenty until ADR 0037 §4 added five, and twenty-five until ADR 0038 §11 added the three of
    the work; ``tests/api/test_security.py`` proves that every one of them is behind the
    middleware, and which identity reaches which."""
    assert len(coded_routes()) == 28


def test_the_three_routes_of_the_work_are_the_ones_adr_0038_adds() -> None:
    """Added, never replacing: the five of ADR 0037 §4 keep their rows there, and a node's routes
    go from two to five (M12.2, I8)."""
    added = documented_node_routes(work_adr_text())

    assert added == {
        ("POST", "/nodes/work"),
        ("POST", "/nodes/work/result"),
        ("POST", "/nodes/work/renew"),
    }
    assert not added & documented_node_routes()


# ----------------------------------------------------------------------------------------
# §10 — which exception becomes which status
# ----------------------------------------------------------------------------------------


def documented_errors(text: str) -> dict[str, int]:
    rows = {
        match.group(2): int(match.group(4))
        for line in text.splitlines()
        if (match := ERROR_ROW.match(line)) is not None and match.group(2) is not None
    }
    assert rows, "ADR 0023 §10 must contain the table of the failures"
    return rows


def test_the_error_table_is_the_one_the_application_installs() -> None:
    assert (
        documented_errors(adr_text())
        | documented_errors(cli_adr_text())
        | documented_errors(nodes_adr_text())
        | documented_errors(work_adr_text())
    ) == {failure.exception.__name__: failure.status for failure in FAILURES}


def test_the_failure_m8_2_adds_is_the_one_adr_0024_documents() -> None:
    assert documented_errors(cli_adr_text()) == {"AuditChainError": 409}


def test_the_failures_of_the_work_are_the_ones_adr_0038_documents() -> None:
    """Added, never replacing (M12.2, ADR 0038 §12): the statuses of the way of the work, and the
    two ``404`` that must also share their *sentence* — which ``tests/api/test_failures.py`` holds,
    because a table cannot say what a body says."""
    added = documented_errors(work_adr_text())

    assert added == {
        "AssignmentExpiredError": 410,
        "AssignmentVoidError": 410,
        "WorkNotYoursError": 404,
        "AssignmentNotUsableError": 404,
        "AssignmentAtCapError": 409,
        "DeliveryConflictError": 409,
        "AssignmentRefusedError": 409,
    }
    assert not set(added) & set(documented_errors(adr_text()))


def test_the_token_row_belongs_to_no_exception() -> None:
    """A 401 comes from the middleware, before any route and any handler (ADR 0023 §7)."""
    rows = [line for line in adr_text().splitlines() if (m := ERROR_ROW.match(line)) and m.group(3)]

    assert len(rows) == 1
    assert "401" in rows[0]


@pytest.mark.parametrize("failure", FAILURES, ids=lambda failure: failure.exception.__name__)
def test_every_failure_has_a_code_to_branch_on(failure: object) -> None:
    code = failure.code
    assert code and code.islower() and " " not in code


def test_the_table_reads_from_the_most_specific_to_the_least() -> None:
    """Which handler runs is decided by walking the exception's ancestry, so the most derived
    registered class wins whatever the order — the order is for whoever reads the table, and a
    base sitting above its own subclass would read as if it swallowed it."""
    for index, failure in enumerate(FAILURES):
        for later in FAILURES[index + 1 :]:
            assert not issubclass(later.exception, failure.exception), (
                f"{later.exception.__name__} must come before {failure.exception.__name__}"
            )


# ----------------------------------------------------------------------------------------
# §12 — the rule this ADR introduces
# ----------------------------------------------------------------------------------------


def test_rule_27_is_registered_under_the_name_the_adr_gives_it() -> None:
    assert RULE_NAME in adr_text()
    assert any(rule for rule in RULES if rule == "concrete-names")


# ----------------------------------------------------------------------------------------
# The declared limit that a caller must be able to read (review of M8.1)
# ----------------------------------------------------------------------------------------


def planner_modules() -> list[Path]:
    """Anything under ``src/ela`` that looks like the Planner of §13."""
    named = [path for path in PACKAGE_ROOT.rglob("*.py") if "planner" in path.stem]
    defines = [
        path
        for path in PACKAGE_ROOT.rglob("*.py")
        if re.search(r"^class Planner\b", path.read_text(encoding="utf-8"), re.MULTILINE)
    ]
    return sorted(set(named + defines))


def test_the_plan_endpoint_says_its_schema_is_temporary_while_it_is() -> None:
    """ADR 0023 keeps this among the constraints to reopen; the caller reads it in the schema.

    The day the Planner (§13) arrives, this test fails on purpose: the sentence has to be
    revisited then — kept, reworded, or removed with the endpoint — and not quietly left behind
    telling people to expect a change that already happened.
    """
    planner = planner_modules()
    assert not planner, f"the Planner exists ({planner}): revisit PLAN_IS_TEMPORARY"

    assert "Planner" in PLAN_IS_TEMPORARY
    assert "temporary" in PLAN_IS_TEMPORARY
    assert "without a version bump" in PLAN_IS_TEMPORARY


def test_the_route_carries_that_sentence_as_its_description() -> None:
    """``description=`` and not the docstring: what the schema says is a decision, and the
    docstring is for whoever reads the code."""
    plan = next(
        route
        for route in api_routers()["tasks"].routes
        if getattr(route, "path", None) == "/tasks/{task_id}/plan"
    )

    assert plan.description == PLAN_IS_TEMPORARY


def test_the_adr_names_the_limit_too() -> None:
    text = adr_text()
    assert "Vincoli dichiarati" in text
    assert "superficie pubblica dell'API" in text
