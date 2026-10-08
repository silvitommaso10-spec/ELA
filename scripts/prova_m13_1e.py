"""La prova a mano di M13.1e: la ragione di una fine sulle tre superfici (la sezione 25 di
``docs/GETTING_STARTED.md``).

    uv run python scripts/prova_m13_1e.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m13_1e.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script parte da ``scripts/prova_m14_2.py`` (decisione 30 della
review della prova di M14.2) e ne usa i controlli del passo 1 — l'``origin``, la migrazione, il
FERMATO alla prima precondizione che cade —; legge dalla sezione 25 i blocchi con il marcatore
sopra, ``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa il
confronto «a parole intere e in ordine», il rapporto, il client dell'API e ``Stop``.
``tests/docs/test_prova_m13_1e.py`` tiene allineati la sezione e lo script, e nutre ogni tipo che
legge l'API con le risposte delle rotte vere (``tests/docs/real_ends.py``).

I tipi ``comando``, ``atteso``, ``occhio`` e ``mano`` della sezione 21 — l'``atteso`` cerca le sue
righe in ciò che hanno stampato **tutti** i comandi del blocco sopra, in ordine; ``mano`` dice a
Tommaso che cosa fare e non aspetta Invio, ed è il ``guarda`` dopo a verificarlo —, ``sì`` della
24 — qui legge la domanda **del task stesso** —, e quattro suoi (la SPEC di M13.1e, «La prova a
mano», e la decisione 8 della review):

* ``guarda``: ``stato <S>``, e aspetta che il task finisca, al più :data:`WATCH_SECONDS`; finito in
  un altro stato il passo è FALLITO, con lo stato — lì può esserci un difetto di ELA —; non finito
  in tempo è **SALTATO**, «nessuno ha risposto in un quarto d'ora: il passo si rifà» (decisione 9
  della review del riepilogo); in tutti e due i casi il passo non va avanti;
* ``fine``: ``GET /tasks/<id>``, ``GET /audit?task_id=<id>`` e ``GET /devices`` — quattro letture
  con l'uscita della CLI, perché il confronto non sia circolare —: la ragione è il sommario
  dell'evento della transizione che ha chiuso il task, l'operazione e il codice sono quelli del
  blocco, e chi ha risposto è il ruolo del blocco, con il nome fisso per ``LOCAL`` e il nome della
  sua riga del registro per ``CONSOLE`` e ``COMPANION``; la stessa ``end`` nella riga del task di
  ``GET /tasks/finished`` — se il task non è fra gli ultimi :data:`FINISHED_LOOK`, quella parte è
  **SALTATA** con la ragione, e il resto si confronta comunque (decisione 10). Riempie
  ``<id di chi ha risposto>`` e ``<nome di chi ha risposto>``;
* ``ultimi``: ``GET /tasks/finished`` con il numero di righe della superficie, e i task dei passi
  nominati fra quelle; uno spinto fuori fa il passo **SALTATO** — la precondizione del passo umano,
  non un errore di ELA — e i suoi occhi non si chiedono;
* ``misura``: le rotte del blocco, :data:`TIMES` volte ciascuna, con quanti task hanno una ragione;
  scrive i millisecondi. **Una misura, non un verdetto.**

I segnaposto sono ``<id>`` — il task del passo —, ``<approval-id>`` — la sua domanda, letta
dall'API —, ``<id di chi ha risposto>``, ``<nome di chi ha risposto>`` e ``<id del passo N>``.
**Una precondizione del passo 1 che cade ferma la prova** — FERMATO, con la ragione. Si ferma ad
aspettare solo per il sì e per l'occhio. **Nessuna chiamata parte, e la chiave del modello non
serve**: nessun piano della sezione ha uno step ``model.complete``. La riga finale è quella di
M6.3c: «La prova è passata» solo senza FALLITO, senza SALTATO e con ogni GUARDATO un sì. Tutto va
anche nel file, in ``~/Downloads``.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planner  # noqa: E402 — the same

from ela.api.tasks import LOCAL_ANSWERER  # noqa: E402
from ela.cli.output import EMPTY  # noqa: E402
from ela.devices import LOCAL_USER  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 25. "
KINDS: Final = ("comando", "atteso", "occhio", "mano", "guarda", "sì", "fine", "ultimi", "misura")
ID = base.ID
APPROVAL_ID: Final = spending.APPROVAL_ID
WHO: Final = "<id di chi ha risposto>"
WHO_NAME: Final = "<nome di chi ha risposto>"
PLACEHOLDERS: Final = (ID, APPROVAL_ID, WHO, WHO_NAME)
"""The placeholders the script fills, beside ``<id del passo N>`` (:data:`base.STEP_ID`)."""
STEP_ID = base.STEP_ID
CREATE: Final = spending.CREATE
MIGRATION = planner.MIGRATION
SITE = planner.SITE
SCHEMA: Final = "EndOut"
"""The schema the Core of the branch has in ``GET /openapi.json``: the code that says the reason."""
CONSOLE: Final = "CONSOLE"
COMPANION: Final = "COMPANION"
LOCAL: Final = "LOCAL"
ROLES: Final = (LOCAL, CONSOLE, COMPANION)
"""What ``ha risposto`` can say, beside :data:`NOBODY`: ``AnswererOut.role``."""
PHONE_PRIVACY: Final = "TRUSTED"
"""The ceiling of the phone of the proof: it sees the ``TRUSTED`` task of step 4 and not the four
``LOCAL_ONLY`` ones, whose row says only ELA's words."""
NOBODY: Final = "nessuno"
OPERATION: Final = "operazione"
CODE: Final = "codice"
ANSWERED: Final = "ha risposto"
END_WORDS: Final = (OPERATION, CODE, ANSWERED)
"""The vocabulary of ``fine``: one line each, in any order."""
WATCHED: Final = "stato"
"""The one word of ``guarda`` here: the task's state, once it has ended."""
ENDED = base.ENDED
SURFACES: Final = {"console": "la console", "telefono": "il telefono"}
"""The first word of ``ultimi``, and how the file names the surface."""
FINISHED_LOOK: Final = 20
"""How many of the last finished tasks ``fine`` reads to find the step's own: it finished last, and
twenty leaves room for anything else that ended in the meantime."""
WATCH_SECONDS: Final = 15 * 60
"""How long ``guarda`` waits for the hand of Tommaso: a quarter of an hour."""
WATCH_PAUSE: Final = 1.0
TIMES: Final = 5
"""How many times ``misura`` reads each route."""
UNANSWERED: Final = "nessuno ha risposto in un quarto d'ora: il passo si rifà"
"""What ``guarda`` says when :data:`WATCH_SECONDS` pass and the task is still alive: the human step
not done, like lesson S of M13.1c — SALTATO, not FALLITO (decision 9 of the review of the
summary)."""
PUSHED_OUT: Final = "un altro task finito l'ha spinto fuori"
"""Why ``fine`` does not compare the row of ``GET /tasks/finished``: the task is not among the last
:data:`FINISHED_LOOK` (decision 10 of the review of the summary, as ``ultimi`` of decision 8)."""
SAID_NO: Final = "hai risposto no: il resto del passo non avrebbe niente da misurare"
NO_QUESTION: Final = "senza la domanda il passo non ha niente da misurare"


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Wanted:
    """What a ``fine`` block says the end must be."""

    operation: str
    code: str | None
    role: str | None
    """One of :data:`ROLES`, or ``None`` for :data:`NOBODY`."""


