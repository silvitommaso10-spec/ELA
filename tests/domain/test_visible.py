"""The one rendering that keeps a surface from being rewritten by what it shows (M13.2 dec. 13).

``visible`` makes every character that deceives a reader into something a reader sees: the C0 and
C1 controls and DEL, the bidirectional controls that reorder a line, the zero-width characters that
hide a difference inside a word — and the backslash itself, or ``\\x1b`` written by a program and
the ESC character would read the same. In a question, newline and tab too: an argument
``"status\\n--force"`` would read as two. In the output of a result they stay, because there they
are the text.

It lives in ``ela.domain`` and not in ``ela.api``, **corrected implementing**: the SPEC placed it in
``ela.api`` on the premise that the CLI imports the API already, and rule 28 says it may not —
only ``cli/serve.py`` does. ``ela.domain`` is the leaf both import.
"""

from __future__ import annotations

import pytest

from ela.domain import listed, visible

ESC = "\x1b"
RLO = "\u202e"


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        (f"{ESC}[31mROSSO{ESC}[0m", "\\x1b[31mROSSO\\x1b[0m"),
        ("\x07\x00\x7f", "\\x07\\x00\\x7f"),
        ("\x85\x9b", "\\x85\\x9b"),
        (f"abc{RLO}def", "abc\\u202edef"),
        ("\u2066x\u2069", "\\u2066x\\u2069"),
        ("a\u200bb\u200dc\u2060d\ufeff", "a\\u200bb\\u200dc\\u2060d\\ufeff"),
        ("C:\\x1b", "C:\\\\x1b"),
        ("già è così", "già è così"),
    ],
)
def test_what_deceives_a_reader_is_made_visible(raw: str, shown: str) -> None:
    assert visible(raw, lines=True) == shown
    assert visible(raw, lines=False) == shown


def test_a_backslash_written_by_a_program_and_an_escape_do_not_read_the_same() -> None:
    assert visible("\\x1b", lines=True) != visible(ESC, lines=True)


def test_in_a_question_a_newline_and_a_tab_are_visible_too() -> None:
    assert visible("status\n--force\tx", lines=False) == "status\\n--force\\tx"


def test_in_an_output_a_newline_and_a_tab_are_the_text() -> None:
    assert visible("uno\ndue\tfine\n", lines=True) == "uno\ndue\tfine\n"


def test_a_carriage_return_is_never_the_text() -> None:
    """``\\r`` rewrites the line it is on: in an output it would hide what came before it."""
    assert visible("sì\rno", lines=True) == "sì\\rno"


def test_a_list_shows_where_every_argument_begins_and_ends() -> None:
    """Decision 12: never recomposed into a line of shell, never joined with a comma."""
    assert listed(["a, b"]) != listed(["a", "b"])
    assert listed(["git status --short"]) != listed(["git", "status", "--short"])
    assert listed(["la parola", "girasole"]) == '["la parola", "girasole"]'
    assert listed([]) == "[]"


def test_a_quote_inside_an_argument_does_not_end_it() -> None:
    assert listed(['a", "b']) == '["a\\", \\"b"]'
    assert listed(['a", "b']) != listed(["a", "b"])


def test_an_argument_in_a_list_is_rendered_as_a_question_renders() -> None:
    assert listed([f"x{ESC}\ny"]) == '["x\\x1b\\ny"]'
