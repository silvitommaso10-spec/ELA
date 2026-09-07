"""What the CLI prints, and what it deliberately does not print (ADR 0024 §6).

Plain aligned text: no boxes, no colour, nothing that becomes noise when the output goes through
a pipe. The claim is small enough to test directly.
"""

from __future__ import annotations

import json

import pytest

from ela.cli.output import emit, fields, table, text
from tests.cli.support import Cli

BOXES = "─│┌┐└┘├┤┬┴┼╭╮╰╯━┃"


def test_a_value_that_is_absent_is_visibly_absent() -> None:
    assert text(None) == "—"
    assert text([]) == "—"
    assert text({}) == "—"


def test_a_boolean_is_a_word_and_not_a_python_literal() -> None:
    assert (text(True), text(False)) == ("yes", "no")


def test_a_list_and_a_mapping_are_readable_on_one_line() -> None:
    assert text(["a", "b"]) == "a, b"
    assert text({"anthropic": "AVAILABLE"}) == "anthropic: AVAILABLE"


def test_a_table_aligns_its_columns_and_upper_cases_the_header() -> None:
    rendered = table(("id", "state"), [("1", "QUEUED"), ("22222", "COMPLETED")])

    lines = rendered.splitlines()
    assert lines[0] == "ID     STATE"
    assert lines[1] == "1      QUEUED"
    assert lines[2] == "22222  COMPLETED"


def test_an_empty_table_is_a_sentence_and_not_a_bare_header() -> None:
    assert table(("id",), []) == "nothing to show"


def test_a_block_of_fields_aligns_its_names() -> None:
    assert fields([("id", 1), ("state", None)]) == "id     1\nstate  —"


def test_json_is_the_payload_and_the_text_is_dropped(capsys: pytest.CaptureFixture[str]) -> None:
    emit({"a": [1, 2]}, True, "a table nobody asked for")

    printed = capsys.readouterr().out
    assert json.loads(printed) == {"a": [1, 2]}
    assert "table" not in printed


def test_without_json_the_text_is_what_is_printed(capsys: pytest.CaptureFixture[str]) -> None:
    emit({"a": 1}, False, "id  1")

    assert capsys.readouterr().out.strip() == "id  1"


async def test_no_command_draws_a_box_or_paints_a_colour(cli: Cli) -> None:
    """typer draws its own help; what ELA prints as an *answer* is plain text."""
    for command in (("health",), ("diagnostics",), ("device", "list"), ("provider", "list")):
        result = await cli(*command)

        assert result.exit_code == 0
        assert not set(result.stdout) & set(BOXES), command
        assert "\x1b[" not in result.stdout


async def test_every_reading_command_can_answer_in_json(cli: Cli) -> None:
    for command in (
        ("health",),
        ("diagnostics",),
        ("approvals",),
        ("task", "list"),
        ("audit", "tail"),
        ("audit", "verify"),
        ("device", "list"),
        ("provider", "list"),
    ):
        result = await cli(*command, "--json")

        assert result.exit_code == 0, command
        json.loads(result.stdout)  # it parses, which is the whole promise of --json
