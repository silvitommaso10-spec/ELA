"""``docs/CHANGELOG.md`` and ``docs/milestones/`` describe the same history (decisione 6a).

The closed world runs both ways: every milestone that is no longer a ``Proposta`` has an entry,
and no entry exists without its milestone. The ADR each entry names must exist in ``docs/adr/``
**and** be named by the milestone's own document — a citation nobody wrote in the milestone is a
citation invented for the changelog. The three milestones that predate the first ADR carry ``—``,
and the world is closed on that too: a ``—`` on a milestone that does name an ADR fails.

A fourth closed world comes free: the ``Stato`` of a milestone must be one of the words
``TEMPLATE.md`` offers, plus ``Completata``, which M9.1 introduced and M9.3 kept.

And a fifth, added on 2026-09-10, closes the way out of all the others: **a milestone that is in
``main`` may not call itself a ``Proposta``**. Until then a proposal owed nothing, so a milestone
that was built, merged and never re-stated fell out of every list at once — which is what happened
to M11.2. The evidence is read from the history of ``main``, not from a list of what is done: a
list would go stale in exactly the way the ``Stato`` line did.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest

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


# ----------------------------------------------------------------------------------------
# The hole the exemption for proposals used to hide
# ----------------------------------------------------------------------------------------
#
# A ``Proposta`` owes nothing: ``test_every_milestone_that_is_no_longer_a_proposal_has_an_entry``
# asks it for no changelog entry, which is right for a milestone nobody has built. It stops being
# right the moment the milestone *is* built and merged and its ``Stato`` line lags behind: the
# document then falls out of **both** lists — no entry in the changelog, and no test asking for one
# — and nothing in ``make check`` can notice. It happened to M11.2, merged on 2026-09-10 and still
# calling itself a proposal.
#
# What closes it has to be a fact read from the repository and not a list somebody keeps: the list
# would go stale exactly like the ``Stato`` line did. The fact is the history of ``main``. This
# repository merges one branch per milestone and says so in the subject — ``Merge M11.2 listening —
# Fase 11 chiusa``, ``Merge M6.1b device refresh``, ``Merge M0.1 + M0.2`` — for all thirty-six
# merges it has. A merge that names no milestone (``Merge platform-choice fix and ADR index test``)
# names nothing, which is what it should do.

MERGE = re.compile(r"^Merge\b")
MILESTONE_ID = re.compile(r"\bM\d+\.\d+[a-z]?\b")
MAIN_REFS = ("main", "origin/main", "refs/remotes/origin/main")


def merged_in(subjects: Iterable[str]) -> set[str]:
    """The milestones the merge commits among ``subjects`` name."""
    return {
        name
        for subject in subjects
        if MERGE.match(subject)
        for name in MILESTONE_ID.findall(subject)
    }


def merged_but_still_proposed(merged: Iterable[str], states: Mapping[str, str]) -> set[str]:
    """The milestones that are in ``main`` and still call themselves a proposal."""
    return {name for name in merged if states.get(name) == PROPOSED}


def _history() -> tuple[list[str], str | None]:
    """The subjects of every commit reachable from main, or the reason they cannot be read.

    The reason is returned rather than swallowed: a shallow clone answers ``git log`` with a
    success and a truncated history, so a test that simply ran would pass while seeing nothing.
    CI checks out with ``fetch-depth: 0`` for this; anywhere else the skip says which precondition
    is missing instead of pretending it was met (ADR 0031 §6).
    """
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=ROOT,
        capture_output=True,
    )
    if shallow.returncode != 0:
        return [], "not a git repository"
    if shallow.stdout.decode().strip() == "true":
        return [], "shallow clone: the history of main is not here (git fetch --unshallow)"
    for ref in MAIN_REFS:
        found = subprocess.run(["git", "log", "--format=%s", ref], cwd=ROOT, capture_output=True)
        if found.returncode == 0:
            return found.stdout.decode("utf-8").splitlines(), None
    return [], f"no main to read: none of {', '.join(MAIN_REFS)} exists"


SUBJECTS, NO_HISTORY = _history()


@pytest.mark.skipif(NO_HISTORY is not None, reason=NO_HISTORY or "")
def test_a_milestone_merged_into_main_cannot_still_call_itself_a_proposal() -> None:
    """The fact is the history, not a list: a list would go stale the same way the line did."""
    merged = merged_in(SUBJECTS)
    assert merged, "no merge commit names a milestone: this test would be vacuous"

    states = {path.stem: state_of(path) for path in milestones()}

    assert merged_but_still_proposed(merged, states) == set()


def test_a_proposal_that_is_already_merged_is_detected() -> None:
    """The negative case, on subjects built here rather than on the history of the day."""
    subjects = ["Merge M1.1 domain model", "feat(m1.1): il dominio"]
    states = {"M1.1": PROPOSED, "M1.2": "Implementata"}

    assert merged_in(subjects) == {"M1.1"}
    assert merged_but_still_proposed(merged_in(subjects), states) == {"M1.1"}


def test_a_merge_that_names_two_milestones_names_both() -> None:
    """``Merge M0.1 + M0.2`` is one commit and two milestones, and the repository has it."""
    assert merged_in(["Merge M0.1 + M0.2"]) == {"M0.1", "M0.2"}


def test_what_is_not_a_merge_of_a_milestone_merges_nothing() -> None:
    """Two independent reasons, and both are needed: a commit on a branch names its milestone in
    lowercase and is not a merge; a merge can be of something that is not a milestone at all."""
    assert merged_in(["docs(m11.2): la spec dell'ascolto"]) == set()
    assert merged_in(["Merge platform-choice fix and ADR index test"]) == set()
    assert merged_in(["Merge M11.2 listening — Fase 11 chiusa"]) == {"M11.2"}
