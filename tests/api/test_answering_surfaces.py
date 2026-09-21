"""A surface may answer a question only if it shows everything that question names (M13.1 dec. H).

The rule is **derivable and closed in both directions**, which is the point of it: not a list of
devices somebody has to keep up to date, but a comparison between the fields a question declares
and the fields each answering surface reads. The day a question learns a new fact, every surface
that offers a yes either shows it or stops being an answering surface — and this test is what
makes that a fact rather than an intention.

It holds for ``CRITICAL`` before ``CRITICAL`` exists, which is why it is written as a rule and not
as a paragraph about the iPhone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.api.schemas import Asked

ROOT = Path(__file__).resolve().parents[2]
ANSWERING = {
    "the Command Center": ROOT / "src" / "ela" / "api" / "console.py",
    "the companion": ROOT / "src" / "ela" / "api" / "companion.py",
}
"""The surfaces that offer a yes. A third one added without a line here answers nothing."""

NOT_SHOWN: dict[str, str] = {
    "description": "shown as the capability's own sentence, not as a pair",
    "goal": "shown in the `asked` fragment with the declared arguments",
    "stated": "shown in the `asked` fragment, one `stated` per argument",
    "risk": "shown by the `pair-risk` fragment, which is what represents the level (§29 design)",
    "max_privacy": "shown as «Dove può andare»",
    "grant_uses": "shown as «Durata», together with grant_seconds",
    "grant_seconds": "shown as «Durata», together with grant_uses",
}
"""Fields shown by a fragment of their own rather than by naming the attribute in a pair.

Each line is a claim somebody made on purpose; a field that arrives without one fails the test
below, which is the whole mechanism: silence is not an answer.
"""


@pytest.mark.parametrize("surface", sorted(ANSWERING), ids=lambda name: name.split()[-1])
def test_an_answering_surface_reads_every_field_a_question_names(surface: str) -> None:
    source = ANSWERING[surface].read_text(encoding="utf-8")
    unread = [
        field
        for field in Asked.model_fields
        if field not in NOT_SHOWN and not re.search(rf"\bfound\.{field}\b", source)
    ]

    assert not unread, (
        f"{surface} offers a yes to a question that names {unread} and never shows "
        f"{'them' if len(unread) > 1 else 'it'}. Either show the field, or add a line to "
        "NOT_SHOWN saying where it is shown instead, or stop offering the answer on that "
        "surface (M13.1 dec. H)."
    )


def test_the_claims_are_about_fields_that_exist() -> None:
    """A claim left behind by a field that went away would excuse the next one silently."""
    assert set(NOT_SHOWN) <= set(Asked.model_fields), set(NOT_SHOWN) - set(Asked.model_fields)


def test_the_rule_can_fail() -> None:
    """The negative case: a surface that shows nothing is refused by the same comparison.

    Without this, a regex that stopped matching would make the rule vacuously true — the shape
    ADR 0026 §7 calls a defence that cannot fire.
    """
    silent = "def answer(): return 'sì'"
    unread = [
        field
        for field in Asked.model_fields
        if field not in NOT_SHOWN and not re.search(rf"\bfound\.{field}\b", silent)
    ]

    assert unread, "the comparison no longer detects a surface that shows nothing"
