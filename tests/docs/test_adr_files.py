"""ADR 0066 — the files from the browser, and the browser's own page — held to the code.

The ADR of the branch ``m13.13-i-file-dal-browser`` is written with the implementation, a piece at a
time (M13.9b, M13.9c, M13.10b, M13.13); what this file holds to the code grows with it. Today: the
ADRs it revises say so on their state line and no other does, each mark names a section of it that
is there, and what M13.9b put in the port is the port's.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.ports import Browser, Glanced, Landed, tried

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0066-browser-files.md"
REVISED_MARK = "**Rivista da ADR 0066 (M13.13)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list() -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of this ADR names, one bullet each."""
    block = adr_text().split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def written() -> dict[str, str]:
    return {
        path.name[:4]: path.read_text(encoding="utf-8")
        for path in ADR_PATH.parent.glob("[0-9]*.md")
        if path != ADR_PATH
    }


def revised_by_their_state(texts: dict[str, str]) -> set[str]:
    return {number for number, text in texts.items() if REVISED_MARK in status_of(text)}


def test_it_is_a_proposal_until_the_proof_of_its_branch() -> None:
    said = " ".join(status_of(adr_text()).split())
    assert said.startswith("Proposta il **2026-11-03**")
    assert "la sezione 30 di `docs/GETTING_STARTED.md`" in said


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list()

    assert listed == {"0063", "0064"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    sections = set(re.findall(r"^### (\d+)\. ", adr_text(), re.MULTILINE))
    for number in revised_by_the_list():
        said = status_of(written()[number]).split(REVISED_MARK, 1)[1]
        named = set(re.findall(r"ADR 0066 §(\d+)", said))
        assert named and named <= sections, number


def test_what_m13_9b_put_in_the_port_is_the_port_s() -> None:
    """§1: the member, the two fields and the one function the ADR names."""
    assert "unanswered" in vars(Browser)
    assert "unanswered" in Landed.__dataclass_fields__
    assert "unanswered" in Glanced.__dataclass_fields__
    assert tried("chrome-error://chromewebdata/", "https://x.example/") == "https://x.example/"
    text = adr_text()
    for named in ("`ela.ports.tried`", "`unanswered`", "`Page.getFrameTree`"):
        assert named in text, named
