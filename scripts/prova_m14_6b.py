"""La prova a mano di M14.6b: Haiku 4.5 fuori dal listino.

La sezione 31 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m14_6b.py               # contro l'ELA che gira
    uv run python scripts/prova_m14_6b.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m13_13.py`` (decisione 13
del prompt di M14.6b): legge dalla sezione 31 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``; delle sezioni 28–30 usa
``comando``, ``atteso``, ``occhio`` e ``schermo``, il controllo del commit e dell'albero e il
«FERMATO»; della sezione 23 ``spesa`` e ``costo``. ``tests/docs/test_prova_m14_6b.py`` legge la
sezione con lo stesso lettore e tiene allineati i due.

I tipi suoi, che la sezione spiega:

* ``ottobre``: un task di ottobre 2026 con un risultato riuscito sul modello della riga e un costo,
  trovato attraverso ``GET /tasks`` e ``GET /tasks/{id}/results``; letto con
  ``uv run ela task results <id> --json`` — il modello e il costo che la CLI stampa sono quelli
  dell'API — e con ``uv run ela task show <id>``, che risponde con lo stato e non ha né modello né
  costo. Nel file l'id, la data, il modello e il costo; il testo del modello mai. **Se il database
  non ne ha uno il passo è SALTATO**, con la ragione, e la prova continua (risposta 28);
* ``ricalcolo``: il risultato della chiamata del passo ha i token d'ingresso, cache compresa, nella
  fascia bassa del suo modello, e il costo che il libro ha scritto è quello che la fascia bassa
  **del listino** dà su quei token — il metodo di ``low_tier`` della prova di M14.3, su una
  chiamata sola, e non ``estimate_cost``, che la fascia la sceglie da sé.

Ogni passo comincia leggendo ``GET /spend``: la ``spesa`` di un passo dice che cosa è cambiato da
lì. **Lo script non tocca il ``.env``, il database né ``ela serve``** (decisione 13): legge ELA
attraverso l'API e la CLI, e ``ela serve`` lo avvia Tommaso.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
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

from ela.executive.spending import dollars  # noqa: E402
from ela.providers.anthropic.models import HAIKU_5_5, MODELS  # noqa: E402
from ela.providers.anthropic.pricing import (  # noqa: E402
    CENTS_OF_A_MICRO_DOLLAR,
    PER_MILLION,
    PRICES,
    TIERS,
    worst_cost,
)
from ela.providers.anthropic.settings import DEFAULT_MAX_OUTPUT_TOKENS  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 31. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "schermo",
    "spesa",
    "costo",
    "ottobre",
    "ricalcolo",
)
LOOKS: Final[Mapping[str, str]] = {
    "occhio": "una domanda all'occhio di Tommaso, su ciò che ha davanti",
}
"""The kinds of block that ask Tommaso's eye, each with its reason (M13.10b): before each of them,
in its step, ``tests/docs/test_prova_eyes.py`` wants a block of a kind of :data:`SHOWS`."""
SHOWS: Final[Mapping[str, str]] = {
    "schermo": "stampa sullo schermo, e non nel file, l'uscita dei suoi comandi",
}
"""The kinds of block that put in front of Tommaso what a question to his eye then asks, each with
its reason (M13.10b)."""
ID = base.ID
APPROVAL_ID: Final = spending.APPROVAL_ID
PLACEHOLDERS: Final = (ID, APPROVAL_ID)
OCTOBER: Final = "2026-10"
"""The month the rows of the model that left were written in: the evening of the guide's §23."""
LOW: Final = "fascia bassa"
ONE_LINE: Final = ("costo", "ricalcolo", "ottobre")
"""The kinds whose block is one line: a model, or the tier."""
"""The vocabulary of ``ricalcolo``: one line, the tier the call's cost is recomputed at."""
CURRENCY: Final = spending.CURRENCY
SUCCEEDED: Final = spending.SUCCEEDED
CHEAP: Final = HAIKU_5_5
"""The model of the cheap profile today (ADR 0067 §1): what step 4 calls, through ``routine``."""
NEEDED: Final = worst_cost(MODELS[CHEAP], output_tokens=DEFAULT_MAX_OUTPUT_TOKENS)
"""What the month must have left: the worst case of the call of step 4, from the function the
adapter's ``worst_case`` calls — never a number written here."""
ON_THE_SCREEN: Final = "l'uscita è sullo schermo, non in questo file"
MODEL_TEXT: Final = "l'uscita non entra nel file: ha il testo del modello"

