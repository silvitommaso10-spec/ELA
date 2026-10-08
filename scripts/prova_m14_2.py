"""La prova a mano di M14.2: il Planner (``docs/GETTING_STARTED.md``, sezione 24).

    uv run python scripts/prova_m14_2.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m14_2.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script legge dalla sezione 24 i blocchi con il marcatore
sopra, ``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa il
confronto «a parole intere e in ordine», il rapporto, il client dell'API e ``Stop``; di
``scripts/prova_m14_1.py`` usa la lettura di una chiamata e del libro del mese.
``tests/docs/test_prova_m14_2.py`` legge la sezione con lo stesso lettore e tiene allineati i due,
con un caso negativo per ogni confronto di questo file.

I tipi di §21 — ``comando``, ``atteso``, ``occhio`` — e cinque suoi (la SPEC di M14.2, «La prova a
mano», e le decisioni 4, 15 e 16 della review):

* ``sì``: legge il task di pianificazione del task del passo e la sua domanda, la mostra, e chiede
  «rispondi sì?»; con un «s» esegue la riga del blocco — il sì con la CLI —, con un «n» la prova si
  ferma: il resto del passo non avrebbe niente da misurare;
* ``piano``: il task ``QUEUED``, l'autore ``MODEL`` con un risultato e il modello della rotta, e
  ogni step dentro il catalogo **del codice** al commit del passo 1 — il catalogo e i verifier,
  mai le funzioni del Planner: una capability, le condizioni nel suo vocabolario, il rischio e la
  domanda del catalogo, nessun tratto, nessuno ``HIGH`` —; ogni riga è una capability che il piano
  deve avere, e per ``model.complete`` un ``task_type`` della tabella. Il catalogo che il Planner
  ha mandato si confronta con lo stesso: ogni sua capability c'è, con lo stesso rischio, la stessa
  domanda e lo stesso vocabolario;
* ``chiamata``: il risultato del task di pianificazione, con il modello, un costo e un
  ``finish_reason``; scrive **se la risposta era un oggetto JSON** e **i token d'uscita**
  (decisione 4);
* ``rifiuto``: il task ``FAILED`` con il codice della riga, nessun piano, e le parole del modello
  stampate; **un piano valido fa il passo SALTATO**, non FALLITO, e lo script lo scrive nel file e
  chiede l'occhio (decisione 16);
* ``spesa``: ``GET /spend`` confrontato con com'era al passo 1.

I segnaposto sono ``<id>`` — il task del passo —, ``<nota>`` — il nome della nota del passo 2,
**unico per giro**, con la data e l'ora (decisione 15) —, ``<id del figlio>`` e ``<approval-id>``.
**Una precondizione del passo 1 che cade ferma la prova** — FERMATO, con la ragione —: il resto
misurerebbe un'altra cosa. Si ferma ad aspettare solo per i sì e per l'occhio. La riga finale è
quella di M6.3c: «La prova è passata» solo senza FALLITO, senza SALTATO e con ogni GUARDATO un sì.
Tutto va anche nel file, in ``~/Downloads``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m14_1 as spending  # noqa: E402 — the same

from ela.executive.planner import PLANNING_OUTPUT_TOKENS  # noqa: E402
from ela.providers.anthropic.models import MODELS, OPUS_5_5  # noqa: E402
from ela.providers.anthropic.pricing import worst_cost  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 24. "
KINDS: Final = ("comando", "atteso", "occhio", "sì", "piano", "chiamata", "rifiuto", "spesa")
ID = base.ID
NOTE: Final = "<nota>"
CHILD: Final = "<id del figlio>"
APPROVAL_ID: Final = spending.APPROVAL_ID
PLACEHOLDERS: Final = (ID, NOTE, CHILD, APPROVAL_ID)
CREATE: Final = spending.CREATE
MODEL: Final = OPUS_5_5
"""The model of the route of ``planning`` (§25): every call of the proof goes there."""
CURRENCY: Final = spending.CURRENCY
SUCCEEDED: Final = spending.SUCCEEDED
PLANNING_ROUTE: Final = "/tasks/{task_id}/planning"
MIGRATION: Final = "0014 (head)"
SITE: Final = "example.com"
CATALOGUE_OPENS: Final = "Catalogue (JSON):\n"
CATALOGUE_CLOSES: Final = "\n\nAnswer schema"
MODEL_COMPLETE: Final = "model.complete"
HIGH: Final = "HIGH"
SPENT_BY_THE_CALLS: Final = "speso cresciuto dei costi delle chiamate"
RESERVED_AS_AT_STEP_1: Final = "prenotato com'era al passo 1"
LEDGER_WORDS: Final = (SPENT_BY_THE_CALLS, RESERVED_AS_AT_STEP_1)
"""The vocabulary of ``spesa``: what changed in ``GET /spend`` since step 1."""
SAID_NO: Final = "hai risposto no: il resto del passo non avrebbe niente da misurare"


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def note_name(now: datetime) -> str:
    """The note of step 2, one per round (decision 15): a second round never finds the first's."""
    return f"prova-m14.2-{now:%Y%m%d-%H%M%S}.md"


