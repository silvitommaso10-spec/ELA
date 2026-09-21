"""ADR 0046 and the running code describe the same consumption, and the lines it revises say so.

ADR 0046 is M13.1b's (decision 3): the rule that decides which decisions spend their grant is
derived and no longer written by hand, the gravity of the defect it repairs is measured and not
assumed, and the lines of older ADRs that M13.1's merge made false are revised in the open. An ADR
is immutable, so an older one is not rewritten: its ``Stato`` line names the one that revises it,
the form ADR 0011 and ADR 0012 already use.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from ela.executive import CONSUMING_RULES
from ela.permissions import ASKING_RULES, Rule
from tests.executive import test_executor_recovery as recovery

ADRS: Final = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH: Final = ADRS / "0046-consumption.md"
STATE: Final = re.compile(r"^- \*\*Stato:\*\*\s*(.+)$", re.MULTILINE)
REVISED: Final = {
    "0011-permission-guardian.md": "§7",
    "0024-cli.md": "§8",
    "0045-filesystem-and-high.md": "§8",
}
"""The ADRs whose lines ADR 0046 revises, with the section each ``Stato`` line must name.

ADR 0024 §8 and ADR 0045 §8 are decision 3's; ADR 0011 §7 — «HIGH resta DENIED» — enters by
decision 5, because M13.1's merge made it false. ADR 0045 also has a line of its Conseguenze
revised (``describe``), which its ``Stato`` line names beside §8."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def state_of(filename: str) -> str:
    found = STATE.search((ADRS / filename).read_text(encoding="utf-8"))
    assert found is not None, f"{filename} declares no state"
    return found.group(1)


def test_the_derivation_the_adr_states_is_the_one_in_the_code() -> None:
    assert "CONSUMING_RULES = ASKING_RULES | {Rule.AUTHORIZATION_REQUIRED}" in adr_text()
    assert ASKING_RULES | {Rule.AUTHORIZATION_REQUIRED} == CONSUMING_RULES


def test_the_adr_names_the_tests_that_hold_it() -> None:
    """A decision whose defence is a test names the test, and the test is where it says."""
    text = adr_text()
    root = ADRS.parents[1]

    for path in (
        "tests/executive/test_consuming_rules.py",
        "tests/security/test_high_risk_capability.py",
    ):
        assert f"`{path}`" in text, path
        assert (root / path).is_file(), path
    window = "test_window_7a_a_spent_single_use_grant_asks_again_and_never_acts_twice"
    assert window in text
    assert hasattr(recovery, window), "the test the ADR names for row 7a is gone"


def test_the_adr_writes_the_gravity_it_measured() -> None:
    """Decision 3: the gravity is in the ADR, and so is how the case of the idempotent closed."""
    text = adr_text()

    assert re.search(r"^### \d+\. La gravità, misurata$", text, re.MULTILINE)
    assert "idempotente" in text
    assert "7a" in text and "ADR 0015 §8" in text


@pytest.mark.parametrize(("filename", "section"), sorted(REVISED.items()))
def test_every_revised_adr_names_adr_0046_in_its_state(filename: str, section: str) -> None:
    state = state_of(filename)

    assert state.startswith("Accettata"), "revised, not superseded: the ADR still stands"
    assert "ADR 0046" in state and section in state, state


@pytest.mark.parametrize(("filename", "section"), sorted(REVISED.items()))
def test_the_adr_names_every_line_it_revises(filename: str, section: str) -> None:
    number = filename[:4]
    assert f"ADR {number} {section}" in adr_text()


def test_the_revised_text_is_left_as_it_was() -> None:
    """An ADR is not rewritten: the old sentence is still there, read beside the line that
    corrects it."""
    assert "l'audit porta il percorso e la dimensione" in (
        ADRS / "0045-filesystem-and-high.md"
    ).read_text(encoding="utf-8")
    assert "che è l'unica obbligatoria" in (ADRS / "0024-cli.md").read_text(encoding="utf-8")
    assert "HIGH resta `DENIED`" in (ADRS / "0011-permission-guardian.md").read_text(
        encoding="utf-8"
    )
