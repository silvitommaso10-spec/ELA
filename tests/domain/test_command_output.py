"""``CommandOutput``: the numbers of a stream agree with each other, or the model refuses them.

Decision 8 of M13.2 (ADR 0047): a result that keeps a head and a tail says **where** it cut and
**how much** is missing, in raw bytes counted before any decoding. The relations between those
numbers are not a convention the tool is trusted to keep — the model states them, the precedent
being ``ContextWork`` — and each one has its negative case here, because a validator that cannot
refuse is a defence that cannot fire (ADR 0026 §7).
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ela.domain import CommandOutput

WHOLE: dict[str, Any] = {
    "head": "uno\n",
    "tail": "",
    "cut_after": 4,
    "missing": 0,
    "shown": 4,
    "total": 4,
    "replaced": 0,
}
CUT: dict[str, Any] = {
    "head": "12",
    "tail": "89",
    "cut_after": 2,
    "missing": 6,
    "shown": 4,
    "total": 10,
    "replaced": 0,
}


@pytest.mark.parametrize("numbers", [WHOLE, CUT], ids=["whole", "cut"])
def test_coherent_numbers_are_a_stream(numbers: dict[str, Any]) -> None:
    assert CommandOutput(**numbers).model_dump() == numbers


def test_nothing_at_all_is_a_stream_too() -> None:
    empty = CommandOutput(head="", tail="", cut_after=0, missing=0, shown=0, total=0, replaced=0)

    assert empty.total == 0


@pytest.mark.parametrize(
    ("change", "why"),
    [
        ({"total": 11}, "total is shown plus missing"),
        ({"missing": 5}, "total is shown plus missing"),
        ({"cut_after": 5}, "the cut is after the head, inside what is shown"),
        ({"shown": 3, "total": 9}, "shown is the bytes of the head and of the tail"),
        ({"head": "123"}, "the head is cut_after bytes long"),
        ({"tail": "8"}, "the tail is what is shown after the head"),
        ({"replaced": -1}, "a count is never negative"),
        ({"missing": -1, "total": 3}, "a count is never negative"),
    ],
)
def test_numbers_that_contradict_each_other_are_refused(change: dict[str, Any], why: str) -> None:
    with pytest.raises(ValidationError):
        CommandOutput(**{**CUT, **change})


def test_without_a_cut_there_is_no_tail() -> None:
    """«Senza taglio ``missing`` è zero e la coda è vuota»: everything is in the head."""
    with pytest.raises(ValidationError):
        CommandOutput(**{**WHOLE, "head": "", "tail": "uno\n", "cut_after": 0})


def test_a_replacement_loosens_only_the_byte_lengths() -> None:
    """A replaced sequence is one character for one to four bytes: the lengths of the text can no
    longer be compared with the raw counts, and the counts themselves still must agree."""
    replaced = CommandOutput(
        head="a\ufffd", tail="", cut_after=2, missing=0, shown=2, total=2, replaced=1
    )

    assert replaced.replaced == 1
    with pytest.raises(ValidationError):
        CommandOutput(head="a\ufffd", tail="", cut_after=2, missing=1, shown=2, total=2, replaced=1)


def test_the_model_is_frozen() -> None:
    kept = CommandOutput(**CUT)

    with pytest.raises(ValidationError):
        kept.total = 3  # type: ignore[misc]
