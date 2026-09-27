"""ADR 0049 (M17.2b): an outcome stays on the surfaces that list tasks.

The ADR that changed the totals pins them — the routes and the commands, each one more —, and the
ADRs it revises say so on their «Stato:» line, in the form of ADR 0046: an ADR is not rewritten.
"""

from __future__ import annotations

from pathlib import Path

from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands, commands_after_0048
from tests.docs.test_adr_composition import coded_routes, routes_after_0048

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0049-finished-on-the-homes.md"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def test_the_conseguenze_count_the_rules_the_ports_the_routes_and_the_commands_of_today() -> None:
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57
    assert "**ventotto**" in text
    assert len(tuple(port_protocols())) == 28
    assert "**quarantanove**" in text
    assert len(coded_routes()) == 49
    assert "**ventisette**" in text
    assert len(coded_commands()) == 27


def test_it_adds_one_route_and_the_command_that_calls_it() -> None:
    """What the tests of the earlier ADRs take away is exactly this — read from here."""
    assert routes_after_0048() == {("GET", "/tasks/finished")}
    assert commands_after_0048() == {"task finished"}


def test_it_says_the_decision_it_revises_worked_as_written_and_names_its_boundary() -> None:
    """The registration of M17.2b fixed both: the revision is open, and M17.5 is named."""
    text = adr_text()

    assert "funzionava come scritta" in text
    assert "decisione 22 di M17.2" in text and "ADR 0044 §5" in text
    assert "M17.5" in text


def test_the_revised_adrs_say_so_on_their_status_line() -> None:
    for revised in (
        "0004-task-transitions.md",
        "0006-persistence.md",
        "0023-composition-root-and-api.md",
        "0043-companion.md",
        "0044-command-center.md",
    ):
        text = (ADR_DIR / revised).read_text(encoding="utf-8")
        status = text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
        assert "ADR 0049" in status, revised
