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
è passato: «PASSATO al secondo giro» non è «PASSATO» (decisione 8 della review). Un giro il cui
«ferma» cade dal lato sbagliato è **DA RIPETERE**, con il lato vero, e non conta: è FALLITO solo se
sbaglia anche il terzo. **Non aspetta mai un Invio**: ciò che fa la mano di Tommaso lo verifica il
``guarda`` che la segue, e ciò che un passo richiede al mondo — un nodo disponibile, il Mac a
batteria — lo legge da ELA e dal Mac, senza chiederlo; se manca, il passo è SALTATO con ciò che
manca. **Lo stesso per il passo 1**, ciò che la prova intera richiede: la prima cosa che manca lo fa
SALTATO, e lo script si ferma lì (dal 2026-10-02, decisione 2-bis della review di M13.1c, M13.1d e
M9.6; prima era FALLITO, che sembrava di ELA). **Ai passi 5 e 6, una ragione che nomina l'altra
superficie** — le parole che la console e il telefono scrivono, lette dal codice — è il passo umano
fatto altrove, ed è DA RIPETERE come un «ferma» caduto dal lato sbagliato (decisione S, 2026-10-05).
**Se ELA smette di rispondere a metà giro**, il file dice INTERROTTO al passo dove è successo, i
passi che restano non si fanno, e l'ultima riga lo dice: mai un traceback (decisione R, 2026-10-05).
Ciò che serve l'occhio di Tommaso non lo giudica: lo chiede finché la risposta è s o n — o «si»,
«sì», «no», dalla decisione U del 2026-10-06 —, e la scrive come **GUARDATO**. La riga finale conta
i PASSATO con i loro giri, i FALLITO, i GUARDATO con un no e i SALTATO, e dice «La prova è passata»
solo senza FALLITO, senza SALTATO e con ogni GUARDATO un sì; altrimenti dice che cosa manca, e lo
script esce con 1. Tutto ciò che stampa va anche nel file, in ``~/Downloads``.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TextIO

from ela.api.companion import STOPPED as STOPPED_BY_THE_PHONE
from ela.api.console import STOPPED as STOPPED_BY_THE_CONSOLE
from ela.cli.client import Unreachable
from ela.cli.errors import UNREACHABLE

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "GETTING_STARTED.md"
HEADING = "## 21. "
MARKED = re.compile(r"<!-- prova: (\d+)\.(\w+) -->\n```[^\n]*\n(.*?)\n```", re.DOTALL)
"""A block of §21 the script reads: the marker on the line before its fence."""
KINDS = ("comando", "guarda", "ferma", "atteso", "mano", "occhio", "richiede")
SIGNS = {
    "processo": "un processo nuovo la cui riga di comando contiene il modello",
    "risultato": "un risultato dello step con lo stato scritto, fra i risultati del task",
    "stato": "il task nello stato scritto: ciò che la mano di Tommaso ha fatto, verificato",
}
"""The vocabulary of ``guarda``: the first word, then what to look for."""
NODE = "un nodo disponibile"
BATTERY = "il Mac a batteria"
REQUIREMENTS = (NODE, BATTERY)
"""The vocabulary of ``richiede``: what a step wants of the world, verified by the script and never
asked — a node that is not this Mac and is available, read from ELA; this Mac drawing from its
battery, read from the Mac. One missing is a step SKIPPED with what is missing."""
BATTERY_POWER = "Battery Power"
"""What ``pmset -g batt`` names when the Mac draws from its battery (M12.3c, P6)."""
ANSWERS = {"s": True, "si": True, "sì": True, "n": False, "no": False}
"""The only answers to a question of the eye, read in lower case: an empty one is asked again, never
a no. «si» and «sì» since decision U of the review of 2026-10-06 — Tommaso wrote «si» in the proofs
of those days, and the script asked again every time."""
SIDES = ("prima dello step", "prima del tool", "prima del punto", "dopo il punto")
"""Where a stop can land, in the order a step goes through them."""
ROUNDS = 3
"""A count, not a time: how many times a step whose stop landed on the wrong side is tried again."""
STOP_WORDS = "la prova di M6.3c"
ID = "<id>"
STEP_ID = re.compile(r"<id del passo (\d+)>")
"""The task of another step, the one of its last round: what an ``occhio`` names so that Tommaso
recognises it among the finished tasks, where repeated rounds leave more rows than steps."""
ON_A_NODE = " su un nodo"
"""The suffix of ``risultato`` for a step that must run on a node: its result is not this Mac's."""
ENDED = frozenset({"COMPLETED", "FAILED", "CANCELLED", "DENIED", "EXPIRED"})
SITES = ("example.com", "httpbin.org")
SLEEPER = "bin/sleep"
SLEPT = 97
PAUSE = 0.05
"""Between two looks at the world: a cadence, not a threshold — nothing is decided by it."""
ROUND_NAMES = {1: "", 2: " al secondo giro", 3: " al terzo giro"}
ROUND_WORDS = {1: "al primo giro", 2: "al secondo", 3: "al terzo"}
Ask = Callable[[str], str]
"""How the script asks Tommaso: ``input``, and a fake in the tests."""
SURFACES: Final = (STOPPED_BY_THE_CONSOLE, STOPPED_BY_THE_PHONE)
"""The words each surface writes as the reason when its «Ferma il task» stops a task — the code's
own constants, not words written here (decision S of 2026-10-05)."""
ELA: Final = "uv run ela "
"""A line of the guide that is a command of ELA's: the one whose exit says whether ELA answered."""


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


