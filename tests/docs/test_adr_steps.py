"""ADR 0065 — the browser in more steps (M13.10) — held to the code.

The ADR is written with the implementation, a section at a time; what this file holds to the code
grows with it. Today: the bag of what a question named, the rule it adds — the seventy-first, and
no other —, and the pin on **today's** totals, taken over from ADR 0064.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.executive import executor
from ela.permissions import production_catalogue
from ela.ports import Prospect
from ela.tools.account import ENTRY_NOT_NAMED
from tests.architecture.rules import NAMED_CONSTANT, RULES
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import STEPS_PORTS
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0065-browser-steps.md"
THE_RULE = "named-reaches-the-tool-only"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# §2 — what the yes named reaches the tool with the yes
# ----------------------------------------------------------------------------------------


def test_the_bag_the_adr_names_is_the_executor_s_and_the_prospect_s() -> None:
    text = adr_text()

    assert executor.NAMED == "named" and "`named`" in text
    assert "named" in Prospect.__dataclass_fields__ and "`Prospect.named`" in text
    assert f"`{ENTRY_NOT_NAMED}`" in text
    assert "`vault.entry_forgotten` è ritirato" in text


# ----------------------------------------------------------------------------------------
# The rule it adds, and the totals of today
# ----------------------------------------------------------------------------------------


def test_the_rule_it_adds_is_the_seventy_first_and_is_anchored_to_the_constant() -> None:
    assert "**Regola di architettura 71**" in conseguenze()
    assert set(_rules_up_to(71)) - set(_rules_up_to(70)) == {THE_RULE}
    assert f"`{NAMED_CONSTANT}`" in conseguenze()
    assert getattr(executor, NAMED_CONSTANT) == executor.NAMED


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0064: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settantuno**" in text
    assert len(RULES) == 71
    assert set(RULES) - set(_rules_up_to(70)) == {THE_RULE}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentasei**" in text and len(tuple(port_protocols())) == 36
    assert {port.__name__ for port in port_protocols()} >= STEPS_PORTS == {"TaskPages"}
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**diciotto**" in text and len(production_catalogue().specs()) == 18
    assert "**sei**" in text and len(Kind) == 6
