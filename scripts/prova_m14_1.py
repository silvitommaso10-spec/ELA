"""La prova a mano di M14.1: il tetto sulla chiave del modello (``docs/GETTING_STARTED.md`` §23).

    uv run python scripts/prova_m14_1.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m14_1.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script legge da §23 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa il confronto «a
parole intere e in ordine», il rapporto, il client dell'API, il vocabolario di ``guarda`` e di
``richiede`` e il controllo del passo 1. ``tests/docs/test_prova_m14_1.py`` legge §23 con lo stesso
lettore e tiene allineati i due, con un caso negativo per ogni confronto di questo file.

I tipi di §21 — ``comando``, ``atteso``, ``occhio``, ``richiede``, ``guarda``, ``mano`` — e sei
suoi (la SPEC di M14.1, «La prova a mano», le decisioni 11, 16 e 17 della review, e quelle del
2026-10-07, che fanno del secondo tetto il limite dell'organizzazione e tolgono la domanda «scrivi»
sul suo azzeramento: la console non risponde a ciò che la documentazione non scrive):

* ``commit``: il comando da dare sul PC; chiede i primi sette caratteri che stampa e li confronta
  con il commit di questo Mac — il confronto lo fa lo script, non l'occhio;
* ``limite``: chiede il limite mensile dell'organizzazione, in dollari, e **PASSATO se il tetto di
  ELA sta sotto**, letto da ``GET /spend``;
* ``costo``: il risultato del task ha il modello scritto, un costo e un ``finish_reason``; scrive la
  workspace. «su un nodo»: il risultato è di un nodo, e la workspace è quella delle chiamate di
  questo Mac;
* ``spesa``: ``GET /spend`` confrontato con com'era all'ultimo ``tetto``, all'ultima ``spesa`` o
  all'inizio del passo;
* ``tetto``: «piccolo» calcola speso + prenotato + 1 e lo stampa come riga del ``.env``; «il tuo»
  rimette quello di prima; aspetta Invio — il Core riavviato da Tommaso — e controlla che ELA lo
  legga. **Un** ``tetto`` **fallito ferma la prova**: i passi dopo sarebbero misurati con un tetto
  che non è quello voluto, e il verdetto lo dice;
* ``tace`` e ``aspetta``: che il nodo non abbia consegnato prima del ``Ctrl-C``, e la scadenza della
  presa, con il TTL del ``.env`` del Core. **Un esito arrivato prima del** ``Ctrl-C`` **fa il giro
  SALTATO, e il passo si rifà** (decisione 17), fino a tre giri: non è un FALLITO di ELA.

I segnaposto sono ``<id>`` — il task del passo — e ``<approval-id>``, la sua domanda, letta da
``GET /approvals``. Si ferma ad aspettare solo dove serve la mano o l'occhio di Tommaso: la console,
il PC, il ``Ctrl-C``, il riavvio del Core. La riga finale è quella di M6.3c: «La prova è passata»
solo senza FALLITO, senza SALTATO e con ogni GUARDATO un sì. Tutto va anche nel file, in
``~/Downloads``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package

from ela.cli.client import Unreachable  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 23. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "richiede",
    "guarda",
    "mano",
    "commit",
    "limite",
    "costo",
    "spesa",
    "tetto",
    "tace",
    "aspetta",
)
ID = base.ID
APPROVAL_ID: Final = "<approval-id>"
CREATE: Final = " task create "
ON_A_NODE: Final = base.ON_A_NODE
SHORT: Final = 7
"""How many characters of a commit Tommaso types: ``git log --oneline -1`` prints them first."""
SMALL: Final = "piccolo"
YOURS: Final = "il tuo"
CAPS: Final = (SMALL, YOURS)
"""The vocabulary of ``tetto``."""
SPENT_SAME: Final = "speso invariato"
RESERVED_SAME: Final = "prenotato invariato"
SPENT_BY_THE_COST: Final = "speso cresciuto del costo"
ONE_MORE_OPEN: Final = "una prenotazione aperta in più"
LEDGER_WORDS: Final = (SPENT_SAME, RESERVED_SAME, SPENT_BY_THE_COST, ONE_MORE_OPEN)
"""The vocabulary of ``spesa``: what changed in ``GET /spend`` since the last look."""
SILENT: Final = "nessun esito prima del Ctrl-C"
LAPSE: Final = "la presa scade"
THE_REST: Final = "il resto del giro sarebbe misurato con un tetto che non è quello voluto"
"""Why a ``tetto`` that fails stops the proof (2026-10-07, 21:17)."""
MARGIN: Final = 5
"""Seconds after the TTL of a claim before the step reads it lapsed: the node's last renewal may
have landed a moment after the script started waiting."""
ROUNDS: Final = base.ROUNDS
ANSWERS_AGAIN: Final = 60
"""How many times, a second apart, the script asks ELA whether it answers after a restart of the
Core: a door for the hand, not a measure."""
CURRENCY: Final = "USD"
SUCCEEDED: Final = "SUCCEEDED"
STARTED: Final = "STARTED"


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def same_commit(mac: str, typed: str) -> str | None:
    """Why the PC is not on this Mac's commit, or ``None`` if the seven characters are the same."""
    pc = typed.strip().lower()[:SHORT]
    here = mac.strip().lower()[:SHORT]
    if pc == here:
        return None
    return f"il PC è su {pc}, il Mac su {here}"