def section(text: str, heading: str = HEADING) -> str:
    """A section of the guide — §21 unless told otherwise — up to the next one of its level.

    The heading is a parameter since the branch of M13.1c, M13.1d and M9.6: its script reads §22
    with this same reader (``scripts/prova_m13_1c_m13_1d_m9_6.py``).
    """
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end == -1 else text[start:end]


def blocks(text: str, heading: str = HEADING) -> list[Block]:
    """The marked blocks of a section — §21 unless told otherwise —, in the order it writes them."""
    return [
        Block(int(match.group(1)), match.group(2), match.group(3))
        for match in MARKED.finditer(section(text, heading))
    ]


def steps(found: Sequence[Block]) -> dict[int, list[Block]]:
    by_step: dict[int, list[Block]] = {}
    for block in found:
        by_step.setdefault(block.step, []).append(block)
    return dict(sorted(by_step.items()))


@dataclass(frozen=True)
class Sign:
    """What ``guarda`` looks for: ``processo sleep 97``, ``risultato STARTED``, and
    ``risultato STARTED su un nodo`` — a result written by a node, not by this Mac."""

    word: str
    model: str
    on_a_node: bool = False


def sign_of(block: Block) -> Sign:
    (line,) = block.lines
    on_a_node = line.endswith(ON_A_NODE)
    word, _, model = line.removesuffix(ON_A_NODE).partition(" ")
    if word not in SIGNS or not model or (on_a_node and word != "risultato"):
        raise ValueError(f"step {block.step}: {line!r} is not in the vocabulary of guarda")
    return Sign(word, model, on_a_node)


def filled(text: str, task_id: str | None, ids: dict[int, str]) -> str:
    """``<id>`` is the step's own task; ``<id del passo N>`` the task of step N's last round."""
    text = text.replace(ID, task_id or ID)
    return STEP_ID.sub(lambda found: ids.get(int(found.group(1)), found.group(0)), text)


# ----------------------------------------------------------------------------------------
# The comparison, and where a stop landed
# ----------------------------------------------------------------------------------------


def contains(words: Sequence[str], wanted: Sequence[str]) -> bool:
    """Whether ``wanted`` is a contiguous run of whole words of ``words``: «0» is not in «10»."""
    width = len(wanted)
    return width > 0 and any(
        list(words[start : start + width]) == list(wanted)
        for start in range(len(words) - width + 1)
    )


