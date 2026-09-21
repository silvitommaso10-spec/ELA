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
"""The surfaces that compose the question out of its parts (M12.5 dec. F).

A third one added without a line here answers nothing."""

CLI = ROOT / "src" / "ela" / "cli" / "system.py"
"""And the one that shows the question as the sentence it is: ``ela approvals``.

It is an answering surface too — ``ela task approve`` is the first yes anybody gives — and it is
held to the same rule for the facts a sentence cannot carry. What it shows instead of the parts is
``prompt``, which **is** the question; the two machine facts of M13.1 are not in it, so they are
shown beside it."""

OF_A_FILE = ("target", "overwrites")
"""The facts a question about a file names, and that no sentence carries (M13.1 dec. G)."""

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


def test_the_command_line_shows_the_facts_of_a_file_it_offers_a_yes_to() -> None:
    """dec. H, on the third surface that answers: `ela task approve` is the first yes given.

    It shows the question as one sentence — the pages show the parts because a page cannot make
    somebody read a sentence (M12.5 dec. F) — so what it must show beside it is what a sentence
    does not carry: where the write really lands, and whether something is already there.
    """
    source = CLI.read_text(encoding="utf-8")
    unread = [field for field in OF_A_FILE if f'"{field}"' not in source]

    assert not unread, (
        f"`ela approvals` offers a yes to a question that names {unread} and never shows it. "
        "A surface that does not show what the question is about does not answer it (dec. H)."
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
