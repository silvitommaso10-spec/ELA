"""La prova a mano di M6.3c: il «ferma» a metà corsa (``docs/GETTING_STARTED.md`` §21).

    uv run python scripts/prova_m6_3c.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m6_3c.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script legge da §21 i blocchi che hanno sopra un marcatore,
``<!-- prova: N.tipo -->``, e fa ciò che dicono: i comandi, che cosa guardare, il «ferma» e il lato
dove deve cadere, le righe attese, ciò che fa Tommaso con la mano e ciò che guarda con gli occhi.
Il codice qui è il lettore, il vocabolario di ``guarda``, l'invio del «ferma» e il confronto;
``tests/docs/test_prova_m6_3c.py`` legge §21 con lo stesso lettore e tiene allineati i due (M6.3c,
proposta 10).

Per ogni passo meccanico stampa **PASSATO** o **FALLITO** con l'uscita vera — e a che giro un passo
è passato: «PASSATO al secondo giro» non è «PASSATO» (decisione 8 della review). Si ferma ad
aspettare Invio solo dove serve la mano di Tommaso; ciò che serve il suo occhio non lo giudica: lo
chiede, e scrive la risposta come **GUARDATO**. Tutto ciò che stampa va anche nel file, in
``~/Downloads``.

Nessuna soglia di tempo (decisione 7): lo script guarda **finché vede il segno, o finché il task
finisce da sé**, e dopo il «ferma» aspetta che lo step in corso si chiuda. Il «ferma» lo manda
direttamente, con ``POST /tasks/<id>/cancel``: ``uv run ela`` impiega troppo ad avviarsi per un
istante che si misura in centinaia di millisecondi.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "GETTING_STARTED.md"
HEADING = "## 21. "
MARKED = re.compile(r"<!-- prova: (\d+)\.(\w+) -->\n```[^\n]*\n(.*?)\n```", re.DOTALL)
"""A block of §21 the script reads: the marker on the line before its fence."""
KINDS = ("comando", "guarda", "ferma", "atteso", "mano", "occhio", "se")
SIGNS = {
    "processo": "un processo nuovo la cui riga di comando contiene il modello",
    "risultato": "un risultato dello step con lo stato scritto, fra i risultati del task",
}
"""The vocabulary of ``guarda``: the first word, then what to look for."""
SIDES = ("prima dello step", "prima del tool", "prima del punto", "dopo il punto")
"""Where a stop can land, in the order a step goes through them."""
ROUNDS = 3
"""A count, not a time: how many times a step whose stop landed on the wrong side is tried again."""
STOP_WORDS = "la prova di M6.3c"
ID = "<id>"
ENDED = frozenset({"COMPLETED", "FAILED", "CANCELLED", "DENIED", "EXPIRED"})
SITES = ("example.com", "httpbin.org")
SLEEPER = "bin/sleep"
SLEPT = 97
PAUSE = 0.05
"""Between two looks at the world: a cadence, not a threshold — nothing is decided by it."""
ROUND_NAMES = {1: "", 2: " al secondo giro", 3: " al terzo giro"}


# ----------------------------------------------------------------------------------------
# The reader: §21, its marked blocks, its steps
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Block:
    step: int
    kind: str
    body: str

    @property
    def lines(self) -> list[str]:
        return [line for line in self.body.splitlines() if line.strip()]


def section(text: str) -> str:
    """§21 of the guide, from its heading to the next one of its level."""
    start = text.index(HEADING)
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def blocks(text: str) -> list[Block]:
    """The marked blocks of §21, in the order the guide writes them."""
    return [
        Block(int(match.group(1)), match.group(2), match.group(3))
        for match in MARKED.finditer(section(text))
    ]


def steps(found: Sequence[Block]) -> dict[int, list[Block]]:
    by_step: dict[int, list[Block]] = {}
    for block in found:
        by_step.setdefault(block.step, []).append(block)
    return dict(sorted(by_step.items()))


def sign_of(block: Block) -> tuple[str, str]:
    """``guarda`` as ``(word, model)``: ``processo sleep 97`` is ``("processo", "sleep 97")``."""
    (line,) = block.lines
    word, _, model = line.partition(" ")
    if word not in SIGNS or not model:
        raise ValueError(f"step {block.step}: {line!r} is not in the vocabulary of guarda")
    return word, model


# ----------------------------------------------------------------------------------------
# The comparison, and where a stop landed
# ----------------------------------------------------------------------------------------


def normalized(line: str) -> str:
    return " ".join(line.split())


def missing(expected: Sequence[str], output: str, task_id: str | None = None) -> list[str]:
    """The expected lines the output does not contain, whitespace aside: each one is looked for
    inside one line of the output, with ``<id>`` replaced by the task's."""
    lines = [normalized(line) for line in output.splitlines()]
    wanted = [normalized(line.replace(ID, task_id or ID)) for line in expected]
    return [one for one in wanted if not any(one in line for line in lines)]


