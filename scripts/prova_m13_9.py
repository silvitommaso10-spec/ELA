"""La prova a mano di M13.9: il browser con i tuoi account (``GETTING_STARTED.md``, sezione 28).

    uv run python scripts/prova_m13_9.py --login PIANO.json   # contro l'ELA che gira
    uv run python scripts/prova_m13_9.py --login PIANO.json --out FILE

**La guida è la fonte di verità.** Lo script **parte da** ``scripts/prova_m13_12.py`` (la SPEC di
M13.9, «La prova a mano»): legge dalla sezione 28 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa i tipi di
sempre — ``comando``, ``atteso``, ``occhio``, ``sì`` —, il controllo del commit e dell'albero, e
il «FERMATO» con chi ha risposto. ``tests/docs/test_prova_m13_9.py`` legge la sezione con lo
stesso lettore e tiene allineati i due: cammina la sezione intera contro un'ELA vera, con finti
solo ai bordi della macchina, e ha un caso negativo per ogni confronto di questo file.

Sette tipi suoi, che la sezione spiega uno per uno:

* ``mano``: ciò che fa Tommaso con le sue mani — incollare una riga nel suo terminale, entrare in
  un sito nella finestra, uscire dal browser, o chiudere la finestra con il pulsante rosso, che
  lascia il browser acceso (il passo di ``ela browser close``) —; lo script lo dice e aspetta
  Invio;
* ``prosegui``: una domanda a Tommaso su ciò che il mondo ha dato; con un «n» la prova si ferma —
  **FERMATO**, non FALLITO — prima di spendere;
* ``disco``: il disco in RAM su cui le password si spostano — creato, stretto a ``0700``, svuotato,
  staccato, e controllato che non ci sia più; lo script non legge i file, ne guarda l'esistenza;
* ``misura``: il tempo dell'elenco del vault per un sito, da fuori e per differenza; sopra la
  soglia la riga è **RIAPRE**, e una prova con un RIAPRE non è passata;
* ``domanda``: le domande in attesa per il task del passo — nessuna, o una di quella capability;
* ``coperte``: le letture di una sessione sono finite senza domanda, coperte dalla sessione;
* ``chiude``: ELA fermata mentre uno step ha il profilo; il processo esce, e la cartella del
  profilo resta libera.

**Niente del vault entra nel file**: né il nome di una voce, né un nome utente. Ciò che Tommaso
deve leggere di una domanda di login lo legge nel suo terminale, e lo script lo chiede con un
``occhio``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 28. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "sì",
    "mano",
    "prosegui",
    "disco",
    "misura",
    "domanda",
    "coperte",
    "chiude",
)
ID = base.ID
APPROVAL_ID: Final = guided.APPROVAL_ID
LOGIN_PLAN: Final = "<il piano del login>"
PLACEHOLDERS: Final = (ID, APPROVAL_ID, LOGIN_PLAN)
CURRENCY: Final = guided.CURRENCY
MODEL: Final = guided.MODEL

SESSION_PLAN: Final = ROOT / "docs" / "examples" / "guided-as-you-youtube.json"
"""The one plan of the proof that spends: the session with the profile of step 8."""
SITES: Final = ("www.youtube.com", "httpbin.org", "accounts.google.com")
"""The sites of the proof: the session's and the reading's, the gesture's, and the one of the
first login by hand. The site of the login from the vault is the user's, read from their plan."""
ROUTES: Final = ("/browser", "/vault")
"""The routes of M13.9, in the schema of the API: the Core runs the branch's code."""
GUIDED_AS_YOU: Final = "browser.guided_as_you"
LOGIN: Final = "browser.login"
FREE: Final = "free"
STEP: Final = "step"
LOCKED: Final = "locked"
CLOSED: Final = frozenset({LOCKED, "unauthenticated"})
"""A vault that is not open, for step 1: locked, or with no account signed in yet — the first
``bw login`` of the proof is in step 2, on a data folder that may be new."""
NOBODY: Final = "nessuna"
"""The line of ``domanda`` that says no question waits for the task of the step."""
SESSION_RULE: Final = "SESSION"
"""The rule of the Guardian under which a reading of a session runs with no question."""
WAITING: Final = "waiting_approval"
VOLUME: Final = "ELA-prova"
MOUNT: Final = Path("/Volumes") / VOLUME
BLOCKS_PER_MEGABYTE: Final = 2048
"""``ram://`` counts sectors of 512 bytes."""
DEVICE: Final = re.compile(r"(/dev/disk\d+)")
BITWARDEN: Final = 'anchor apple generic and certificate leaf[subject.OU] = "LTZ2PFU5D6"'
"""The requirement a ``bw`` signed by Bitwarden meets: the team of ``scripts/misura_m13_9.py``."""
EXCLUDED: Final = "[Excluded]"
"""What ``tmutil isexcluded`` says of a folder Time Machine leaves out."""
SIGNALS: Final = {"SIGINT": signal.SIGINT, "SIGTERM": signal.SIGTERM}
WAIT: Final = 0.05
EXIT_SECONDS: Final = 60.0
"""How long ``chiude`` waits for ELA to end: well past the grace of the close."""
HOLD_SECONDS: Final = 120.0
"""How long ``chiude`` waits for the step to hold the profile: a run that never comes to hold it
— a window holds it, ELA does not answer — is a failure of the step, and not a wait for ever."""
SERVES: Final = re.compile(r"(?:^|[\s/])ela(?:\.cli)?\s+serve(?:\s|$)")
"""The command line of an ELA that serves: ``ela serve``, or the module's ``ela.cli serve``."""
NO_OWNERS: Final = "noowners"
"""How ``mount`` says a volume ignores who owns its files: every user is their owner there."""
SAID_NO: Final = "hai risposto no: i passi che restano non hanno niente da misurare"
PROFILE_VARIABLE: Final = "ELA_BROWSER_PROFILE_DIR"
LOCK: Final = "SingletonLock"


