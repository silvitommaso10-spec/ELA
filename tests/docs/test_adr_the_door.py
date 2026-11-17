"""ADR 0070 — the door of the downloads says itself closed at the browser's answer (M13.13b) —
held to the tree: a ``Proposta`` until the proof by hand of the branch, the ADR it revises saying so
on its state line, the facts of its measure written, and the three states in the code.
"""

from __future__ import annotations

import re
import typing
from pathlib import Path

from ela.infrastructure.machine import browser

ROOT = Path(__file__).resolve().parents[2]
ADRS = ROOT / "docs" / "adr"
ADR_PATH = ADRS / "0070-the-door-closes-at-the-answer.md"
REVISED_MARK = "**Rivista da ADR 0070 (M13.13b)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list(text: str) -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of an ADR names, one bullet each."""
    block = text.split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def revised_by_their_state(mark: str, exclude: Path) -> set[str]:
    return {
        path.name[:4]
        for path in ADRS.glob("[0-9]*.md")
        if path != exclude and mark in status_of(path.read_text(encoding="utf-8"))
    }


def test_it_is_a_proposal_until_the_proof_of_its_branch() -> None:
    said = " ".join(status_of(ADR_PATH.read_text(encoding="utf-8")).split())

    assert said.startswith("**Proposta** il **2026-11-17**")
    assert "la sezione 33 di `docs/GETTING_STARTED.md`" in said


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list(ADR_PATH.read_text(encoding="utf-8"))

    assert listed == {"0066"}
    assert listed == revised_by_their_state(REVISED_MARK, ADR_PATH)


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    sections = set(re.findall(r"^### (\d+)\. ", text, re.MULTILINE))
    for number in revised_by_the_list(text):
        said = status_of((next(ADRS.glob(f"{number}-*.md"))).read_text(encoding="utf-8"))
        named = set(re.findall(r"ADR 0070 §(\d+)", said.split(REVISED_MARK, 1)[1]))
        assert named and named <= sections, number


def test_the_measure_and_what_is_declared_are_written() -> None:
    """Decision 62: the order under load, how many of how many, and the fact of ``_shut``."""
    text = " ".join(ADR_PATH.read_text(encoding="utf-8").split())

    for fact in (
        "**0 su 100**",
        "**28 su 100**",
        "**0 su 28**",
        "**`_shut` — il contesto, il browser, il driver — è durata 30,0 s in 20 turni su 20**",
        "**il driver di Playwright**",
        "20,5–37,6 ms",
    ):
        assert fact in text, fact


def test_the_door_has_the_three_states_the_adr_says() -> None:
    assert typing.get_args(browser._DoorState) == ("open", "closing", "closed")
