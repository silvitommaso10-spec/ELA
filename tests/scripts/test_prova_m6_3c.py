"""``scripts/prova_m6_3c.py`` on a world of its own: the rounds, the file, the questions.

The script runs against a real ELA, and the hand test is where it does; what it decides on the
way — when a step passed, at which round, what it asks and what it writes — is tested here, on a
fake API, fake commands and a fake table of processes, so that the reviewer reads a script whose
logic has run before Tommaso runs it.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
from functools import cache
from types import ModuleType
from typing import Any

import pytest

from tests.docs.test_prova_m6_3c import SCRIPT

TASK = "11111111-1111-4111-8111-111111111111"


@cache
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prova_m6_3c_rounds", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class World:
    """ELA as the script sees it: the API, the commands it runs, the processes it looks at."""

    def __init__(self, sides: list[str]) -> None:
        self.sides = sides
        """The side each round's stop lands on, one per round."""
        self.round = 0
        self.cancelled: list[str] = []
        self.looks = 0
        self.lines: list[str] = []

    # the API
    def get(self, path: str) -> Any:
        if path.endswith("/results"):
            return self._results()
        if path == "/health":
            return {"status": "ok"}
        if not self.cancelled:
            return {"state": "EXECUTING", "halt": None, "steps": [{"state": "RUNNING"}]}
        return {"state": "CANCELLED", "halt": "NOT_ACTED", "steps": [{"state": "CANCELLED"}]}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.cancelled.append(path)
        return {}

    def close(self) -> None:
        return None

    def _results(self) -> list[dict[str, Any]]:
        if not self.cancelled:
            return [{"status": "STARTED", "error": None}]
        side = self.sides[min(self.round, len(self.sides)) - 1]
        if side == "prima del punto":
            return [{"status": "CANCELLED", "error": {"code": "execution.stopped"}}]
        return [{"status": "SUCCEEDED", "error": None}]

    # the commands
    def run(self, line: str, task_id: str | None) -> subprocess.CompletedProcess[str]:
        self.lines.append(line)
        if "task create" in line:
            self.round += 1
            self.cancelled = []
            self.looks = 0
            return subprocess.CompletedProcess(line, 0, json.dumps({"id": TASK}), "")
        if "task results" in line:
            return subprocess.CompletedProcess(line, 0, "error execution.stopped\n", "")
        return subprocess.CompletedProcess(line, 0, "outcome  cancelled\n", "")

    def started(self, line: str, task_id: str | None) -> Any:
        self.lines.append(line)
        return _Background("outcome  cancelled\nstopped step  had not acted\n")

    def processes(self) -> dict[int, str]:
        """The browser of each round appears at the second look after its baseline, with a pid
        of its own: the one of the round before is gone, as a stopped browser is."""
        self.looks += 1
        if self.looks < 3:
            return {1: "launchd"}
        return {1: "launchd", 100 + self.round: "chrome-headless-shell"}


class _Background:
    def __init__(self, output: str) -> None:
        self.output = output

    def communicate(self) -> tuple[str, None]:
        return self.output, None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    made = World(["prima del punto"])
    module = script()
    monkeypatch.setattr(module, "run", made.run)
    monkeypatch.setattr(module, "started", made.started)
    monkeypatch.setattr(module, "processes", made.processes)
    monkeypatch.setattr(module, "PAUSE", 0)
    return made


def report() -> Any:
    return script().Report(io.StringIO())


def browser_step(side: str = "prima del punto") -> list[Any]:
    block = script().Block
    return [
        block(2, "comando", 'uv run ela task create "x" --json\nuv run ela task run <id>'),
        block(2, "guarda", "processo chrome-headless-shell"),
        block(2, "ferma", side),
        block(2, "atteso", "outcome cancelled\nstopped step had not acted"),
        block(2, "comando", "uv run ela task results <id>"),
        block(2, "atteso", "error execution.stopped"),
    ]


def never(question: str) -> str:
    raise AssertionError(f"the script asked {question!r} where nobody's hand is needed")


def test_a_step_whose_stop_lands_where_the_guide_says_passes_at_the_first_round(
    world: World,
) -> None:
    written = report()

    script().a_step(2, browser_step(), world, written, never)

    assert world.cancelled == [f"/tasks/{TASK}/cancel"]
    assert "[2] PASSATO: il «ferma» è caduto prima del punto" in written.lines
    assert written.lines.count("[2] PASSATO: l'uscita è quella attesa") == 2
    assert written.failed == 0
    assert world.lines[-2].endswith("task run <id>"), "the run is the one in the background"


def test_a_stop_on_the_wrong_side_is_failed_and_the_step_is_tried_again(world: World) -> None:
    world.sides = ["dopo il punto", "prima del punto"]
    written = report()

    script().a_step(2, browser_step(), world, written, never)

    assert world.round == 2
    assert written.failed == 1
    assert any("FALLITO: il «ferma» è caduto dopo il punto" in line for line in written.lines)
    assert "[2] PASSATO al secondo giro: il «ferma» è caduto prima del punto" in written.lines


def test_three_rounds_on_the_wrong_side_are_three_failures_and_no_fourth(world: World) -> None:
    world.sides = ["dopo il punto"] * 4
    written = report()

    script().a_step(2, browser_step(), world, written, never)

    assert world.round == script().ROUNDS == 3
    assert written.failed == 3


def test_an_output_that_misses_a_line_is_failed_with_the_true_output(world: World) -> None:
    todo = browser_step()
    todo[3] = script().Block(2, "atteso", "outcome cancelled\nreason cancel: it was stopped")
    written = report()

    script().a_step(2, todo, world, written, never)

    assert written.failed == 1
    assert "    | outcome  cancelled" in written.lines


def test_a_question_that_says_no_skips_the_step(world: World) -> None:
    block = script().Block
    written = report()

    script().a_step(
        8, [block(8, "se", "Il PC è acceso?"), *browser_step()], world, written, "n".strip
    )

    assert written.lines[-1] == "[8] SALTATO: Il PC è acceso?"
    assert world.lines == []


def test_what_the_eye_sees_is_written_as_looked_and_the_hand_waits_for_enter(
    world: World,
) -> None:
    block = script().Block
    asked: list[str] = []

    def answer(question: str) -> str:
        asked.append(question)
        return "s"

    todo = [
        block(5, "comando", 'uv run ela task create "x" --json'),
        block(5, "mano", "Ferma il task dalla console."),
        block(5, "occhio", "La conferma dice il vero?"),
        block(5, "comando", "uv run ela task run <id>"),
        block(5, "atteso", "outcome cancelled"),
    ]
    written = report()

    script().a_step(5, todo, world, written, answer)

    assert len(asked) == 2, "Invio after the hand, and the question of the eye"
    assert "[5] GUARDATO: La conferma dice il vero?" in written.lines
    assert "    risposta di Tommaso: sì" in written.lines
    assert written.failed == 0


def test_a_task_that_ends_before_the_sign_is_a_round_to_repeat(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(script(), "seen", lambda *args: False)
    monkeypatch.setattr(script(), "ended", lambda *args: True)
    written = report()

    script().a_step(2, browser_step(), world, written, never)

    assert world.round == 3
    assert written.failed == 3
    assert all("finito da sé" in line for line in written.lines if "FALLITO" in line)
