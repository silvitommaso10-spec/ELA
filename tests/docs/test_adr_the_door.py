"""ADR 0070 — the door of the downloads says itself closed at the browser's answer (M13.13b) —
held to the tree: accepted after the proof by hand of the branch, saying what it showed, the ADR
it revises saying so on its state line, the facts of its measure written, and the three states in
the code.
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


THE_PROOF = "`~/Downloads/prova-m9.5-20261117-133606.txt`"
PASSED_ON = "`fa3377a`"
WHAT_PROVES_THE_CUT = (
    "test_a_download_that_is_cut_short_is_cancelled_and_nothing_of_it_stays",
    "test_a_download_the_time_of_its_step_cuts_leaves_nothing_in_the_folder",
    "test_what_is_announced_while_the_door_closes_is_cancelled_and_taken_away",
)
"""The tests that prove the cut short download: step 4 of the proof did not exercise it."""
FILES_OF_A_PAGE = ROOT / "tests" / "infrastructure" / "machine" / "test_the_files_of_a_page.py"


def test_it_is_accepted_and_its_state_says_what_the_proof_showed_and_what_the_tests_prove() -> None:
    """Decision 111 of the last review of M9.5: accepted with a commit of its own, once the proof
    by hand had passed on the last commit of the branch on origin. The state says which file and
    which commit, what the proof showed — steps 2 and 3 —, and that the cut short download is
    proved by the tests and not by the hand, because step 4 ended with no download started; the
    tests it names are there."""
    said = " ".join(status_of(ADR_PATH.read_text(encoding="utf-8")).split())

    assert said.startswith("**Accettata** il **2026-11-17**")
    assert "la sezione 33 di `docs/GETTING_STARTED.md`" in said
    assert THE_PROOF in said and PASSED_ON in said
    assert "**L'interruzione la prova il test, non la mano**" in said
    assert "`browser.download_not_started`" in said
    tests = FILES_OF_A_PAGE.read_text(encoding="utf-8")
    for name in WHAT_PROVES_THE_CUT:
        assert f"`{name}`" in said, name
        assert f"async def {name}(" in tests, name


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
