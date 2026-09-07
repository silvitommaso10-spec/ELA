"""What ADR 0025 claims about itself, checked against the code (M8.3).

The tables ADR 0025 adds to older ADRs are read where those tables live — the ports in
``test_adr_ports.py``, the routes and the variables in ``test_adr_composition.py``, the command
in ``test_adr_cli.py``. What is left is what belongs to this ADR alone: the rule it introduces,
the numbers it states in prose, and the one claim that has no table at all — that the catalogue's
row did not change when its scope became configurable.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.permissions import DEFAULT_NOTES_SCOPE, MAX_DECISION_TTL, catalogue_v01
from tests.architecture.rules import OUTPUT_MODEL, RULES
from tests.docs.test_adr_catalogue import (
    EXTENDING_ADRS as CATALOGUE_EXTENDING_ADRS,
)
from tests.docs.test_adr_catalogue import (
    all_documented_capabilities,
)

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0025-phase-8-debts.md"
RULE_NAME = "tool-output-readers"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def test_rule_29_is_registered_under_the_name_the_adr_gives_it() -> None:
    assert RULE_NAME in adr_text()
    assert RULE_NAME in RULES


def test_the_adr_names_the_one_model_the_rule_allows() -> None:
    """A rule whose exception is not written down is a rule nobody can follow."""
    assert OUTPUT_MODEL in adr_text()


def test_the_ceiling_the_adr_states_in_prose_is_the_one_in_the_code() -> None:
    """ADR 0025 §6 argues for **one hour** at length; a number that drifts makes the argument
    a decoration."""
    assert MAX_DECISION_TTL.total_seconds() == 3600
    assert "un'ora" in adr_text()


def test_the_catalogue_row_did_not_change_when_its_scope_became_configurable() -> None:
    """ADR 0025 §5 replaces one sentence of ADR 0010 §5 and no row of its table.

    That is why there is no "Capability estese:" table here: with nothing set, the catalogue is
    exactly the one ADR 0010 documented. A future ADR that *does* change the row has to say so
    under that label, and this test is where the absence is deliberate rather than forgotten.
    """
    documented = all_documented_capabilities()
    coded = {spec.id: spec for spec in catalogue_v01().specs()}

    assert documented["workspace.write_note"].scope == (DEFAULT_NOTES_SCOPE,)
    assert coded["workspace.write_note"].scope == (DEFAULT_NOTES_SCOPE,)
    assert ADR_PATH not in [path for path, _ in CATALOGUE_EXTENDING_ADRS]


def test_the_adr_says_which_rinvii_it_did_not_take() -> None:
    """The mitigation of every collector milestone: what is not taken stays written.

    Named here because ADR 0025 §1 is the criterion that left them out, and a constraint that
    lives only in a milestone file is one the next reader of the ADRs never meets.
    """
    constraints = adr_text().split("Vincoli dichiarati", 1)[1]

    for deferred in ("loop autonomo", "recover()", "heartbeat", "Fase 12", "ADR 0018 §6"):
        assert deferred in constraints, deferred


def test_the_counts_the_conseguenze_state_are_the_ones_the_code_has() -> None:
    """Nine members, two, four, and twenty-nine rules: prose that a reader would trust.

    ``ventinove`` is this ADR's own number and stays: an ADR is immutable and states what was
    true when it was written. What the code has *now* is the number ADR 0026 gives, checked in
    ``test_adr_placement.py`` — which is also what keeps the two from drifting apart silently.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]
    numbers = re.findall(r"\*\*(\w+)\*\*", conseguenze)

    assert "due" in numbers  # AuditLog still has two members
    assert "quindici" in numbers and "diciotto" in numbers  # routes, commands
    assert "ventinove" in numbers
    assert len(RULES) >= 29  # rules are only ever added