def wanted_of(block: base.Block) -> Wanted:
    """The three lines of a ``fine`` block: ``operazione``, ``codice`` — ``—`` for none — and ``ha
    risposto`` — a role of :data:`ROLES` or ``nessuno``."""
    said: dict[str, str] = {}
    for line in block.lines:
        word = next((one for one in END_WORDS if line.startswith(f"{one} ")), None)
        if word is None or word in said:
            raise ValueError(f"step {block.step}: {line!r} is not in the vocabulary of fine")
        said[word] = line[len(word) :].strip()
    if set(said) != set(END_WORDS):
        raise ValueError(f"step {block.step}: fine wants {', '.join(END_WORDS)}")
    role = said[ANSWERED]
    if role != NOBODY and role not in ROLES:
        raise ValueError(f"step {block.step}: {role!r} is not a role of ha risposto")
    return Wanted(
        said[OPERATION],
        None if said[CODE] == EMPTY else said[CODE],
        None if role == NOBODY else role,
    )


def closing_event(events: Sequence[Mapping[str, Any]], state: Any) -> Mapping[str, Any] | None:
    """The audit event of the transition that put the task in ``state``: the last whose payload says
    ``new_state`` is that state (ADR 0055)."""
    found = [one for one in events if (one.get("payload") or {}).get("new_state") == state]
    return found[-1] if found else None


