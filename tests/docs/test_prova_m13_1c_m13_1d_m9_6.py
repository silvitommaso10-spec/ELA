"""§22 and ``scripts/prova_m13_1c_m13_1d_m9_6.py`` say the same thing (M13.1c, «La prova a mano»).

The guide is the source of truth, and the script reads it with the reader of M6.3c: this file reads
§22 with the script's own functions and asserts that every marker is a kind the script knows and a
step of the section, that every placeholder is one it fills, and that the three checks of its own
have where to fire — the reasons of steps 2–4, the question of step 4, the exit of step 6. **Each
check has its negative case**, on constructed outputs: a check that only ever passes proves
nothing. That the lines §22 expects are the lines the CLI prints is proved by running steps 2–6
through the script itself, in ``tests/cli/test_section_22_on_the_cli.py``.
"""

from __future__ import annotations

import importlib.util
import io
import re
import subprocess
import sys
import urllib.error
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from ela.cli.output import EMPTY
from ela.executive.runner import _REASONED, OUTCOMES

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prova_m13_1c_m13_1d_m9_6.py"
PLACEHOLDER = re.compile(r"<[^>\s][^>]*>")

THE_SIX_OF_AB87D9D = """\
approval  47fbce38-66ab-519c-b7dc-8cce4bd4a7f2
task      55ed2ab5-94aa-581f-9468-c4d247d9fe04
grant     one use, 3600 seconds
expires   2026-09-30T10:00:00+00:00
file      workspace/notes/first-task.md
asks      workspace.write_note on workspace/notes/first-task.md
"""
"""A question in the shape §6 showed before M13.1d: the labels of before, at the width of before."""


@cache
def script() -> ModuleType:
    """The script, loaded by path: ``scripts/`` is not a package."""
    spec = importlib.util.spec_from_file_location("prova_m13_1c_m13_1d_m9_6", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def guide() -> str:
    return str(script().GUIDE.read_text(encoding="utf-8"))


def marked() -> dict[int, list[Any]]:
    module = script()
    by_step: dict[int, list[Any]] = module.base.steps(module.base.blocks(guide(), module.HEADING))
    return by_step


def lines_of(kind: str) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, blocks in marked().items()
        for block in blocks
        if block.kind == kind
        for line in block.lines
    ]


# ----------------------------------------------------------------------------------------
# The section and the script
# ----------------------------------------------------------------------------------------


def test_every_marker_is_a_kind_the_script_knows_and_belongs_to_a_step_of_the_section() -> None:
    section = script().base.section(guide(), script().HEADING)
    headings = {int(number) for number in re.findall(r"^### (\d+)\. ", section, re.MULTILINE)}
    found = marked()

    assert found, "§22 has no marked block: the script would do nothing"
    assert set(found) <= headings
    assert all(block.kind in script().KINDS for blocks in found.values() for block in blocks)
    every_marker = re.findall(r"<!-- prova: (\d+)\.(\w+) -->", section)
    assert len(every_marker) == sum(len(blocks) for blocks in found.values()), (
        "a marker the reader did not take: it is not right above a fenced block"
    )


def test_every_step_starts_with_its_commands() -> None:
    for number, blocks in marked().items():
        assert blocks[0].kind == "comando", number


def test_every_placeholder_is_one_the_script_fills() -> None:
    module = script()
    fills = {module.ID, module.APPROVAL_ID, module.VOICE_ID}
    used = {
        found
        for blocks in marked().values()
        for block in blocks
        for found in PLACEHOLDER.findall(block.body)
    }

    assert used == fills


def test_the_question_is_read_before_its_id_is_used() -> None:
    """``<approval-id>`` comes from the block of ``ela approvals``: it must have been printed."""
    module = script()
    for number, blocks in marked().items():
        lines = [line for block in blocks if block.kind == "comando" for line in block.lines]
        if any(module.APPROVAL_ID in line for line in lines):
            first = next(at for at, line in enumerate(lines) if module.APPROVAL_ID in line)
            assert module.APPROVALS in lines[:first], number


def test_a_task_is_created_with_the_json_the_script_reads_its_id_from() -> None:
    created = [line for _, line in lines_of("comando") if script().CREATE in f" {line} "]

    assert created
    assert all(line.endswith(" --json") for line in created), created


def test_the_three_checks_have_where_to_fire() -> None:
    module = script()
    commands = lines_of("comando")

    assert [number for number, line in commands if line == module.APPROVALS] == [4]
    assert [number for number, line in commands if line == module.VOICE] == [6]
    assert [number for number, line in commands if line.endswith(module.HELP)] == [5]
    for step in (2, 3, 4):
        runs = [line for number, line in commands if number == step and module.RUN in f" {line} "]
        assert len(runs) >= 2, step


def test_the_ends_with_a_reason_are_the_runner_s() -> None:
    assert {OUTCOMES[state].value for state in _REASONED} == script().REASONED


def test_the_question_of_section_6_is_found() -> None:
    question = script().the_guides_question(guide())

    assert question.labels[0] == "approval"
    assert question.labels[-1] == "asks"
    assert question.column > len("grant if you say yes")


def test_the_file_is_in_downloads_with_the_name_of_the_branch() -> None:
    out = script().default_out()

    assert out.parent == Path.home() / "Downloads"
    assert out.name.startswith("prova-m13.1c-m13.1d-m9.6-")


# ----------------------------------------------------------------------------------------
# The checks of its own, each with its negative case
# ----------------------------------------------------------------------------------------


def test_one_reason_said_twice_is_the_same_reason() -> None:
    assert script().same_reason(["fail: EXECUTING -> FAILED (x)"] * 2) is None


