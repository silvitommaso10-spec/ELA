"""La prova a mano di M14.3 e M14.6: il browser guidato da un modello (``docs/GETTING_STARTED.md``,
sezione 26).

    uv run python scripts/prova_m14_3.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m14_3.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script **parte da** ``scripts/prova_m14_2.py`` (la SPEC di
M14.3, «La prova a mano»): legge dalla sezione 26 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa il confronto «a
parole intere e in ordine», il rapporto, il client dell'API, ``Stop`` e la corsa in sfondo; di
``scripts/prova_m14_1.py`` il libro del mese e la chiave; di ``scripts/prova_m14_2.py`` il commit,
la migrazione, il margine che basta, il passo 1 che si ferma al primo che manca e le parole di
``spesa``. ``tests/docs/test_prova_m14_3.py`` legge la sezione con lo stesso lettore e tiene
allineati i due, con un caso negativo per ogni confronto di questo file.

I tipi della sezione 21 — ``comando``, ``atteso``, ``occhio`` —, con l'``atteso`` confrontato con
ciò che hanno stampato **tutti** i comandi del blocco che lo precede, e nove suoi, che la sezione
spiega uno per uno:

* ``sì`` e ``no``: la domanda del task che la prima riga del blocco nomina — la sessione,
  ``<id>``, o il gesto, ``<id del figlio>`` —, mostrata; «rispondi sì?» o «rispondi no?»; con un
  «s» le righe del blocco, con un «n» la prova si ferma. La domanda deve essere in attesa quando
  si mostra e subito prima del comando; una risposta data da un'altra superficie ferma la prova con
  chi l'ha data, letto dall'audit nella forma di ADR 0059 — FERMATO, mai FALLITO (decisione 40);
* ``sfondo``: ``ela task run`` lanciato in sfondo, perché la sessione gira mentre lo script guarda;
* ``aspetta``: il figlio della sessione che chiede, **senza soglia di tempo** — finché lo vede, o
  finché la sessione finisce —; il figlio diventa ``<id del figlio>``. Se la sessione finisce prima,
  lo script dice come è finita, con lo stato e il codice;
* ``fine``: la corsa in sfondo finita, e le righe del blocco cercate in ciò che ha stampato;
* ``sessione``: il risultato della sessione, la prenotazione chiusa, il costo vero, nessun processo
  rimasto;
* ``figli``: ogni gesto un figlio scritto dalla sessione, con i suoi siti come confine, e la regola
  del Guardian letta nell'audit; la riga ``tutti dentro i siti della sessione`` vuole ogni gesto su
  uno dei siti della sessione, anche nessuno (decisione 47);
* ``fascia``: le chiamate di una sessione ricalcolate con la fascia bassa di Haiku 5.5 — il
  listino, non la funzione del gateway — e confrontate con il costo del libro (la prova di M14.6);
* ``spesa``: ``GET /spend`` confrontato con com'era al passo 1.

**Un gesto che la sessione non ha chiesto fa SALTATO solo se la sessione è finita da sé, o su un
limite che il sì ha concesso** — ``guided.looks``, ``guided.duration`` —; ogni altra fine,
``guided.cost`` compreso, è FALLITO con il suo codice (decisione 35 della review del riepilogo). Un
salto chiude il suo giro, non il passo: il giro dopo, che crea il suo task, va avanti. **Il costo di
ogni sessione entra nel conto della spesa quando la sessione finisce**, comunque finisca il passo.
**Una precondizione del passo 1 che cade ferma la prova** — FERMATO, con la ragione: per il margine,
ciò che resta e ciò che le sessioni prenotano (decisione 38) —, e così un no a una domanda. Si ferma
ad aspettare solo per i sì, i no e l'occhio. La riga finale è quella di M6.3c. Tutto va anche nel
file, in ``~/Downloads``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same

from ela.api.tasks import ANSWERING_ROLES, LOCAL_ANSWERER  # noqa: E402
from ela.cli.client import ApiRefusal  # noqa: E402
from ela.cli.tasks import answered_words  # noqa: E402
from ela.devices import LOCAL_USER  # noqa: E402
from ela.permissions.guardian import Rule  # noqa: E402
from ela.ports import GUIDED_DURATION, GUIDED_LOOKS  # noqa: E402
from ela.providers.anthropic.models import HAIKU_5_5  # noqa: E402
from ela.providers.anthropic.pricing import (  # noqa: E402
    CENTS_OF_A_MICRO_DOLLAR,
    PER_MILLION,
    PRICES,
    TIERS,
)

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 26. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "sì",
    "no",
    "sfondo",
    "aspetta",
    "fine",
    "sessione",
    "figli",
    "fascia",
    "spesa",
)
ID = base.ID
CHILD: Final = "<id del figlio>"
APPROVAL_ID: Final = spending.APPROVAL_ID
STEP_2: Final = "<id del passo 2>"
PLACEHOLDERS: Final = (ID, CHILD, APPROVAL_ID, STEP_2)
CREATE: Final = spending.CREATE
CURRENCY: Final = spending.CURRENCY
STARTED: Final = spending.STARTED
MODEL: Final = HAIKU_5_5
"""The model of the route ``browsing``, the cheap profile (decision 27): every session goes
there."""
GUIDED: Final = "browser.guided"
READ: Final = "browser.read"
ACT: Final = "browser.act"
GESTURES: Final = (READ, ACT)
SESSION_ROUTE: Final = "/sessions/{session}/v1/messages"
"""The route of a session's gateway, in the schema of the API: the Core runs the branch's code."""
SITES: Final = ("www.youtube.com", "example.com", "httpbin.org")
"""The sites of the proof (decision 17): the only line of the ``.env`` the proof may touch."""
PLAN_FILE: Final = re.compile(r"--file (docs/examples/[\w-]+\.json)")
SESSION_AUTHOR: Final = "SESSION"
DECIDED: Final = "PERMISSION_DECIDED"
WAITING: Final = "WAITING_APPROVAL"
STATES: Final = ("COMPLETED", "DENIED", "FAILED", "CANCELLED", "EXPIRED", WAITING)
RULES: Final = tuple(rule.value for rule in Rule)
"""The rules a line of ``figli`` may name: the Guardian's own, ``ela.permissions.guardian.Rule``."""
INSIDE: Final = "tutti dentro i siti della sessione"
"""The line of ``figli`` that says every gesture went to one of the session's sites — none at all
included (decision 47: what a proof with a real model that obeys can build)."""
UNREAD: Final = "never-sent"
"""What stands for the key in the provider that prices a session for the margin: ``worst_case``
reads the price list and sends nothing, and the script never reads the key of the ``.env``."""
WAIT: Final = 0.5
"""Seconds between two looks of ``aspetta``: a person answers in seconds, and every look reads the
questions of the whole ELA."""
SAID_NO: Final = "hai risposto no: il resto del passo non avrebbe niente da misurare"
APPROVED_LIMITS: Final = frozenset({GUIDED_LOOKS, GUIDED_DURATION})
"""The ends of a session on a limit the yes allowed: with these, a gesture never asked is SKIPPED
(decision 35 (c)); any other end of ELA's is FAILED."""
NOT_SO: Final = "e non è così"
"""What step 1 says of a check that does not hold and has nothing more to say."""
NO_QUESTION: Final = "senza la domanda il passo non ha niente da misurare"
REQUESTED: Final = "APPROVAL_REQUESTED"
RESOLVED: Final = "APPROVAL_RESOLVED"
ONLY_HERE: Final = "nella prova si risponde solo nel Terminale"
ANSWERS: Final = {"GRANTED": "un sì", "REJECTED": "un no"}
"""What an answer the audit records is called in the sentence that stops the proof (decision 40)."""
ROLES: Final = {role.value: said for role, said in ANSWERING_ROLES.items()}


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def plans_of(todo: Mapping[int, Sequence[base.Block]]) -> list[Path]:
    """The plan of every session of the section, in order: one for each ``--file`` its commands
    send — the same file twice is two sessions, and two reservations."""
    return [
        ROOT / found
        for blocks in todo.values()
        for block in blocks
        if block.kind == "comando"
        for line in block.lines
        for found in PLAN_FILE.findall(line)
    ]