@dataclass(frozen=True)
class Answerer:
    """Who answered, as ``fine`` found them: what fills the placeholders of the blocks after."""

    identity: str
    name: str


def end_failures(
    task: Mapping[str, Any],
    events: Sequence[Mapping[str, Any]],
    devices: Sequence[Mapping[str, Any]],
    finished: Sequence[Mapping[str, Any]],
    wanted: Wanted,
) -> list[str]:
    """What ``fine`` finds wrong with the end of ``task``, one sentence each; ``[]`` if nothing.

    Four reads — the task's route, the audit, the registry, the finished list — and the output of
    the CLI in the ``atteso`` around: the reason is the audit's summary, never composed here. A task
    that is not in ``finished`` has no row to compare: :func:`pushed_out_of_finished` says why."""
    end = task.get("end")
    if not isinstance(end, Mapping):
        return [f"il task {task.get('state')} non ha una ragione: end è {end!r}"]
    failures: list[str] = []
    event = closing_event(events, task.get("state"))
    payload: Mapping[str, Any] = {} if event is None else (event.get("payload") or {})
    if event is None:
        failures.append(f"nessun evento d'audit ha messo il task in {task.get('state')}")
    else:
        if end.get("reason") != event.get("summary"):
            failures.append(
                f"la ragione è {end.get('reason')!r}, il sommario dell'evento "
                f"{event.get('summary')!r}"
            )
        if payload.get("operation") != wanted.operation:
            failures.append(
                f"l'evento dice l'operazione {payload.get('operation')!r}, il passo "
                f"{wanted.operation!r}"
            )
        if payload.get("code") != wanted.code:
            failures.append(
                f"l'evento dice il codice {payload.get('code')!r}, il passo {wanted.code!r}"
            )
    if end.get("operation") != wanted.operation:
        failures.append(
            f"end dice l'operazione {end.get('operation')!r}, il passo {wanted.operation!r}"
        )
    if end.get("reason_code") != wanted.code:
        failures.append(f"end dice il codice {end.get('reason_code')!r}, il passo {wanted.code!r}")
    failures.extend(_answered_failures(end.get("answered_by"), payload, devices, wanted))
    row = _row_of(task, finished)
    if row is not None and row.get("end") != end:
        failures.append(f"la riga di GET /tasks/finished dice {row.get('end')!r}, il task {end!r}")
    return failures


def _row_of(
    task: Mapping[str, Any], finished: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any] | None:
    return next((one for one in finished if one.get("id") == task.get("id")), None)


def pushed_out_of_finished(
    task: Mapping[str, Any], finished: Sequence[Mapping[str, Any]]
) -> str | None:
    """Why the row of ``task`` in ``GET /tasks/finished`` is not compared, or ``None`` when it is
    there: the task is not among the last :data:`FINISHED_LOOK`, and :func:`end_failures` compares
    the rest — the route of the task, the audit, the registry (decision 10)."""
    if _row_of(task, finished) is not None:
        return None
    return (
        f"il task {task.get('id')} non è fra gli ultimi {FINISHED_LOOK} finiti di "
        f"GET /tasks/finished: {PUSHED_OUT}, e la sua riga non si confronta"
    )


def _answered_failures(
    answered: Any,
    payload: Mapping[str, Any],
    devices: Sequence[Mapping[str, Any]],
    wanted: Wanted,
) -> list[str]:
    if wanted.role is None:
        return (
            []
            if answered is None
            else [f"risulta che ha risposto {answered!r}: il passo dice nessuno"]
        )
    if not isinstance(answered, Mapping):
        return [f"nessuno ha risposto, e il passo dice {wanted.role}"]
    identity, name, role = answered.get("identity"), answered.get("name"), answered.get("role")
    failures: list[str] = []
    if role != wanted.role:
        failures.append(f"ha risposto un {role!r}, il passo dice {wanted.role}")
    if payload and payload.get("responded_by") != identity:
        failures.append(
            f"l'evento dice che ha risposto {payload.get('responded_by')!r}, end {identity!r}"
        )
    if wanted.role == LOCAL:
        if identity != str(LOCAL_USER.id) or name != LOCAL_ANSWERER:
            failures.append(
                f"la riga di comando è {identity!r} «{name}», "
                f"non {LOCAL_USER.id} «{LOCAL_ANSWERER}»"
            )
        return failures
    row = next((one for one in devices if one.get("id") == identity), None)
    if row is None:
        return [*failures, f"il registro non ha {identity!r}"]
    if row.get("role") != wanted.role:
        failures.append(f"nel registro {identity} è un {row.get('role')!r}, non un {wanted.role}")
    if row.get("name") != name:
        failures.append(f"nel registro {identity} si chiama {row.get('name')!r}, end dice {name!r}")
    if row.get("revoked_at") is not None:
        failures.append(f"nel registro {identity} è revocato")
    return failures