def missing(
    expected: Sequence[str],
    output: str,
    task_id: str | None = None,
    ids: dict[int, str] | None = None,
) -> list[str]:
    """The expected lines the output does not have, whitespace aside.

    Each one must be a contiguous run of whole words of one line of the output, **in the order the
    guide writes them**: an expected line is looked for after the line the one before it matched —
    STARTED before CANCELLED. ``<id>`` and ``<id del passo N>`` are filled first.
    """
    lines = [line.split() for line in output.splitlines()]
    absent: list[str] = []
    after = 0
    for line in expected:
        wanted = filled(line, task_id, ids or {}).split()
        found = next((at for at in range(after, len(lines)) if contains(lines[at], wanted)), None)
        if found is None:
            absent.append(" ".join(wanted))
        else:
            after = found + 1
    return absent


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
    """What the screen and the file say, and the count the last line is made of.

    A round to repeat is **not** a failure: it prints DA RIPETERE with the true side, and only the
    last round that goes wrong is FALLITO. A no to an ``occhio`` and a step skipped by its ``se``
    are not failures either, and the proof has not passed with any of them (decision B).
    """

    out: TextIO
    lines: list[str] = field(default_factory=list)
    passes: dict[int, int] = field(default_factory=dict)
    """How many checks passed at each round."""
    failures: int = 0
    refused: list[int] = field(default_factory=list)
    """The steps where Tommaso answered no to what he looked at."""
    skipped_steps: list[int] = field(default_factory=list)
    lost_at: int | None = None
    """The step where ELA stopped answering, if it did: no step after it was done (decision R)."""
    stopped: tuple[int, str] | None = None
    """The step that stopped the proof, and why: what followed it would have measured something
    else (M14.1, 2026-10-07)."""

    def say(self, text: str = "") -> None:
        print(text, flush=True)
        self.out.write(text + "\n")
        self.out.flush()
        self.lines.append(text)

    def passed(self, step: int, what: str, round_: int = 1) -> None:
        self.passes[round_] = self.passes.get(round_, 0) + 1
        self.say(f"[{step}] PASSATO{ROUND_NAMES[round_]}: {what}")

    def to_repeat(self, step: int, what: str) -> None:
        self.say(f"[{step}] DA RIPETERE: {what}")

    def failure(self, step: int, what: str, output: str = "") -> None:
        self.failures += 1
        self.say(f"[{step}] FALLITO: {what}")
        if output:
            for line in output.rstrip("\n").splitlines():
                self.say(f"    | {line}")

    def looked(self, step: int, question: str, yes: bool) -> None:
        if not yes:
            self.refused.append(step)
        self.say(f"[{step}] GUARDATO: {question}")
        self.say(f"    risposta di Tommaso: {'sì' if yes else 'no'}")

    def skipped(self, step: int, why: str) -> None:
        self.skipped_steps.append(step)
        self.say(f"[{step}] SALTATO: {why}")

    def lost(self, step: int, said: str) -> None:
        """ELA stopped answering during ``step``: written here, never a traceback (decision R)."""
        self.lost_at = step
        self.say(
            f"[{step}] INTERROTTO: ELA ha smesso di rispondere — {said}; "
            "i passi che restano non si fanno"
        )

    def stop(self, step: int, why: str) -> None:
        """``step`` failed in a way that makes the rest measure something else: no step after it."""
        self.stopped = (step, why)
        self.say(f"[{step}] FERMATO: {why}; i passi che restano non si fanno")

    @property
    def ok(self) -> bool:
        return (
            self.failures == 0
            and not self.skipped_steps
            and not self.refused
            and self.lost_at is None
            and self.stopped is None
        )

    def verdict(self) -> None:
        """The last lines: the count, and whether the proof passed — or what it lacks."""
        rounds = ", ".join(
            f"{ROUND_WORDS[round_]} {self.passes.get(round_, 0)}" for round_ in range(1, ROUNDS + 1)
        )
        self.say(
            f"PASSATI: {sum(self.passes.values())} ({rounds}) — FALLITI: {self.failures} — "
            f"GUARDATI con un no: {len(self.refused)} — SALTATI: {len(self.skipped_steps)}"
        )
        if self.ok:
            self.say("La prova è passata.")
            return
        lacking = [
            *([f"ELA ha smesso di rispondere al passo {self.lost_at}"] if self.lost_at else []),
            *(
                [f"la prova si è fermata al passo {self.stopped[0]} — {self.stopped[1]}"]
                if self.stopped
                else []
            ),
            *([f"{self.failures} FALLITI"] if self.failures else []),
            *(f"il passo {step} SALTATO" for step in self.skipped_steps),
            *(f"un no al passo {step}" for step in self.refused),
        ]
        self.say(f"La prova non è passata: {', '.join(lacking)}.")


