"""The policy table and the ``decide`` signature in ADR 0011 describe the running Guardian.

Same pattern as the other ADR tests: the ADR is the documented decision, ``RISK_POLICY`` and
``PermissionGuardianPort.decide`` are the running code, and neither may drift — a risk level, its
rule, a parameter of ``decide`` or its default — without this test noticing. Policy rows have
three cells and start with a risk level, so no other table test mistakes them for its own.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from ela.domain import RiskLevel
from ela.permissions import RISK_POLICY, Rule
from ela.ports import PermissionGuardianPort

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0011-permission-guardian.md"
ROW = re.compile(r"^\| (SAFE|LOW|MEDIUM|HIGH|CRITICAL) \| `(\w+)` \| (.+) \|$")
SIGNATURE = re.compile(r"```python\n(def decide\(.*?\) -> PermissionDecision: \.\.\.)\n```", re.S)


def documented_policy(text: str) -> dict[RiskLevel, Rule]:
    """Risk level -> rule, in the order of the table."""
    rows: dict[RiskLevel, Rule] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            level, rule, _ = match.groups()
            rows[RiskLevel(level)] = Rule(rule)
    assert rows, "ADR 0011 must contain the policy table"
    return rows


Parameter = tuple[str, str, str | None]
"""Name, kind and default (as source text) of one parameter, ``self`` excluded."""


def documented_signature(text: str) -> list[Parameter]:
    match = SIGNATURE.search(text)
    assert match is not None, "ADR 0011 must contain the signature of decide"
    function = ast.parse(match.group(1)).body[0]
    assert isinstance(function, ast.FunctionDef)
    arguments = function.args
    positional = [(a, None) for a in arguments.args[1:]]
    defaults = arguments.defaults[-len(positional) :] if positional and arguments.defaults else []
    for index, default in enumerate(defaults):
        positional[len(positional) - len(defaults) + index] = (
            positional[len(positional) - len(defaults) + index][0],
            default,
        )
    shape: list[Parameter] = [
        (a.arg, "POSITIONAL_OR_KEYWORD", None if d is None else ast.unparse(d))
        for a, d in positional
    ]
    shape.extend(
        (a.arg, "KEYWORD_ONLY", None if d is None else ast.unparse(d))
        for a, d in zip(arguments.kwonlyargs, arguments.kw_defaults, strict=True)
    )
    return shape


def coded_signature() -> list[Parameter]:
    function = inspect.getattr_static(PermissionGuardianPort, "decide")
    return [
        (p.name, p.kind.name, None if p.default is inspect.Parameter.empty else repr(p.default))
        for p in list(inspect.signature(function).parameters.values())[1:]
    ]


def test_policy_table_matches_the_code() -> None:
    documented = documented_policy(ADR_PATH.read_text(encoding="utf-8"))
    assert list(documented) == list(RISK_POLICY)
    assert documented == dict(RISK_POLICY)


def test_policy_table_covers_every_risk_level() -> None:
    assert set(documented_policy(ADR_PATH.read_text(encoding="utf-8"))) == set(RiskLevel)


def test_decide_signature_matches_the_port() -> None:
    assert documented_signature(ADR_PATH.read_text(encoding="utf-8")) == coded_signature()


def test_a_drifted_policy_table_is_detected() -> None:
    """Negative case: a rule swapped, a level made permissive; each must show."""
    text = ADR_PATH.read_text(encoding="utf-8")
    for before, after in [
        ("| HIGH | `DENY` |", "| HIGH | `APPROVAL_UNLESS_AUTHORIZED` |"),
        ("| LOW | `ALLOW_WITHIN_SCOPE` |", "| LOW | `ALLOW` |"),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_policy(drifted) != dict(RISK_POLICY), before
    without_critical = text.replace("| CRITICAL | `DENY` | `DENIED` sempre |\n", "", 1)
    assert without_critical != text
    assert set(documented_policy(without_critical)) != set(RiskLevel)


def test_a_drifted_signature_is_detected() -> None:
    """Negative case: a parameter renamed, a default changed, the keyword dropped."""
    text = ADR_PATH.read_text(encoding="utf-8")
    for before, after in [
        ("    authorization_uses: int = 0,\n", "    authorization_uses: int = 1,\n"),
        ("    authorization_uses: int = 0,\n", "    uses: int = 0,\n"),
        ("    authorization_uses: int = 0,\n", ""),
        ("    *,\n    task: Task | None = None,\n", "    task: Task | None = None,\n    *,\n"),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_signature(drifted) != coded_signature(), before


def test_a_missing_table_or_signature_is_detected() -> None:
    with pytest.raises(AssertionError, match="policy table"):
        documented_policy("no table here")
    with pytest.raises(AssertionError, match="signature of decide"):
        documented_signature("no code here")
