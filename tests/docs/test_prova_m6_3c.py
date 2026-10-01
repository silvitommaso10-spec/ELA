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
from ela.cli.tasks import HALT_WORDS, RUN_LABELS, _detail, _ran, _results
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


def signs() -> dict[int, Any]:
    return {
        number: script().sign_of(block)
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == "guarda"
    }


def test_every_guarda_is_in_the_vocabulary_and_every_word_of_it_is_used() -> None:
    assert {sign.word for sign in signs().values()} == set(script().SIGNS)


def test_only_the_step_on_the_pc_wants_its_result_written_by_a_node() -> None:
    """F of the review: the script checks that the step went to the PC."""
    assert [number for number, sign in signs().items() if sign.on_a_node] == [8]
    assert signs()[8] == script().Sign("risultato", "STARTED", on_a_node=True)


def test_a_guarda_outside_the_vocabulary_is_refused() -> None:
    with pytest.raises(ValueError, match="not in the vocabulary"):
        script().sign_of(script().Block(9, "guarda", "aspetta due secondi"))
    with pytest.raises(ValueError, match="not in the vocabulary"):
        script().sign_of(script().Block(9, "guarda", "processo"))
    with pytest.raises(ValueError, match="not in the vocabulary"):
        script().sign_of(script().Block(9, "guarda", "processo sleep 97 su un nodo"))


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


def test_the_ids_of_other_steps_are_of_earlier_steps_that_made_a_task() -> None:
    """D of the review: a question names the tasks of steps 2–4 by their id, which the script
    fills with the task of their last round — so each one must be of a step that made a task, and
    run before the question."""
    made = {
        number
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == "comando" and " task create " in f" {block.body} "
    }
    for number, blocks in marked().items():
        for block in blocks:
            for named in script().STEP_ID.findall(block.body):
                assert int(named) in made, (number, named)
                assert int(named) < number, (number, named)
    named_by_the_eye = {
        int(named)
        for blocks in marked().values()
        for block in blocks
        if block.kind == "occhio"
        for named in script().STEP_ID.findall(block.body)
    }
    assert named_by_the_eye == {2, 3, 4}


def test_the_script_fills_the_id_of_a_step_and_leaves_one_it_does_not_have() -> None:
    filled = script().filled(
        "i task <id del passo 2> e <id del passo 3>; questo <id>", "t", {2: "a"}
    )

    assert filled == "i task a e <id del passo 3>; questo t"


def test_the_hand_of_the_console_and_of_the_phone_confirms_before_enter() -> None:
    """C of the review: an Enter before the confirmation would run the echo, and the step would
    fail without saying why."""
    for number in (5, 6):
        (hand,) = [block.body for block in marked()[number] if block.kind == "mano"]
        assert "poi conferma" in hand
        assert hand.endswith("premi Invio.")


def test_the_pc_runs_from_the_branch_because_its_runner_changed() -> None:
    """E of the review: the protocol does not change, the node's runner does."""
    section = script().section(guide())
    step = section[section.index("### 7. ") : section.index("### 8. ")]

    assert "src/ela/node/runner.py" in step
    assert "il protocollo fra il\nCore e il nodo non cambia" in step
    assert "è una prova del Core,\ne il nodo non cambia" not in step
    assert "git checkout main" in step


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


def test_ten_sleeps_left_alive_are_not_zero() -> None:
    """A of the review: a substring would find «0» in «10»; whole words do not."""
    assert script().missing(["0"], "10\n") == ["0"]
    assert script().missing(["stopped step had acted"], "stopped step had acted; its") != []


def test_two_lines_in_the_wrong_order_are_what_is_missing() -> None:
    """A of the review: STARTED before CANCELLED, as the guide writes them."""
    expected = ["x browser.act STARTED browser-act", "x browser.act CANCELLED browser-act"]
    right = "x  browser.act  STARTED  browser-act  t1\nx  browser.act  CANCELLED  browser-act  t2\n"
    inverted = "\n".join(reversed(right.splitlines())) + "\n"

    assert script().missing(expected, right) == []
    assert script().missing(expected, inverted) == ["x browser.act CANCELLED browser-act"]


def test_a_line_is_a_run_of_whole_words_inside_one_line() -> None:
    assert script().contains(["a", "b", "c", "d"], ["b", "c"])
    assert not script().contains(["a", "b", "c", "d"], ["b", "d"])
    assert not script().contains(["ab", "c"], ["b", "c"])
    assert not script().contains(["a", "b"], [])


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