# ----------------------------------------------------------------------------------------
# The report: the words of the base, and RIAPRE
# ----------------------------------------------------------------------------------------


@dataclass
class Report(base.Report):
    """The report of the base, with one outcome more: **RIAPRE**, for the measure of step 6 and
    for no other line — the decision that stands on the number is reopened, and a proof with a
    RIAPRE has not passed (the SPEC of M13.9, «La prova a mano»; decision 64)."""

    reopened: list[int] = field(default_factory=list)

    def reopens(self, step: int, what: str) -> None:
        self.reopened.append(step)
        self.say(f"[{step}] RIAPRE: {what}")

    @property
    def ok(self) -> bool:
        return base.Report.ok.fget(self) and not self.reopened  # type: ignore[attr-defined]

    def verdict(self) -> None:
        if not self.reopened:
            super().verdict()
            return
        self.say(
            f"PASSATI: {sum(self.passes.values())} — FALLITI: {self.failures} — "
            f"GUARDATI con un no: {len(self.refused)} — SALTATI: {len(self.skipped_steps)} — "
            f"RIAPRE: {len(self.reopened)}"
        )
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
            *(f"un RIAPRE al passo {step}" for step in self.reopened),
        ]
        self.say(f"La prova non è passata: {', '.join(lacking)}.")


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def question_failures(
    expected: str, approvals: Sequence[Mapping[str, Any]], task_id: str | None
) -> list[str]:
    """What ``domanda`` finds wrong: with :data:`NOBODY`, a question waiting for the task; with a
    capability, anything but one question of that capability."""
    mine = [one for one in approvals if str(one.get("task_id")) == str(task_id)]
    named = [str(one.get("capability_id")) for one in mine]
    if expected == NOBODY:
        return [f"il task {task_id} ha una domanda in attesa ({', '.join(named)})"] if mine else []
    if named != [expected]:
        return [f"il task {task_id} aspetta {named or 'nessuna domanda'}, non una di {expected}"]
    return []


