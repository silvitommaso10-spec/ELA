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
from typing import Final

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
# would go stale exactly like the ``Stato`` line did. The fact is the history of ``main``, where a
# milestone's branch is merged with a title that says so — ``Merge M11.2 listening — Fase 11
# chiusa``, ``Merge M0.1 + M0.2``, ``Merge M13.2: il terminale — …``, ``Merge m13.1-filesystem-…``.
#
# **What a title merges is its head, not its prose** (2026-09-25). Until then every id anywhere in
# a merge's title counted, and only in capitals. Two consequences, one in each direction. The merge
# of two registrations, ``a60eda0``, said in its prose which milestones it registered, and turned
# the CI of ``main`` red for two milestones that are rightly still proposals. And the two merges
# whose head is the branch in lowercase, ``m13.1-…`` and ``m17.2-…``, named nothing, so for M13.1
# and M17.2 this defence could not have fired. The head is the text after ``Merge`` and before the
# prose — the first ``: `` or `` — ``. It names milestones in two forms: ids at its start, in
# capitals, joined by ``+``; or, when it is one word, the ids of a branch name in lowercase. A head
# of several words that does not start with an id — ``main in docs-…``, ``remote-tracking branch
# 'origin/main' into …``, ``platform-choice fix and ADR index test`` — names nothing.
#
# **A branch whose name begins with ``docs-`` registers milestones and merges none.** That is a
# name, and a name can lie, so the name is checked against what git says each such merge brought
# into ``main``: never code (``test_a_registration_branch_brought_no_code_into_main``).

MERGE = re.compile(r"^Merge\s+(?P<rest>.+)$")
PROSE = re.compile(r": | — ")
MILESTONE_ID = re.compile(r"\bM\d+\.\d+[a-z]?\b")
IDS_FIRST = re.compile(r"^M\d+\.\d+[a-z]?(?:\s*\+\s*M\d+\.\d+[a-z]?)*")
BRANCH_ID = re.compile(r"(?:^|[-_/])m(\d+\.\d+[a-z]?)(?=$|[-_/])")
REGISTRATION: Final = "docs-"
"""The prefix of a branch that registers milestones: its merge brings no milestone into ``main``."""
CODE: Final = "src/"
MAIN_REFS = ("main", "origin/main", "refs/remotes/origin/main")


def head(subject: str) -> str | None:
    """What a merge's title says it merges: the words after ``Merge`` and before the prose.

    ``None`` for a title that is not a merge.
    """
    found = MERGE.match(subject)
    if found is None:
        return None
    return PROSE.split(found.group("rest"), maxsplit=1)[0].strip()


def named_by(merged: str) -> set[str]:
    """The milestones a head names (the comment above says in which two forms)."""
    first = IDS_FIRST.match(merged)
    if first is not None:
        return set(MILESTONE_ID.findall(first.group(0)))
    if merged.split() != [merged] or merged.startswith(REGISTRATION):
        return set()
    return {f"M{number}" for number in BRANCH_ID.findall(merged)}


def merged_in(subjects: Iterable[str]) -> set[str]:
    """The milestones the merge commits among ``subjects`` merge, read from their heads."""
    return {
        name
        for subject in subjects
        if (merged := head(subject)) is not None
        for name in named_by(merged)
    }


def brought_code(paths: Iterable[str]) -> bool:
    """Whether a merge that changed ``paths`` brought code into ``main``."""
    return any(path.startswith(CODE) for path in paths)


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


def _git(*arguments: str) -> list[str]:
    found = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, check=True)
    return found.stdout.decode("utf-8").splitlines()


def first_parent_merges() -> list[tuple[str, str]]:
    """``(sha, title)`` of every merge **into** ``main``: its first-parent history, where a merge of
    ``main`` into a branch never appears."""
    for ref in MAIN_REFS:
        known = subprocess.run(["git", "rev-parse", "--verify", "--quiet", ref], cwd=ROOT)
        if known.returncode == 0:
            lines = _git("log", "--first-parent", "--merges", "--format=%H%x09%s", ref)
            return [(sha, title) for sha, title in (line.split("\t", 1) for line in lines)]
    raise AssertionError(NO_HISTORY)


def changed_by(sha: str) -> list[str]:
    """The paths a merge changed in ``main``: the diff from its first parent."""
    return _git("diff", "--name-only", f"{sha}^1", sha)


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


# ----------------------------------------------------------------------------------------
# The head of a title, and the prose after it (2026-09-25)
# ----------------------------------------------------------------------------------------
#
# Each case is a title of ``main``, copied as it is; the last test checks that it still is one.