def short_commit(typed: str) -> bool:
    """Whether Tommaso typed seven hexadecimal characters, the ones ``git log --oneline`` prints."""
    text = typed.strip().lower()
    return len(text) >= SHORT and all(char in "0123456789abcdef" for char in text[:SHORT])


def dollars_typed(typed: str) -> Decimal | None:
    """An amount as Tommaso types it — ``50``, ``50,00``, ``$50`` —, or ``None``."""
    text = typed.strip().removeprefix("$").removesuffix(CURRENCY).strip().replace(",", ".")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def under_the_limit(cap: str | None, limit: Decimal) -> str | None:
    """Why ELA's cap is not below the organization's monthly limit, or ``None`` if it is (the
    second cap)."""
    if cap is None:
        return "ELA non ha un tetto: GET /spend dice cap null"
    if Decimal(cap) < limit:
        return None
    return (
        f"il tetto di ELA, {cap} {CURRENCY}, non sta sotto il limite dell'organizzazione, {limit}"
    )


@dataclass(frozen=True)
class Call:
    """What ``costo`` read of a call: its cost and the workspace that paid."""

    cost: Decimal
    workspace: str | None
    device_id: str | None


def the_call(
    results: Sequence[Mapping[str, Any]],
    model: str,
    *,
    on_a_node: bool,
    here: str,
    workspaces: Sequence[str | None],
) -> Call | str:
    """The call of the task's result, or why ``costo`` fails.

    The result that answered — ``SUCCEEDED``, whatever the verification said after — names the
    model the line names, carries a cost (decision 16: a cost missing is a name the table does not
    know, and a month of calls held at their worst case) and a ``finish_reason``. On a node: the
    result is not this Mac's, and the workspace is the one of every call this Mac made
    (decision 12).
    """
    answered = [one for one in results if one.get("status") == SUCCEEDED]
    if not answered:
        return f"nessun risultato SUCCEEDED fra {len(results)}"
    found = answered[-1]
    output: Mapping[str, Any] = found.get("output") or {}
    usage: Mapping[str, Any] = found.get("usage") or {}
    if output.get("model") != model:
        return f"il modello è {output.get('model')!r}, non {model!r}"
    if usage.get("cost") is None:
        return (
            f"la chiamata a {model} non ha un costo: la tabella dei prezzi non conosce il modello"
        )
    if not output.get("finish_reason"):
        return "la risposta non dice il suo finish_reason"
    workspace = output.get("workspace")
    device = found.get("device_id")
    if on_a_node:
        if device == here:
            return "il risultato è di questo Mac, non di un nodo"
        mine = set(workspaces)
        if not workspaces or None in mine or len(mine) != 1:
            return (
                f"le chiamate di questo Mac non hanno una workspace sola: {sorted(map(str, mine))}"
            )
        if workspace != workspaces[0]:
            return f"la workspace del PC è {workspace!r}, quella del Mac {workspaces[0]!r}"
    return Call(Decimal(str(usage["cost"])), workspace, device)