def decided(audit: Sequence[Mapping[str, Any]]) -> list[tuple[str, str]]:
    """The decisions of a task's audit, in order: the outcome and the rule of each."""
    return [
        (str(event["payload"].get("outcome")), str(event["payload"].get("rule")))
        for event in audit
        if event.get("event_type") == "PERMISSION_DECIDED"
    ]


def covered_failures(
    capability: str,
    children: Sequence[Mapping[str, Any]],
    decisions: Mapping[str, Sequence[tuple[str, str]]],
) -> list[str]:
    """What ``coperte`` finds wrong: no child of that capability at all, one that did not end
    ``COMPLETED``, or one whose decisions are anything but a single ``ALLOWED`` under the
    session's cover — a question asked, or a yes of the user's, is not a cover."""
    mine = [child for child in children if guided.capability_of(child) == capability]
    if not mine:
        return [f"nessun figlio {capability}: la sessione non ha letto niente"]
    failures: list[str] = []
    for child in mine:
        name = f"il figlio {child.get('id')}"
        if child.get("state") != "COMPLETED":
            failures.append(f"{name} è {child.get('state')}, non COMPLETED")
        found = list(decisions.get(str(child.get("id")), ()))
        if found != [("ALLOWED", SESSION_RULE)]:
            failures.append(f"{name} non è coperto dalla sessione: le sue decisioni sono {found}")
    return failures


def listing(status_seconds: float, question_seconds: float) -> float:
    """The time of the listing of the vault for one site, by difference: the run of a login up to
    its question launches the vault's program twice — its state, then the listing —, and
    ``ela vault status`` once."""
    return max(0.0, question_seconds - status_seconds)


def reopens(listing_seconds: float, threshold: float) -> bool:
    """Whether the measure reopens the decision: **above** the threshold, not at it."""
    return listing_seconds > threshold


def blocks_of(megabytes: int) -> int:
    return megabytes * BLOCKS_PER_MEGABYTE


def device_of(printed: str) -> str | None:
    """The device ``hdiutil attach -nomount`` printed, or ``None``."""
    found = DEVICE.search(printed)
    return None if found is None else found.group(1)


def mounted() -> bool:
    """Whether a volume of the proof's name is mounted now."""
    return MOUNT.exists()


def _mounted_line(said: str, device: str) -> str | None:
    """The line of ``mount`` that says ``device`` is what is mounted on the proof's volume."""
    start = f"{device} on {MOUNT} ("
    return next((line for line in said.splitlines() if line.startswith(start)), None)


def mounted_on(said: str, device: str) -> bool:
    """Whether the volume of the proof **is the device just made**: a volume of that name that
    was already there is another device's, and macOS mounts the new one beside it under another
    name."""
    return _mounted_line(said, device) is not None


def ignores_owners(said: str, device: str) -> bool:
    """Whether the volume of the proof ignores who owns its files — how macOS mounts a disk
    ``diskutil erasevolume`` made (measured). ``0700`` stops no other user of the machine there."""
    line = _mounted_line(said, device)
    return line is not None and NO_OWNERS in line.rpartition("(")[2].replace(")", "").split(", ")


def serving(command: str) -> bool:
    """Whether a command line is an ELA that serves."""
    return SERVES.search(command) is not None


def the_ela_among(listeners: Sequence[int], commands: Mapping[int, str]) -> int | None:
    """Which of the processes that listen on ELA's port is ELA: the one whose command line is an
    ELA that serves. ``None`` when none is, or more than one: a signal is sent to one process
    the script can name, or to nobody."""
    found = [pid for pid in listeners if serving(commands.get(pid, ""))]
    return found[0] if len(found) == 1 else None


def still_there(mounted: bool, info: str, device: str) -> list[str]:
    """What is left of the RAM disk after it was detached: its volume, or its device."""
    left = []
    if mounted:
        left.append(f"il volume {MOUNT} c'è ancora")
    if device in info.split():
        left.append(f"il dispositivo {device} c'è ancora")
    return left


def lock_pid(target: str | None) -> int | None:
    """The pid the profile's ``SingletonLock`` names — ``<host>-<pid>`` —, or ``None``."""
    if target is None:
        return None
    _, _, pid = target.rpartition("-")
    return int(pid) if pid.isdigit() else None