def arguments_of(plan: Path) -> dict[str, Any]:
    """The arguments of the one ``browser.guided`` step of a plan file."""
    (step,) = json.loads(plan.read_text(encoding="utf-8"))["steps"]
    if step["required_capabilities"] != [GUIDED]:
        raise ValueError(f"{plan.name} is not the plan of one session")
    arguments: dict[str, Any] = step["arguments"]
    return arguments


def reserved(arguments: Mapping[str, Any]) -> Decimal:
    """What the gate reserves for a session with ``arguments``: the amount of the tool's own
    ``worst_case``, which the executor hands the gate (M14.3, proposal 2) — **never a number written
    here**. Built over the routes of the ``.env``, as the Core builds them, and a provider whose key
    is :data:`UNREAD`: nothing leaves this machine."""
    from ela.composition.system import SystemClock, UuidGenerator
    from ela.domain import WorstCase
    from ela.providers.anthropic import AnthropicSettings, anthropic_provider
    from ela.providers.registry import ProviderRegistry
    from ela.routing import ModelRouter
    from ela.routing.settings import RoutingSettings
    from ela.tools.guided import BrowserGuidedTool

    clock, ids = SystemClock(), UuidGenerator()
    priced = anthropic_provider(clock, ids, settings=AnthropicSettings(anthropic_api_key=UNREAD))  # type: ignore[arg-type]
    providers = ProviderRegistry((priced,))
    router = ModelRouter(RoutingSettings().policy(), providers)
    tool = BrowserGuidedTool(None, None, router, providers, clock, ids, gateway="")  # type: ignore[arg-type]
    worst = asyncio.run(tool.worst_case(dict(arguments)))
    if not isinstance(worst, WorstCase) or worst.amount is None:
        raise ValueError(f"the gate would reserve nothing for this session: {worst}")
    return worst.amount