A60EDA0: Final = (
    "Merge docs-m17.2b-e-m17.5: M17.2b e M17.5 registrate — un esito finale che sparisce, e il Task"
    " Center che non aveva proprietaria"
)
"""The merge of two registrations, whose prose names the two milestones it registered."""
MAIN_INTO_A_BRANCH: Final = (
    "Merge main in docs-m17.2b-e-m17.5: M13.2 (e383800) sotto le due registrazioni",
    "Merge remote-tracking branch 'origin/main' into m13.2-terminale",
)
"""``08da04d``, and one before it: ``main`` merged into a branch, which merges nothing into main."""
DOCS_FASE_13: Final = (
    "Merge docs-fase-13: la Fase 13 registrata — sei milestone, il criterio che una registrazione"
    " non è un inizio, e §1 che torna vera"
)
M13_1_BY_ITS_BRANCH: Final = (
    "Merge m13.1-filesystem-e-il-primo-high: il filesystem fuori dalla workspace e il primo HIGH"
    " — lo scope legato al fatto, il grant nato da un sì, e nessuna domanda già condannata"
)
M17_2_BY_ITS_BRANCH: Final = (
    "Merge m17.2-command-center: il Command Center — la terza identità, il tetto derivato dal"
    " socket, e due regole che smettono di nominare un file"
)


def test_the_prose_after_the_head_never_names_a_merged_milestone() -> None:
    """``a60eda0``: the prose names M17.2b and M17.5, and the head is the branch that merged."""
    assert set(MILESTONE_ID.findall(A60EDA0)) == {"M17.2b", "M17.5"}  # the case bites

    # The same prose behind a head that does merge a milestone: only the head counts.
    spliced = A60EDA0.replace("docs-m17.2b-e-m17.5", "m17.2-command-center", 1)
    assert merged_in([spliced]) == {"M17.2"}


def test_a_merge_of_main_into_a_branch_merges_nothing() -> None:
    """``08da04d``: its prose names M13.2, and what it merges is ``main``, into a branch."""
    assert "M13.2" in MAIN_INTO_A_BRANCH[0]  # the case bites
    assert merged_in(MAIN_INTO_A_BRANCH) == set()


def test_a_registration_branch_merges_nothing() -> None:
    """A branch whose name begins with ``docs-`` registers milestones and merges none.

    The negative case is the same title without the prefix: the branch name then names the two
    milestones, which is exactly what makes the prefix the fact that decides.
    """
    assert merged_in([A60EDA0, DOCS_FASE_13]) == set()
    assert merged_in([A60EDA0.replace("docs-", "", 1)]) == {"M17.2b", "M17.5"}


def test_a_head_that_is_the_branch_in_lowercase_names_its_milestone() -> None:
    """Until 2026-09-25 these two named nothing: for M13.1 and M17.2 the defence could not fire."""
    assert merged_in([M13_1_BY_ITS_BRANCH]) == {"M13.1"}
    assert merged_in([M17_2_BY_ITS_BRANCH]) == {"M17.2"}


@pytest.mark.skipif(NO_HISTORY is not None, reason=NO_HISTORY or "")
def test_the_titles_of_these_cases_are_titles_of_main() -> None:
    """A case built on a title nobody wrote would prove the parser, not the history."""
    for title in (
        A60EDA0,
        *MAIN_INTO_A_BRANCH,
        DOCS_FASE_13,
        M13_1_BY_ITS_BRANCH,
        M17_2_BY_ITS_BRANCH,
    ):
        assert title in SUBJECTS, title


@pytest.mark.skipif(NO_HISTORY is not None, reason=NO_HISTORY or "")
def test_a_registration_branch_brought_no_code_into_main() -> None:
    """The prefix is a name, and names can lie: what every ``docs-`` merge brought into ``main`` is
    read from git, and none of it is code. The negative case is the merge of M13.1's branch, which
    brought code — the thing a branch that only registers never brings."""
    merges = first_parent_merges()
    registrations = [
        (sha, title)
        for sha, title in merges
        if (merged := head(title)) is not None and merged.startswith(REGISTRATION)
    ]
    assert registrations, "no registration branch was ever merged: this test would be vacuous"
    for sha, title in registrations:
        assert not brought_code(changed_by(sha)), title

    (m13_1,) = [sha for sha, title in merges if title == M13_1_BY_ITS_BRANCH]
    assert brought_code(changed_by(m13_1))