def left_running(exited: bool, lock: str | None, alive: Callable[[int], bool]) -> list[str]:
    """What ``chiude`` finds wrong after ELA was told to stop: its process still there, or the
    folder of the profile held by a process that is alive."""
    failures = []
    if not exited:
        failures.append(f"ELA non è uscita entro {EXIT_SECONDS:.0f} s")
    pid = lock_pid(lock)
    if pid is not None and alive(pid):
        failures.append(f"la cartella del profilo è ancora tenuta dal processo {pid}")
    return failures


def login_plan_failures(plan: Mapping[str, Any], declared: Sequence[str]) -> list[str]:
    """What is wrong with the plan of the login the user wrote: it is one step of
    ``browser.login``, on a site they declared."""
    steps = plan.get("steps") or []
    if len(steps) != 1 or steps[0].get("required_capabilities") != [LOGIN]:
        return [f"il piano non è un solo step di {LOGIN}"]
    site = (steps[0].get("arguments") or {}).get("site")
    if site not in declared:
        return [f"il sito del piano, {site}, non è fra quelli dichiarati"]
    return []


def arguments_of(plan: Path) -> dict[str, Any]:
    """The arguments of the one step of a plan of a session with the profile."""
    (step,) = json.loads(plan.read_text(encoding="utf-8"))["steps"]
    if step["required_capabilities"] != [GUIDED_AS_YOU]:
        raise ValueError(f"{plan.name} is not a session of {GUIDED_AS_YOU}")
    found: dict[str, Any] = step["arguments"]
    return found


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


@dataclass
class Proof(guided.Proof):
    login: Path | None = None
    """The plan of the login from the vault: the user's own, what ``<il piano del login>`` is."""


def filled(text: str, turn: guided.Turn, proof: Proof) -> str:
    text = guided.filled(text, turn, proof)
    return text.replace(LOGIN_PLAN, str(proof.login) if proof.login else LOGIN_PLAN)


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    """The commands of a block, in order: ``turn.last`` is what **all** of them printed."""
    turn.last = ""
    for line in lines:
        guided.a_command(filled(line, turn, proof), turn, proof)


def a_hand(number: int, block: base.Block, proof: Proof) -> None:
    """``mano``: what Tommaso does himself, said whole; the script waits for Enter."""
    proof.report.say(f"[{number}] A TE: {' '.join(block.lines)}")
    proof.ask(f"[{number}] Premi Invio quando hai fatto. ")