@dataclass(frozen=True)
class Ledger:
    """``GET /spend``, the numbers the gate judges with."""

    cap: str | None
    spent: Decimal
    reserved: Decimal
    open: int

    @classmethod
    def of(cls, payload: Mapping[str, Any]) -> Ledger:
        return cls(
            payload["cap"],
            Decimal(payload["spent"]),
            Decimal(payload["reserved"]),
            int(payload["open"]),
        )


def ledger_failures(
    lines: Sequence[str], before: Ledger, after: Ledger, cost: Decimal | None
) -> list[str]:
    """What ``spesa`` says changed and did not, one sentence per line that does not hold."""
    failures: list[str] = []
    for line in lines:
        if line == SPENT_SAME and after.spent != before.spent:
            failures.append(f"lo speso è passato da {before.spent} a {after.spent}")
        elif line == RESERVED_SAME and after.reserved != before.reserved:
            failures.append(f"il prenotato è passato da {before.reserved} a {after.reserved}")
        elif line == SPENT_BY_THE_COST and (cost is None or after.spent - before.spent != cost):
            failures.append(
                f"lo speso è cresciuto di {after.spent - before.spent}, il costo è {cost}"
            )
        elif line == ONE_MORE_OPEN and (
            after.open != before.open + 1 or after.reserved <= before.reserved
        ):
            failures.append(
                f"le prenotazioni aperte sono {after.open}, prima {before.open}; il prenotato "
                f"{after.reserved}, prima {before.reserved}"
            )
        elif line not in LEDGER_WORDS:
            raise ValueError(f"{line!r} is not in the vocabulary of spesa")
    return failures


def small_cap(ledger: Ledger) -> Decimal:
    """Speso + prenotato + 1 dollaro: Opus 5.5 no longer fits, Haiku 4.5 does (step 4)."""
    return ledger.spent + ledger.reserved + 1


def said(amount: Decimal) -> str:
    """An amount as the ``.env`` and ``GET /spend`` write it: exact, no trailing zeros."""
    return f"{amount.normalize():f}"


