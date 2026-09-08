"""The seven questions of §44 and :class:`~ela.domain.ContextQuestion` are the same list.

The binding this milestone exists for. §44 is a bullet list in the specification, and a snapshot
that answered six of its seven lines would be a snapshot nobody could notice was incomplete — so
the enum is read **against the specification** rather than believed, in both directions and in
order: a bullet added to §44 fails until a member is added, a member added fails until §44 says
so, and a reordering fails too, because the order is what makes the two lists comparable at all.

The Italian text lives here and not in ``src``: it is a quotation of the specification, and
quotations of the specification live in ``tests/docs`` already (``test_spec_headings.py``).

The second half is the mechanism of ADR 0032 §3 — a question carries what answers it *and* what
is missing from it, and which is which is **derived** from the fields the snapshot really has.
That is what makes an absence disappear on the day its source arrives, instead of on the day
somebody remembers to delete a line.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.context import held, questions, snapshot_fields
from ela.domain import (
    QUESTION_SOURCES,
    SOURCE_FIELDS,
    ContextQuestion,
    ContextSnapshot,
    ContextSource,
)

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "spec" / "ELA_spec.md"
SECTION = "## 44. Contesto globale"
NEXT_SECTION = re.compile(r"^## \d+\. ")
BULLET = re.compile(r"^- (.+?)[;.]$")

QUESTIONS: dict[str, ContextQuestion] = {
    "cosa sta facendo l'utente": ContextQuestion.CURRENT_ACTIVITY,
    "cosa stava facendo prima": ContextQuestion.PREVIOUS_ACTIVITY,
    "quali task sono in corso": ContextQuestion.TASKS_IN_FLIGHT,
    "quali scadenze esistono": ContextQuestion.DEADLINES,
    "quale dispositivo sta usando": ContextQuestion.DEVICE_IN_USE,
    "quali informazioni sono rilevanti": ContextQuestion.RELEVANT_INFORMATION,
    "cosa sta accadendo nei progetti": ContextQuestion.PROJECT_ACTIVITY,
}
"""Each line of §44, in §44's order, and the member that answers for it."""

ABSENT = frozenset(
    {
        ContextSource.CALENDAR,
        ContextSource.MAIL,
        ContextSource.DOCUMENTS,
        ContextSource.PROJECTS,
        ContextSource.RELEVANCE,
    }
)
"""The five sources §44 asks for that this ELA has no field for. Asserted, never assumed."""


def bullets() -> list[str]:
    """The bullet list of §44, read out of the specification."""
    lines = SPEC_PATH.read_text(encoding="utf-8").splitlines()
    start = lines.index(SECTION)
    found: list[str] = []
    for line in lines[start + 1 :]:
        if NEXT_SECTION.match(line):
            break
        if (bullet := BULLET.match(line)) is not None:
            found.append(bullet.group(1))
    return found


# ----------------------------------------------------------------------------------------
# The enum is §44
# ----------------------------------------------------------------------------------------


def test_the_seven_questions_of_44_are_the_enum_in_order() -> None:
    """Closed in both directions and on the order: the two lists are one list."""
    assert list(QUESTIONS) == bullets()
    assert tuple(QUESTIONS.values()) == tuple(ContextQuestion)
    assert len(ContextQuestion) == 7


def test_every_question_appears_in_a_snapshot_even_the_unanswerable_ones() -> None:
    """A question that vanished when ELA could not answer it is a gap nobody would notice."""
    assert tuple(status.question for status in questions(snapshot_fields())) == tuple(
        ContextQuestion
    )


# ----------------------------------------------------------------------------------------
# Every question has sources, every source has a field
# ----------------------------------------------------------------------------------------


def test_every_question_names_at_least_one_source() -> None:
    """A question with neither an answer nor a named absence is a hole in the picture."""
    assert set(QUESTION_SOURCES) == set(ContextQuestion)
    for question in ContextQuestion:
        assert QUESTION_SOURCES[question], question


def test_every_source_declares_a_field_and_is_used_by_a_question() -> None:
    """No orphan on either side: a source nobody asks for is a source nobody would maintain."""
    assert set(SOURCE_FIELDS) == set(ContextSource)
    used = {source for sources in QUESTION_SOURCES.values() for source in sources}
    assert used == set(ContextSource)


def test_the_five_missing_sources_name_a_field_the_snapshot_does_not_have() -> None:
    """The assertion that stops somebody adding the field and leaving the absence in place.

    This is the whole of ADR 0032 §3 in one line: what is missing is not a list, it is the
    difference between the sources §44 needs and the fields the snapshot carries.
    """
    fields = frozenset(ContextSnapshot.model_fields)
    assert {source for source in ContextSource if SOURCE_FIELDS[source] not in fields} == ABSENT
    assert {source for source in ContextSource if SOURCE_FIELDS[source] not in fields} == ABSENT


def test_the_answerable_sources_name_a_field_that_exists() -> None:
    fields = frozenset(ContextSnapshot.model_fields)
    for source in set(ContextSource) - ABSENT:
        assert SOURCE_FIELDS[source] in fields, source


def test_the_snapshot_has_no_field_that_no_source_names() -> None:
    """A section nobody declared as a source would answer a question nobody could see."""
    declared = set(SOURCE_FIELDS.values()) | {"at", "questions"}
    assert set(ContextSnapshot.model_fields) <= declared


# ----------------------------------------------------------------------------------------
# What §44 asks for and this ELA cannot answer
# ----------------------------------------------------------------------------------------


def test_the_deadlines_question_is_answered_and_incomplete_at_the_same_time() -> None:
    """The row that decided the shape (ADR 0032 §3): both lists non-empty, and it is not a bug."""
    answered, missing = held(QUESTION_SOURCES[ContextQuestion.DEADLINES], snapshot_fields())

    assert answered == (ContextSource.TASK_DEADLINES,)
    assert missing == (ContextSource.CALENDAR,)


def test_the_two_questions_with_no_source_at_all_say_so_by_name() -> None:
    """§44's own worked example rests on these: relevance, mail, documents, projects."""
    for question, expected in (
        (
            ContextQuestion.RELEVANT_INFORMATION,
            (ContextSource.RELEVANCE, ContextSource.MAIL, ContextSource.DOCUMENTS),
        ),
        (
            ContextQuestion.PROJECT_ACTIVITY,
            (ContextSource.PROJECTS, ContextSource.MAIL, ContextSource.DOCUMENTS),
        ),
    ):
        answered, missing = held(QUESTION_SOURCES[question], snapshot_fields())
        assert answered == ()
        assert missing == expected
