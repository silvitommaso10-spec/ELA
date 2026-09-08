"""``ela context``: what is going on, and the block that says what ELA has no source for.

The assertion that matters is the last block. A terminal picture that showed only what ELA can
answer would read as complete, and §44's own worked example rests on three sources this ELA does
not have. The second is the truncation: ``20 of 137`` and never a bare ``20``.
"""

from __future__ import annotations

import json

import pytest

from ela.cli.context import _answer, _of
from ela.cli.errors import OK
from ela.domain import ContextQuestion, ContextSource
from tests.cli.support import Cli, plain


async def test_it_prints_all_seven_questions_of_44(cli: Cli) -> None:
    answered = await cli("context")

    assert answered.exit_code == OK
    output = plain(answered.stdout).lower()
    for question in ContextQuestion:
        assert f"§44 {question.value.lower()}" in output


async def test_it_names_what_is_missing_rather_than_staying_silent(cli: Cli) -> None:
    """The five sources §44 asks for that this ELA has no field for."""
    output = plain((await cli("context")).stdout)

    for absent in (ContextSource.CALENDAR, ContextSource.MAIL, ContextSource.PROJECTS):
        assert absent.value in output
    assert "missing" in output


async def test_the_json_form_is_the_whole_snapshot(cli: Cli) -> None:
    answered = await cli("context", "--json")

    assert answered.exit_code == OK
    payload = json.loads(answered.stdout)
    assert set(payload) == {"at", "activity", "device", "work", "deadlines", "recent", "questions"}
    assert len(payload["questions"]) == len(ContextQuestion)


async def test_a_live_task_is_printed_with_its_goal(cli: Cli) -> None:
    await cli("task", "create", "preparare la riunione")

    output = plain((await cli("context")).stdout)

    assert "preparare la riunione" in output


@pytest.mark.parametrize(
    "shown, total, expected", [(0, 0, "0"), (3, 3, "3"), (20, 137, "20 of 137")]
)
def test_a_truncated_count_says_how_many_of_how_many(shown: int, total: int, expected: str) -> None:
    """ "There are no more" and "I am not showing you the rest" must not look the same."""
    assert _of({"shown": shown, "total": total}) == expected


def test_a_question_with_nothing_behind_it_says_nothing_and_names_the_gap() -> None:
    """``nothing`` and never an empty cell: a blank reads as "no answer needed"."""
    rendered = _answer({"answered_by": [], "missing": ["calendar", "mail"]})

    assert rendered.startswith("nothing")
    assert "missing: calendar, mail" in rendered


def test_a_question_fully_answered_names_no_gap() -> None:
    assert _answer({"answered_by": ["tasks"], "missing": []}) == "tasks"
