"""The exemptions of the architecture rules, made able to notice that they became false.

An exemption is a door in a rule. Until ADR 0027 the only tests of a door were the ``ALLOWED``
cases of :mod:`tests.architecture.violations`, which *synthesise* inside a temporary copy the
code the exemption exists for and then check that the rule stays quiet. They are good tests **of
the rule** and, by construction, say nothing **about the door**: five exemptions had nobody
behind them for milestones, and no test could have noticed.

So the door is tested against the tree that exists. :data:`~tests.architecture.rules.CONSTANTS`
has one row per (rule, constant) pair the rules actually read — the pairs are derived here from
the AST of ``rules.py``, so a constant added to an existing rule fails the closed world until
somebody classifies it — and the classes carry **opposite** assertions:

* an ``EXEMPTION`` restricted must make its rule report at least one violation;
* a ``DETECTOR`` restricted must leave its rule reporting none.

Filing a live door as a detector therefore fails. What can still hide is a ``SUBJECT`` row, and
there are three constants in that class, each with its reason written next to it.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.architecture import rules
from tests.architecture.rules import (
    CONSTANTS,
    DETECTOR,
    EACH,
    EXEMPTION,
    RULES,
    SUBJECT,
    WHOLE,
    Constant,
    Violation,
)
from tests.architecture.violations import ALLOWED, PACKAGE_ROOT, apply, copy_package

RULES_SOURCE = Path(rules.__file__)
#: A name no module, no path and no package has.
NOWHERE = "__nowhere__"
NO_ADR = "—"
KINDS = frozenset({EXEMPTION, DETECTOR, SUBJECT})
ALLOWED_BY_ID = {case.id: case for case in ALLOWED}


# --------------------------------------------------------------------------------------
# The pairs, read from the source rather than from a list
# --------------------------------------------------------------------------------------


def pairs_in(source: str) -> set[tuple[str, str]]:
    """Every (rule, constant) pair the rules of ``source`` read, following their helpers."""
    tree = ast.parse(source)
    constants = {
        target.id
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id.isupper()
    }
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    table = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "RULES"
    )
    assert isinstance(table.value, ast.Dict)
    checks = {
        key.value: value.id
        for key, value in zip(table.value.keys, table.value.values, strict=True)
        if isinstance(key, ast.Constant) and isinstance(value, ast.Name)
    }
    assert len(checks) == len(table.value.keys), "RULES must map a name to a function"

    def read_by(function: ast.FunctionDef, seen: set[str]) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(function):
            if not isinstance(node, ast.Name):
                continue
            if node.id in constants:
                names.add(node.id)
            elif node.id in functions and node.id not in seen:
                seen.add(node.id)
                names |= read_by(functions[node.id], seen)
        return names

    return {
        (rule, name) for rule, check in checks.items() for name in read_by(functions[check], set())
    }


def test_the_table_is_exactly_the_pairs_the_rules_read() -> None:
    """Both directions: a constant added to a rule, or a row left behind, fails here."""
    assert pairs_in(RULES_SOURCE.read_text(encoding="utf-8")) == {
        (row.rule, row.name) for row in CONSTANTS
    }
    assert len(CONSTANTS) == len({(row.rule, row.name) for row in CONSTANTS}), "no pair twice"
    assert {row.rule for row in CONSTANTS} == set(RULES)


def test_a_constant_added_to_an_existing_rule_is_noticed() -> None:
    """The negative case of the closed world: rule 1 widened through a constant nobody classified.

    Written as text rather than applied to the module, because the point is that the *source*
    betrays the new door — no import of ``rules.py`` is needed to see it.
    """
    source = RULES_SOURCE.read_text(encoding="utf-8")
    widened = source.replace(
        'DOMAIN_ALLOWED_EXTERNAL = frozenset({"pydantic"})',
        'DOMAIN_ALLOWED_EXTERNAL = frozenset({"pydantic"})\nA_NEW_DOOR = frozenset({"yaml"})',
        1,
    ).replace("allowed = STDLIB | DOMAIN_ALLOWED_EXTERNAL", "allowed = STDLIB | A_NEW_DOOR", 1)
    assert widened != source

    assert pairs_in(widened) - {(row.rule, row.name) for row in CONSTANTS} == {
        ("domain", "A_NEW_DOOR")
    }


# --------------------------------------------------------------------------------------
# Restricting a constant (decision 1a: generic by type)
# --------------------------------------------------------------------------------------


def nowhere(value: Any) -> Any:
    """The same shape, matching nothing: an empty set, a path nobody has, a pattern that fails."""
    if isinstance(value, Path):
        return Path(NOWHERE)
    if isinstance(value, str):
        return NOWHERE
    if isinstance(value, re.Pattern):
        return re.compile(r"(?!x)x")
    if isinstance(value, frozenset):
        return frozenset()
    if isinstance(value, tuple):
        return tuple(nowhere(element) for element in value)
    raise TypeError(f"no way to restrict a {type(value).__name__}")  # pragma: no cover


def without(value: Any, element: Any) -> Any:
    if isinstance(value, frozenset):
        return value - {element}
    return tuple(kept for kept in value if kept != element)


def restrictions(row: Constant) -> Iterator[tuple[str, Any]]:
    """One restriction per element for ``EACH``, one for the whole constant otherwise."""
    value = getattr(rules, row.name)
    if row.by == EACH:
        assert isinstance(value, (frozenset, tuple)), f"{row.name} has no elements to remove"
        assert value, f"{row.name} is empty: an allowlist with no entry is not a door"
        for element in sorted(value, key=str):
            yield str(element), without(value, element)
    else:
        yield WHOLE, nowhere(value)


def cases(kind: str) -> list[tuple[Constant, str, Any]]:
    return [
        (row, label, restricted)
        for row in CONSTANTS
        if row.kind == kind
        for label, restricted in restrictions(row)
    ]


def identify(case: tuple[Constant, str, Any]) -> str:
    row, label, _ = case
    return f"{row.rule}:{row.name}" + ("" if label == WHOLE else f"[{label}]")


def reported(
    row: Constant, restricted: Any, tree: Path, patch: pytest.MonkeyPatch
) -> list[Violation]:
    patch.setattr(rules, row.name, restricted)
    return RULES[row.rule](tree)


# --------------------------------------------------------------------------------------
# The two opposite assertions
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", cases(EXEMPTION), ids=identify)
def test_an_exemption_restricted_makes_its_rule_speak(
    case: tuple[Constant, str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Take the door away and somebody must be standing there — on the real tree.

    One row of the thirty-six cannot be proved that way and names the ``ALLOWED`` case that
    stands in for it (rule 11, ADR 0027): the exemption's user is the Task Engine, which writes
    its step events through a variable the rule's name heuristic cannot see. An exemption is
    proved by the tree or by a case it names, never by nothing.
    """
    row, _, restricted = case
    tree = PACKAGE_ROOT
    if row.proof:
        tree = copy_package(tmp_path)
        apply(ALLOWED_BY_ID[row.proof], tree)

    assert reported(row, restricted, tree, monkeypatch), (
        f"nobody is behind {row.name} in rule {row.rule}: an exemption with no code behind it is "
        "a door opened before anyone knocks (ADR 0017 §9, ADR 0027)"
    )


