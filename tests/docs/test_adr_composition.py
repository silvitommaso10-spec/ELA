"""The tables of ADR 0023 and the code say the same thing.

Three tables, three shapes: §3 (the seven new variables), §6 (the twelve routes) and §10 (which
exception becomes which status). Plus the name architecture rule 27 is registered under.

What is *not* here is checked where the other tables of its kind are: the ports in
``test_adr_ports.py``, the capabilities in ``test_adr_catalogue.py``. This module holds what only
ADR 0023 says.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.api import approvals, audit, system, tasks
from ela.api.app import FAILURES
from ela.api.tasks import PLAN_IS_TEMPORARY
from ela.composition.settings import ApiSettings, CoreSettings
from tests.architecture.rules import RULES
from tests.architecture.violations import PACKAGE_ROOT

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0023-composition-root-and-api.md"
SETTING_ROW = re.compile(r"^\| `(ELA_\w+)` \| `([^`]+)` \| (?:`([^`]+)`|\*\(([^)]+)\)\*) \|")
ROUTE_ROW = re.compile(r"^\| `(GET|POST)` \| `(/[\w{}/]*)` \| ([^|]+) \|$")
ERROR_ROW = re.compile(r"^\| ([^|]+) \| (?:`(\w+)`|\*\(([^)]+)\)\*) \| `(\d{3})` \|$")
RULE_NAME = "concretes-named-only-by-the-composition-root"
ROUTERS = (system.router, tasks.router, approvals.router, audit.router)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


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


def test_the_seven_variables_are_the_ones_the_settings_declare() -> None:
    assert documented_settings(adr_text()) == coded_settings()


def test_the_table_names_the_two_ceilings_the_ttls_have() -> None:
    """No TTL without a ceiling (ADR 0012, ADR 0013): the constraint column says so."""
    text = adr_text()
    rows = [line for line in text.splitlines() if SETTING_ROW.match(line)]
    ttls = [row for row in rows if "TTL_SECONDS" in row]

    assert len(ttls) == 2
    assert all("MAX_" in row for row in ttls)


# ----------------------------------------------------------------------------------------
# §6 — the twelve routes
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
    return {
        (method, route.path)
        for router in ROUTERS
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }


def test_the_routes_of_the_adr_are_the_routes_of_the_code() -> None:
    assert documented_routes(adr_text()) == coded_routes()


def test_there_are_twelve_of_them() -> None:
    """The number is in the prose of §6 and in ``tests/api/test_security.py``, which proves that
    every one of them is behind the token."""
    assert len(coded_routes()) == 12


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
    assert documented_errors(adr_text()) == {
        failure.exception.__name__: failure.status for failure in FAILURES
    }


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
        for route in tasks.router.routes
        if getattr(route, "path", None) == "/tasks/{task_id}/plan"
    )

    assert plan.description == PLAN_IS_TEMPORARY


def test_the_adr_names_the_limit_too() -> None:
    text = adr_text()
    assert "Vincoli dichiarati" in text
    assert "superficie pubblica dell'API" in text
