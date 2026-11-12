"""ADR 0062 against the tree (M13.12): the tables, the signature and the constants it writes, and
the pin on today's totals, which moves here from ADR 0060.

The shape of ``test_adr_authorizations.py``: the ADR is the documented decision, the code is the
running one, and neither may drift — a reason reordered, a check renamed, a parameter, a number —
without this test noticing. Every comparison has its negative case.
"""

from __future__ import annotations

import ast
import inspect
import re
import tomllib
from pathlib import Path
from typing import Final

import pytest

from ela.api.security import Kind
from ela.permissions import (
    BROWSER_GUIDED,
    GAPS,
    MAX_DAYS,
    MIN_DAYS,
    POLICY_CHECKS,
    SHORT_ID,
    WHY_DAYS,
    WHY_MAX,
    Gap,
    PolicyCheck,
    authorization_from_policy,
    production_catalogue,
)
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import ACCOUNT_PORTS, STEPS_PORTS, before_the_accounts
from tests.docs.test_adr_cli import coded_commands, commands_after_0062
from tests.docs.test_adr_composition import coded_routes, routes_after_0062
from tests.docs.test_adr_guardian import Parameter
from tests.docs.test_adr_placement import _rules_up_to
from tests.docs.test_adr_planner import contracts_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0062-policies.md"
ROW = re.compile(r"^\| (\d+) \| `(\w+)` \| (.+) \|$")
TERMS_ROW = re.compile(
    r"^\| `(?P<capability>[\w.]+)` \| (?P<limits>[^|]+) \| (?P<uncovered>[^|]+) \| "
    r"(?P<free>[^|]+) \| (?:`(?P<route>\w+)`|—) \|$"
)
GAPS_OF_0062: Final = ["REVOKED", "EXPIRED", "TERMS", "SITE", "LIMIT", "ARGUMENT"]
CHECKS_OF_0062: Final = ["CATALOGUE", "ADMITS", "SCOPE", "LIMITS", "DAYS"]
"""ADR 0062's two tables as they were the day it was accepted: since M13.14 the predicate and the
birth are ADR 0068's (§5), and ``tests/docs/test_adr_policies_on_high.py`` compares them with the
code. This ADR keeps what it decided, which is history."""
SIGNATURE = re.compile(
    r"```python\n(def authorization_from_policy\(.*?\) -> Authorization: \.\.\.)\n```", re.S
)
CONSTANT = re.compile(r"^(MIN_DAYS|MAX_DAYS|WHY_DAYS|WHY_MAX|SHORT_ID) = (\d+)$", re.M)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def numbered(text: str) -> list[tuple[int, str]]:
    return [
        (int(match.group(1)), match.group(2))
        for line in text.splitlines()
        if (match := ROW.match(line))
    ]


def documented_gaps(text: str) -> list[str]:
    rows = [(n, name) for n, name in numbered(text) if name in Gap.__members__]
    assert rows, "ADR 0062 must contain the table of the gaps"
    assert [n for n, _ in rows] == list(range(1, len(rows) + 1)), "rows are numbered from 1"
    return [name for _, name in rows]


def documented_checks(text: str) -> list[str]:
    rows = [(n, name) for n, name in numbered(text) if name in PolicyCheck.__members__]
    assert rows, "ADR 0062 must contain the table of the checks"
    assert [n for n, _ in rows] == list(range(1, len(rows) + 1)), "rows are numbered from 1"
    return [name for _, name in rows]