Report = base.Report


@dataclass
class Turn(guided.Turn):
    """What a step has done so far, and what its ``spesa`` and ``ricalcolo`` read."""

    before: spending.Ledger | None = None
    """``GET /spend`` at the start of the step, or at its last ``spesa``."""
    cost: Decimal | None = None
    """The cost of the call ``costo`` read."""
    found: Mapping[str, Any] | None = None
    """The result ``costo`` read: what ``ricalcolo`` recomputes."""


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    ids: dict[int, str] = field(default_factory=dict)
    """The task of each step: what ``<id del passo N>`` stands for."""


# ----------------------------------------------------------------------------------------
# The vocabulary of every kind
# ----------------------------------------------------------------------------------------


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
    """The lines of the section the script cannot read, by kind: ``spesa`` in its words,
    ``costo`` a model of the list, ``ricalcolo`` its one word, ``ottobre`` a model **the list
    no longer has** — a row of a month gone by."""
    wrong: list[str] = []
    for number, blocks in todo.items():
        for block in blocks:
            if block.kind in ONE_LINE and len(block.lines) != 1:
                wrong.append(f"{number}.{block.kind}: {block.lines!r}")
                continue
            for line in block.lines:
                if (
                    (block.kind == "spesa" and line not in spending.LEDGER_WORDS)
                    or (block.kind == "costo" and line not in MODELS)
                    or (block.kind == "ricalcolo" and line != LOW)
                    or (block.kind == "ottobre" and line in MODELS)
                ):
                    wrong.append(f"{number}.{block.kind}: {line!r}")
    return wrong


# ----------------------------------------------------------------------------------------
# ``ottobre``: a call of the month gone by, read as it was written
# ----------------------------------------------------------------------------------------


Results = Callable[[str], Sequence[Mapping[str, Any]]]


def answered_on(result: Mapping[str, Any], model: str) -> bool:
    output: Mapping[str, Any] = result.get("output") or {}
    usage: Mapping[str, Any] = result.get("usage") or {}
    return (
        result.get("status") == SUCCEEDED
        and output.get("model") == model
        and usage.get("cost") is not None
    )