def answerer_of(task: Mapping[str, Any]) -> Answerer | None:
    """Who answered the task, from its ``end``: the id and the name for the placeholders."""
    answered = (task.get("end") or {}).get("answered_by")
    if not isinstance(answered, Mapping):
        return None
    return Answerer(str(answered.get("identity")), str(answered.get("name") or ""))


def watched_word(block: base.Block) -> str:
    """The state a ``guarda`` waits for: ``stato <S>``, with ``S`` a final state."""
    (line,) = block.lines
    word, _, state = line.partition(" ")
    if word != WATCHED or state not in ENDED:
        raise ValueError(f"step {block.step}: {line!r} is not in the vocabulary of guarda")
    return state


def surface_of(block: base.Block) -> tuple[str, int, list[int]]:
    """An ``ultimi`` block: the surface, how many finished tasks it shows, and the steps whose
    tasks must be among them."""
    first, *rest = block.lines
    word, _, number = first.partition(" ")
    found = [STEP_ID.fullmatch(line.strip()) for line in rest]
    if word not in SURFACES or not number.isdigit() or not rest or None in found:
        raise ValueError(f"step {block.step}: {block.body!r} is not in the vocabulary of ultimi")
    return word, int(number), [int(one.group(1)) for one in found if one is not None]


def pushed_out(
    finished: Sequence[Mapping[str, Any]], steps: Sequence[int], ids: Mapping[int, str]
) -> list[str]:
    """The steps of ``steps`` whose task is not among ``finished``, one sentence each."""
    shown = {one.get("id") for one in finished}
    lacking: list[str] = []
    for step in steps:
        task = ids.get(step)
        if task is None:
            lacking.append(f"il passo {step} non ha un task")
        elif task not in shown:
            lacking.append(f"il task {task} del passo {step}")
    return lacking


def has_the_end(openapi: Mapping[str, Any]) -> bool:
    """Whether the Core answering is the code of the branch: its schema has :data:`SCHEMA`."""
    return SCHEMA in ((openapi.get("components") or {}).get("schemas") or {})


def enrolled(devices: Sequence[Mapping[str, Any]], role: str, privacy: str | None = None) -> bool:
    """Whether the registry has a row of ``role``, not revoked — with ``privacy``, if given."""
    return any(
        one.get("role") == role
        and one.get("revoked_at") is None
        and (privacy is None or one.get("privacy") == privacy)
        for one in devices
    )


def measured(times: Sequence[float], answer: Any) -> str:
    """One line of ``misura``: how many tasks, how many with a reason, and the milliseconds."""
    tasks = answer.get("tasks") if isinstance(answer, Mapping) else answer
    rows: Sequence[Mapping[str, Any]] = tasks or []
    reasons = sum(1 for one in rows if one.get("end") is not None)
    middle = statistics.median(times)
    each = f"{middle / reasons:.2f} ms per ragione" if reasons else "nessuna ragione"
    return (
        f"{len(rows)} task, {reasons} con una ragione; {len(times)} letture, mediana "
        f"{middle:.1f} ms (da {min(times):.1f} a {max(times):.1f}); {each}"
    )


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


class Done(Exception):
    """The step ended before its last block: a ``guarda`` that saw another end, an ``ultimi`` whose
    precondition fell."""


@dataclass
class Turn:
    """What a step has done so far: its task, its question, who answered, and what the commands of
    its last block printed, every one in order."""

    task_id: str | None = None
    approval_id: str | None = None
    who: Answerer | None = None
    last: str = ""


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    ids: dict[int, str] = field(default_factory=dict)
    """The task of each step: what ``<id del passo N>`` stands for."""