def names(cell: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`(\w+)`", cell))


def documented_terms(text: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    found = {
        match["capability"]: (
            names(match["limits"]),
            names(match["uncovered"]),
            names(match["free"]),
            (match["route"] or "",),
        )
        for line in text.splitlines()
        if (match := TERMS_ROW.match(line))
    }
    assert found, "ADR 0062 must contain the table of the declarations"
    return found


def coded_terms() -> dict[str, tuple[tuple[str, ...], ...]]:
    return {
        spec.id: (
            spec.policy_terms.limits,
            spec.policy_terms.uncovered,
            spec.policy_terms.free,
            (spec.policy_terms.route or "",),
        )
        for spec in production_catalogue().specs()
        if spec.policy_terms is not None
    }


def documented_signature(text: str) -> list[Parameter]:
    match = SIGNATURE.search(text)
    assert match is not None, "ADR 0062 must contain the signature of authorization_from_policy"
    function = ast.parse(match.group(1)).body[0]
    assert isinstance(function, ast.FunctionDef)
    arguments = function.args
    shape: list[Parameter] = [(a.arg, "POSITIONAL_OR_KEYWORD", None) for a in arguments.args]
    shape.extend(
        (a.arg, "KEYWORD_ONLY", None if d is None else ast.unparse(d))
        for a, d in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    )
    return shape


def coded_signature() -> list[Parameter]:
    return [
        (p.name, p.kind.name, None)
        for p in inspect.signature(authorization_from_policy).parameters.values()
    ]


def documented_constants(text: str) -> dict[str, int]:
    found = {name: int(value) for name, value in CONSTANT.findall(text)}
    assert set(found) == {"MIN_DAYS", "MAX_DAYS", "WHY_DAYS", "WHY_MAX", "SHORT_ID"}, found
    return found


CODED_CONSTANTS = {
    "MIN_DAYS": MIN_DAYS,
    "MAX_DAYS": MAX_DAYS,
    "WHY_DAYS": WHY_DAYS,
    "WHY_MAX": WHY_MAX,
    "SHORT_ID": SHORT_ID,
}


def test_the_gaps_are_the_ones_of_that_day_and_still_the_predicate_s_in_their_order() -> None:
    """The six of that day, and every one of them still a gap of the predicate, in the same order
    among today's: ADR 0068 added two between them, it took none away."""
    assert documented_gaps(adr_text()) == GAPS_OF_0062
    assert [gap for gap in GAPS if gap in GAPS_OF_0062] == GAPS_OF_0062


def test_the_checks_of_the_birth_are_the_ones_of_that_day_in_the_function_s_order() -> None:
    assert documented_checks(adr_text()) == CHECKS_OF_0062
    assert [check for check in POLICY_CHECKS if check in CHECKS_OF_0062] == CHECKS_OF_0062


def test_the_declarations_are_the_catalogue_s() -> None:
    """ADR 0062's table, the row ADR 0063 adds in the same form since M13.9, and the three rows of
    ADR 0068 since M13.14: together they are every capability that declares terms."""
    accounts = ADR_PATH.with_name("0063-browser-with-your-accounts.md").read_text(encoding="utf-8")
    high = ADR_PATH.with_name("0068-policies-on-high.md").read_text(encoding="utf-8")
    here, later, latest = (
        documented_terms(adr_text()),
        documented_terms(accounts),
        documented_terms(high),
    )

    assert set(here) == {BROWSER_GUIDED} and not set(here) & set(later)
    assert not (set(here) | set(later)) & set(latest)
    assert here | later | latest == coded_terms()


def test_the_signature_and_the_constants_are_the_code_s() -> None:
    assert documented_signature(adr_text()) == coded_signature()
    assert documented_constants(adr_text()) == CODED_CONSTANTS


def test_a_drifted_table_signature_or_constant_is_detected() -> None:
    text = adr_text()
    swapped = text.replace("| 1 | `REVOKED` |", "| 1 | `EXPIRED` |", 1).replace(
        "| 2 | `EXPIRED` |", "| 2 | `REVOKED` |", 1
    )
    assert swapped != text and documented_gaps(swapped) != GAPS_OF_0062
    dropped = re.sub(r"^\| 5 \| `DAYS` \|.*\n", "", text, count=1, flags=re.M)
    assert dropped != text and documented_checks(dropped) != CHECKS_OF_0062
    with pytest.raises(AssertionError, match="numbered"):
        documented_gaps(text.replace("| 6 | `ARGUMENT` |", "| 7 | `ARGUMENT` |", 1))
    widened = text.replace("| `task_type` |", "| — |", 1)
    assert widened != text and documented_terms(widened) != coded_terms()
    moved = text.replace("    now: datetime,\n", "    at: datetime,\n", 1)
    assert moved != text and documented_signature(moved) != coded_signature()
    longer = text.replace("MAX_DAYS = 90", "MAX_DAYS = 365", 1)
    assert longer != text and documented_constants(longer) != CODED_CONSTANTS


def test_a_missing_table_signature_or_constant_is_detected() -> None:
    with pytest.raises(AssertionError, match="gaps"):
        documented_gaps("no table here")
    with pytest.raises(AssertionError, match="checks"):
        documented_checks("no table here")
    with pytest.raises(AssertionError, match="declarations"):
        documented_terms("no table here")
    with pytest.raises(AssertionError, match="signature"):
        documented_signature("no code here")
    with pytest.raises(AssertionError):
        documented_constants("MIN_DAYS = 1")


def test_the_conseguenze_count_the_totals_as_this_adr_saw_them() -> None:
    """The totals of the day ADR 0062 was written. The pin on **today's** totals moved to the ADR
    that changed them — ADR 0063, ``test_adr_accounts.py`` —, as it had moved here from ADR 0060:
    what is counted here is what came up to this ADR, and no later."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**sessantasei**" in text
    assert len(_rules_up_to(66)) == 66 <= len(RULES)
    assert set(_rules_up_to(66)) - set(_rules_up_to(65)) == {"a-policy-is-born-at-its-route"}
    assert "**quindici**" in text and len(contracts_up_to(15)) == 15 <= len(contracts)
    assert "**trentatré**" in text
    assert (
        len(tuple(p for p in port_protocols() if p.__name__ not in ACCOUNT_PORTS | STEPS_PORTS))
        == 33
    )
    assert "**sessanta**" in text and len(coded_routes() - routes_after_0062()) == 60
    assert "**trentuno**" in text and len(coded_commands() - commands_after_0062()) == 31
    assert "**quattordici**" in text and len(before_the_accounts()) == 14
    assert "**sei**" in text and len(Kind) == 6


def test_the_store_that_does_not_answer_is_declared_in_the_conseguenze() -> None:
    """Decision 20 of the review: «mai un'esecuzione», declared where a reader looks for it."""
    flat = " ".join(conseguenze().split())
    assert "mai un'esecuzione" in flat
    assert "tests/executive/test_policy_question.py" in flat


REVISED = (
    "0011-permission-guardian.md",
    "0012-authorizations.md",
    "0013-executor.md",
    "0044-command-center.md",
    "0045-filesystem-and-high.md",
    "0060-guided-browser.md",
)
"""The ADRs whose lines M13.12 makes false or incomplete (decisions 13, 22 and 23)."""


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def test_the_adrs_it_revises_say_so_on_their_state_line() -> None:
    """The form of ADR 0046 and ADR 0060: an ADR is not rewritten, its «Stato:» line points on."""
    for name in REVISED:
        status = status_of((ADR_PATH.parent / name).read_text(encoding="utf-8"))
        assert "**Riletta da ADR 0062 (M13.12)**" in status, name


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    text = (ADR_PATH.parent / REVISED[0]).read_text(encoding="utf-8")
    silent = text.replace("**Riletta da ADR 0062 (M13.12)**", "", 1)
    assert "**Riletta da ADR 0062 (M13.12)**" not in status_of(silent)


def test_it_declares_no_constraints_section() -> None:
    """``tests/docs/test_simplifications.py`` admits «Vincoli dichiarati» only from 0020 to 0042."""
    assert "### Vincoli dichiarati" not in adr_text()
