"""The checks table, the signature and the TTL constants in ADR 0012 describe the running code.

Same pattern as ``test_adr_guardian.py``: the ADR is the documented decision, ``CHECKS``,
``authorization_from_approval`` and the two TTL constants are the running code, and neither may
drift — a check added, reordered or renamed, a parameter, a default, an hour — without this test
noticing. Check rows have three cells and start with a number, so no other table test mistakes
them for its own (the port rows of the same file start with a backticked name).
"""

from __future__ import annotations

import ast
import inspect
import re
from datetime import timedelta
from pathlib import Path

import pytest

from ela.permissions import (
    CHECKS,
    DEFAULT_AUTHORIZATION_TTL,
    MAX_AUTHORIZATION_TTL,
    Check,
    authorization_from_approval,
)
from tests.docs.test_adr_guardian import Parameter

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0012-authorizations.md"
ROW = re.compile(r"^\| (\d+) \| `(\w+)` \| (.+) \|$")
SIGNATURE = re.compile(
    r"```python\n(def authorization_from_approval\(.*?\) -> Authorization: \.\.\.)\n```", re.S
)
CONSTANT = re.compile(
    r"^(DEFAULT_AUTHORIZATION_TTL|MAX_AUTHORIZATION_TTL) = timedelta\(hours=(\d+)\)$", re.M
)


def documented_checks(text: str) -> list[Check]:
    rows: list[tuple[int, Check]] = []
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            number, name, _ = match.groups()
            rows.append((int(number), Check(name)))
    assert rows, "ADR 0012 must contain the checks table"
    assert [n for n, _ in rows] == list(range(1, len(rows) + 1)), "rows are numbered from 1"
    return [check for _, check in rows]


def documented_signature(text: str) -> list[Parameter]:
    match = SIGNATURE.search(text)
    assert match is not None, "ADR 0012 must contain the signature of authorization_from_approval"
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
        (p.name, p.kind.name, None if p.default is inspect.Parameter.empty else _name(p.default))
        for p in inspect.signature(authorization_from_approval).parameters.values()
    ]


def _name(default: object) -> str:
    assert default == DEFAULT_AUTHORIZATION_TTL
    return "DEFAULT_AUTHORIZATION_TTL"


def documented_constants(text: str) -> dict[str, timedelta]:
    found = {name: timedelta(hours=int(hours)) for name, hours in CONSTANT.findall(text)}
    assert set(found) == {"DEFAULT_AUTHORIZATION_TTL", "MAX_AUTHORIZATION_TTL"}, found
    return found


def test_checks_table_matches_the_code() -> None:
    assert documented_checks(ADR_PATH.read_text(encoding="utf-8")) == list(CHECKS)


def test_checks_table_covers_every_check() -> None:
    assert set(documented_checks(ADR_PATH.read_text(encoding="utf-8"))) == set(Check)


def test_signature_matches_the_function() -> None:
    assert documented_signature(ADR_PATH.read_text(encoding="utf-8")) == coded_signature()


def test_ttl_constants_match_the_code() -> None:
    assert documented_constants(ADR_PATH.read_text(encoding="utf-8")) == {
        "DEFAULT_AUTHORIZATION_TTL": DEFAULT_AUTHORIZATION_TTL,
        "MAX_AUTHORIZATION_TTL": MAX_AUTHORIZATION_TTL,
    }


def test_a_drifted_table_is_detected() -> None:
    """Negative cases: two checks swapped, one dropped, one renamed."""
    text = ADR_PATH.read_text(encoding="utf-8")
    swapped = text.replace("| 4 | `TASK` |", "| 4 | `STEP` |", 1).replace(
        "| 5 | `STEP` |", "| 5 | `TASK` |", 1
    )
    assert swapped != text
    assert documented_checks(swapped) != list(CHECKS)
    dropped = re.sub(r"^\| 8 \| `TARGETS` \|.*\n", "", text, count=1, flags=re.M)
    assert dropped != text
    assert set(documented_checks(dropped)) != set(Check)
    with pytest.raises(ValueError):
        documented_checks(text.replace("| 1 | `STATUS` |", "| 1 | `GRANTED` |", 1))
    with pytest.raises(AssertionError, match="numbered"):
        documented_checks(text.replace("| 8 | `TARGETS` |", "| 9 | `TARGETS` |", 1))


def test_a_drifted_signature_or_constant_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    for before, after in [
        ("    ttl: timedelta = DEFAULT_AUTHORIZATION_TTL,\n", "    ttl: timedelta,\n"),
        ("    now: datetime,\n", "    at: datetime,\n"),
        ("    *,\n    task: Task,\n", "    task: Task,\n    *,\n"),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_signature(drifted) != coded_signature(), before
    slower = text.replace(
        "MAX_AUTHORIZATION_TTL = timedelta(hours=24)",
        "MAX_AUTHORIZATION_TTL = timedelta(hours=48)",
        1,
    )
    assert slower != text
    assert documented_constants(slower)["MAX_AUTHORIZATION_TTL"] != MAX_AUTHORIZATION_TTL


def test_a_missing_table_signature_or_constant_is_detected() -> None:
    with pytest.raises(AssertionError, match="checks table"):
        documented_checks("no table here")
    with pytest.raises(AssertionError, match="signature"):
        documented_signature("no code here")
    with pytest.raises(AssertionError):
        documented_constants("DEFAULT_AUTHORIZATION_TTL = timedelta(hours=1)")
