"""ADR 0072 — a closing of the browser has a limit (M13.9d) — held to the tree: a proposal until the
proof by hand of its branch, the ADRs it revises saying so on their state line and no other, the
facts of its measures written, and its constants the code's.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS, KILLED, killed_at_a_closing
from ela.infrastructure.machine import browser

ROOT = Path(__file__).resolve().parents[2]
ADRS = ROOT / "docs" / "adr"
ADR_PATH = ADRS / "0072-a-closing-has-a-limit.md"
REVISED_MARK = "**Rivista da ADR 0072 (M13.9d)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
REVISED: frozenset[str] = frozenset({"0052", "0054", "0063", "0066", "0070"})
"""What the census of the implementation found (decision 96): the four the SPEC named, and ADR
0052 §10, «a single deadline around all the work of the port»."""


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


def test_it_is_a_proposal_until_the_proof_by_hand_and_says_what_the_proof_is() -> None:
    said = " ".join(status_of(ADR_PATH.read_text(encoding="utf-8")).split())

    assert said.startswith("**Proposta** il **2026-11-18**")
    assert "`tests/infrastructure/machine/test_a_closing_has_a_limit.py`" in said
    assert "la sezione 34 di `docs/GETTING_STARTED.md`" in said
    assert "**La riga dirà chi ha visto che cosa**" in said


def test_the_index_names_it_with_its_state() -> None:
    index = (ADRS / "README.md").read_text(encoding="utf-8")

    assert (
        "| [0072](0072-a-closing-has-a-limit.md) | Una chiusura del browser ha un limite | "
        "Proposta |" in index
    )


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list(ADR_PATH.read_text(encoding="utf-8"))

    assert listed == REVISED
    assert listed == revised_by_their_state(REVISED_MARK, ADR_PATH)


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    """The negative case: a mark nobody wrote is not found on a state line."""
    assert revised_by_their_state("**Rivista da ADR 9999 (M0.0)**", ADR_PATH) == set()


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    sections = set(re.findall(r"^### (\d+)\. ", text, re.MULTILINE))
    for number in revised_by_the_list(text):
        said = status_of(next(ADRS.glob(f"{number}-*.md")).read_text(encoding="utf-8"))
        named = set(re.findall(r"ADR 0072 §(\d+)", said.split(REVISED_MARK, 1)[1]))
        assert named and named <= sections, number


def test_the_measures_and_what_is_declared_are_written() -> None:
    """Decisions 81, 92 and 95: the end of the browser as an event on the two browsers, the
    longest healthy closing under the load of the suite, and the fact of Playwright."""
    text = " ".join(ADR_PATH.read_text(encoding="utf-8").split())

    for fact in (
        "**13453 passed, 17 skipped**",
        "**La più lunga è di 694,4 ms**",
        "11 ms dopo con il browser del profilo e 4 ms dopo con quello vuoto",
        "`CRConnection._onClose` scarta solo la sessione radice",
        "**Il test che ci poggia afferma di aver costruito la sua precondizione**",
        "**ADR 0070 §4 misurava una chiusura di 30,0 s**",
    ):
        assert fact in text, fact


def test_its_constants_and_its_line_are_the_code_s() -> None:
    text = " ".join(ADR_PATH.read_text(encoding="utf-8").split())
    names = ("Google Chrome for Testing", "node")

    assert f"«{browser.ENDED}»" in text
    assert f"`{browser.LEFT}`" in text
    assert KILLED in text
    assert f"`{killed_at_a_closing(names)}`" in text
    assert f"{BROWSER_CLOSE_GRACE_SECONDS} s" in text


def test_the_worst_case_after_the_stop_is_a_formula_of_the_constants_and_a_test_builds_it() -> None:
    """Answer 107: the bound is written from the constants, never as a number, and the test that
    builds it is there."""
    text = ADR_PATH.read_text(encoding="utf-8")
    first = text.split("### 1. ", 1)[1].split("\n### 2. ", 1)[0]
    flat = " ".join(first.split())
    tests = (
        ROOT / "tests" / "infrastructure" / "machine" / "test_a_closing_has_a_limit.py"
    ).read_text(encoding="utf-8")

    formula = (
        "il tempo del tool + `BROWSER_CLOSE_GRACE_SECONDS` + `GONE_SECONDS` + "
        "`BROWSER_CLOSE_GRACE_SECONDS`"
    )
    assert formula in flat
    assert "`test_the_worst_case_after_the_stop_ends_within_the_written_formula`" in flat
    assert "async def test_the_worst_case_after_the_stop_ends_within_the_written_formula(" in tests
    worst = first.split("caso peggiore", 1)[1].split("\n\n", 2)[1]
    assert not re.search(r"\d", worst), f"the worst case is written as a number: {worst!r}"
    assert browser.GONE_SECONDS and BROWSER_CLOSE_GRACE_SECONDS