def filled(text: str, turn: Turn, proof: Proof) -> str:
    who = turn.who
    for placeholder, value in (
        (ID, turn.task_id),
        (APPROVAL_ID, turn.approval_id),
        (WHO, None if who is None else who.identity),
        (WHO_NAME, None if who is None else who.name),
    ):
        text = text.replace(placeholder, value or placeholder)
    return STEP_ID.sub(lambda found: proof.ids.get(int(found.group(1)), found.group(0)), text)


def the_question(proof: Proof, turn: Turn) -> Mapping[str, Any] | None:
    """The question of the step's own task, from the API."""
    for one in proof.api.get("/approvals"):
        if one.get("task_id") == turn.task_id:
            turn.approval_id = str(one["id"])
            return dict(one)
    return None


def commands(number: int, lines: Sequence[str], turn: Turn, proof: Proof) -> None:
    """The commands of a block, in order: ``turn.last`` is what **all** of them printed (decision 23
    of the review of the proof of M14.2). A line with ``<approval-id>`` reads the task's question
    first: without it, the step has nothing to measure."""
    turn.last = ""
    for line in lines:
        if APPROVAL_ID in line and turn.approval_id is None and the_question(proof, turn) is None:
            proof.report.failure(number, f"il task {turn.task_id} non ha una domanda")
            raise base.Stop(NO_QUESTION)
        a_command(filled(line, turn, proof), turn, proof)


def a_command(line: str, turn: Turn, proof: Proof) -> None:
    report = proof.report
    report.say(f"    $ {line}")
    done = base.heard(line, base.run(line))
    printed = done.stdout + done.stderr
    turn.last += printed
    for one in printed.rstrip("\n").splitlines():
        report.say(f"    | {one}")
    if CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        report.say(f"    il task: {turn.task_id}")


