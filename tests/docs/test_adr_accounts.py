"""ADR 0063 against the code (M13.9): the browser with your accounts, and the session's cover.

The ADR is written with the implementation, a section at a time; what this file holds to the code
grows with it. Today: the totals of today, which this ADR is the last to change.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.permissions import POLICY_VERSION, production_catalogue
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0063-browser-with-your-accounts.md"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0062: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**sessantotto**" in text
    assert len(RULES) == 68
    assert set(RULES) - set(_rules_up_to(66)) == {
        "the-room-s-word-is-the-room-s",
        "a-secret-is-opened-only-by-an-adapter",
    }
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentacinque**" in text and len(tuple(port_protocols())) == 35
    assert "**sessantatré**" in text and len(coded_routes()) == 63
    assert "**trentaquattro**" in text.split("i port diventano", 1)[1].split("le rotte", 1)[1]
    assert len(coded_commands()) == 34
    assert "**quattordici**" in text and len(production_catalogue().specs()) == 14
    assert "**sei**" in text and len(Kind) == 6


def test_the_version_of_the_policy_is_the_one_this_adr_gives_it() -> None:
    assert f"`POLICY_VERSION` diventa `{POLICY_VERSION}`" in adr_text()