# ----------------------------------------------------------------------------------------
# The world: commands, processes, the API
# ----------------------------------------------------------------------------------------


def run(line: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S602 — the lines are the guide's, read from the repository
        line,
        shell=True,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class Silent(Exception):
    """ELA stopped answering in the middle of the proof: what said so, for the file (decision R)."""


class Stop(Exception):
    """A step failed so that every step after it would measure something else: why, for the file.

    M14.1, 2026-10-07: a ``tetto`` that ELA did not read, and step 7 measured five FALLITO under
    the cap of step 4. A test asserts only what it built the preconditions of.
    """


def heard(line: str, done: subprocess.CompletedProcess[str]) -> subprocess.CompletedProcess[str]:
    """``done`` as it is, unless it is a command of ELA's whose exit says nothing answered.

    The CLI's own code for it, :data:`~ela.cli.errors.UNREACHABLE`: a ``task create`` that met no
    ELA would otherwise reach the script as JSON nobody wrote, and fall there with a traceback.
    """
    if line.startswith(ELA) and done.returncode == UNREACHABLE:
        raise Silent((done.stderr or done.stdout).strip())
    return done


def walk(
    report: Report,
    todo: Mapping[int, list[Block]],
    one: Callable[[int, list[Block]], None],
) -> None:
    """Every step in order, and where ELA stopped answering if it did (decision R, 2026-10-05).

    At 10:45 of 2026-10-05 ELA stopped at step 8 — a Ctrl-C pressed on ``ela serve`` — and the
    script fell with a traceback that reached the terminal and not the file, with no last line.
    Now the step is in the file, no step after it is done, and the verdict says so: exit 1. A
    :class:`Stop` ends the walk the same way, with the step's own reason (M14.1, 2026-10-07).
    """
    for number, its in todo.items():
        try:
            one(number, its)
        except (Unreachable, Silent) as away:
            report.lost(number, str(away))
            return
        except Stop as why:
            report.stop(number, str(why))
            return


def started(line: str) -> subprocess.Popen[str]:
    return subprocess.Popen(  # noqa: S602 — as above
        line,
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


def seen(api: Api, task_id: str, sign: Sign, before: dict[int, str]) -> bool:
    """One look: the sign of ``guarda``."""
    if sign.word == "processo":
        return any(
            sign.model in command for pid, command in processes().items() if pid not in before
        )
    if sign.word == "stato":
        return bool(api.get(f"/tasks/{task_id}")["state"] == sign.model)
    return any(one["status"] == sign.model for one in api.get(f"/tasks/{task_id}/results"))


def this_machine() -> str:
    """The id this Mac has as a node: ``local``'s (M12.2, dec. A)."""
    from ela.devices.local import LOCAL_DEVICE_ID

    return str(LOCAL_DEVICE_ID)


def ran_here(api: Api, task_id: str, sign: Sign) -> bool:
    """Whether the result ``guarda`` saw was written by this Mac and not by a node."""
    here = this_machine()
    return any(
        one["status"] == sign.model and one.get("device_id") == here
        for one in api.get(f"/tasks/{task_id}/results")
    )


def node_available(api: Api) -> bool:
    """A node that is not this Mac, available and not revoked, in ELA's register of devices."""
    here = this_machine()
    return any(
        one["role"] == "WORKER"
        and one["id"] != here
        and one["available"]
        and one["revoked_at"] is None
        for one in api.get("/devices")
    )


def on_battery() -> bool:
    """Whether this Mac draws from its battery: ``pmset -g batt``, read by ELA's own reader."""
    import asyncio

    from ela.infrastructure.machine.darwin import pmset_source

    return asyncio.run(pmset_source()) == BATTERY_POWER


def lacking(block: Block, api: Api) -> list[str]:
    """What ``richiede`` wants that the world does not have."""
    checks: dict[str, Callable[[], bool]] = {
        NODE: lambda: node_available(api),
        BATTERY: on_battery,
    }
    for line in block.lines:
        if line not in checks:
            raise ValueError(f"step {block.step}: {line!r} is not in the vocabulary of richiede")
    return [line for line in block.lines if not checks[line]()]


def yes_or_no(ask: Ask, question: str) -> bool:
    """A question of the eye, asked until the answer is one of :data:`ANSWERS`: an empty Enter is
    not a no, and neither is anything else."""
    while True:
        answer = ask(question).strip().lower()
        if answer in ANSWERS:
            return ANSWERS[answer]


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


@dataclass
class Proof:
    """What every step shares: the API, the report, Tommaso's answers, and the task of each step."""

    api: Api
    report: Report
    ask: Ask
    ids: dict[int, str] = field(default_factory=dict)
    """The task of each step's last round: what ``<id del passo N>`` stands for."""


def created_id(output: str) -> str:
    task_id: str = json.loads(output)["id"]
    return task_id


def commands(
    number: int, block: Block, turn: Turn, proof: Proof, *, last_in_background: bool
) -> None:
    for index, written in enumerate(block.lines):
        line = filled(written, turn.task_id, proof.ids)
        proof.report.say(f"    $ {line}")
        if last_in_background and index == len(block.lines) - 1:
            turn.background = started(line)
            continue
        done = heard(line, run(line))
        turn.last = done.stdout + done.stderr
        if " task create " in f" {line} ":
            turn.task_id = created_id(done.stdout)
            proof.ids[number] = turn.task_id
            proof.report.say(f"    il task: {turn.task_id}")


def other_surface(expected: str, output: str) -> str | None:
    """Why a human step must be done again: the reason names a surface the step did not ask for.

    Steps 5 and 6 ask the hand to stop the task from one surface, and the reason ELA writes names
    the surface that did it (:data:`SURFACES`). Another one there is the hand's step done
    elsewhere, truly reported — not a failure of ELA (decision S of 2026-10-05: at 17:46 «Ferma» was
    pressed on the phone at step 5). Any other difference is ELA's, and stays a failure.
    """
    asked = [one for one in SURFACES if f"({one})" in expected]
    said = [one for one in SURFACES if f"({one})" in output]
    if len(asked) == 1 and len(said) == 1 and asked != said:
        return (
            f"il passo umano non è stato fatto come chiesto: la ragione dice «{said[0]}», il passo "
            f"chiede «{asked[0]}»"
        )
    return None


def a_round(number: int, todo: list[Block], proof: Proof, round_: int) -> str | None:
    """One round of a step: ``None`` if it went to its end — passed, or failed in a way another
    round would repeat —, or why it must be tried again: the side the stop truly landed on, the
    task that ended before the step was seen, or the surface the hand stopped the task from."""
    api, report = proof.api, proof.report
    turn = Turn()
    stopped = False
    before: dict[int, str] = {}
    for index, block in enumerate(todo):
        text = filled(block.body, turn.task_id, proof.ids)
        if block.kind == "comando":
            watching = not stopped and any(one.kind == "guarda" for one in todo[index:])
            if watching:
                before = processes()
            # The run a stop lands on goes on while the script looks; nothing else does.
            stopping = not stopped and any(one.kind == "ferma" for one in todo[index:])
            commands(number, block, turn, proof, last_in_background=stopping)
        elif block.kind == "mano":
            # Never an Enter: what the hand did, the ``guarda`` after it verifies.
            report.say(f"[{number}] A TE: {text}")
        elif block.kind == "guarda":
            assert turn.task_id is not None
            sign = sign_of(block)
            report.say(f"[{number}] guardo: {block.body}")
            while not seen(api, turn.task_id, sign, before):
                if ended(api, turn.task_id):
                    return "il task è finito da sé prima che lo step si vedesse"
                time.sleep(PAUSE)
            if sign.on_a_node and ran_here(api, turn.task_id, sign):
                # Another round would do the same: the placement does not change by trying again.
                report.failure(number, "lo step è girato sul Mac, non sul PC")
                return None
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
                return f"il «ferma» è caduto {landed}, non {block.body.strip()}"
            report.passed(number, f"il «ferma» è caduto {landed}", round_)
        elif block.kind == "atteso":
            absent = missing(block.lines, turn.last, turn.task_id, proof.ids)
            elsewhere = other_surface(block.body, turn.last) if absent else None
            if elsewhere is not None:
                return elsewhere
            if absent:
                report.failure(number, f"mancano {absent}", turn.last)
            else:
                report.passed(number, "l'uscita è quella attesa", round_)
        elif block.kind == "occhio":
            report.looked(number, text, yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
    if turn.background is not None:
        turn.last, _ = turn.background.communicate()
    return None


def a_step(number: int, todo: list[Block], proof: Proof) -> None:
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    if todo[0].kind == "richiede":
        missing_here = lacking(todo[0], proof.api)
        if missing_here:
            report.skipped(number, f"manca {', '.join(missing_here)}")
            return
        report.passed(number, f"c'è ciò che il passo richiede: {', '.join(todo[0].lines)}")
        todo = todo[1:]
    for round_ in range(1, ROUNDS + 1):
        again = a_round(number, todo, proof, round_)
        if again is None:
            return
        if round_ < ROUNDS:
            report.to_repeat(number, f"{again} (giro {round_}): ripeto il passo con un task nuovo")
        else:
            report.failure(number, f"{again} (giro {round_}, l'ultimo)")


# ----------------------------------------------------------------------------------------
# Step 1: the preconditions
# ----------------------------------------------------------------------------------------


Check = Callable[[], bool]
"""One thing step 1 requires of the world, read where ELA reads it: true when it is there."""


def required(report: Report, checks: Sequence[tuple[str, Check]]) -> bool:
    """Step 1: what the proof requires of the world, in order — never a behaviour of ELA.

    Each one there is PASSED. **The first one missing makes step 1 SKIPPED with what is missing,
    and the script stops there**, as a ``richiede`` does for its step: a FAILED would read as ELA's
    (decision 2-bis of the review of M13.1c, M13.1d and M9.6, 2026-10-02). A check that raises is
    missing too, with what it said. Shared by the step 1 of every proof script.
    """
    for what, check in checks:
        try:
            ok = check()
        except Exception as error:  # noqa: BLE001 — every miss is reported with what it said
            report.skipped(
                1, f"la prova richiede «{what}», e non è così ({type(error).__name__}: {error})"
            )
            return False
        if not ok:
            report.skipped(1, f"la prova richiede «{what}», e non è così")
            return False
        report.passed(1, what)
    return True


def preconditions(report: Report) -> bool:
    """What the plans need, read where ELA reads it: the API, the ``.env``, the shell's folder."""
    from ela.composition.settings import BrowserSettings, TerminalSettings
    from ela.infrastructure.machine.browser import shell_folder

    checks: list[tuple[str, Check]] = [
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
    return required(report, checks)


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
        if preconditions(report):
            proof = Proof(Api(), report, ask)
            try:
                walk(report, todo, lambda number, its: a_step(number, its, proof))
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {out}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