def margin(plans: Sequence[Path]) -> Decimal:
    """What the month must have left for every session of the proof at its most."""
    return sum((reserved(arguments_of(plan)) for plan in plans), Decimal(0))


def route_model() -> str | None:
    """The model of the route of a session as this ``.env`` declares it: the profile of
    ``browsing``, and the model the profile names."""
    from ela.providers.anthropic.models import model_for_hint
    from ela.routing.settings import RoutingSettings
    from ela.tools.guided import GUIDED_ROUTE

    found = model_for_hint(RoutingSettings().policy().route_for(GUIDED_ROUTE).profile)
    return None if found is None else found.id


def sites_missing(declared: Sequence[str]) -> list[str]:
    """The sites of the proof the ``.env`` does not declare."""
    return [site for site in SITES if site not in declared]


def binary_ready() -> bool:
    """The binary of Claude Code that the SDK of the lock carries, there and runnable."""
    from ela.infrastructure.machine.agent import bundled_binary

    return os.access(bundled_binary(), os.X_OK)


def the_session(results: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The result that closed the session's reservation: the last one that is not ``STARTED``."""
    ended = [one for one in results if one.get("status") != STARTED]
    return ended[-1] if ended else None


def session_failures(
    line: str, results: Sequence[Mapping[str, Any]], start_open: int, open_now: int
) -> list[str]:
    """What ``sessione`` finds wrong, one sentence each: the status — and the code — of the line,
    the reservation closed, the true cost, the model, no call with an unknown outcome, no process
    of the session left."""
    status, _, code = line.partition(" ")
    found = the_session(results)
    if found is None:
        return ["la sessione non ha un risultato: la sua prenotazione è aperta"]
    failures: list[str] = []
    if found.get("status") != status:
        failures.append(f"la sessione è {found.get('status')}, non {status}")
    error = (found.get("error") or {}).get("code")
    if error != (code or None):
        failures.append(f"il codice della sessione è {error!r}, non {code or None!r}")
    starts = sum(1 for one in results if one.get("status") == STARTED)
    if starts > len(results) - starts:
        failures.append("un STARTED della sessione non ha il suo esito: la prenotazione è aperta")
    output: Mapping[str, Any] = found.get("output") or {}
    usage: Mapping[str, Any] = found.get("usage") or {}
    if usage.get("cost") is None:
        failures.append("la sessione non ha un costo: il libro la terrebbe al caso peggiore")
    if output.get("model") != MODEL:
        failures.append(f"il modello della sessione è {output.get('model')!r}, non {MODEL!r}")
    if output.get("unknown_calls"):
        failures.append(
            f"{output['unknown_calls']} chiamate dall'esito ignoto: il libro le conta al caso "
            "peggiore, non al costo vero"
        )
    if output.get("closed") is not True:
        failures.append("un processo della sessione è rimasto su questa macchina")
    if open_now != start_open:
        failures.append(f"le prenotazioni aperte sono {open_now}, al passo 1 {start_open}")
    return failures


def ending_of(found: Mapping[str, Any] | None) -> tuple[str, bool]:
    """How a session ended, said with its state and its code — never a judgement —, and whether a
    gesture it never asked for is a skip: it ended by itself, or on a limit the yes allowed."""
    if found is None:
        return "senza un risultato: la sua prenotazione è aperta", False
    status = str(found.get("status"))
    code = (found.get("error") or {}).get("code")
    said = status if code is None else f"{status} con {code}"
    by_itself = status == "SUCCEEDED" and code is None
    return said, by_itself or (status == "FAILED" and code in APPROVED_LIMITS)


def cost_of(found: Mapping[str, Any] | None) -> Decimal | None:
    """The cost the session's result writes in the month's ledger, or ``None``."""
    cost = ((found or {}).get("usage") or {}).get("cost")
    return None if cost is None else Decimal(str(cost))


def gesture_ids(task_id: str, session: str, looks: int) -> list[str]:
    """The ids the children of a session's gestures would have — the room derives them from the
    task, the step of the session and the gesture's number (``gesture-<n>/<step>``) —: one for
    each look the session's result counts. A gesture refused before its child has none."""
    from ela.domain import StepId, TaskId
    from ela.executive.sessions import gesture_key
    from ela.tasks.engine import child_id

    return [
        str(child_id(TaskId(UUID(task_id)), gesture_key(number, StepId(UUID(session)))))
        for number in range(1, looks + 1)
    ]


def capability_of(child: Mapping[str, Any]) -> str | None:
    steps: Sequence[Mapping[str, Any]] = child.get("steps") or []
    if len(steps) != 1:
        return None
    named = steps[0].get("required_capabilities") or []
    return str(named[0]) if len(named) == 1 else None


def child_failures(child: Mapping[str, Any], session: str, sites: Sequence[str]) -> list[str]:
    """What is wrong with a gesture's child: the author is the session — with its step and its
    model —, its step is bounded by the session's sites, and a reading never asks."""
    where = f"il figlio {child.get('id')}"
    failures: list[str] = []
    author: Mapping[str, Any] = child.get("plan_author") or {}
    if (author.get("by"), author.get("session"), author.get("model")) != (
        SESSION_AUTHOR,
        session,
        MODEL,
    ):
        failures.append(f"{where} ha l'autore {dict(author)}, non la sessione {session} su {MODEL}")
    capability = capability_of(child)
    if capability not in GESTURES:
        return [*failures, f"{where} non è un gesto: {capability!r}"]
    (step,) = child["steps"]
    if list(step.get("within") or []) != list(sites):
        failures.append(
            f"{where} ha il confine {step.get('within')}, non i siti della sessione {list(sites)}"
        )
    if capability == READ and step.get("requires_authorization"):
        failures.append(f"{where} è una lettura che chiede")
    return failures


def inside(child: Mapping[str, Any], sites: Sequence[str]) -> bool:
    """Whether the gesture of ``child`` went to one of the session's sites — the Guardian's own
    reading of a site against a scope."""
    from ela.permissions.scope import within_scope

    (step,) = child["steps"]
    return within_scope(sites, (step.get("arguments") or {}).get("site"))


def wanted(line: str) -> tuple[str, str, str | None]:
    """A line of ``figli``: a capability, a state and, if named, the rule of the Guardian."""
    words = line.split()
    if (
        len(words) not in (2, 3)
        or words[0] not in GESTURES
        or words[1] not in STATES
        or (len(words) == 3 and words[2] not in RULES)
    ):
        raise ValueError(f"{line!r} is not in the vocabulary of figli")
    return words[0], words[1], words[2] if len(words) == 3 else None


def waited(line: str) -> str:
    """A line of ``aspetta``: a gesture that asks, ``<capability> WAITING_APPROVAL``."""
    words = line.split()
    if len(words) != 2 or words[0] not in GESTURES or words[1] != WAITING:
        raise ValueError(f"{line!r} is not in the vocabulary of aspetta")
    return words[0]


def rule_of(events: Sequence[Mapping[str, Any]]) -> str | None:
    """The rule of the Guardian's last decision on a child, as the audit writes it."""
    rules = [
        (one.get("payload") or {}).get("rule") for one in events if one.get("event_type") == DECIDED
    ]
    return str(rules[-1]) if rules and rules[-1] is not None else None


def asked_for(capability: str, children: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the model asked for any gesture of ``capability``: if not, the line is the model's
    choice and the step is SKIPPED, never FAILED."""
    return any(capability_of(child) == capability for child in children)


def unmatched(
    line: str, children: Sequence[Mapping[str, Any]], rules: Mapping[str, str | None]
) -> str | None:
    """Why no child is the one the line names, or ``None`` if one is."""
    capability, state, rule = wanted(line)
    mine = [child for child in children if capability_of(child) == capability]
    for child in mine:
        if child.get("state") == state and (rule is None or rules.get(str(child["id"])) == rule):
            return None
    seen = ", ".join(
        f"{child.get('state')} {rules.get(str(child['id']))}".strip() for child in mine
    )
    return f"nessun {line}: i figli {capability} sono {seen or 'nessuno'}"


def low_tier(calls: Sequence[Sequence[Any]]) -> Decimal:
    """The calls at the low tier of Haiku 5.5, call by call, rounded as the price list rounds one
    call (ADR 0020 §6): **the list, not** ``estimate_cost``, which chooses the tier itself."""
    price = PRICES[MODEL]
    return sum(
        (
            ((price.input * int(call[1]) + price.output * int(call[2])) / PER_MILLION).quantize(
                CENTS_OF_A_MICRO_DOLLAR
            )
            for call in calls
        ),
        Decimal(0),
    )


def tier_failures(found: Mapping[str, Any]) -> list[str]:
    """What ``fascia`` finds wrong: every call on Haiku 5.5 with its tokens and its bytes, under the
    bound of the low tier, and the cost the ledger wrote equal to the low tier's."""
    output: Mapping[str, Any] = found.get("output") or {}
    calls: Sequence[Sequence[Any]] = output.get("per_call") or []
    if not calls:
        return ["la sessione non ha chiamate da ricalcolare"]
    ((bound, _),) = TIERS[MODEL]
    failures: list[str] = []
    for number, call in enumerate(calls, start=1):
        model, input_tokens, output_tokens, request_bytes = call
        if model != MODEL:
            failures.append(f"la chiamata {number} è di {model!r}, non di {MODEL!r}")
        if not all(type(value) is int for value in (input_tokens, output_tokens, request_bytes)):
            failures.append(f"la chiamata {number} non ha i token e i byte: {list(call)}")
        elif input_tokens > bound:
            failures.append(
                f"la chiamata {number} ha {input_tokens} token d'ingresso, sopra la fascia bassa "
                f"({bound})"
            )
    if failures:
        return failures
    if output.get("unknown_calls"):
        return ["una chiamata dall'esito ignoto è nel libro al suo caso peggiore"]
    written = cost_of(found)
    if written is None:
        return ["il libro non ha un costo per la sessione"]
    if low_tier(calls) != written:
        return [f"il libro ha scritto {written} {CURRENCY}, la fascia bassa dà {low_tier(calls)}"]
    return []


QUESTION: Final = (
    ("capability_id", "capability"),
    ("phrase", "frase"),
    ("sites", "siti"),
    ("model", "modello"),
    ("max_cost", "costo massimo"),
    ("looks", "gesti"),
    ("timeout_seconds", "secondi"),
    ("sends", "che cosa esce"),
    ("worst_case", "caso peggiore"),
    ("left", "resta nel mese"),
    ("address", "indirizzo"),
    ("gestures", "gesti sulla pagina"),
    ("expect", "testo atteso"),
    ("prompt", "domanda"),
)
"""What the script shows of a question before Tommaso answers, in this order: of a session's, the
sentence, the sites, the model, the money, the looks, the time and what leaves; of a gesture's, the
address, the gestures and the text it expects."""


def shown(question: Mapping[str, Any]) -> list[str]:
    return [
        f"    | {label}: {question[key]}"
        for key, label in QUESTION
        if question.get(key) not in (None, "", [])
    ]


def after_answer(yes: bool, on_child: bool) -> str | None:
    """The state the task is in after the answer: a session's yes queues it; a no denies it; a
    gesture's yes is followed by its run in the same block, which the ``atteso`` after it reads."""
    if not yes:
        return "DENIED"
    return None if on_child else "QUEUED"


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


class Done(Exception):
    """The step ended before its last block: a gesture the model never asked for."""


@dataclass
class Turn:
    """What a step has done so far: its task, the child that asks, the question, what the commands
    of its last block printed, and the run in the background."""

    task_id: str | None = None
    child_id: str | None = None
    approval_id: str | None = None
    last: str = ""
    background: subprocess.Popen[str] | None = None
    background_line: str = ""


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    start: spending.Ledger
    costs: dict[str, Decimal] = field(default_factory=dict)
    """The cost of each session, by its task, written once when the script sees the session ended
    — whatever happens to its step after — : what ``spesa`` adds up (decision 35 (a))."""
    ids: dict[int, str] = field(default_factory=dict)
    """The task of each step: what ``<id del passo N>`` stands for."""


def filled(text: str, turn: Turn, proof: Proof) -> str:
    for placeholder, value in (
        (ID, turn.task_id),
        (CHILD, turn.child_id),
        (APPROVAL_ID, turn.approval_id),
    ):
        text = text.replace(placeholder, value or placeholder)
    return base.STEP_ID.sub(lambda found: proof.ids.get(int(found.group(1)), found.group(0)), text)


def commands(lines: Sequence[str], turn: Turn, proof: Proof) -> None:
    """The commands of a block, in order: ``turn.last`` is what **all** of them printed."""
    turn.last = ""
    for line in lines:
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
        turn.child_id = None
        report.say(f"    il task: {turn.task_id}")


def question_of(api: base.Api, task_id: str | None) -> Mapping[str, Any] | None:
    for one in api.get("/approvals"):
        if one.get("task_id") == task_id:
            return dict(one)
    return None


def answer_in(
    events: Sequence[Mapping[str, Any]], approval_id: str | None
) -> tuple[str, str] | None:
    """The answer the audit records to ``approval_id`` — to the last question of the task when it
    is ``None`` —: its status and who gave it, or ``None`` if nobody has answered."""
    if approval_id is None:
        asked = [
            (one.get("payload") or {}).get("approval_id")
            for one in events
            if one.get("event_type") == REQUESTED
        ]
        approval_id = str(asked[-1]) if asked else None
    for one in reversed(events):
        payload: Mapping[str, Any] = one.get("payload") or {}
        if one.get("event_type") == RESOLVED and payload.get("approval_id") == approval_id:
            return str(payload.get("status")), str(payload.get("responded_by"))
    return None


def answerer_words(identity: str, devices: Sequence[Mapping[str, Any]]) -> str:
    """Who answered, as the command line says it (ADR 0059), resolved as the API resolves it:
    the Core's token by its fixed name, a row of the registry by its name with its role, an id the
    registry does not know alone."""
    if identity == LOCAL_USER.id:
        answered: dict[str, Any] = {"identity": identity, "name": LOCAL_ANSWERER, "role": "LOCAL"}
    else:
        row = next((one for one in devices if str(one.get("id")) == identity), None)
        answered = {
            "identity": identity,
            "name": None if row is None else row.get("name"),
            "role": None if row is None else ROLES.get(str(row.get("role"))),
        }
    said = answered_words({"end": {"answered_by": answered}})
    return identity if said is None else said


def answered_elsewhere(api: base.Api, task_id: str | None, approval_id: str | None) -> str | None:
    """Why the proof stops if the question was answered by someone else than this terminal — a
    page, which also starts the run (``answered_and_resumed``) —, read from the machine; ``None``
    if nobody else did (decision 40)."""
    found = answer_in(api.get(f"/audit?task_id={task_id}"), approval_id)
    if found is None or found[1] == LOCAL_USER.id:
        return None
    status, identity = found
    approval = approval_id or "del task"
    said = ANSWERS.get(status, f"una risposta {status}")
    return (
        f"la domanda {approval} aveva già {said} da {answerer_words(identity, api.get('/devices'))}"
        f"; {ONLY_HERE}"
    )


def an_answer(number: int, block: base.Block, turn: Turn, proof: Proof, *, yes: bool) -> None:
    """``sì`` and ``no``: the question of the task the block's first line names, shown, and
    Tommaso's answer given with the lines of the block. **The question is still waiting** when he
    is asked and right before the command; an answer from another surface stops the proof with who
    gave it — FERMATO, never FAILED: the human step was done elsewhere (decision 40)."""
    report = proof.report
    on_child = CHILD in block.lines[0]
    target = turn.child_id if on_child else turn.task_id
    question = question_of(proof.api, target)
    if question is None:
        no_question(number, target, None, proof)
    assert question is not None
    turn.approval_id = str(question["id"])
    report.say(f"    la domanda {question['id']}, del task {target}:")
    for line in shown(question):
        report.say(line)
    word = "sì" if yes else "no"
    if not base.yes_or_no(proof.ask, f"[{number}] Rispondi {word}? (s/n) "):
        raise base.Stop(SAID_NO)
    if question_of(proof.api, target) is None:
        no_question(number, target, turn.approval_id, proof)
    commands(block.lines, turn, proof)
    expected = after_answer(yes, on_child)
    state = proof.api.get(f"/tasks/{target}").get("state")
    if expected is None or state == expected:
        report.passed(number, f"il {word} al task {target}")
        return
    elsewhere = answered_elsewhere(proof.api, target, turn.approval_id)
    if elsewhere is not None:
        raise base.Stop(elsewhere)
    report.failure(number, f"dopo il {word} il task {target} è {state}, non {expected}")


def no_question(number: int, target: str | None, approval_id: str | None, proof: Proof) -> None:
    """The question is not waiting: answered elsewhere — FERMATO with who —, or gone for another
    reason — FAILED, and the proof stops, since the step has nothing left to measure."""
    elsewhere = answered_elsewhere(proof.api, target, approval_id)
    if elsewhere is not None:
        raise base.Stop(elsewhere)
    proof.report.failure(number, f"il task {target} non ha una domanda in attesa")
    raise base.Stop(NO_QUESTION)


def a_background(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    (line,) = block.lines
    turn.background_line = filled(line, turn, proof)
    proof.report.say(f"    $ {turn.background_line}   (in sfondo)")
    turn.background = base.started(turn.background_line)


def ended_background(turn: Turn, proof: Proof) -> str:
    """What the run in the background printed once it is over — and ELA silent if it said so."""
    running = turn.background
    if running is None:
        raise ValueError(
            "no run in the background to wait for: the guide has a fine without sfondo"
        )
    printed, _ = running.communicate()
    turn.background = None
    base.heard(
        turn.background_line,
        subprocess.CompletedProcess(turn.background_line, running.returncode, printed or "", ""),
    )
    for one in (printed or "").rstrip("\n").splitlines():
        proof.report.say(f"    | {one}")
    return printed or ""


def asking_child(api: base.Api, task_id: str | None, capability: str) -> str | None:
    """A child of ``task_id`` whose gesture of ``capability`` waits for an answer: from the
    questions that wait — a gesture that asks has one —, never from the list of every task."""
    for one in api.get("/approvals"):
        if one.get("capability_id") != capability:
            continue
        child = api.get(f"/tasks/{one['task_id']}")
        if child.get("parent_id") == task_id:
            return str(one["task_id"])
    return None


def session_over(proof: Proof, task_id: str | None) -> Mapping[str, Any] | None:
    """The result that closed a session the script has seen end, and its cost counted for
    ``spesa`` — once per session, whatever its step does after (decision 35 (a))."""
    found = the_session(proof.api.get(f"/tasks/{task_id}/results"))
    cost = cost_of(found)
    if task_id is not None and cost is not None:
        proof.costs.setdefault(task_id, cost)
    return found


def a_wait(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    """``aspetta``: no threshold of time (M6.3c, decision 7) — until the child asks, or until the
    session ends. A session over before the gesture is said as it ended: SKIPPED if it ended by
    itself or on a limit the yes allowed, FAILED with its code otherwise (decision 35)."""
    (line,) = block.lines
    capability = waited(line)
    while True:
        found = asking_child(proof.api, turn.task_id, capability)
        if found is not None:
            turn.child_id = found
            proof.report.passed(number, f"il gesto {capability} chiede: il figlio {found}")
            return
        if turn.background is None or turn.background.poll() is not None:
            turn.last = ended_background(turn, proof) if turn.background is not None else ""
            said, skipped = ending_of(session_over(proof, turn.task_id))
            what = f"la sessione è finita {said}, senza un {capability} che chiede"
            if skipped:
                proof.report.skipped(number, what)
            else:
                proof.report.failure(number, what)
            raise Done
        time.sleep(WAIT)


def an_end(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    proof.report.say(f"    la corsa in sfondo: {turn.background_line}")
    turn.last = ended_background(turn, proof)
    session_over(proof, turn.task_id)
    absent = base.missing(block.lines, turn.last)
    if absent:
        proof.report.failure(number, f"mancano {absent}", turn.last)
    else:
        proof.report.passed(number, "la corsa in sfondo ha stampato ciò che è atteso")


def written_session(report: base.Report, found: Mapping[str, Any]) -> None:
    """The session in the file: the model's answer, the gestures, the calls, the cost."""
    output: Mapping[str, Any] = found.get("output") or {}
    report.say(f"    la risposta del modello: {output.get('text')!r}")
    report.say(
        f"    gesti {output.get('looks')}, negati {output.get('refused')}, azioni "
        f"{output.get('acts')}; chiamate {output.get('calls')}, token {output.get('input_tokens')} "
        f"in e {output.get('output_tokens')} out, costo {output.get('cost')} {CURRENCY}"
    )
    report.say(
        f"    il costo che Claude Code ha stimato: {output.get('reported_cost')}; la sua versione: "
        f"{output.get('version')}; token meno byte, al più: {output.get('input_minus_bytes_max')}"
    )
    for number, call in enumerate(output.get("per_call") or [], start=1):
        report.say(f"    chiamata {number}: {call[1]} token in, {call[2]} out, {call[3]} byte")


def a_session(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    (line,) = block.lines
    results = proof.api.get(f"/tasks/{turn.task_id}/results")
    found = session_over(proof, turn.task_id)
    if found is not None:
        written_session(proof.report, found)
    cost = cost_of(found)
    now = spending.Ledger.of(proof.api.get("/spend"))
    failures = session_failures(line, results, proof.start.open, now.open)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la sessione {line}, chiusa, costo {cost} {CURRENCY}")


def existing(api: base.Api, task_id: str) -> Mapping[str, Any] | None:
    """A task, or ``None`` when ELA does not have it: a gesture refused before its child."""
    try:
        found: Mapping[str, Any] = api.get(f"/tasks/{task_id}")
    except ApiRefusal as refused:
        if refused.status == 404:
            return None
        raise
    return found


def a_family(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    """``figli``: the children of the session's gestures, read and checked one by one."""
    report = proof.report
    detail = proof.api.get(f"/tasks/{turn.task_id}")
    (step,) = detail["steps"]
    session, sites = str(step["id"]), list(step["arguments"]["sites"])
    found = the_session(proof.api.get(f"/tasks/{turn.task_id}/results"))
    looks = int(((found or {}).get("output") or {}).get("looks") or 0)
    children = [
        child
        for one in gesture_ids(str(turn.task_id), session, looks)
        if (child := existing(proof.api, one)) is not None
    ]
    rules = {
        str(child["id"]): rule_of(proof.api.get(f"/audit?task_id={child['id']}"))
        for child in children
    }
    for child in children:
        end = (child.get("end") or {}).get("reason") or ""
        if not child.get("steps"):
            # Arguments ELA could not plan: the child is cancelled before it has a plan, and the
            # session read the gesture as refused. The model's malformed gesture, not a broken rule.
            report.say(f"    un gesto senza piano → {child.get('state')} {end}".rstrip())
            continue
        arguments = child["steps"][0].get("arguments") or {}
        report.say(
            f"    {capability_of(child)} {arguments.get('site')}{arguments.get('path', '')} → "
            f"{child.get('state')} {rules.get(str(child['id'])) or ''} {end}".rstrip()
        )
    planned = [child for child in children if child.get("steps")]
    failures = [one for child in planned for one in child_failures(child, session, sites)]
    matched = 0
    for line in block.lines:
        if line == INSIDE:
            outside = [child for child in planned if not inside(child, sites)]
            failures.extend(
                f"il gesto del figlio {child.get('id')} è andato a "
                f"{child['steps'][0]['arguments'].get('site')}, fuori dai siti della sessione"
                for child in outside
            )
            matched += 1
            continue
        capability = wanted(line)[0]
        if not asked_for(capability, planned):
            report.skipped(number, f"nessun gesto {capability} fra i figli della sessione")
            continue
        why = unmatched(line, planned, rules)
        if why is None:
            matched += 1
        else:
            failures.append(why)
    if failures:
        report.failure(number, "; ".join(failures))
    elif matched:
        report.passed(
            number,
            f"{len(children)} figli, scritti dalla sessione e dentro i suoi siti: {block.body}",
        )


def a_tier(number: int, block: base.Block, proof: Proof) -> None:
    (line,) = block.lines
    task = filled(line, Turn(), proof)
    found = the_session(proof.api.get(f"/tasks/{task}/results"))
    if found is None:
        proof.report.failure(number, f"il task {task} non ha il risultato della sessione")
        return
    calls = (found.get("output") or {}).get("per_call") or []
    for index, call in enumerate(calls, start=1):
        proof.report.say(f"    chiamata {index}: {list(call)}")
    failures = tier_failures(found)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        ((bound, _),) = TIERS[MODEL]
        proof.report.passed(
            number,
            f"{len(calls)} chiamate sotto i {bound} token d'ingresso: la fascia bassa dà "
            f"{low_tier(calls)} {CURRENCY}, il libro ha scritto {cost_of(found)}",
        )


def a_ledger(number: int, block: base.Block, proof: Proof) -> None:
    now = spending.Ledger.of(proof.api.get("/spend"))
    failures = planning.ledger_failures(block.lines, proof.start, now, list(proof.costs.values()))
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(
            number, f"speso +{now.spent - proof.start.spent} {CURRENCY}, prenotato {now.reserved}"
        )


def a_step(number: int, todo: Sequence[base.Block], proof: Proof, turn: Turn | None = None) -> None:
    """The blocks of a step in order; ``turn`` is a new one, unless a test hands its own."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = Turn() if turn is None else turn
    blocks = list(todo)
    index = 0
    try:
        while index < len(blocks):
            index += 1
            try:
                a_block(number, blocks[index - 1], turn, proof)
            except Done:
                index = next_round(blocks, index)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id
        if turn.background is not None and turn.background.poll() is None:
            report.say(
                f"    la corsa in sfondo di {turn.task_id} gira ancora: la ferma la durata della "
                f"sessione, o `uv run ela task cancel {turn.task_id}`"
            )


def next_round(blocks: Sequence[base.Block], start: int) -> int:
    """Where the step goes on after a round that ended early: the next block that creates its own
    task — the second round of step 5 —, or the end of the step."""
    for index in range(start, len(blocks)):
        block = blocks[index]
        if block.kind == "comando" and any(CREATE in f" {line} " for line in block.lines):
            return index
    return len(blocks)


def a_block(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
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
    elif kind in ("sì", "no"):
        an_answer(number, block, turn, proof, yes=kind == "sì")
    elif kind == "sfondo":
        a_background(number, block, turn, proof)
    elif kind == "aspetta":
        a_wait(number, block, turn, proof)
    elif kind == "fine":
        an_end(number, block, turn, proof)
    elif kind == "sessione":
        a_session(number, block, turn, proof)
    elif kind == "figli":
        a_family(number, block, turn, proof)
    elif kind == "fascia":
        a_tier(number, block, proof)
    elif kind == "spesa":
        a_ledger(number, block, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


Why = Callable[[], "str | None"]
"""A check of step 1: ``None`` if it holds, or why it does not."""


def so(condition: bool) -> str | None:
    return None if condition else NOT_SO


def margin_short(left: str | None, needed: Decimal, sessions: int) -> str | None:
    """Why what is left of the month is not enough for the sessions at their most — with the two
    numbers, what is left and what they reserve (decision 38) —, or ``None``."""
    if left is None:
        return "e ELA non ha un tetto: GET /spend dice left null"
    if Decimal(left) >= needed:
        return None
    return f"e restano {left} {CURRENCY}, mentre le {sessions} sessioni ne prenotano {needed}"


def stopping(report: base.Report, checks: Sequence[tuple[str, Why]]) -> bool:
    """The checks of step 1 in order; **the first that does not hold stops the proof** — FERMATO,
    with why, or with what it raised —: the rest would measure something else."""
    for what, check in checks:
        try:
            why = check()
        except Exception as error:  # noqa: BLE001 — every miss is reported with what it said
            report.stop(1, f"la prova richiede «{what}» ({type(error).__name__}: {error})")
            return False
        if why is not None:
            report.stop(1, f"la prova richiede «{what}», {why}")
            return False
        report.passed(1, what)
    return True


def preconditions(report: base.Report, plans: Sequence[Path]) -> bool:
    """Step 1: what the proof requires of the world, the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    try:
        needed = margin(plans)
    except Exception as error:  # noqa: BLE001 — the miss is reported with what it said
        report.stop(
            1, f"il margine delle sessioni non si calcola ({type(error).__name__}: {error})"
        )
        return False
    checks: list[tuple[str, Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: {GUIDED} è nel catalogo di /diagnostics",
            lambda: so(GUIDED in base.Api().get("/diagnostics")["capabilities"]),
        ),
        (
            f"lo schema dell'API ha {SESSION_ROUTE}",
            lambda: so(SESSION_ROUTE in base.Api().get("/openapi.json")["paths"]),
        ),
        (f"uv run alembic current dice {planning.MIGRATION}", lambda: so(planning.migrated())),
        (
            f"il .env manda la rotta di una sessione a {MODEL} (la domanda del passo 2 lo legge "
            "dal Core)",
            lambda: so(route_model() == MODEL),
        ),
        ("il provider del modello ha una chiave", lambda: so(spending.keyed())),
        ("il tetto è dichiarato", lambda: so(base.Api().get("/spend")["cap"] is not None)),
        (
            f"restano almeno {needed} {CURRENCY}, {len(plans)} sessioni al loro costo massimo",
            lambda: margin_short(base.Api().get("/spend")["left"], needed, len(plans)),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: so(not sites_missing(BrowserSettings().sites)),
        ),
        (
            "il binario di Claude Code che l'SDK porta c'è, e si può lanciare",
            lambda: so(binary_ready()),
        ),
    ]
    return stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m14.3-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M14.3 e M14.6, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if preconditions(report, plans_of(todo)):
            api = base.Api()
            proof = Proof(api, report, ask, spending.Ledger.of(api.get("/spend")))
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