# ----------------------------------------------------------------------------------------
# Every expected block, against what the command line prints for the outcome the step expects
# ----------------------------------------------------------------------------------------

TASK = "7c1e2d3f-0a4b-4c5d-8e6f-000000000042"
STEP_OF = {
    2: "b4c2d7e1-5a3f-4b69-8d20-000000000001",
    3: "b4c2d7e1-5a3f-4b69-8d20-000000000005",
    4: "c6d3e2f1-7a48-4c3b-9e05-000000000001",
    8: "5a1e0c3d-7b2f-4e8a-9c41-000000000001",
}


def ran(reason: str, steps: list[str], halt: str | None) -> str:
    return _ran(
        {
            "outcome": "cancelled",
            "reason": reason,
            "task": {"state": "CANCELLED"},
            "steps": steps,
            "halt": halt,
        }
    )


def shown(number: int, step_state: str, halt: str, risk: str, capability: str) -> str:
    return _detail(
        {
            "id": TASK,
            "state": "CANCELLED",
            "goal": "la prova di M6.3c",
            "created_at": "2026-10-01T10:00:00Z",
            "deadline": None,
            "max_privacy": "LOCAL_ONLY",
            "plan_id": "7c1e2d3f-0a4b-4c5d-8e6f-000000000043",
            "halt": halt,
            "steps": [
                {
                    "id": STEP_OF[number],
                    "state": step_state,
                    "risk": risk,
                    "required_capabilities": [capability],
                    "goal": "lo step della prova",
                }
            ],
        }
    )


def row(
    number: int,
    capability: str,
    status: str,
    tool: str,
    output: dict[str, Any] | None = None,
    code: str | None = None,
) -> dict[str, Any]:
    return {
        "step_id": STEP_OF[number],
        "capability_id": capability,
        "status": status,
        "tool_name": tool,
        "created_at": "2026-10-01T10:00:01Z",
        "output": output or {},
        "error": None if code is None else {"code": code, "message": "m", "retryable": False},
    }


SLEPT = {
    "program": "bin/sleep",
    "runs": "/bin/sleep",
    "args": ["97"],
    "argument_count": 1,
    "cwd": "ELA",
    "ended": "stopped_with_the_task",
    "signal": 15,
}
PRINTED: dict[int, list[str]] = {
    2: [
        ran("cancel: EXECUTING -> CANCELLED (la prova di M6.3c)", [STEP_OF[2]], "NOT_ACTED"),
        _results([row(2, "browser.read", "CANCELLED", "browser-read", code="execution.stopped")]),
    ],
    3: [
        shown(3, "CANCELLED", "NOT_ACTED", "HIGH", "browser.act"),
        _results(
            [
                row(3, "browser.act", "STARTED", "browser-act"),
                row(3, "browser.act", "CANCELLED", "browser-act", code="execution.stopped"),
            ]
        ),
    ],
    4: [
        shown(4, "FAILED", "ACTED", "HIGH", "terminal.run"),
        _results(
            [
                row(4, "terminal.run", "STARTED", "terminal-run"),
                row(4, "terminal.run", "FAILED", "terminal-run", SLEPT, "terminal.stopped"),
            ]
        ),
        "0\n",
    ],
    5: [ran(f"cancel: QUEUED -> CANCELLED ({STOPPED_BY_THE_CONSOLE})", [], None)],
    6: [ran(f"cancel: QUEUED -> CANCELLED ({STOPPED_BY_THE_PHONE})", [], None)],
    8: [shown(8, "COMPLETED", "ACTED_VERIFIED", "MEDIUM", "voice.speak")],
}
"""What the command line prints when each step goes as the guide says, rendered by the CLI's own
functions: the expected blocks of §21 must be found in it, in their order."""


def test_every_expected_block_is_what_the_command_line_prints_for_its_outcome() -> None:
    expected = {
        number: [block for block in blocks if block.kind == "atteso"]
        for number, blocks in marked().items()
    }

    assert {number for number, found in expected.items() if found} == set(PRINTED)
    for number, printed in PRINTED.items():
        assert len(expected[number]) == len(printed), number
        for block, output in zip(expected[number], printed, strict=True):
            assert script().missing(block.lines, output, TASK) == [], (number, output)


def test_the_expected_block_of_step_4_fails_on_a_step_that_completed() -> None:
    """The negative case of the test above: the other outcome is not the expected one."""
    (block, *_) = [one for one in marked()[4] if one.kind == "atteso"]
    other = shown(4, "COMPLETED", "ACTED_VERIFIED", "HIGH", "terminal.run")

    assert script().missing(block.lines, other, TASK) != []