def answered_already(results: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the node delivered before the ``Ctrl-C``: any result that is not the ``STARTED``."""
    return any(one.get("status") != STARTED for one in results)


# ----------------------------------------------------------------------------------------
# One step, in rounds
# ----------------------------------------------------------------------------------------


class Redo(Exception):
    """The round proved nothing — the node answered before the ``Ctrl-C`` —: the step is redone."""


@dataclass
class Turn:
    """What a round of a step has done so far."""

    task_id: str | None = None
    approval_id: str | None = None
    last: str = ""
    before: Ledger | None = None
    cost: Decimal | None = None


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    yours: str | None = None
    """The cap Tommaso wrote, kept by ``tetto piccolo`` for ``tetto il tuo``."""
    workspaces: list[str | None] = field(default_factory=list)
    """The workspace of each call this Mac made: what a call of the PC is compared with."""
    reconnect: Callable[[], base.Api] = base.Api

    def ledger(self) -> Ledger:
        return Ledger.of(self.api.get("/spend"))


def filled(text: str, turn: Turn) -> str:
    return text.replace(ID, turn.task_id or ID).replace(
        APPROVAL_ID, turn.approval_id or APPROVAL_ID
    )


def question_of(api: base.Api, task_id: str | None) -> str | None:
    """The id of the task's question, from ``GET /approvals``."""
    for one in api.get("/approvals"):
        if one.get("task_id") == task_id:
            return str(one["id"])
    return None


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
    if turn.task_id is not None:
        turn.approval_id = question_of(proof.api, turn.task_id) or turn.approval_id


def back(proof: Proof) -> None:
    """A new client once ELA answers again — the Core restarted by Tommaso's hand."""
    proof.api.close()
    for _ in range(ANSWERS_AGAIN):
        try:
            proof.api = proof.reconnect()
            proof.api.get("/health")
            return
        except (Unreachable, OSError):
            time.sleep(1)
    raise base.Silent(f"ELA non risponde dopo {ANSWERS_AGAIN} secondi dal riavvio")


def a_cap(number: int, line: str, turn: Turn, proof: Proof) -> None:
    report = proof.report
    if line == SMALL:
        now = proof.ledger()
        proof.yours = now.cap
        wanted = said(small_cap(now))
    elif line == YOURS:
        if proof.yours is None:
            report.failure(number, "il tetto di prima non è mai stato letto")
            raise base.Stop(THE_REST)
        wanted = proof.yours
    else:
        raise ValueError(f"step {number}: {line!r} is not in the vocabulary of tetto")
    report.say(f"    la riga del .env del Core: ELA_SPENDING_CAP_USD={wanted}")
    proof.ask(f"[{number}] Scrivi la riga nel .env del Core, riavvia il Core, poi Invio. ")
    back(proof)
    read = proof.ledger()
    if read.cap is None or Decimal(read.cap) != Decimal(wanted):
        report.failure(number, f"ELA legge il tetto {read.cap}, non {wanted}")
        raise base.Stop(THE_REST)
    report.passed(number, f"ELA legge il tetto {read.cap} {CURRENCY}")
    turn.before = read


def a_cost(number: int, line: str, turn: Turn, proof: Proof) -> None:
    report = proof.report
    on_a_node = line.endswith(ON_A_NODE)
    model = line.removesuffix(ON_A_NODE).strip()
    results = proof.api.get(f"/tasks/{turn.task_id}/results")
    found = the_call(
        results,
        model,
        on_a_node=on_a_node,
        here=base.this_machine(),
        workspaces=proof.workspaces,
    )
    if isinstance(found, str):
        report.failure(number, found)
        return
    turn.cost = found.cost
    if not on_a_node:
        proof.workspaces.append(found.workspace)
    where = "un nodo" if on_a_node else "questo Mac"
    report.passed(
        number,
        f"{model}, su {where}: costo {found.cost} {CURRENCY}, workspace {found.workspace}",
    )


def a_ledger(number: int, block: base.Block, turn: Turn, proof: Proof) -> None:
    now = proof.ledger()
    before = turn.before or now
    failures = ledger_failures(block.lines, before, now, turn.cost)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"ela spend: {', '.join(block.lines)}")
    turn.before = now


def a_look(number: int, block: base.Block, turn: Turn, proof: Proof, round_: int) -> None:
    """``guarda``: until the sign is seen, or the task ends by itself."""
    sign = base.sign_of(block)
    while not base.seen(proof.api, turn.task_id or "", sign, {}):
        if base.ended(proof.api, turn.task_id or ""):
            proof.report.failure(number, f"il task è finito senza «{block.body.strip()}»")
            return
        time.sleep(base.PAUSE)
    if sign.on_a_node and base.ran_here(proof.api, turn.task_id or "", sign):
        proof.report.failure(number, f"«{block.body.strip()}»: il risultato è di questo Mac")
        return
    proof.report.passed(number, f"visto: {block.body.strip()}", round_)


