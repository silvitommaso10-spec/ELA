"""The table of renamed rules cannot rot (M11.2 dec. A).

An ADR is immutable and keeps naming a rule as it was called when it was written, so a rename
needs somewhere for the old name to keep meaning something. That somewhere is
:data:`~tests.architecture.rules.RENAMED_RULES`, and a table of aliases nobody checks is exactly
where a name that no longer exists survives — so it is checked here, from three sides:

* every **old** name is gone from :data:`~tests.architecture.rules.RULES`, or the rename did not
  happen and the alias is a lie;
* every **new** name is registered, or the alias points at nothing;
* every old name is still **printed by some ADR**, or the row is dead weight: the table exists to
  serve documents that cannot be edited, and a row no document needs is a row to delete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.rules import RENAMED_RULES, RULES, current_name

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
MILESTONE_DIR = Path(__file__).resolve().parents[2] / "docs" / "milestones"


@pytest.mark.parametrize("old", sorted(RENAMED_RULES))
def test_the_old_name_is_no_longer_registered(old: str) -> None:
    assert old not in RULES


@pytest.mark.parametrize(("old", "new"), sorted(RENAMED_RULES.items()))
def test_the_new_name_is_registered(old: str, new: str) -> None:
    assert new in RULES, f"{old} forwards to {new}, which no rule answers to"


def adrs_naming(rule: str) -> list[str]:
    return [
        path.name
        for path in sorted(ADR_DIR.glob("*.md"))
        if rule in path.read_text(encoding="utf-8")
    ]


def decisions_naming(rule: str) -> list[str]:
    """Every accepted document that prints ``rule`` — an ADR, or the milestone spec that decided it.

    Not only ADRs, and the reason is an ordering the milestone chose on purpose. M11.2's rename is
    the **first commit**, alone, before any code of the listening — so that review looks at the
    rename and not at new code (ADR 0030 §15's discipline, applied to a rename). The ADR that will
    carry it does not exist yet at that commit, and cannot: it is written with the milestone. What
    *does* exist is the approved spec, and that is the document that decided the rename.

    The guard keeps its teeth either way: a row nobody wrote down anywhere still fails.
    """
    return adrs_naming(rule) + [
        path.name
        for path in sorted(MILESTONE_DIR.glob("*.md"))
        if rule in path.read_text(encoding="utf-8")
    ]


@pytest.mark.parametrize("old", sorted(RENAMED_RULES))
def test_some_immutable_document_still_prints_the_old_name(old: str) -> None:
    """The reason the table exists: an ADR that names it and may not be edited."""
    assert adrs_naming(old), f"nothing names {old}: the row is dead weight, not history"


@pytest.mark.parametrize(("old", "new"), sorted(RENAMED_RULES.items()))
def test_some_document_makes_the_rename_it_claims(old: str, new: str) -> None:
    """No row may invent a rename: a decision document has to have made it.

    This is the property the local table in ``tests/docs/test_adr_perception.py`` used to hold,
    kept when that table was folded into :data:`RENAMED_RULES`. Without it the register could
    quietly forward a name to one nobody decided on.
    """
    assert decisions_naming(new), f"{old} forwards to {new}, which no document decides"


def test_current_name_leaves_an_unrenamed_rule_alone() -> None:
    for rule in RULES:
        assert current_name(rule) == rule


def test_current_name_resolves_a_renamed_one() -> None:
    """The negative case of the two above: without the table, the doc tests would fail."""
    for old, new in RENAMED_RULES.items():
        assert current_name(old) == new
        assert current_name(old) in RULES
