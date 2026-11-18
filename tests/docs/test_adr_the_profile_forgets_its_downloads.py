"""ADR 0073 — the browser of the profile forgets its downloads before every guided launch (M13.13c)
— held to the tree: a proposal until the proof by hand, whose step it names (decision 118); the one
ADR it revises saying so on its state line and no other; the facts of its measures written; and its
constants and its line the code's.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.composition.root import history_kept
from ela.infrastructure.machine.account import DOWNLOAD_TABLES, FORGET, HISTORY_FILE

ROOT = Path(__file__).resolve().parents[2]
ADRS = ROOT / "docs" / "adr"
ADR_PATH = ADRS / "0073-the-profile-forgets-its-downloads.md"
REVISED_MARK = "**Rivista da ADR 0073 (M13.13c)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
REVISED: frozenset[str] = frozenset({"0063"})


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def revised_by_the_list(text: str) -> set[str]:
    block = text.split("## Conseguenze", 1)[1].split("**Righe riviste**", 1)[1]
    rows = block.split("\n\n", 2)[1]
    return {match.group(1) for line in rows.splitlines() if (match := REVISED_ROW.match(line))}


def revised_by_their_state(mark: str, exclude: Path) -> set[str]:
    return {
        path.name[:4]
        for path in ADRS.glob("[0-9]*.md")
        if path != exclude and mark in status_of(path.read_text(encoding="utf-8"))
    }


def test_it_is_a_proposal_until_the_proof_by_hand_and_names_the_step_that_proves_it() -> None:
    said = " ".join(status_of(ADR_PATH.read_text(encoding="utf-8")).split())

    assert said.startswith("**Proposta** il **2026-11-18**")
    assert "**La prova a mano del criterio 2 è il passo 3 della sezione 34" in said
    assert "Prima del passo 3 non si pulisce niente a mano, e lo script lo chiede" in said
    assert "**La riga dirà chi ha visto che cosa**" in said


def test_the_index_names_it_with_its_state() -> None:
    index = (ADRS / "README.md").read_text(encoding="utf-8")

    assert (
        "| [0073](0073-the-profile-forgets-its-downloads.md) | Il browser del profilo dimentica i "
        "suoi scaricamenti prima di ogni lancio guidato | Proposta |" in index
    )


def test_the_adr_it_revises_says_so_on_its_state_line_and_no_other_does() -> None:
    listed = revised_by_the_list(ADR_PATH.read_text(encoding="utf-8"))

    assert listed == REVISED
    assert listed == revised_by_their_state(REVISED_MARK, ADR_PATH)


def test_a_mark_nobody_wrote_is_not_found() -> None:
    assert revised_by_their_state("**Rivista da ADR 9999 (M0.0)**", ADR_PATH) == set()


def test_each_mark_names_a_section_of_this_adr_that_is_there() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    sections = set(re.findall(r"^### (\d+)\. ", text, re.MULTILINE))
    for number in revised_by_the_list(text):
        said = status_of(next(ADRS.glob(f"{number}-*.md")).read_text(encoding="utf-8"))
        named = set(re.findall(r"ADR 0073 §(\d+)", said.split(REVISED_MARK, 1)[1]))
        assert named and named <= sections, number


def test_the_measures_are_written() -> None:
    text = " ".join(ADR_PATH.read_text(encoding="utf-8").split())

    for fact in (
        "**Chrome for Testing 153.0.8010.12 cade a uno scaricamento nuovo quando, al lancio,",
        "0 crash in 60 corse su profili nuovi (A3 due volte)",
        "0 in 30 corse (M1), e 0 in 12 con la finestra (A5-S1)",
        "La lista ha **2 elementi**, e dopo S1 ne ha ancora **2**",
        "**Nessuna riga di `History` è letta**",
    ):
        assert fact in text, fact


def test_its_constants_and_its_line_are_the_code_s() -> None:
    text = " ".join(ADR_PATH.read_text(encoding="utf-8").split())

    assert f"`{'/'.join(HISTORY_FILE)}`" in text
    assert ", ".join(f"`{table}`" for table in DOWNLOAD_TABLES) in text
    assert all(statement.startswith("DELETE FROM ") for statement in FORGET)
    assert "`FORGET`, `DELETE FROM` senza `WHERE`" in text
    assert f"`{history_kept('OperationalError')}`" in text