def side_of(detail: dict[str, Any], results: Sequence[dict[str, Any]]) -> str:
    """Where the stop landed, read from the task's steps and its results.

    The step never started: before the step. Started, and no tool answered: before the tool. A
    result stopped at its point — ``CANCELLED``, ``execution.stopped`` —: before the point. Any
    other answer of the tool: after the point.
    """
    (step,) = detail["steps"]
    if step["state"] == "PENDING":
        return SIDES[0]
    answers = [one for one in results if one["status"] != "STARTED"]
    if not answers:
        return SIDES[1]
    if any(
        one["status"] == "CANCELLED" and (one.get("error") or {}).get("code") == "execution.stopped"
        for one in answers
    ):
        return SIDES[2]
    return SIDES[3]


# ----------------------------------------------------------------------------------------
# The report: the screen and the file, the same lines
# ----------------------------------------------------------------------------------------


@dataclass
class Report:
    out: TextIO
    failed: int = 0
    lines: list[str] = field(default_factory=list)

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.out.write(text + "\n")
        self.out.flush()
        self.lines.append(text)

    def passed(self, step: int, what: str, round_: int = 1) -> None:
        self.say(f"[{step}] PASSATO{ROUND_NAMES[round_]}: {what}")

    def failure(self, step: int, what: str, output: str = "") -> None:
        self.failed += 1
        self.say(f"[{step}] FALLITO: {what}")
        if output:
            for line in output.rstrip("\n").splitlines():
                self.say(f"    | {line}")

    def looked(self, step: int, question: str, answer: str) -> None:
        self.say(f"[{step}] GUARDATO: {question}")
        self.say(f"    risposta di Tommaso: {answer}")

    def skipped(self, step: int, why: str) -> None:
        self.say(f"[{step}] SALTATO: {why}")


# ----------------------------------------------------------------------------------------
# The world: commands, processes, the API
# ----------------------------------------------------------------------------------------