@pytest.mark.parametrize("case", cases(DETECTOR), ids=identify)
def test_a_detector_restricted_leaves_its_rule_silent(
    case: tuple[Constant, str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a rule looks for can only make it quieter: louder would mean it is a door."""
    row, _, restricted = case

    assert reported(row, restricted, PACKAGE_ROOT, monkeypatch) == [], (
        f"{row.name} makes rule {row.rule} speak when it shrinks: it is a door, not a detector"
    )


DEAD_DOORS = (
    ("testing-imports", "TESTING_ALLOWED_INTERNAL", f"{rules.ROOT_PACKAGE}.testing"),
    ("authorization-builders", "AUTHORIZATION_BUILDERS_EXEMPT", rules.TESTING_DIR),
    ("tool-execute-callers", "SQL_EXECUTORS", "connection"),
    ("device-port-readers", "DEVICE_PORT_ALLOWED", f"{rules.ROOT_PACKAGE}.ports"),
    (
        "device-port-readers",
        "DEVICE_PORT_ALLOWED",
        f"{rules.ROOT_PACKAGE}.infrastructure.persistence.device_registry",
    ),
)


@pytest.mark.parametrize(("rule", "name", "element"), DEAD_DOORS, ids=lambda value: str(value))
def test_the_five_doors_adr_0027_closed_would_be_caught_if_reopened(
    rule: str, name: str, element: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative case of the gate: put one of the five back and its assertion fails.

    Reopening does not break any rule — that is precisely the problem, and why nothing noticed
    for milestones. What the gate adds is the next line: restrict the entry that was just added
    and *nothing* speaks, which is the failure
    ``test_an_exemption_restricted_makes_its_rule_speak`` reports.
    """
    door = getattr(rules, name)
    reopened = door | {element} if isinstance(door, frozenset) else (*door, element)
    monkeypatch.setattr(rules, name, reopened)
    assert RULES[rule](PACKAGE_ROOT) == [], "a wider door breaks nothing: that is the whole point"

    monkeypatch.setattr(rules, name, without(reopened, element))
    assert RULES[rule](PACKAGE_ROOT) == [], "and nobody is behind it, which is what the gate sees"


# --------------------------------------------------------------------------------------
# What each row must carry
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("row", CONSTANTS, ids=lambda row: f"{row.rule}:{row.name}")
def test_every_row_is_filled_in_for_its_kind(row: Constant) -> None:
    assert row.kind in KINDS
    assert row.by in {WHOLE, EACH}
    if row.kind == EXEMPTION:
        assert row.adr, f"{row.name}: name the ADR that opened the door, or {NO_ADR}"
        assert row.adr == NO_ADR or row.adr.startswith("ADR ")
        assert not row.proof or row.reason, "a proof that is not the tree needs its reason"
        assert not row.proof or row.proof in ALLOWED_BY_ID
    else:
        assert row.by == WHOLE and not row.adr and not row.proof
        assert (row.kind == SUBJECT) == bool(row.reason), "a subject is the row that has a reason"


def test_the_subjects_are_the_three_declared_ones() -> None:
    """The only class without an assertion, kept small and named on purpose (ADR 0027)."""
    assert {row.name for row in CONSTANTS if row.kind == SUBJECT} == {
        "ROOT_PACKAGE",
        "SECURITY_MODULE",
        "CLI_DIR",
    }


def test_the_standard_library_allowance_is_derived_and_not_written_by_hand() -> None:
    """``STDLIB`` is an exemption of four rules, and the one nobody edits: it comes from ``sys``."""
    assert frozenset(sys.stdlib_module_names) == rules.STDLIB
    assert {row.rule for row in CONSTANTS if row.name == "STDLIB"} == {
        "domain",
        "ports",
        "permissions-imports",
        "testing-imports",
    }
