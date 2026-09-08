"""The derivation of ADR 0032 §3, proved instead of believed.

``held`` is a pure function of two arguments — the sources a question names and the fields the
snapshot has — and it is pure for exactly this reason: the property this milestone was built to
guarantee is about a **future** commit, the one that adds a calendar. A comment claiming "the
absence will disappear on its own" cannot be checked. Calling the function with the field added
can.

It is the shape ADR 0031 §3 already uses for the ADR index: a comparison that is a pure function
of two arguments has every one of its outcomes exercised here, rather than waited for.
"""

from __future__ import annotations

from ela.context import held, snapshot_fields
from ela.domain import QUESTION_SOURCES, SOURCE_FIELDS, ContextQuestion, ContextSource

DEADLINES = QUESTION_SOURCES[ContextQuestion.DEADLINES]


def test_a_source_whose_field_arrives_stops_being_missing() -> None:
    """The day the calendar lands, ``DEADLINES`` has nothing missing — and nobody edits a list."""
    fields = snapshot_fields()
    assert held(DEADLINES, fields) == ((ContextSource.TASK_DEADLINES,), (ContextSource.CALENDAR,))

    with_calendar = fields | {SOURCE_FIELDS[ContextSource.CALENDAR]}
    answered, missing = held(DEADLINES, with_calendar)

    assert answered == (ContextSource.TASK_DEADLINES, ContextSource.CALENDAR)
    assert missing == ()


def test_a_question_with_no_source_at_all_becomes_answerable_the_same_way() -> None:
    """Relevance is a judgement today; the mechanism does not care what makes it arrive."""
    sources = QUESTION_SOURCES[ContextQuestion.RELEVANT_INFORMATION]
    fields = snapshot_fields() | {SOURCE_FIELDS[source] for source in sources}

    assert held(sources, fields) == (sources, ())


def test_a_source_whose_field_goes_away_becomes_missing() -> None:
    """The fail-safe direction, and the one that matters more: an absence is never assumed away."""
    fields = snapshot_fields() - {SOURCE_FIELDS[ContextSource.TASK_DEADLINES]}

    assert held(DEADLINES, fields) == ((), (ContextSource.TASK_DEADLINES, ContextSource.CALENDAR))


def test_the_partition_is_total_and_disjoint() -> None:
    """Every source lands in exactly one of the two lists, and the order of each is the input's."""
    every = tuple(ContextSource)
    answered, missing = held(every, snapshot_fields())

    assert set(answered) | set(missing) == set(every)
    assert not set(answered) & set(missing)
    assert answered + missing != ()
    assert answered == tuple(s for s in every if s in answered)
    assert missing == tuple(s for s in every if s in missing)


def test_no_sources_is_no_answer_and_no_absence() -> None:
    """The empty case, which no question has and every implementation still has to handle."""
    assert held((), snapshot_fields()) == ((), ())


def test_the_snapshot_fields_are_read_from_the_model_and_not_listed() -> None:
    """A hand-written list here would make the mechanism a promise instead of a derivation."""
    from ela.domain import ContextSnapshot

    assert snapshot_fields() == frozenset(ContextSnapshot.model_fields)
