"""§21 and ``scripts/prova_m6_3c.py`` say the same thing (M6.3c, proposal 10; criterion 11).

The guide is the source of truth, and the script reads it: this file reads §21 with the script's
own reader and asserts, both ways, that every mechanical step has its markers and every marker
its step; that every ``guarda`` is in the vocabulary and every word of the vocabulary is used; that
every ``ferma`` names a side the script knows; and that the lines that come from the code — the
labels of ``ela task run``, the words of ``halt``, the reasons of the two pages — are the code's.

**And the comparison has its negative case** (C-R22): run on recorded outputs that are wrong — the
wrong side of a browser, an empty reason, a ``sleep 97`` left alive —, it must find what is missing,
and it must find nothing on the right ones.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.api.companion import STOPPED as STOPPED_BY_THE_PHONE
from ela.api.console import STOPPED as STOPPED_BY_THE_CONSOLE
from ela.cli.output import EMPTY
from ela.cli.tasks import HALT_WORDS, RUN_LABELS
from ela.domain import Halt

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m6_3c.py"
GUIDE = ROOT / "docs" / "GETTING_STARTED.md"


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("prova_m6_3c", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def guide() -> str:
    return GUIDE.read_text(encoding="utf-8")


def marked() -> dict[int, list[Any]]:
    by_step: dict[int, list[Any]] = script().steps(script().blocks(guide()))
    return by_step


def kinds(blocks: list[Any]) -> list[str]:
    return [block.kind for block in blocks]


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    section = script().section(guide())
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section, re.MULTILINE)}
    found = marked()

    assert found, "the section has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section)
    assert len(every_marker) == sum(len(blocks) for blocks in found.values()), (
        "a marker the reader did not take: it is not right above a fenced block"
    )


def test_every_mechanical_step_has_its_commands_and_what_they_must_print() -> None:
    for number, blocks in marked().items():
        found = kinds(blocks)
        assert "comando" in found, number
        assert "atteso" in found, number
        assert found.index("comando") < found.index("atteso"), number


def test_a_stop_is_watched_for_and_comes_after_the_commands_that_run_the_task() -> None:
    stopped = {number: blocks for number, blocks in marked().items() if "ferma" in kinds(blocks)}

    assert set(stopped) == {2, 3, 4, 8}
    for number, blocks in stopped.items():
        found = kinds(blocks)
        assert found.count("ferma") == found.count("guarda") == 1, number
        assert found.index("comando") < found.index("guarda") < found.index("ferma"), number
        (side,) = [block.body.strip() for block in blocks if block.kind == "ferma"]
        assert side in script().SIDES, (number, side)


def test_the_sides_of_the_guide_are_the_table_of_the_spec() -> None:
    sides = {
        number: block.body.strip()
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == "ferma"
    }

    assert sides == {
        2: "prima del punto",
        3: "prima del punto",
        4: "dopo il punto",
        8: "dopo il punto",
    }


def test_every_guarda_is_in_the_vocabulary_and_every_word_of_it_is_used() -> None:
    used = {
        script().sign_of(block)[0]
        for blocks in marked().values()
        for block in blocks
        if block.kind == "guarda"
    }

    assert used == set(script().SIGNS)


def test_a_guarda_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(ValueError, match="not in the vocabulary"):
        script().sign_of(script().Block(9, "guarda", "aspetta due secondi"))
    with pytest.raises(ValueError, match="not in the vocabulary"):
        script().sign_of(script().Block(9, "guarda", "processo"))


def test_the_only_question_that_skips_a_step_is_the_node_s() -> None:
    asking = [number for number, blocks in marked().items() if kinds(blocks)[0] == "se"]

    assert asking == [8]
    assert all("se" not in kinds(blocks)[1:] for blocks in marked().values()), (
        "a question that skips is the first block of its step"
    )


def expected_lines() -> list[str]:
    return [
        line
        for blocks in marked().values()
        for block in blocks
        if block.kind == "atteso"
        for line in block.lines
    ]


def test_the_words_of_the_stopped_step_are_the_code_s() -> None:
    said = [
        " ".join(line.split()[2:])
        for line in expected_lines()
        if line.startswith(RUN_LABELS[-1] + " ")
    ]

    assert said
    assert set(said) <= {*HALT_WORDS.values(), EMPTY}
    assert set(HALT_WORDS.values()) & set(said), "no value of halt is checked"


def test_the_reasons_are_the_words_the_script_and_the_pages_send() -> None:
    reasons = [line for line in expected_lines() if line.startswith("reason ")]

    assert any(f"({script().STOP_WORDS})" in line for line in reasons)
    assert any(f"({STOPPED_BY_THE_CONSOLE})" in line for line in reasons)
    assert any(f"({STOPPED_BY_THE_PHONE})" in line for line in reasons)


def test_the_plans_the_commands_name_exist() -> None:
    plans = re.findall(r"--file (docs/examples/[\w-]+\.json)", script().section(guide()))

    assert plans
    assert all((ROOT / plan).is_file() for plan in plans)
    assert "docs/examples/terminal-stop.json" in plans


# ----------------------------------------------------------------------------------------
# The comparison, on outputs recorded right and wrong
# ----------------------------------------------------------------------------------------

RUN_RIGHT = """\
outcome        cancelled
reason         cancel: EXECUTING -> CANCELLED (la prova di M6.3c)
state          CANCELLED
steps handled  b4c2d7e1-5a3f-4b69-8d20-000000000001
stopped step   had not acted
"""
EXPECTED_RUN = [
    "outcome        cancelled",
    "reason         cancel: EXECUTING -> CANCELLED (la prova di M6.3c)",
    "stopped step   had not acted",
]


def test_the_right_output_is_found_whatever_its_spaces() -> None:
    assert script().missing(EXPECTED_RUN, RUN_RIGHT) == []
    assert script().missing(EXPECTED_RUN, RUN_RIGHT.replace("  ", " ")) == []


def test_an_empty_reason_is_what_is_missing() -> None:
    wrong = RUN_RIGHT.replace("cancel: EXECUTING -> CANCELLED (la prova di M6.3c)", EMPTY)

    assert script().missing(EXPECTED_RUN, wrong) == [
        "reason cancel: EXECUTING -> CANCELLED (la prova di M6.3c)"
    ]


def test_the_other_side_of_a_browser_is_what_is_missing() -> None:
    """The stop landed after the navigation: the page was read, and the step had acted."""
    wrong = RUN_RIGHT.replace("had not acted", HALT_WORDS[Halt.ACTED_VERIFIED])

    assert script().missing(EXPECTED_RUN, wrong) == ["stopped step had not acted"]


def test_a_sleep_left_alive_is_what_is_missing() -> None:
    assert script().missing(["0"], "1\n") == ["0"]
    assert script().missing(["0"], "0\n") == []


def test_the_id_of_the_task_is_put_where_the_guide_writes_it() -> None:
    assert script().missing(["task <id> CANCELLED"], "task abc CANCELLED", "abc") == []
    assert script().missing(["task <id> CANCELLED"], "task abd CANCELLED", "abc") != []


def detail(state: str) -> dict[str, Any]:
    return {"steps": [{"state": state}]}


def result(status: str, code: str | None = None) -> dict[str, Any]:
    return {"status": status, "error": None if code is None else {"code": code}}


@pytest.mark.parametrize(
    ("state", "results", "side"),
    [
        ("PENDING", [], "prima dello step"),
        ("CANCELLED", [], "prima del tool"),
        ("CANCELLED", [result("STARTED")], "prima del tool"),
        ("CANCELLED", [result("CANCELLED", "execution.stopped")], "prima del punto"),
        (
            "CANCELLED",
            [result("STARTED"), result("CANCELLED", "execution.stopped")],
            "prima del punto",
        ),
        ("COMPLETED", [result("SUCCEEDED")], "dopo il punto"),
        ("FAILED", [result("STARTED"), result("FAILED", "terminal.stopped")], "dopo il punto"),
    ],
)
def test_the_side_a_stop_landed_on_is_read_from_the_step_and_its_results(
    state: str, results: list[dict[str, Any]], side: str
) -> None:
    assert script().side_of(detail(state), results) == side