def run(line: str, task_id: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S602 — the lines are the guide's, read from the repository
        line.replace(ID, task_id or ID),
        shell=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def started(line: str, task_id: str | None) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S602 — as above
        line.replace(ID, task_id or ID),
        shell=True,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def processes() -> dict[int, str]:
    listing = subprocess.run(
        ["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=True
    ).stdout
    found: dict[int, str] = {}
    for row in listing.splitlines():
        pid, _, command = row.strip().partition(" ")
        if pid.isdigit():
            found[int(pid)] = command
    return found


class Api:
    """ELA's API, as ``ela`` reaches it: the address and the token of the ``.env``."""

    def __init__(self) -> None:
        from ela.cli import client

        self._client = client.connect()

    def get(self, path: str) -> Any:
        return self._client.get(path)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._client.post(path, body)

    def close(self) -> None:
        self._client.close()


def seen(api: Api, task_id: str, word: str, model: str, before: dict[int, str]) -> bool:
    """One look: the sign of ``guarda``."""
    if word == "processo":
        return any(model in command for pid, command in processes().items() if pid not in before)
    return any(one["status"] == model for one in api.get(f"/tasks/{task_id}/results"))


def ended(api: Api, task_id: str) -> bool:
    return str(api.get(f"/tasks/{task_id}")["state"]) in ENDED


def settled(api: Api, task_id: str) -> dict[str, Any]:
    """The task once the step in progress has closed: no step RUNNING, no halt still finishing."""
    while True:
        detail: dict[str, Any] = api.get(f"/tasks/{task_id}")
        if detail["halt"] != "FINISHING" and all(
            step["state"] != "RUNNING" for step in detail["steps"]
        ):
            return detail
        time.sleep(PAUSE)


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


@dataclass
class Turn:
    """What a round of a step has done so far."""

    task_id: str | None = None
    last: str = ""
    background: subprocess.Popen[str] | None = None


Ask = Callable[[str], str]


def created_id(output: str) -> str:
    task_id: str = json.loads(output)["id"]
    return task_id


def commands(block: Block, turn: Turn, report: Report, *, last_in_background: bool) -> None:
    for index, line in enumerate(block.lines):
        report.say(f"    $ {line.replace(ID, turn.task_id or ID)}")
        if last_in_background and index == len(block.lines) - 1:
            turn.background = started(line, turn.task_id)
            continue
        done = run(line, turn.task_id)
        turn.last = done.stdout + done.stderr
        if " task create " in f" {line} ":
            turn.task_id = created_id(done.stdout)
            report.say(f"    il task: {turn.task_id}")


def a_round(
    number: int, todo: list[Block], api: Api, report: Report, ask: Ask, round_: int
) -> str | None:
    """One round of a step: ``None`` if it went to its end, or the side the stop truly landed on
    when it is not the one the guide expects — the round to repeat."""
    turn = Turn()
    stopped = False
    before: dict[int, str] = {}
    for index, block in enumerate(todo):
        following = todo[index + 1].kind if index + 1 < len(todo) else None
        if block.kind == "comando":
            watching = not stopped and any(one.kind == "guarda" for one in todo[index:])
            if watching:
                before = processes()
            commands(block, turn, report, last_in_background=watching)
        elif block.kind == "mano":
            report.say(f"[{number}] A TE: {block.body}")
            if following != "guarda":
                ask("    premi Invio quando hai fatto ")
        elif block.kind == "guarda":
            assert turn.task_id is not None
            word, model = sign_of(block)
            report.say(f"[{number}] guardo: {block.body}")
            while not seen(api, turn.task_id, word, model, before):
                if ended(api, turn.task_id):
                    report.failure(
                        number,
                        f"il task è finito da sé prima che lo step si vedesse (giro {round_})",
                    )
                    return SIDES[3]
                time.sleep(PAUSE)
        elif block.kind == "ferma":
            assert turn.task_id is not None
            api.post(f"/tasks/{turn.task_id}/cancel", {"reason": STOP_WORDS})
            stopped = True
            report.say(f"[{number}] «ferma» mandato")
            if turn.background is not None:
                turn.last, _ = turn.background.communicate()
                turn.background = None
            detail = settled(api, turn.task_id)
            landed = side_of(detail, api.get(f"/tasks/{turn.task_id}/results"))
            if landed != block.body.strip():
                report.failure(
                    number,
                    f"il «ferma» è caduto {landed}, non {block.body.strip()} (giro {round_})",
                )
                return landed
            report.passed(number, f"il «ferma» è caduto {landed}", round_)
        elif block.kind == "atteso":
            absent = missing(block.lines, turn.last, turn.task_id)
            if absent:
                report.failure(number, f"mancano {absent}", turn.last)
            else:
                report.passed(number, "l'uscita è quella attesa", round_)
        elif block.kind == "occhio":
            answer = ask(f"[{number}] {block.body} (s/n) ").strip().lower()
            report.looked(number, block.body, "sì" if answer.startswith("s") else "no")
    if turn.background is not None:
        turn.last, _ = turn.background.communicate()
    return None


def a_step(number: int, todo: list[Block], api: Api, report: Report, ask: Ask) -> None:
    report.say()
    report.say(f"—— passo {number} ——")
    if todo[0].kind == "se":
        answer = ask(f"[{number}] {todo[0].body} (s/n) ").strip().lower()
        if not answer.startswith("s"):
            report.skipped(number, todo[0].body)
            return
        todo = todo[1:]
    for round_ in range(1, ROUNDS + 1):
        if a_round(number, todo, api, report, ask, round_) is None:
            return
        if round_ < ROUNDS:
            report.say(f"[{number}] ripeto il passo con un task nuovo")


# ----------------------------------------------------------------------------------------
# Step 1: the preconditions
# ----------------------------------------------------------------------------------------


def preconditions(report: Report) -> bool:
    """What the plans need, read where ELA reads it: the API, the ``.env``, the shell's folder."""
    from ela.composition.settings import BrowserSettings, TerminalSettings
    from ela.infrastructure.machine.browser import shell_folder

    checks: list[tuple[str, Callable[[], bool]]] = [
        ("ELA risponde", lambda: Api().get("/health") is not None),
        (
            "lo shell di Chromium c'è",
            lambda: any(
                (shell_folder(os.environ, platform.system()) or Path("/nowhere")).glob(
                    "chrome-headless-shell-*/chrome-headless-shell"
                )
            ),
        ),
        (
            f"i siti {', '.join(SITES)} sono dichiarati",
            lambda: set(SITES) <= set(BrowserSettings().sites),
        ),
        (f"{SLEEPER} è dichiarato", lambda: SLEEPER in TerminalSettings().programs),
        (
            f"un comando può durare più di {SLEPT} secondi",
            lambda: TerminalSettings().timeout_seconds > SLEPT,
        ),
    ]
    for what, check in checks:
        try:
            ok = check()
        except Exception as error:  # noqa: BLE001 — every failure is reported with what it said
            report.failure(1, what, f"{type(error).__name__}: {error}")
            return False
        if not ok:
            report.failure(1, what)
            return False
        report.passed(1, what)
    return True


# ----------------------------------------------------------------------------------------
# The whole
# ----------------------------------------------------------------------------------------


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m6.3c-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = steps(blocks(GUIDE.read_text(encoding="utf-8")))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M6.3c, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if not preconditions(report):
            return 1
        api = Api()
        try:
            for number, its in todo.items():
                a_step(number, its, api, report, ask)
        finally:
            api.close()
        report.say()
        report.say(f"FALLITI: {report.failed}. Il file: {out}")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