@pytest.mark.parametrize(
    "reasons",
    [
        ["fail: EXECUTING -> FAILED (x)"],
        ["fail: EXECUTING -> FAILED (x)", EMPTY],
        [EMPTY, EMPTY],
        ["fail: EXECUTING -> FAILED (x)", "fail: EXECUTING -> FAILED (y)"],
    ],
)
def test_one_run_an_empty_reason_or_two_reasons_are_reported(reasons: list[str]) -> None:
    assert script().same_reason(reasons) is not None


def test_the_question_of_section_6_is_like_itself_and_unlike_the_one_of_before() -> None:
    module = script()
    question = module.the_guides_question(guide())
    (before,) = module.questions(THE_SIX_OF_AB87D9D)

    assert module.unlike(question, question) == []
    differences = module.unlike(before, question)
    assert len(differences) == 2, "the labels and the column"


def test_values_at_two_columns_are_not_a_question() -> None:
    assert script().question_of(["approval  abc", "task       def"]) is None


def test_two_questions_are_two_blocks_and_nothing_is_none() -> None:
    module = script()
    two = THE_SIX_OF_AB87D9D + "\n" + THE_SIX_OF_AB87D9D

    assert len(module.questions(two)) == 2
    assert module.questions("nothing to show\n") == []


def test_a_row_of_run_is_read_at_the_command_s_column() -> None:
    printed = "outcome        denied\nreason         deny_by_decision: x\n"

    assert script().run_row(printed, "reason") == "deny_by_decision: x"
    assert script().run_row(printed, "state") is None


def proof(report: Any) -> Any:
    module = script()
    return module.Proof(None, report, input, module.the_guides_question(guide()), "a-voice")


def test_the_voice_that_exits_1_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: subprocess.CompletedProcess(line, 1, "", "ELA is not configured"),
    )
    report = module.base.Report(io.StringIO())

    module.a_command(6, module.VOICE, module.Turn(), proof(report))

    assert f"[6] FALLITO: «{module.VOICE}» esce con 1, non con 0" in report.lines
    assert report.failures == 1


def test_the_voice_that_exits_0_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(
        module.base, "run", lambda line: subprocess.CompletedProcess(line, 0, "enabled  true\n", "")
    )
    report = module.base.Report(io.StringIO())

    module.a_command(6, module.VOICE, module.Turn(), proof(report))

    assert report.failures == 0


def test_a_help_is_read_with_its_spaces_joined(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: subprocess.CompletedProcess(line, 0, " always carry\n their why: \n", ""),
    )
    turn = module.Turn()

    module.a_command(
        5, "uv run ela task run --help", turn, proof(module.base.Report(io.StringIO()))
    )

    assert turn.last == "always carry their why:"


def test_a_question_of_another_shape_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    task = "55ed2ab5-94aa-581f-9468-c4d247d9fe04"
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: subprocess.CompletedProcess(line, 0, THE_SIX_OF_AB87D9D, ""),
    )
    report = module.base.Report(io.StringIO())
    turn = module.Turn(task_id=task)

    module.a_command(4, module.APPROVALS, turn, proof(report))

    assert report.failures == 1
    assert turn.approval_id == "47fbce38-66ab-519c-b7dc-8cce4bd4a7f2", "the id is read all the same"


def test_a_task_without_its_question_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    module = script()
    monkeypatch.setattr(
        module.base,
        "run",
        lambda line: subprocess.CompletedProcess(line, 0, "nothing to show\n", ""),
    )
    report = module.base.Report(io.StringIO())

    module.a_command(4, module.APPROVALS, module.Turn(task_id="t"), proof(report))

    assert report.failures == 1


# ----------------------------------------------------------------------------------------
# Step 1: what the proof requires of the world is SKIPPED when it is missing, never FAILED
# ----------------------------------------------------------------------------------------


class Answering:
    """An ELA that answers, with an online voice configured."""

    def get(self, path: str) -> Any:
        if path == "/voice":
            return {"voice": {"online": {"configured": True, "voice_id": "a-voice"}}}
        return {"status": "ok"}


class Declared:
    sites = ("example.com", "httpbin.org")


def test_a_site_that_does_not_answer_skips_step_1_and_fails_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Review of M13.1c+M13.1d+M9.6, 2-bis: a site that does not answer is a world the proof needs
    and does not have — step 1 SKIPPED with what is missing, not a FAILED that would read as ELA's.
    Everything before it is there: ELA, the shell of Chromium, the declared sites."""
    module = script()
    shell = tmp_path / "chrome-headless-shell-mac-arm64" / "chrome-headless-shell"
    shell.parent.mkdir()
    shell.touch()

    def no_route(site: str) -> bool:
        if site == "example.com":
            raise urllib.error.URLError("no route to host")
        return True

    monkeypatch.setattr(module.base, "Api", Answering)
    monkeypatch.setattr("ela.infrastructure.machine.browser.shell_folder", lambda *_: tmp_path)
    monkeypatch.setattr("ela.composition.settings.BrowserSettings", Declared)
    monkeypatch.setattr(module, "answers", no_route)
    report = module.base.Report(io.StringIO())

    assert module.preconditions(report) is None

    assert report.failures == 0, report.lines
    assert report.skipped_steps == [1]
    assert report.lines[:3] == [
        "[1] PASSATO: ELA risponde",
        "[1] PASSATO: lo shell di Chromium c'è",
        "[1] PASSATO: i siti example.com, httpbin.org sono dichiarati",
    ]
    assert report.lines[3] == (
        "[1] SALTATO: la prova richiede «example.com risponde», e non è così "
        "(URLError: <urlopen error no route to host>)"
    )
    report.verdict()
    assert report.lines[-1] == "La prova non è passata: il passo 1 SALTATO."
