"""ADR 0027 and the exemptions the rules actually have say the same thing.

An ADR is immutable, so the doors ADR 0012 §7, ADR 0013 §9 and ADR 0017 §9 opened are still
written where they were opened; ADR 0027 repeats the rows it changes under ``Esenzioni ritirate:``
and ``Regole estese:``. This module is what keeps the two ends together: every withdrawn entry
must be gone from the constant, every constant and rule the ADR names must exist, and putting one
of the entries back — in the code or in the table — is noticed here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.architecture import rules
from tests.architecture.rules import CONSTANTS, EXEMPTION, RULES, SUBJECT

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0027-exemptions-withdrawn.md"
ADR_0012 = ADR_PATH.with_name("0012-authorizations.md")
ADR_0013 = ADR_PATH.with_name("0013-executor.md")
#: ``SQL_EXECUTORS = {"session", "connection", "cursor"}``, written into the prose of ADR 0013 §9.
SQL_EXECUTORS_IN_PROSE = re.compile(r"`SQL_EXECUTORS = \{([^}]+)\}`")
#: ``| 21 `device-port-readers` | `DEVICE_PORT_ALLOWED` | `ela.ports` | why nobody is behind |``
WITHDRAWN_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| `([A-Z_]+)` \| `([^`|]+)` \| ([^|]+) \|$")
#: ``| 15 | the rule | the exemptions before (ADR) | the exemptions now |``
EXTENDED_ROW = re.compile(r"^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$")
#: ``| `ROOT_PACKAGE` | `INEVITABLE` | why the question cannot be asked |``
SUBJECT_ROW = re.compile(r"^ *\| `([A-Z_]+)` \| `([A-Z]+)` \| ([^|]+) \|$")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def withdrawn(text: str) -> list[re.Match[str]]:
    found = [match for line in text.splitlines() if (match := WITHDRAWN_ROW.match(line))]
    assert found, "ADR 0027 must contain the table of the withdrawn exemptions"
    return found


def extended(text: str) -> list[re.Match[str]]:
    found = [match for line in text.splitlines() if (match := EXTENDED_ROW.match(line))]
    assert found, "ADR 0027 must repeat the rows it changes under 'Regole estese:'"
    return found


def test_the_five_withdrawn_entries_are_the_five_the_rules_no_longer_have() -> None:
    """The closed world of the withdrawal: the table names five, and the code has none of them."""
    rows = withdrawn(adr_text())

    assert {(row.group(2), row.group(3), row.group(4)) for row in rows} == {
        ("testing-imports", "TESTING_ALLOWED_INTERNAL", "ela.testing"),
        ("authorization-builders", "AUTHORIZATION_BUILDERS_EXEMPT", "testing"),
        ("tool-execute-callers", "SQL_EXECUTORS", "connection"),
        ("device-port-readers", "DEVICE_PORT_ALLOWED", "ela.ports"),
        (
            "device-port-readers",
            "DEVICE_PORT_ALLOWED",
            "ela.infrastructure.persistence.device_registry",
        ),
    }
    for row in rows:
        assert row.group(2) in RULES, row.group(2)
        assert row.group(4) not in getattr(rules, row.group(3)), row.group(4)


def test_every_withdrawn_entry_belongs_to_a_constant_the_rule_still_reads() -> None:
    """A withdrawal is a narrowing, never a deletion: the door is smaller, not gone."""
    doors = {(row.rule, row.name) for row in CONSTANTS if row.kind == EXEMPTION}
    for row in withdrawn(adr_text()):
        assert (row.group(2), row.group(3)) in doors
        assert getattr(rules, row.group(3)), f"{row.group(3)} is empty: nothing left to exempt"


def test_the_repeated_rows_name_the_three_rules_whose_adr_is_superseded() -> None:
    """Rules 15, 16 and 21 had their exemptions written in an ADR; rule 6's had none."""
    assert {row.group(1) for row in extended(adr_text())} == {"15", "16", "21"}
    assert "**non è\nscritta in nessun ADR**" in adr_text()


def test_the_price_of_the_connection_entry_is_written_where_it_can_be_found() -> None:
    """Decision approved with the reason: reopening is a line plus a motive, not an accident."""
    text = adr_text()
    assert "una riga più una motivazione" in text
    assert "sql-executed-on-a-connection" in text


def test_the_criterion_that_keeps_rule_11_open_is_written() -> None:
    """The sixth silent door, and why it is not a sixth withdrawal (ADR 0027 §3)."""
    text = adr_text()
    assert "l'attore legittimo della regola" in text
    assert "step-event-built-by-engine" in text
    assert "step-event-writers" not in {row.group(2) for row in withdrawn(text)}

    (rule_11,) = [
        row for row in CONSTANTS if row.rule == "step-event-writers" and row.name == "TASKS_DIR"
    ]
    assert rule_11.kind == EXEMPTION
    assert rule_11.proof == "step-event-built-by-engine"
    assert rule_11.reason


def test_a_reopened_entry_or_a_drifted_row_is_detected() -> None:
    """The negative case: the table without a row, and the ADR that forgets one."""
    text = adr_text()
    shortened = text.replace(
        "| 16 `tool-execute-callers` | `SQL_EXECUTORS` | `connection` |", "| skipped |", 1
    )
    assert shortened != text
    assert ("tool-execute-callers", "SQL_EXECUTORS", "connection") not in {
        (row.group(2), row.group(3), row.group(4)) for row in withdrawn(shortened)
    }

    with pytest.raises(AssertionError, match="withdrawn exemptions"):
        withdrawn("nothing")
    with pytest.raises(AssertionError, match="Regole estese"):
        extended("nothing")


def gone_from(rule: str) -> set[str]:
    """What ADR 0027 withdrew from one rule, read from its table."""
    return {row.group(4) for row in withdrawn(adr_text()) if row.group(2) == rule}


def test_the_receiver_names_of_adr_0013_are_the_ones_left_plus_the_one_withdrawn() -> None:
    """ADR 0013 §9 spells the set out; it stays as it was written, and 0027 says what left it."""
    (written,) = SQL_EXECUTORS_IN_PROSE.findall(ADR_0013.read_text(encoding="utf-8"))
    documented = {name.strip().strip('"') for name in written.split(",")}

    assert documented == {"session", "connection", "cursor"}
    assert rules.SQL_EXECUTORS | gone_from("tool-execute-callers") == documented
    assert "connection" not in rules.SQL_EXECUTORS


def test_the_packages_of_adr_0012_are_the_ones_left_plus_the_one_withdrawn() -> None:
    """Rule 15 was opened for two packages; the fakes never used theirs (ADR 0027)."""
    text = ADR_0012.read_text(encoding="utf-8")
    assert "fuori da `ela.permissions` e `ela.testing`" in text

    documented = {rules.PERMISSIONS_DIR, rules.TESTING_DIR}
    assert rules.AUTHORIZATION_BUILDERS_EXEMPT | gone_from("authorization-builders") == documented


def test_the_three_subjects_and_their_words_are_the_ones_in_the_table() -> None:
    """The class without an assertion is the one the ADR spells out row by row (§5, review M9.3)."""
    documented = {
        match.group(1): match.group(2)
        for line in adr_text().splitlines()
        if (match := SUBJECT_ROW.match(line))
    }
    assert documented, "ADR 0027 §5 must list the subjects and the word each carries"

    assert documented == {row.name: row.why.upper() for row in CONSTANTS if row.kind == SUBJECT}