def calls_of(todo: Mapping[int, Sequence[base.Block]]) -> int:
    """How many planning calls the proof makes: one for each ``sì`` of the section."""
    return sum(1 for blocks in todo.values() for block in blocks if block.kind == "sì")


def margin(calls: int) -> Decimal:
    """What the month must have left for ``calls`` plannings at their worst case: the worst case
    is the one the gate reserves, from the function the adapter's ``worst_case`` calls with the
    Planner's output budget (decision 14) — never a number written here."""
    worst = worst_cost(MODELS[MODEL], output_tokens=PLANNING_OUTPUT_TOKENS)
    assert worst is not None, f"{MODEL} has no price"
    return calls * worst


def enough_left(left: str | None, needed: Decimal) -> str | None:
    """Why the month has not ``needed`` left, or ``None`` if it has."""
    if left is None:
        return "ELA non ha un tetto: GET /spend dice left null"
    if Decimal(left) >= needed:
        return None
    return f"restano {left} {CURRENCY}, e le chiamate della prova ne prenotano {needed}"


def same_as_origin(head: str, upstream: str, dirty: str) -> str | None:
    """Why this Mac is not on the last commit of its branch on ``origin`` with a clean tree."""
    if dirty.strip():
        return "l'albero non è pulito: `git status --porcelain` non è vuoto"
    if head.strip() != upstream.strip():
        return f"il Mac è su {head.strip()[:7]}, origin su {upstream.strip()[:7]}"
    return None


def at_the_migration(printed: str) -> bool:
    """Whether ``alembic current`` says the database is at ``0014``, the head of M14.2."""
    return MIGRATION in printed