def an_october_call(
    tasks: Sequence[Mapping[str, Any]], results_of: Results, model: str
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    """The first task of :data:`OCTOBER` with a result that answered on ``model`` with a cost, and
    that result — or ``None`` if the database has none."""
    for task in tasks:
        if not str(task.get("created_at", "")).startswith(OCTOBER):
            continue
        for result in results_of(str(task["id"])):
            if answered_on(result, model):
                return task, result
    return None


def printed_results_failures(
    done: subprocess.CompletedProcess[str], result: Mapping[str, Any]
) -> list[str]:
    """What ``ela task results <id> --json`` prints, against what the API gave: the same result,
    with the same model and the same cost."""
    if done.returncode != 0:
        return [f"«ela task results --json» esce con {done.returncode}"]
    try:
        printed = json.loads(done.stdout)
    except json.JSONDecodeError:
        return ["«ela task results --json» non stampa JSON"]
    same = [one for one in printed if one.get("id") == result.get("id")]
    if not same:
        return [f"la CLI non stampa il risultato {result.get('id')}"]
    (one,) = same
    failures: list[str] = []
    model = (result.get("output") or {}).get("model")
    if (one.get("output") or {}).get("model") != model:
        failures.append(f"la CLI dice il modello {(one.get('output') or {}).get('model')!r}")
    cost = Decimal(str((result.get("usage") or {}).get("cost")))
    said = (one.get("usage") or {}).get("cost")
    if said is None or Decimal(str(said)) != cost:
        failures.append(f"la CLI dice il costo {said}, l'API {cost}")
    return failures


def shown_failures(
    done: subprocess.CompletedProcess[str], state: str, model: str, cost: Decimal
) -> list[str]:
    """What ``ela task show <id>`` prints: it answers, with the state, and has neither the model
    nor the cost — only the results have them (ADR 0067 §6)."""
    if done.returncode != 0:
        return [f"«ela task show» esce con {done.returncode}"]
    failures: list[str] = []
    if state not in done.stdout.split():
        failures.append(f"«ela task show» non dice lo stato {state}")
    if model in done.stdout:
        failures.append(f"«ela task show» nomina {model}")
    if dollars(cost) in done.stdout:
        failures.append(f"«ela task show» dice il costo {dollars(cost)}")
    return failures


def an_october(number: int, block: base.Block, proof: Proof) -> None:
    report = proof.report
    (model,) = block.lines
    found = an_october_call(
        proof.api.get("/tasks"), lambda task_id: proof.api.get(f"/tasks/{task_id}/results"), model
    )
    if found is None:
        report.skipped(
            number,
            f"il database non ha un task di {OCTOBER} con un risultato riuscito su {model} e un "
            "costo: niente da leggere",
        )
        return
    task, result = found
    task_id = str(task["id"])
    cost = Decimal(str(result["usage"]["cost"]))
    report.say(
        f"    il task di ottobre: {task_id}, del {task.get('created_at')}, {model}, "
        f"costo {dollars(cost)} {CURRENCY}"
    )
    line = f"uv run ela task results {task_id} --json"
    printed = base.heard(line, base.run(line))
    report.say(f"    $ {line} — {MODEL_TEXT}")
    line = f"uv run ela task show {task_id}"
    shown = base.heard(line, base.run(line))
    report.say(f"    $ {line}")
    for one in (shown.stdout + shown.stderr).rstrip("\n").splitlines():
        report.say(f"    | {one}")
    failures = printed_results_failures(printed, result) + shown_failures(
        shown, str(task.get("state")), model, cost
    )
    if failures:
        report.failure(number, "; ".join(failures))
    else:
        report.passed(
            number,
            f"il task di ottobre su {model}, con il costo scritto, {dollars(cost)} {CURRENCY}: "
            "la CLI dice ciò che l'API dice, e «ela task show» non ha né modello né costo",
        )


# ----------------------------------------------------------------------------------------
# ``ricalcolo``: the cost of one call, at the low tier of the list
# ----------------------------------------------------------------------------------------


def low_tier_failures(found: Mapping[str, Any] | None) -> list[str]:
    """What ``ricalcolo`` finds wrong in the result of the step's call: its input tokens, cache
    included, under the bound of the low tier of its model, and the cost the ledger wrote equal
    to the low tier's price on those tokens."""
    if found is None:
        return ["il passo non ha una chiamata da ricalcolare"]
    output: Mapping[str, Any] = found.get("output") or {}
    usage: Mapping[str, Any] = found.get("usage") or {}
    model = str(output.get("model"))
    if model not in TIERS:
        return [f"{model!r} non ha una fascia bassa nel listino"]
    ((bound, _), *_) = TIERS[model]
    tokens_in, tokens_out = usage.get("input_tokens"), usage.get("output_tokens")
    cached = usage.get("cached_input_tokens") or 0
    if not all(type(value) is int for value in (tokens_in, tokens_out, cached)):
        return [f"il risultato non ha i token: {dict(usage)}"]
    assert isinstance(tokens_in, int) and isinstance(tokens_out, int)
    if tokens_in + cached > bound:
        return [
            f"la chiamata ha {tokens_in + cached} token d'ingresso, sopra la fascia bassa ({bound})"
        ]
    written = usage.get("cost")
    if written is None:
        return ["il libro non ha un costo per la chiamata"]
    price = PRICES[model]
    low = (
        (price.input * tokens_in + price.cache_read * cached + price.output * tokens_out)
        / PER_MILLION
    ).quantize(CENTS_OF_A_MICRO_DOLLAR)
    if Decimal(str(written)) != low:
        return [f"il libro ha scritto {written} {CURRENCY}, la fascia bassa dà {low}"]
    return []


def a_recount(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    failures = low_tier_failures(turn.found)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(
            number, f"il costo scritto è la fascia bassa del listino: {turn.cost} {CURRENCY}"
        )


# ----------------------------------------------------------------------------------------
# The kinds of the sections before
# ----------------------------------------------------------------------------------------


def filled(text: str, turn: Turn, proof: Proof) -> str:
    """``<id>``, ``<id del passo N>`` and ``<approval-id>`` — the question the step's task waits on,
    read from ``GET /approvals`` the first time it is needed."""
    if APPROVAL_ID in text and turn.approval_id is None:
        asked = guided.question_of(proof.api, turn.task_id)
        turn.approval_id = None if asked is None else str(asked["id"])
    return guided.filled(text, turn, proof)


def a_cost(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    """``costo``: the call of the step's task, with the model of the line, a cost and a
    ``finish_reason`` — the reading of §23, on this Mac."""
    (model,) = block.lines
    results = proof.api.get(f"/tasks/{turn.task_id}/results")
    found = spending.the_call(
        results, model, on_a_node=False, here=base.this_machine(), workspaces=()
    )
    if isinstance(found, str):
        proof.report.failure(number, found)
        return
    turn.cost = found.cost
    turn.found = [one for one in results if one.get("status") == SUCCEEDED][-1]
    proof.report.passed(number, f"{model}: costo {found.cost} {CURRENCY}")


def a_ledger(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    now = spending.Ledger.of(proof.api.get("/spend"))
    failures = spending.ledger_failures(block.lines, turn.before or now, now, turn.cost)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"ela spend: {', '.join(block.lines)}")
    turn.before = now


def on_the_screen(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    """``schermo``: what the eye has to look at, put in front of it. What the commands print goes
    to the screen alone; the file says which command was shown."""
    for line in block.lines:
        asked = filled(line, turn, proof)
        done = base.heard(asked, base.run(asked))
        print(f"    $ {asked}", flush=True)
        for one in (done.stdout + done.stderr).rstrip("\n").splitlines():
            print(f"    | {one}", flush=True)
        proof.report.say(f"    $ {asked} — {ON_THE_SCREEN}")


def a_block(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    report = proof.report
    kind = block.kind
    if kind == "comando":
        turn.last = ""
        for line in block.lines:
            guided.a_command(filled(line, turn, proof), turn, proof)
    elif kind == "atteso":
        absent = base.missing([filled(line, turn, proof) for line in block.lines], turn.last)
        if absent:
            report.failure(number, f"mancano {absent}", turn.last)
        else:
            report.passed(number, "l'uscita è quella attesa")
    elif kind == "occhio":
        text = filled(block.body, turn, proof)
        report.looked(number, text, base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
    elif kind == "schermo":
        on_the_screen(number, block, turn, proof)
    elif kind == "spesa":
        a_ledger(number, block, turn, proof)
    elif kind == "costo":
        a_cost(number, block, turn, proof)
    elif kind == "ottobre":
        an_october(number, block, proof)
    elif kind == "ricalcolo":
        a_recount(number, block, turn, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(number: int, todo: Sequence[base.Block], proof: Proof) -> None:
    """The blocks of a step in order, after reading ``GET /spend``: what its ``spesa`` compares."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = Turn(before=spending.Ledger.of(proof.api.get("/spend")))
    try:
        for block in todo:
            a_block(number, block, turn, proof)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def preconditions(report: base.Report) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO).
    The task of October is not one of them (answer 28): ``ottobre`` says if there is none."""
    assert NEEDED is not None, f"{CHEAP} has no price"
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        ("il provider del modello ha una chiave", lambda: guided.so(spending.keyed())),
        ("il tetto è dichiarato", lambda: guided.so(base.Api().get("/spend")["cap"] is not None)),
        (
            f"restano almeno {NEEDED.normalize():f} {CURRENCY}, una chiamata economica al caso "
            "peggiore",
            lambda: planning.enough_left(base.Api().get("/spend")["left"], NEEDED),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m14.6b-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M14.6b, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
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