def a_yes(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    report = proof.report
    question = the_question(proof, turn)
    if question is None:
        report.failure(number, f"il task {turn.task_id} non ha una domanda")
        raise base.Stop(NO_QUESTION)
    report.say(f"    la domanda {question['id']}, del task {turn.task_id}:")
    report.say(f"    | {question.get('prompt')}")
    report.say(f"    | rischio: {question.get('risk')}")
    if not base.yes_or_no(proof.ask, f"[{number}] Rispondi sì? (s/n) "):
        raise base.Stop(SAID_NO)
    commands(number, block.lines, turn, proof)
    task = proof.api.get(f"/tasks/{turn.task_id}")
    if task.get("state") == "QUEUED":
        report.passed(number, f"il sì al task {turn.task_id}")
    else:
        report.failure(number, f"dopo il sì il task è {task.get('state')}")


def a_watch(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    """Until the task ends, or :data:`WATCH_SECONDS` pass: what the hand did, verified. Another end
    is FALLITO, with the state: there may be a defect of ELA. No end in time is SALTATO: nobody
    acted, and the step is done again (decision 9)."""
    wanted = watched_word(block)
    deadline = time.monotonic() + WATCH_SECONDS
    while True:
        state = proof.api.get(f"/tasks/{turn.task_id}").get("state")
        if state in ENDED or time.monotonic() >= deadline:
            break
        time.sleep(WATCH_PAUSE)
    if state == wanted:
        proof.report.passed(number, f"il task {turn.task_id} è {wanted}")
        return
    if state in ENDED:
        proof.report.failure(number, f"il task {turn.task_id} è finito {state}, non {wanted}")
    else:
        proof.report.skipped(number, f"il task {turn.task_id} è ancora {state}: {UNANSWERED}")
    raise Done


def an_end(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    wanted = wanted_of(block)
    api = proof.api
    task = api.get(f"/tasks/{turn.task_id}")
    finished = api.get(f"/tasks/finished?limit={FINISHED_LOOK}").get("tasks") or []
    failures = end_failures(
        task, api.get(f"/audit?task_id={turn.task_id}"), api.get("/devices"), finished, wanted
    )
    turn.who = answerer_of(task)
    end = task.get("end") or {}
    proof.report.say(f"    la ragione: {end.get('reason')}")
    if turn.who is not None:
        proof.report.say(f"    ha risposto: {turn.who.name} ({turn.who.identity})")
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        who = "nessuno" if wanted.role is None else wanted.role
        proof.report.passed(
            number, f"la ragione è il sommario dell'audit: {wanted.operation}, ha risposto {who}"
        )
    pushed = pushed_out_of_finished(task, finished)
    if pushed is not None:
        proof.report.skipped(number, pushed)


def the_last(number: int, block: base.Block, proof: Proof) -> None:
    """Decision 8: before the eye, the tasks of the steps among those the surface shows."""
    surface, shown, steps = surface_of(block)
    finished = proof.api.get(f"/tasks/finished?limit={shown}").get("tasks") or []
    lacking = pushed_out(finished, steps, proof.ids)
    where = f"gli ultimi {shown} finiti che {SURFACES[surface]} mostra"
    if lacking:
        proof.report.skipped(
            number,
            f"{', '.join(lacking)} non è fra {where}: un altro task finito l'ha spinto fuori, "
            "e l'occhio non avrebbe niente da guardare",
        )
        raise Done
    proof.report.passed(number, f"i task dei passi {', '.join(map(str, steps))} sono fra {where}")


def a_measure(block: base.Block, proof: Proof) -> None:
    for path in block.lines:
        times: list[float] = []
        answer: Any = None
        for _ in range(TIMES):
            start = time.perf_counter()
            answer = proof.api.get(path)
            times.append((time.perf_counter() - start) * 1000)
        proof.report.say(f"    {path}: {measured(times, answer)}")
    proof.report.say("    una misura, non un verdetto")


def a_step(number: int, todo: Sequence[base.Block], proof: Proof, turn: Turn | None = None) -> None:
    """The blocks of a step in order; ``turn`` is a new one, unless a test hands its own."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = Turn() if turn is None else turn
    try:
        for block in todo:
            kind = block.kind
            if kind == "comando":
                commands(number, block.lines, turn, proof)
            elif kind == "atteso":
                wanted = [filled(line, turn, proof) for line in block.lines]
                absent = base.missing(wanted, turn.last)
                if absent:
                    report.failure(number, f"mancano {absent}", turn.last)
                else:
                    report.passed(number, "l'uscita è quella attesa")
            elif kind == "occhio":
                text = filled(block.body, turn, proof)
                yes = base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) ")
                report.looked(number, text, yes)
            elif kind == "mano":
                # Never an Enter: what the hand did, the ``guarda`` after it verifies.
                report.say(f"[{number}] A TE: {filled(block.body, turn, proof)}")
            elif kind == "guarda":
                a_watch(number, block, turn, proof)
            elif kind == "sì":
                a_yes(number, block, turn, proof)
            elif kind == "fine":
                an_end(number, block, turn, proof)
            elif kind == "ultimi":
                the_last(number, block, proof)
            elif kind == "misura":
                a_measure(block, proof)
            else:
                raise ValueError(f"step {number}: {kind!r} is not a kind of the section")
    except Done:
        return
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def shell_installed() -> bool:
    """The shell of Chromium, where ELA's browser looks for it (as ``prova_m6_3c``)."""
    from ela.infrastructure.machine.browser import shell_folder

    folder = shell_folder(os.environ, platform.system()) or Path("/nowhere")
    return any(folder.glob("chrome-headless-shell-*/chrome-headless-shell"))


def preconditions(report: base.Report) -> bool:
    from ela.composition.settings import BrowserSettings

    checks: list[tuple[str, base.Check]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planner.on_origin() is None,
        ),
        ("ELA risponde", lambda: base.Api().get("/health") is not None),
        (
            f"il Core gira dal codice del branch: lo schema ha {SCHEMA}",
            lambda: has_the_end(base.Api().get("/openapi.json")),
        ),
        (f"uv run alembic current dice {MIGRATION}", planner.migrated),
        (f"{SITE} è fra i siti dichiarati", lambda: SITE in BrowserSettings().sites),
        ("lo shell di Chromium c'è", shell_installed),
        (
            "nel registro c'è una console, non revocata",
            lambda: enrolled(base.Api().get("/devices"), CONSOLE),
        ),
        (
            f"nel registro c'è un telefono {PHONE_PRIVACY}, non revocato",
            lambda: enrolled(base.Api().get("/devices"), COMPANION, PHONE_PRIVACY),
        ),
    ]
    return planner.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.1e-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M13.1e, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if preconditions(report):
            proof = Proof(base.Api(), report, ask)
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
