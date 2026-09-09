"""``docs/CHANGELOG.md`` and ``docs/milestones/`` describe the same history (decisione 6a).

The closed world runs both ways: every milestone that is no longer a ``Proposta`` has an entry,
and no entry exists without its milestone. The ADR each entry names must exist in ``docs/adr/``
**and** be named by the milestone's own document — a citation nobody wrote in the milestone is a
citation invented for the changelog. The three milestones that predate the first ADR carry ``—``,
and the world is closed on that too: a ``—`` on a milestone that does name an ADR fails.

A fourth closed world comes free: the ``Stato`` of a milestone must be one of the words
``TEMPLATE.md`` offers, plus ``Completata``, which M9.1 introduced and M9.3 kept.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = ROOT / "docs" / "CHANGELOG.md"
MILESTONES = ROOT / "docs" / "milestones"
ADRS = ROOT / "docs" / "adr"
TEMPLATE = MILESTONES / "TEMPLATE.md"

ENTRY = re.compile(r"^- \*\*(M\d+\.\d+[a-z]?)\*\* — (.+?) \((ADR \d{4}|—)\)$")
STATE = re.compile(r"^- \*\*Stato:\*\*\s*(.+)$", re.MULTILINE)
WORD = re.compile(r"[A-Za-zÀ-ÿ]+")
CITED = re.compile(r"ADR\s*(\d{4})")
PROPOSED = "Proposta"
EXTRA_STATE = "Completata"
"""A state ``TEMPLATE.md`` does not list, in use since M9.1: declared here rather than tolerated,
so that the fifth word somebody invents is not tolerated too."""


def milestones() -> list[Path]:
    return sorted(p for p in MILESTONES.glob("M*.md") if p.name != TEMPLATE.name)


def state_of(path: Path) -> str:
    """The one word the ``Stato`` line begins with, bold markers and commentary stripped."""
    found = STATE.search(path.read_text(encoding="utf-8"))
    assert found is not None, f"{path.name} has no Stato line"
    word = WORD.search(found.group(1))
    assert word is not None, f"{path.name}: the Stato line names no state"
    return word.group(0)


def cited_by(path: Path) -> set[str]:
    return set(CITED.findall(path.read_text(encoding="utf-8")))


def entries() -> dict[str, tuple[str, str]]:
    """Milestone id -> (what it brought, the ADR cited or ``—``)."""
    found = {
        match.group(1): (match.group(2), match.group(3))
        for line in CHANGELOG.read_text(encoding="utf-8").splitlines()
        if (match := ENTRY.match(line)) is not None
    }
    assert found, "the changelog must contain entries"
    return found


def template_states() -> set[str]:
    """The words ``TEMPLATE.md`` offers on its own Stato line."""
    found = STATE.search(TEMPLATE.read_text(encoding="utf-8"))
    assert found is not None
    return {word for word in WORD.findall(found.group(1))}


def test_every_state_is_a_word_the_template_offers() -> None:
    allowed = template_states() | {EXTRA_STATE}
    assert allowed == {"Proposta", "In", "corso", "Implementata", "Chiusa", EXTRA_STATE}
    for path in milestones():
        assert state_of(path) in allowed, path.name


def test_every_milestone_that_is_no_longer_a_proposal_has_an_entry() -> None:
    done = {path.stem for path in milestones() if state_of(path) != PROPOSED}
    assert done, "some milestone must be done, or this test is vacuous"
    assert done <= set(entries()), done - set(entries())


def test_no_entry_exists_without_its_milestone() -> None:
    known = {path.stem for path in milestones() if state_of(path) != PROPOSED}
    assert set(entries()) <= known, set(entries()) - known


def test_every_cited_adr_exists_and_is_cited_by_the_milestone_itself() -> None:
    for milestone, (_, citation) in entries().items():
        path = MILESTONES / f"{milestone}.md"
        if citation == "—":
            continue
        number = citation.removeprefix("ADR ")
        assert list(ADRS.glob(f"{number}-*.md")), citation
        assert number in cited_by(path), f"{milestone} does not name {citation}"


def test_the_dash_means_the_milestone_names_no_adr_at_all() -> None:
    """Decisione 9a: ``—`` is an absence that was checked, not one that was assumed.

    M0.1, M0.2 and M0.3 are the whole of it: the repository, the CI and the architecture-test
    framework were built before the first ADR was written. The day one of them is amended to cite
    an ADR, this fails and the entry has to say so.
    """
    dashed = {name for name, (_, citation) in entries().items() if citation == "—"}
    assert dashed == {"M0.1", "M0.2", "M0.3"}
    for milestone, (_, citation) in entries().items():
        cited = cited_by(MILESTONES / f"{milestone}.md")
        assert (citation == "—") == (not cited), milestone


NUMBER = re.compile(r"^M(\d+)\.(\d+)([a-z]*)$")


def order_of(name: str) -> tuple[int, int, str]:
    """A milestone id as something sortable: phase, number, and the letter of a repair.

    M6.1b is the first id with a letter (M6.1b decisione A: the number says where the defect
    lives, the letter says when it was repaired), and it belongs between M6.1 and M6.2 — where
    somebody looking for the defect will look. The empty letter sorts first, which is what puts
    the original ahead of its repair.
    """
    found = NUMBER.match(name)
    assert found is not None, f"{name} is not a milestone id"
    phase, number, letter = found.groups()
    return int(phase), int(number), letter


def test_the_history_runs_from_the_first_milestone_to_the_release() -> None:
    ordered = list(entries())
    assert ordered[0] == "M0.1"
    assert ordered == sorted(ordered, key=order_of)
    assert "v0.1" in CHANGELOG.read_text(encoding="utf-8")


def test_a_repair_is_ordered_after_the_milestone_whose_defect_it_repairs() -> None:
    """The negative of the sort key: without the letter it would not be an id at all."""
    assert order_of("M6.1") < order_of("M6.1b") < order_of("M6.2")
    assert NUMBER.match("M6") is None


def test_the_release_entry_points_at_the_list_of_what_v01_simplifies() -> None:
    """Decisione 7a: one list, in the milestone, and everything else points at it."""
    text = CHANGELOG.read_text(encoding="utf-8")
    assert "milestones/M9.4.md" in text
    assert "semplificato" in text
    assert "ARCHITECTURE.md" in text


def test_a_state_nobody_declared_is_detected() -> None:
    """The negative case, on a synthetic milestone rather than on a real one."""
    allowed = template_states() | {EXTRA_STATE}
    for word, known in [("Implementata", True), ("Completata", True), ("Inventata", False)]:
        found = STATE.search(f"- **Stato:** **{word}**, in attesa di merge")
        assert found is not None
        state = WORD.search(found.group(1))
        assert state is not None and state.group(0) == word
        assert (word in allowed) is known


def test_an_entry_for_a_milestone_that_does_not_exist_is_detected() -> None:
    """And the other direction: a milestone file with no entry."""
    known = {path.stem for path in milestones() if state_of(path) != PROPOSED}
    assert not ({"M9.9"} <= known)
    assert "M9.9" not in entries()
    assert not (set(entries()) | {"M9.9"}) <= known
