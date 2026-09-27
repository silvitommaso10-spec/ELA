"""ADR 0050 (M17.2c): the page of whoever is nobody yet carries its sheets, admitted by their hash.

What the registration of M17.2c fixed and a document can hold: the revision of ADR 0043 §5 is open
and says the previous choice worked as written; no route is added; the rule of the block is named
with the test that defends it; and the ADRs it revises say so on their «Stato:» line.
"""

from __future__ import annotations

from pathlib import Path

from tests.docs.test_adr_composition import ROUTE_ROW, coded_routes

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0050-sheets-inside-the-page.md"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def test_it_revises_adr_0043_and_says_the_previous_choice_worked_as_written() -> None:
    text = adr_text()

    assert "ADR 0043 §5" in text
    assert "funzionato esattamente come era" in text
    assert "era un'esenzione" in text and "Questa strada non la apre" in text


def test_it_adds_no_route() -> None:
    """ADR 0037 §3: the sheets travel in the answer, and the routes stay where they were."""
    assert not [line for line in adr_text().splitlines() if ROUTE_ROW.match(line)]
    assert "Nessuna rotta nuova" in adr_text().split("## Conseguenze", 1)[1]
    assert len(coded_routes()) == 49


def test_it_names_the_rule_of_the_block_with_its_test() -> None:
    text = adr_text()

    assert "closes_the_block" in text
    assert "tests/design/test_inline_block.py" in text


def test_the_revised_adrs_say_so_on_their_status_line() -> None:
    for revised in ("0043-companion.md", "0044-command-center.md"):
        text = (ADR_DIR / revised).read_text(encoding="utf-8")
        status = text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
        assert "ADR 0050" in status, revised