def code_catalogue(
    specs: Sequence[Any], verifiers: Sequence[Any], task_types: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """What the code says of every capability a verifier checks: its risk, whether it asks, the
    vocabulary of its verifier — and for ``model.complete`` the task types of the routing table.

    Read from the catalogue and the verifiers, **never from the Planner's functions** (question 3
    of the review of the summary, 2026-10-08): the Planner derives its catalogue and writes the
    risk of a step from the same source, so a derivation gone wrong would make plan and catalogue
    agree, and a check of one against the other would pass."""
    vocabulary = {str(one.capability_id): sorted(one.conditions) for one in verifiers}
    found: dict[str, dict[str, Any]] = {}
    for spec in specs:
        name = str(spec.id)
        if name not in vocabulary:
            continue
        entry: dict[str, Any] = {
            "risk": spec.risk.value,
            "asks_the_user": spec.requires_authorization,
            "success_conditions": vocabulary[name],
        }
        if name == MODEL_COMPLETE:
            entry["task_types"] = sorted(task_types)
        found[name] = entry
    return found


def read_code_catalogue() -> dict[str, dict[str, Any]]:
    """:func:`code_catalogue` of the code of this checkout — the commit step 1 verified: the
    production catalogue, and the verifiers of :func:`~ela.tools.registry.production_verifiers`,
    the function the composition calls. Built with arguments nothing reads — a verifier's
    vocabulary is an attribute of its class, its capability the constructor's —, so nothing is
    opened: no database, no browser, no network. ``build`` would write the row of ``local``."""
    from types import SimpleNamespace

    from ela.permissions.capabilities import production_catalogue
    from ela.routing.settings import RoutingSettings
    from ela.tools.registry import production_verifiers

    unread = SimpleNamespace(directory=ROOT, settings=SimpleNamespace(capture_ttl=None))
    verifiers = production_verifiers(
        root=ROOT,
        router=None,  # type: ignore[arg-type]
        captures=unread,  # type: ignore[arg-type]
        fs_root=ROOT,
        programs=None,  # type: ignore[arg-type]
        browser=None,  # type: ignore[arg-type]
        browser_seconds=0,
    )
    return code_catalogue(
        production_catalogue().specs(),
        verifiers.verifiers(),
        RoutingSettings().policy().task_types(),
    )


def sent_failures(
    sent: Mapping[str, Mapping[str, Any]], code: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """What the catalogue the Planner sent says and the code does not: every capability of it is
    in the code, with the same risk, the same question and the same vocabulary."""
    failures: list[str] = []
    for name, entry in sent.items():
        known = code.get(name)
        if known is None:
            failures.append(f"il catalogo mandato ha {name}, che il codice non ha")
            continue
        if entry.get("risk") != known["risk"]:
            failures.append(
                f"il catalogo mandato dice {name} {entry.get('risk')}, il codice {known['risk']}"
            )
        if bool(entry.get("asks_the_user")) != known["asks_the_user"]:
            failures.append(
                f"il catalogo mandato dice che {name} chiede: {bool(entry.get('asks_the_user'))}, "
                f"il codice {known['asks_the_user']}"
            )
        if sorted(entry.get("success_conditions") or []) != known["success_conditions"]:
            failures.append(f"il vocabolario mandato di {name} non è quello del suo verifier")
    return failures


def catalogue_of(instructions: str) -> dict[str, Mapping[str, Any]]:
    """The catalogue the Planner sent the model, read from the planning task's own step: it is
    checked against the code's (:func:`sent_failures`), and the plan is read against the code's
    too — never against what the Planner itself derived."""
    if CATALOGUE_OPENS not in instructions:
        raise ValueError("the instructions carry no catalogue")
    listed = instructions.split(CATALOGUE_OPENS, 1)[1].split(CATALOGUE_CLOSES, 1)[0]
    return {str(entry["capability"]): entry for entry in json.loads(listed)}


def plan_failures(
    task: Mapping[str, Any], catalogue: Mapping[str, Mapping[str, Any]], wanted: Sequence[str]
) -> list[str]:
    """What ``piano`` finds wrong with the plan of ``task``, one sentence each; ``[]`` if none."""
    failures: list[str] = []
    if task.get("state") != "QUEUED":
        failures.append(f"il task è {task.get('state')}, non QUEUED")
    author = task.get("plan_author") or {}
    if author.get("by") != "MODEL" or not author.get("result_id"):
        failures.append(f"l'autore è {author}, non MODEL con un risultato")
    elif author.get("model") != MODEL:
        failures.append(f"il modello dell'autore è {author.get('model')!r}, non {MODEL!r}")
    steps: Sequence[Mapping[str, Any]] = task.get("steps") or []
    if not steps:
        failures.append("il piano non ha step")
    named: list[str] = []
    for index, step in enumerate(steps, start=1):
        failures.extend(_step_failures(index, step, catalogue))
        named.extend(step.get("required_capabilities") or [])
    failures.extend(f"nessuno step usa {one}" for one in wanted if one not in named)
    return failures


def _step_failures(
    index: int, step: Mapping[str, Any], catalogue: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    where = f"lo step {index}"
    capabilities = step.get("required_capabilities") or []
    if len(capabilities) != 1 or capabilities[0] not in catalogue:
        return [f"{where} dichiara {capabilities}, non una capability del catalogo"]
    entry = catalogue[capabilities[0]]
    failures: list[str] = []
    conditions = step.get("success_conditions") or []
    vocabulary = set(entry.get("success_conditions") or [])
    if not conditions or not set(conditions) <= vocabulary:
        failures.append(f"{where} ha le condizioni {conditions}, fuori da {sorted(vocabulary)}")
    if step.get("risk") != entry.get("risk"):
        failures.append(
            f"{where} ha il rischio {step.get('risk')}, il catalogo {entry.get('risk')}"
        )
    if step.get("risk") == HIGH:
        failures.append(f"{where} è HIGH")
    if bool(step.get("requires_authorization")) != bool(entry.get("asks_the_user")):
        failures.append(f"{where} non chiede come il catalogo")
    if step.get("preferred_device_traits"):
        failures.append(f"{where} preferisce dei tratti: {step.get('preferred_device_traits')}")
    if capabilities[0] == MODEL_COMPLETE:
        task_type = (step.get("arguments") or {}).get("task_type")
        if task_type not in (entry.get("task_types") or []):
            failures.append(f"{where} ha il task_type {task_type!r}, fuori dalla tabella")
    return failures


@dataclass(frozen=True)
class Measure:
    """What ``chiamata`` writes of an answer (decision 4): the measure the question of the
    structured outputs is reopened with."""

    json_object: bool
    output_tokens: int | None


def measured(results: Sequence[Mapping[str, Any]]) -> Measure:
    """Whether the answer that came back was one JSON object, and its output tokens."""
    answered = [one for one in results if one.get("status") == SUCCEEDED]
    if not answered:
        return Measure(False, None)
    found = answered[-1]
    text = (found.get("output") or {}).get("output")
    try:
        parsed = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        parsed = None
    tokens = (found.get("usage") or {}).get("output_tokens")
    return Measure(isinstance(parsed, dict), tokens if isinstance(tokens, int) else None)


def refusal_failures(task: Mapping[str, Any], code: str) -> list[str]:
    """What ``rifiuto`` finds wrong: the task ``FAILED`` with ``code``, no plan, and the model's
    words."""
    failures: list[str] = []
    if task.get("state") != "FAILED":
        failures.append(f"il task è {task.get('state')}, non FAILED")
    if code not in (task.get("reason") or ""):
        failures.append(f"la ragione non dice {code}: {task.get('reason')!r}")
    if task.get("plan_id") is not None:
        failures.append("il task ha un piano")
    if not task.get("no_plan"):
        failures.append("le parole del modello non ci sono")
    return failures


def ledger_failures(
    lines: Sequence[str], start: spending.Ledger, now: spending.Ledger, costs: Sequence[Decimal]
) -> list[str]:
    """What ``spesa`` says changed and did not since step 1, one sentence per line that fails."""
    failures: list[str] = []
    for line in lines:
        if line == SPENT_BY_THE_CALLS and now.spent - start.spent != sum(costs, Decimal(0)):
            failures.append(
                f"lo speso è cresciuto di {now.spent - start.spent}, le chiamate costano "
                f"{sum(costs, Decimal(0))}"
            )
        elif line == RESERVED_AS_AT_STEP_1 and now.reserved != start.reserved:
            failures.append(f"il prenotato è {now.reserved}, al passo 1 {start.reserved}")
        elif line not in LEDGER_WORDS:
            raise ValueError(f"{line!r} is not in the vocabulary of spesa")
    return failures


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


class Done(Exception):
    """The step ended before its last block: a valid plan where none was asked (decision 16)."""


@dataclass
class Turn:
    """What a step has done so far: its task, the planning task, the question, the last output."""

    task_id: str | None = None
    child_id: str | None = None
    approval_id: str | None = None
    last: str = ""


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    note: str
    start: spending.Ledger
    costs: list[Decimal] = field(default_factory=list)
    """The cost of each call ``chiamata`` read: what ``spesa`` adds up."""
    code: Mapping[str, Mapping[str, Any]] = field(default_factory=read_code_catalogue)
    """The catalogue of the code, read once, after step 1 verified the commit: what ``piano``
    reads a plan against, and what the catalogue the Planner sent is checked against."""


def filled(text: str, turn: Turn, note: str) -> str:
    for placeholder, value in (
        (ID, turn.task_id),
        (NOTE, note),
        (CHILD, turn.child_id),
        (APPROVAL_ID, turn.approval_id),
    ):
        text = text.replace(placeholder, value or placeholder)
    return text


def a_command(line: str, turn: Turn, proof: Proof) -> None:
    report = proof.report
    report.say(f"    $ {line}")
    done = base.heard(line, base.run(line))
    turn.last = done.stdout + done.stderr
    for printed in turn.last.rstrip("\n").splitlines():
        report.say(f"    | {printed}")
    if CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        report.say(f"    il task: {turn.task_id}")


def the_question(proof: Proof, turn: Turn) -> Mapping[str, Any] | None:
    """The planning task of the step's task, and its question, from the API."""
    detail = proof.api.get(f"/tasks/{turn.task_id}")
    turn.child_id = detail.get("planning_task_id")
    for one in proof.api.get("/approvals"):
        if one.get("task_id") == turn.child_id:
            turn.approval_id = str(one["id"])
            return dict(one)
    return None


def a_yes(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    report = proof.report
    question = the_question(proof, turn)
    if question is None:
        report.failure(number, f"il task di pianificazione {turn.child_id} non ha una domanda")
        raise base.Stop("senza la domanda il passo non ha niente da misurare")
    report.say(f"    la domanda {question['id']}, del task di pianificazione {turn.child_id}:")
    report.say(f"    | {question.get('prompt')}")
    report.say(f"    | caso peggiore: {question.get('worst_case')}")
    report.say(f"    | resta nel mese: {question.get('left')}")
    if not base.yes_or_no(proof.ask, f"[{number}] Rispondi sì? (s/n) "):
        raise base.Stop(SAID_NO)
    for line in block.lines:
        a_command(filled(line, turn, proof.note), turn, proof)
    child = proof.api.get(f"/tasks/{turn.child_id}")
    if child.get("state") == "QUEUED":
        report.passed(number, f"il sì al task di pianificazione {turn.child_id}")
    else:
        report.failure(number, f"dopo il sì il task di pianificazione è {child.get('state')}")


def written_plan(proof: Proof, task: Mapping[str, Any]) -> None:
    """The plan in the file, step by step, with its arguments: what the eye judges."""
    for index, step in enumerate(task.get("steps") or [], start=1):
        capability = ", ".join(step.get("required_capabilities") or [])
        proof.report.say(f"    step {index}: {capability} — {step.get('goal')}")
        arguments = json.dumps(step.get("arguments") or {}, ensure_ascii=False)
        proof.report.say(f"      argomenti: {arguments}")
        proof.report.say(f"      condizioni: {', '.join(step.get('success_conditions') or [])}")


def a_plan(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    task = proof.api.get(f"/tasks/{turn.task_id}")
    turn.child_id = task.get("planning_task_id") or turn.child_id
    child = proof.api.get(f"/tasks/{turn.child_id}")
    (call,) = child.get("steps") or [{}]
    sent = catalogue_of(str((call.get("arguments") or {}).get("instructions", "")))
    written_plan(proof, task)
    failures = [*sent_failures(sent, proof.code), *plan_failures(task, proof.code, block.lines)]
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(
            number,
            f"un piano di {len(task['steps'])} step dentro il catalogo del codice, scritto da "
            f"{MODEL}; il catalogo mandato è quello del codice",
        )


def a_call(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    (model,) = block.lines
    results = proof.api.get(f"/tasks/{turn.child_id}/results")
    found = spending.the_call(
        results, model, on_a_node=False, here=base.this_machine(), workspaces=[]
    )
    measure = measured(results)
    proof.report.say(
        f"    la risposta era un oggetto JSON: {'sì' if measure.json_object else 'no'}; "
        f"token d'uscita: {measure.output_tokens}"
    )
    if isinstance(found, str):
        proof.report.failure(number, found)
        return
    proof.costs.append(found.cost)
    proof.report.passed(number, f"{model}: costo {found.cost} {CURRENCY}")


def a_refusal(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    (code,) = block.lines
    task = proof.api.get(f"/tasks/{turn.task_id}")
    if task.get("plan_id") is not None and task.get("state") == "QUEUED":
        proof.report.skipped(
            number, "il modello ha scritto un piano valido: non è un errore di ELA"
        )
        written_plan(proof, task)
        proof.report.looked(
            number,
            "Il piano scritto dal modello",
            base.yes_or_no(proof.ask, f"[{number}] Il piano nel file ha senso? (s/n) "),
        )
        raise Done
    failures = refusal_failures(task, code)
    if failures:
        proof.report.failure(number, "; ".join(failures))
        return
    proof.report.say(f"    le parole del modello: {task['no_plan']}")
    proof.report.passed(number, f"FAILED con {code}, nessun piano")


def a_ledger(number: int, block: base.Block, proof: Proof) -> None:
    now = spending.Ledger.of(proof.api.get("/spend"))
    failures = ledger_failures(block.lines, proof.start, now, proof.costs)
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
    try:
        for block in todo:
            kind = block.kind
            if kind == "comando":
                for line in block.lines:
                    a_command(filled(line, turn, proof.note), turn, proof)
            elif kind == "atteso":
                wanted = [filled(line, turn, proof.note) for line in block.lines]
                absent = base.missing(wanted, turn.last)
                if absent:
                    report.failure(number, f"mancano {absent}", turn.last)
                else:
                    report.passed(number, "l'uscita è quella attesa")
            elif kind == "occhio":
                text = filled(block.body, turn, proof.note)
                yes = base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) ")
                report.looked(number, text, yes)
            elif kind == "sì":
                a_yes(number, block, turn, proof)
            elif kind == "piano":
                a_plan(number, block, turn, proof)
            elif kind == "chiamata":
                a_call(number, block, turn, proof)
            elif kind == "rifiuto":
                a_refusal(number, block, turn, proof)
            elif kind == "spesa":
                a_ledger(number, block, proof)
            else:
                raise ValueError(f"step {number}: {kind!r} is not a kind of the section")
    except Done:
        return


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def git(*arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def on_origin() -> str | None:
    git("fetch", "--quiet")
    return same_as_origin(
        git("rev-parse", "HEAD"), git("rev-parse", "@{u}"), git("status", "--porcelain")
    )


def migrated() -> bool:
    printed = subprocess.run(
        ["uv", "run", "alembic", "current"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return at_the_migration(printed.stdout + printed.stderr)


def stopping(report: base.Report, checks: Sequence[tuple[str, base.Check]]) -> bool:
    """Step 1: what the proof requires of the world. **The first one missing stops the proof** —
    FERMATO, with what is missing (rule 5 of the session of M14.2): the rest would measure
    something else. A check that raises is missing too, with what it said."""
    for what, check in checks:
        try:
            ok = check()
        except Exception as error:  # noqa: BLE001 — every miss is reported with what it said
            report.stop(1, f"la prova richiede «{what}» ({type(error).__name__}: {error})")
            return False
        if not ok:
            report.stop(1, f"la prova richiede «{what}», e non è così")
            return False
        report.passed(1, what)
    return True


def preconditions(report: base.Report, calls: int) -> bool:
    from ela.composition.settings import BrowserSettings

    needed = margin(calls)
    checks: list[tuple[str, base.Check]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: on_origin() is None,
        ),
        ("ELA risponde", lambda: base.Api().get("/health") is not None),
        (
            f"il Core gira dal codice del branch: lo schema ha {PLANNING_ROUTE}",
            lambda: PLANNING_ROUTE in base.Api().get("/openapi.json")["paths"],
        ),
        (f"uv run alembic current dice {MIGRATION}", migrated),
        ("il provider del modello ha una chiave", spending.keyed),
        ("il tetto è dichiarato", lambda: base.Api().get("/spend")["cap"] is not None),
        (
            f"restano almeno {needed} {CURRENCY}, {calls} pianificazioni al caso peggiore",
            lambda: enough_left(base.Api().get("/spend")["left"], needed) is None,
        ),
        (f"{SITE} è fra i siti dichiarati", lambda: SITE in BrowserSettings().sites),
    ]
    return stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m14.2-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M14.2, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if preconditions(report, calls_of(todo)):
            api = base.Api()
            note = note_name(datetime.now())
            report.say(f"    la nota del passo 2: {note}")
            proof = Proof(api, report, ask, note, spending.Ledger.of(api.get("/spend")))
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
