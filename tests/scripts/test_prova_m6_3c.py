"""``scripts/prova_m6_3c.py`` on a world of its own: the rounds, the count, the questions.

The script runs against a real ELA, and the hand test is where it does; what it decides on the
way — when a step passed and at which round, what is a round to repeat and what a failure, what it
asks, and what its last line says — is tested here, on a fake API, fake commands and a fake table
of processes, so that the reviewer reads a script whose logic has run before Tommaso runs it.
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
PC = "22222222-2222-4222-8222-222222222222"


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
        self.device = PC
        """Who writes the step's STARTED: a node, unless a test says this Mac."""

    # the API
    def get(self, path: str) -> Any:
        if path.endswith("/results"):
            return self._results()
        if not self.cancelled:
            return {"state": "EXECUTING", "halt": None, "steps": [{"state": "RUNNING"}]}
        return {"state": "CANCELLED", "halt": "NOT_ACTED", "steps": [{"state": "CANCELLED"}]}

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        self.cancelled.append(path)
        return {}

    def close(self) -> None:
        return None

    def _results(self) -> list[dict[str, Any]]:
        started = {"status": "STARTED", "error": None, "device_id": self.device}
        if not self.cancelled:
            return [started]
        side = self.sides[min(self.round, len(self.sides)) - 1]
        if side == "prima del punto":
            return [started, {"status": "CANCELLED", "error": {"code": "execution.stopped"}}]
        return [started, {"status": "SUCCEEDED", "error": None}]

    # the commands
    def run(self, line: str) -> subprocess.CompletedProcess[str]:
        self.lines.append(line)
        if "task create" in line:
            self.round += 1
            self.cancelled = []
            self.looks = 0
            return subprocess.CompletedProcess(line, 0, json.dumps({"id": TASK}), "")
        if "task results" in line:
            return subprocess.CompletedProcess(line, 0, "error execution.stopped\n", "")
        return subprocess.CompletedProcess(line, 0, "outcome  cancelled\n", "")

    def started(self, line: str) -> Any:
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


def never(question: str) -> str:
    raise AssertionError(f"the script asked {question!r} where nobody's hand is needed")


def proof(world: World, ask: Any = never) -> Any:
    return script().Proof(world, script().Report(io.StringIO()), ask)


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


def last_lines(done: Any) -> list[str]:
    done.report.verdict()
    lines: list[str] = done.report.lines[-2:]
    return lines


# ----------------------------------------------------------------------------------------
# The rounds
# ----------------------------------------------------------------------------------------


def test_a_step_whose_stop_lands_where_the_guide_says_passes_at_the_first_round(
    world: World,
) -> None:
    done = proof(world)

    script().a_step(2, browser_step(), done)

    assert world.cancelled == [f"/tasks/{TASK}/cancel"]
    assert "[2] PASSATO: il «ferma» è caduto prima del punto" in done.report.lines
    assert done.report.lines.count("[2] PASSATO: l'uscita è quella attesa") == 2
    assert world.lines[1].endswith(f"task run {TASK}"), "the run is the one in the background"
    assert last_lines(done) == [
        "PASSATI: 3 (al primo giro 3, al secondo 0, al terzo 0) — FALLITI: 0 — "
        "GUARDATI con un no: 0 — SALTATI: 0",
        "La prova è passata.",
    ]
    assert done.report.ok


def test_a_round_to_repeat_is_not_a_failure_and_the_step_passes_at_the_second(
    world: World,
) -> None:
    """B of the review: a step passed at the second round closes with the proof passed."""
    world.sides = ["dopo il punto", "prima del punto"]
    done = proof(world)

    script().a_step(2, browser_step(), done)

    assert world.round == 2
    assert any(
        line.startswith("[2] DA RIPETERE: il «ferma» è caduto dopo il punto, non prima del punto")
        for line in done.report.lines
    )
    assert "[2] PASSATO al secondo giro: il «ferma» è caduto prima del punto" in done.report.lines
    assert not any("FALLITO" in line for line in done.report.lines)
    assert last_lines(done)[1] == "La prova è passata."


def test_three_rounds_on_the_wrong_side_are_two_to_repeat_and_one_failure(world: World) -> None:
    world.sides = ["dopo il punto"] * 4
    done = proof(world)

    script().a_step(2, browser_step(), done)

    assert world.round == script().ROUNDS == 3
    assert sum("DA RIPETERE" in line for line in done.report.lines) == 2
    assert done.report.failures == 1
    assert done.report.lines[-1].startswith("[2] FALLITO: il «ferma» è caduto dopo il punto")
    assert "(giro 3, l'ultimo)" in done.report.lines[-1]
    assert last_lines(done)[1] == "La prova non è passata: 1 FALLITI."
    assert not done.report.ok