def a_go_on(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``prosegui``: a question about what the world gave; a no stops the proof — FERMATO."""
    text = filled(block.body, turn, proof)
    yes = base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) ")
    proof.report.say(f"[{number}] GUARDATO: {text}")
    proof.report.say(f"    risposta di Tommaso: {'sì' if yes else 'no'}")
    if not yes:
        raise base.Stop(SAID_NO)


def a_question(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    (line,) = block.lines
    failures = question_failures(line, proof.api.get("/approvals"), turn.task_id)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    elif line == NOBODY:
        proof.report.passed(number, "nessuna domanda: il rifiuto è nato prima")
    else:
        proof.report.passed(number, f"una domanda di {line}")


def a_cover(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``coperte``: the children of the session's gestures of one capability, each ended with no
    question under the session's cover."""
    (capability,) = block.lines
    api = proof.api
    detail = api.get(f"/tasks/{turn.task_id}")
    (step,) = detail["steps"]
    found = guided.the_session(api.get(f"/tasks/{turn.task_id}/results"))
    looks = int(((found or {}).get("output") or {}).get("looks") or 0)
    children = [
        child
        for one in guided.gesture_ids(str(turn.task_id), str(step["id"]), looks)
        if (child := guided.existing(api, one)) is not None
    ]
    decisions = {
        str(child["id"]): decided(api.get(f"/audit?task_id={child['id']}")) for child in children
    }
    failures = covered_failures(capability, children, decisions)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(
            number, f"le letture {capability} non hanno chiesto: le copre la sessione"
        )


def a_disk(number: int, block: base.Block, proof: Proof) -> None:
    """``disco``: the RAM disk the passwords are moved on. Made, narrowed, handed to Tommaso, then
    emptied, detached and looked for — **the script never reads a file of it**.

    **A volume of the proof's name that is already there is not touched**: it is not this run's
    — a run that was killed while it waited left it, with what was exported, or it is the
    user's —, and everything below would be done to it."""
    report = proof.report
    megabytes = int(block.lines[0])
    if mounted():
        report.failure(number, f"un volume {MOUNT} è già montato, e non è di questa prova")
        raise base.Stop(
            f"stacca {MOUNT} — dal Finder, o con `diskutil unmount` — e rilancia: lo script non "
            "tocca un volume che non ha fatto"
        )
    made = base.run(f"hdiutil attach -nomount ram://{blocks_of(megabytes)}")
    device = device_of(made.stdout)
    if made.returncode != 0 or device is None:
        report.failure(number, "il disco in RAM non è nato", made.stdout + made.stderr)
        raise base.Stop("senza il disco in RAM le password non si spostano")
    emptied: subprocess.CompletedProcess[str] | None = None
    try:
        formatted = base.run(f'diskutil erasevolume HFS+ "{VOLUME}" {device}')
        said = base.run("mount").stdout
        if formatted.returncode != 0 or not mounted_on(said, device):
            report.failure(
                number, f"il volume {MOUNT} non è il disco appena fatto", formatted.stderr
            )
            raise base.Stop("senza il disco in RAM le password non si spostano")
        if base.run(f'chmod 700 "{MOUNT}"').returncode != 0:
            report.failure(number, f"il volume {MOUNT} non si è stretto a 0700")
            raise base.Stop("senza il disco in RAM le password non si spostano")
        owners = (
            "; il volume ignora i proprietari, e 0700 lì non ferma un altro utente di questo Mac"
            if ignores_owners(said, device)
            else ""
        )
        report.say(
            f"    il disco in RAM è {MOUNT}, di {megabytes} MB, 0700{owners}: non è cifrato, e "
            "ciò che sta in memoria può finire nello swap"
        )
        report.say(f"[{number}] A TE: {' '.join(block.lines[1:])}")
        proof.ask(f"[{number}] Premi Invio quando hai importato. ")
        emptied = base.run(f'find "{MOUNT}" -mindepth 1 -delete')
    finally:
        base.run(f"hdiutil detach {device} -force")
    left = still_there(mounted(), base.run("hdiutil info").stdout, device)
    if emptied is not None and emptied.returncode != 0:
        left.insert(0, "il disco non è stato svuotato prima di essere staccato")
    if left:
        report.failure(number, "; ".join(left))
    else:
        report.passed(number, "il disco in RAM è stato svuotato e staccato: non c'è più")


def timed(line: str) -> tuple[float, subprocess.CompletedProcess[str]]:
    started = time.monotonic()
    done = base.run(line)
    return time.monotonic() - started, done


def a_measure(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``misura``: the listing of the vault for one site, on the full vault, from outside. The
    numbers go to the file; no name of an entry does."""
    report = proof.report
    threshold = float(block.lines[0])
    status_seconds, status = timed("uv run ela vault status")
    base.heard("uv run ela vault status", status)
    run_line = f"uv run ela task run {turn.task_id}"
    question_seconds, ran = timed(run_line)
    base.heard(run_line, ran)
    turn.last = ran.stdout + ran.stderr
    if WAITING not in turn.last:
        report.failure(number, "la corsa del login non è arrivata alla domanda", turn.last)
        raise base.Stop("senza la domanda del login non c'è niente da misurare")
    between = listing(status_seconds, question_seconds)
    said = (
        f"ela vault status {status_seconds:.1f} s, fino alla domanda {question_seconds:.1f} s, "
        f"l'elenco per differenza {between:.1f} s (la soglia: {threshold:.0f} s)"
    )
    if reopens(between, threshold):
        report.reopens(number, f"{said}: si riapre che cosa ELA chiede al vault prima del sì")
    else:
        report.passed(number, said)


def ela_pid() -> int | None:
    """The ELA that listens on ELA's port: who listens is asked of ``lsof``, and which of them is
    ELA of their command lines (:func:`the_ela_among`)."""
    from ela.composition.settings import ApiSettings

    port = ApiSettings().api_port
    found = base.run(f"lsof -ti tcp:{port} -sTCP:LISTEN").stdout.split()
    return the_ela_among([int(one) for one in found if one.isdigit()], base.processes())


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def profile_lock() -> str | None:
    """What the ``SingletonLock`` of the profile's folder points at, or ``None``. The link, never
    a file of the folder."""
    from ela.composition.settings import AccountSettings

    folder = AccountSettings().browser_profile_dir
    if folder is None:
        return None
    try:
        return os.readlink(folder / LOCK)
    except OSError:
        return None


def a_close(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``chiude``: the step of the turn runs in the background; when the profile says a step
    holds it ELA is told to stop, and the script looks at what is left."""
    report = proof.report
    (name,) = block.lines
    if name not in SIGNALS:
        raise ValueError(f"{name!r} is not in the vocabulary of chiude")
    pid = ela_pid()
    if pid is None:
        report.failure(
            number,
            "sulla porta di ELA non ascolta un processo `ela serve`, o ne ascolta più d'uno: "
            "il segnale non si manda a un processo che lo script non sa nominare",
        )
        return
    running = base.started(f"uv run ela task run {turn.task_id}")
    held = False
    deadline = time.monotonic() + HOLD_SECONDS
    while running.poll() is None and not held and time.monotonic() < deadline:
        held = proof.api.get("/browser").get("state") == STEP
        time.sleep(WAIT)
    if not held and running.poll() is None:
        running.terminate()
        report.failure(
            number, f"in {HOLD_SECONDS:.0f} s lo step non ha tenuto il profilo: ELA non è fermata"
        )
        return
    if not held:
        report.skipped(number, "lo step è finito prima che il profilo risultasse tenuto")
        return
    os.kill(pid, SIGNALS[name])
    report.say(f"    {name} a ELA (processo {pid}), con il profilo tenuto da uno step")
    deadline = time.monotonic() + EXIT_SECONDS
    while alive(pid) and time.monotonic() < deadline:
        time.sleep(WAIT)
    failures = left_running(not alive(pid), profile_lock(), alive)
    if failures:
        report.failure(number, "; ".join(failures))
    else:
        report.passed(number, "ELA è uscita, e la cartella del profilo è libera")


def a_block(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    report = proof.report
    kind = block.kind
    if kind == "comando":
        commands(block.lines, turn, proof)
    elif kind == "atteso":
        absent = base.missing([filled(line, turn, proof) for line in block.lines], turn.last)
        if absent:
            report.failure(number, f"mancano {absent}", turn.last)
        else:
            report.passed(number, "l'uscita è quella attesa")
    elif kind == "occhio":
        text = filled(block.body, turn, proof)
        report.looked(number, text, base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
    elif kind == "sì":
        guided.an_answer(number, block, turn, proof, yes=True)
    elif kind == "mano":
        a_hand(number, block, proof)
    elif kind == "prosegui":
        a_go_on(number, block, turn, proof)
    elif kind == "disco":
        a_disk(number, block, proof)
    elif kind == "misura":
        a_measure(number, block, turn, proof)
    elif kind == "domanda":
        a_question(number, block, turn, proof)
    elif kind == "coperte":
        a_cover(number, block, turn, proof)
    elif kind == "chiude":
        a_close(number, block, turn, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, turn: guided.Turn | None = None
) -> None:
    """The blocks of a step in order, with this section's kinds."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = guided.Turn() if turn is None else turn
    try:
        for block in todo:
            a_block(number, block, turn, proof)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1: what the proof requires of the world
# ----------------------------------------------------------------------------------------


def margin_short(left: str | None, needed: Decimal) -> str | None:
    if left is not None and Decimal(left) >= needed:
        return None
    return f"e il mese ne ha liberi {left}: la sessione del passo 8 ne chiede {needed}"


def profile_ready() -> str | None:
    found = base.Api().get("/browser")
    if found.get("state") == FREE:
        return None
    return f"e il profilo è {found.get('state')}: {found.get('message')}"


def narrow_and_left_out() -> str | None:
    """The folder of the profile is the user's alone, and Time Machine leaves it out — the script
    asks Time Machine to, then looks."""
    from ela.composition.settings import AccountSettings

    folder = AccountSettings().browser_profile_dir
    if folder is None:
        return f"e {PROFILE_VARIABLE} non è dichiarata"
    mode = folder.stat().st_mode & 0o777
    if mode != 0o700:
        return f"e la cartella è {mode:o}"
    quoted = shlex.quote(str(folder))
    base.run(f"tmutil addexclusion {quoted}")
    if EXCLUDED not in base.run(f"tmutil isexcluded {quoted}").stdout:
        return "e Time Machine non la esclude"
    return None


def vault_vouched() -> str | None:
    """The vault's program is the declared one, unchanged since ELA started, signed by its maker
    — looked at before the user types a master password into it."""
    found = base.Api().get("/vault")
    program = found.get("program")
    if found.get("state") not in CLOSED or not program:
        return f"e il vault è {found.get('state')}: {found.get('message')}"
    signed = base.run(f"codesign --verify -R='{BITWARDEN}' {shlex.quote(str(program))}")
    if signed.returncode != 0:
        return f"e {program} non è firmato da Bitwarden"
    return None


def program_digest() -> str:
    """The sha256 of the declared program of the vault, for the file: what was vouched for."""
    program = base.Api().get("/vault").get("program")
    return hashlib.sha256(Path(str(program)).read_bytes()).hexdigest()


def login_plan_ready(login: Path | None) -> str | None:
    from ela.composition.settings import BrowserSettings

    if login is None:
        return "e manca --login PIANO.json: il sito del login dal vault lo scegli tu"
    try:
        plan = json.loads(login.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return f"e {login} non si legge ({type(error).__name__})"
    failures = login_plan_failures(plan, BrowserSettings().sites)
    return f"e {'; '.join(failures)}" if failures else None


def preconditions(report: base.Report, login: Path | None) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    needed = guided.reserved(arguments_of(SESSION_PLAN))
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: lo schema dell'API ha {' e '.join(ROUTES)}",
            lambda: guided.so(
                all(route in base.Api().get("/openapi.json")["paths"] for route in ROUTES)
            ),
        ),
        (
            f"il .env manda la rotta di una sessione a {MODEL}",
            lambda: guided.so(guided.route_model() == MODEL),
        ),
        ("il provider del modello ha una chiave", lambda: guided.so(spending.keyed())),
        ("il tetto è dichiarato", lambda: guided.so(base.Api().get("/spend")["cap"] is not None)),
        (
            f"restano almeno {needed} {CURRENCY}, ciò che chiede la sessione del passo 8",
            lambda: margin_short(base.Api().get("/spend")["left"], needed),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(all(site in BrowserSettings().sites for site in SITES)),
        ),
        (
            "il piano del login è uno step di browser.login su un sito dichiarato",
            lambda: login_plan_ready(login),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            profile_ready,
        ),
        ("la cartella del profilo è 0700, e Time Machine la esclude", narrow_and_left_out),
        (
            "il vault è chiuso, e il suo programma è quello dichiarato, firmato da Bitwarden",
            vault_vouched,
        ),
    ]
    if not guided.stopping(report, checks):
        return False
    report.say(f"    lo sha256 del programma del vault: {program_digest()}")
    return True


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.9-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    parser.add_argument("--login", type=Path, default=None, help="il piano del login dal vault")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.9, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if preconditions(report, arguments.login):
            api = base.Api()
            proof = Proof(
                api, report, ask, spending.Ledger.of(api.get("/spend")), login=arguments.login
            )
            try:
                base.walk(report, todo, lambda number, its: a_step(number, its, proof))
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {out}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