def a_round(number: int, todo: Sequence[base.Block], proof: Proof, round_: int) -> None:
    report = proof.report
    turn = Turn(before=proof.ledger())
    for block in todo:
        kind = block.kind
        if kind == "richiede":
            absent = base.lacking(block, proof.api)
            if absent:
                report.skipped(number, f"il passo richiede {', '.join(absent)}")
                return
            report.passed(number, f"c'è {', '.join(block.lines)}", round_)
        elif kind == "comando":
            for line in block.lines:
                a_command(filled(line, turn), turn, proof)
        elif kind == "atteso":
            wanted = [filled(line, turn) for line in block.lines]
            absent = base.missing(wanted, turn.last)
            if absent:
                report.failure(number, f"mancano {absent}", turn.last)
            else:
                report.passed(number, "l'uscita è quella attesa", round_)
        elif kind == "occhio":
            text = filled(block.body, turn)
            report.looked(number, text, base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
        elif kind == "mano":
            proof.ask(f"[{number}] {block.body.strip()} ")
        elif kind == "guarda":
            a_look(number, block, turn, proof, round_)
        elif kind == "commit":
            a_commit(number, block, proof)
        elif kind == "limite":
            a_limit(number, block, proof)
        elif kind == "costo":
            for line in block.lines:
                a_cost(number, line, turn, proof)
        elif kind == "spesa":
            a_ledger(number, block, turn, proof)
        elif kind == "tetto":
            for line in block.lines:
                a_cap(number, line, turn, proof)
        elif kind == "tace":
            if answered_already(proof.api.get(f"/tasks/{turn.task_id}/results")):
                raise Redo("la risposta è arrivata prima del Ctrl-C")
            report.passed(number, SILENT, round_)
        elif kind == "aspetta":
            a_lapse(number, proof)
        else:
            raise ValueError(f"step {number}: {kind!r} is not a kind of §23")


def a_commit(number: int, block: base.Block, proof: Proof) -> None:
    mac = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    proof.report.say(f"    sul PC: {block.body.strip()}")
    typed = ""
    while not short_commit(typed):
        typed = proof.ask(f"[{number}] I primi {SHORT} caratteri che il PC ha stampato: ")
    why = same_commit(mac, typed)
    if why is None:
        proof.report.passed(number, f"il PC e il Mac sono su {mac[:SHORT]}")
    else:
        proof.report.failure(number, why)


def a_limit(number: int, block: base.Block, proof: Proof) -> None:
    limit: Decimal | None = None
    while limit is None:
        limit = dollars_typed(proof.ask(f"[{number}] {block.body.strip()}: "))
    cap = proof.ledger().cap
    why = under_the_limit(cap, limit)
    if why is None:
        proof.report.passed(
            number, f"il tetto di ELA, {cap} {CURRENCY}, sta sotto il limite, {limit}"
        )
    else:
        proof.report.failure(number, why)


def a_lapse(number: int, proof: Proof) -> None:
    from ela.composition.settings import CoreSettings

    seconds = CoreSettings().assignment_ttl_seconds + MARGIN
    proof.report.say(f"    la presa scade: lo script aspetta {seconds} secondi")
    time.sleep(seconds)
    proof.report.passed(number, f"{LAPSE}: {seconds} secondi")


def a_step(number: int, todo: Sequence[base.Block], proof: Proof) -> None:
    """A step, in rounds: a round whose node answered before the ``Ctrl-C`` is SKIPPED and done
    again, after the node is started again (decision 17); the third is SKIPPED for good."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    for round_ in range(1, ROUNDS + 1):
        try:
            a_round(number, todo, proof, round_)
            return
        except Redo as why:
            if round_ == ROUNDS:
                report.skipped(number, f"{why}, al giro {round_}: il passo non ha provato niente")
                return
            report.say(f"[{number}] SALTATO al giro {round_}: {why} — si rifà")
            proof.ask(f"[{number}] Riaccendi il nodo sul PC, poi Invio. ")


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def preconditions(report: base.Report) -> bool:
    """What §23 needs of the world, read where ELA reads it (the reader of M6.3c's step 1)."""
    checks: list[tuple[str, base.Check]] = [
        ("ELA risponde", lambda: base.Api().get("/health") is not None),
        ("il Core risponde a GET /spend: il codice del branch, la migrazione 0013", spends),
        ("il tetto è dichiarato", lambda: base.Api().get("/spend")["cap"] is not None),
        ("il provider del modello ha una chiave", keyed),
    ]
    return base.required(report, checks)


def spends() -> bool:
    return base.Api().get("/spend") is not None


def keyed() -> bool:
    return bool(base.Api().get("/diagnostics")["providers"].get("anthropic") == "AVAILABLE")


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m14.1-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M14.1, {datetime.now():%Y-%m-%d %H:%M:%S}")
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