def test_a_task_that_ends_before_the_sign_is_a_round_to_repeat(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second half of question 1: DA RIPETERE, and FALLITO only at the third."""
    monkeypatch.setattr(script(), "seen", lambda *args: False)
    monkeypatch.setattr(script(), "ended", lambda *args: True)
    done = proof(world)

    script().a_step(2, browser_step(), done)

    assert world.round == 3
    assert sum("DA RIPETERE: il task è finito da sé" in line for line in done.report.lines) == 2
    assert done.report.failures == 1


def test_an_output_that_misses_a_line_is_failed_with_the_true_output(world: World) -> None:
    todo = browser_step()
    todo[3] = script().Block(2, "atteso", "outcome cancelled\nreason cancel: it was stopped")
    done = proof(world)

    script().a_step(2, todo, done)

    assert done.report.failures == 1
    assert "    | outcome  cancelled" in done.report.lines
    assert world.round == 1, "a wrong output is not a round to repeat"


# ----------------------------------------------------------------------------------------
# The node: the step must have gone to the PC
# ----------------------------------------------------------------------------------------


def node_step() -> list[Any]:
    block = script().Block
    return [
        block(8, "comando", 'uv run ela task create "x" --json\nuv run ela task run <id>'),
        block(8, "mano", "Dai il sì dal telefono."),
        block(8, "guarda", "risultato STARTED su un nodo"),
        block(8, "ferma", "dopo il punto"),
    ]


def test_a_step_that_went_to_the_pc_is_stopped_after_its_envelope(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.sides = ["dopo il punto"]
    monkeypatch.setattr(script(), "this_machine", lambda: "the-mac")
    done = proof(world)

    script().a_step(8, node_step(), done)

    assert world.cancelled == [f"/tasks/{TASK}/cancel"]
    assert "[8] PASSATO: il «ferma» è caduto dopo il punto" in done.report.lines


def test_a_step_that_ran_on_the_mac_fails_once_and_is_not_repeated(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F of the review: another round would do the same."""
    monkeypatch.setattr(script(), "this_machine", lambda: PC)
    done = proof(world)

    script().a_step(8, node_step(), done)

    assert world.round == 1
    assert world.cancelled == []
    assert done.report.lines[-1] == "[8] FALLITO: lo step è girato sul Mac, non sul PC"
    assert done.report.failures == 1


def test_this_machine_is_the_id_of_local() -> None:
    from ela.devices.local import LOCAL_DEVICE_ID

    assert script().this_machine() == str(LOCAL_DEVICE_ID)


# ----------------------------------------------------------------------------------------
# The hand, the eye, the question
# ----------------------------------------------------------------------------------------


def test_a_question_that_says_no_skips_the_step_and_the_proof_has_not_passed(
    world: World,
) -> None:
    block = script().Block
    done = proof(world, lambda question: "n")

    script().a_step(8, [block(8, "se", "Il PC è acceso?"), *node_step()], done)

    assert done.report.lines[-1] == "[8] SALTATO: Il PC è acceso?"
    assert world.lines == []
    assert last_lines(done)[1] == "La prova non è passata: il passo 8 SALTATO."


def test_what_the_eye_sees_is_written_as_looked_and_a_no_fails_the_proof(world: World) -> None:
    block = script().Block
    asked: list[str] = []
    answers = iter(["", "n"])

    def answer(question: str) -> str:
        asked.append(question)
        return next(answers)

    todo = [
        block(5, "comando", 'uv run ela task create "x" --json'),
        block(5, "mano", "Ferma il task dalla console, poi conferma; poi premi Invio."),
        block(5, "occhio", "Il task <id del passo 2> dice il vero?"),
        block(5, "comando", "uv run ela task run <id>"),
        block(5, "atteso", "outcome cancelled"),
    ]
    done = proof(world, answer)
    done.ids[2] = "the-task-of-step-2"

    script().a_step(5, todo, done)

    assert len(asked) == 2, "Enter after the hand, and the question of the eye"
    assert asked[1] == "[5] Il task the-task-of-step-2 dice il vero? (s/n) "
    assert "[5] GUARDATO: Il task the-task-of-step-2 dice il vero?" in done.report.lines
    assert "    risposta di Tommaso: no" in done.report.lines
    assert done.ids[5] == TASK
    assert last_lines(done)[1] == "La prova non è passata: un no al passo 5."
