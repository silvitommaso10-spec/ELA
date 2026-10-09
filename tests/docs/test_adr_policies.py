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
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_guardian import Parameter
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0062-policies.md"
ROW = re.compile(r"^\| (\d+) \| `(\w+)` \| (.+) \|$")
TERMS_ROW = re.compile(
    r"^\| `(?P<capability>[\w.]+)` \| (?P<limits>[^|]+) \| (?P<uncovered>[^|]+) \| "
    r"(?P<free>[^|]+) \| `(?P<route>\w+)` \|$"
)
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


def documented_gaps(text: str) -> list[Gap]:
    rows = [(n, name) for n, name in numbered(text) if name in Gap.__members__]
    assert rows, "ADR 0062 must contain the table of the gaps"
    assert [n for n, _ in rows] == list(range(1, len(rows) + 1)), "rows are numbered from 1"
    return [Gap(name) for _, name in rows]


def documented_checks(text: str) -> list[PolicyCheck]:
    rows = [(n, name) for n, name in numbered(text) if name in PolicyCheck.__members__]
    assert rows, "ADR 0062 must contain the table of the checks"
    assert [n for n, _ in rows] == list(range(1, len(rows) + 1)), "rows are numbered from 1"
    return [PolicyCheck(name) for _, name in rows]


def names(cell: str) -> tuple[str, ...]:
    return tuple(re.findall(r"`(\w+)`", cell))


def documented_terms(text: str) -> dict[str, tuple[tuple[str, ...], ...]]:
    found = {
        match["capability"]: (
            names(match["limits"]),
            names(match["uncovered"]),
            names(match["free"]),
            (match["route"],),
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


def test_the_gaps_are_the_predicate_s_in_its_order() -> None:
    assert documented_gaps(adr_text()) == list(GAPS)


def test_the_checks_of_the_birth_are_the_function_s_in_its_order() -> None:
    assert documented_checks(adr_text()) == list(POLICY_CHECKS)
    assert set(documented_checks(adr_text())) == set(PolicyCheck)


def test_the_declarations_are_the_catalogue_s() -> None:
    assert documented_terms(adr_text()) == coded_terms()
    assert set(coded_terms()) == {BROWSER_GUIDED}


def test_the_signature_and_the_constants_are_the_code_s() -> None:
    assert documented_signature(adr_text()) == coded_signature()
    assert documented_constants(adr_text()) == CODED_CONSTANTS


def test_a_drifted_table_signature_or_constant_is_detected() -> None:
    text = adr_text()
    swapped = text.replace("| 1 | `REVOKED` |", "| 1 | `EXPIRED` |", 1).replace(
        "| 2 | `EXPIRED` |", "| 2 | `REVOKED` |", 1
    )
    assert swapped != text and documented_gaps(swapped) != list(GAPS)
    dropped = re.sub(r"^\| 5 \| `DAYS` \|.*\n", "", text, count=1, flags=re.M)
    assert dropped != text and set(documented_checks(dropped)) != set(PolicyCheck)
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


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0060: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**sessantasei**" in text
    assert len(RULES) == 66
    assert set(RULES) - set(_rules_up_to(65)) == {"a-policy-is-born-at-its-route"}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentatré**" in text and len(tuple(port_protocols())) == 33
    assert "**sessanta**" in text and len(coded_routes()) == 60
    assert "**trentuno**" in text and len(coded_commands()) == 31
    assert "**quattordici**" in text and len(production_catalogue().specs()) == 14
    assert "**sei**" in text and len(Kind) == 6


def test_the_store_that_does_not_answer_is_declared_in_the_conseguenze() -> None:
    """Decision 20 of the review: «mai un'esecuzione», declared where a reader looks for it."""
    flat = " ".join(conseguenze().split())
    assert "mai un'esecuzione" in flat
    assert "tests/executive/test_policy_question.py" in flat


def test_it_declares_no_constraints_section() -> None:
    """``tests/docs/test_simplifications.py`` admits «Vincoli dichiarati» only from 0020 to 0042."""
    assert "### Vincoli dichiarati" not in adr_text()
