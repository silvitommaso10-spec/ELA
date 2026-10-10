"""La prova a mano di M13.12: le policy di §59 (``docs/GETTING_STARTED.md``, sezione 27).

    uv run python scripts/prova_m13_12.py              # contro l'ELA che gira, dal repository
    uv run python scripts/prova_m13_12.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script **parte da** ``scripts/prova_m14_3.py`` (la SPEC di
M13.12, «La prova a mano», decisione 14): legge dalla sezione 27 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa i tipi della
sezione 26 — ``comando``, ``atteso``, ``occhio``, ``no``, ``sfondo``, ``aspetta``, ``fine``,
``sessione``, ``figli``, ``spesa`` —, il controllo del commit e dell'albero, il «FERMATO» con chi
ha risposto, e il prezzo di una sessione con la funzione del cancello. ``tests/docs/
test_prova_m13_12.py`` legge la sezione con lo stesso lettore e tiene allineati i due, con un caso
negativo per ogni confronto di questo file.

Cinque tipi suoi, che la sezione spiega uno per uno:

* ``perché``: la riga ``why I ask`` della domanda del task del passo dice ciò che il blocco dice;
  la riga «no policy of yours for browser.guided» si accetta anche, **dal secondo giro nello
  stesso mese**, come una riga che nomina solo policy revocate o scadute (decisione 21);
* ``nessuna``: nessuna policy viva — una nata dove non doveva è revocata, e il passo è FALLITO;
* ``crea``: la riga del blocco senza ``--confirm`` — l'anteprima, e niente creato —, mostrata;
  «crei la policy?»; con un «s» la stessa riga con ``--confirm``, e la policy diventa
  ``<id della policy>``; con un «n» la prova si ferma;
* ``policy``: lo stato e gli usi della policy del passo 4;
* ``console``: con nessuna domanda in attesa, una policy creata da una console e revocata.

**Il margine è passo per passo** (la SPEC, «La prova a mano», passo 1): a ogni passo il mese deve
avere libero ciò che il passo gli chiede — la prenotazione di una sessione che parte, o il caso
peggiore di una domanda — più il costo massimo delle sessioni partite prima. Non la somma dei piani:
le sessioni che chiedono non prenotano. Il prezzo è quello di ``prova_m14_3.reserved``, la funzione
del tool che il cancello legge per prenotare **e** per giudicare una domanda (``foresee``).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
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
HEADING = "## 27. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "no",
    "sfondo",
    "aspetta",
    "fine",
    "sessione",
    "figli",
    "spesa",
    "perché",
    "nessuna",
    "crea",
    "policy",
    "console",
)
ID = base.ID
CHILD: Final = guided.CHILD
APPROVAL_ID: Final = guided.APPROVAL_ID
POLICY: Final = "<id della policy>"
PLACEHOLDERS: Final = (ID, CHILD, APPROVAL_ID, POLICY)
CREATE: Final = guided.CREATE
CURRENCY: Final = guided.CURRENCY
MODEL: Final = guided.MODEL
GUIDED: Final = guided.GUIDED
SITES: Final = guided.SITES
MIGRATION: Final = "0015 (head)"
"""What ``uv run alembic current`` says after the migration of M13.12."""
POLICIES_ROUTE: Final = "/policies"
"""The route of the policies, in the schema of the API: the Core runs the branch's code."""
NOBODY: Final = f"no policy of yours for {GUIDED}"
ENDED: Final = ("was revoked on", "expired on")
"""What a line of ``why I ask`` says of a policy that ended: revoked, or expired."""
NONE_LIVE: Final = "nessuna policy viva"
BY_A_CONSOLE: Final = "una policy creata da una console, revocata"
CONSOLE_ROLE: Final = "CONSOLE"
CONFIRM: Final = " --confirm"
CREATED: Final = re.compile(r"created policy ([0-9a-f]{8})")
NOT_CREATED: Final = "not created"
STATES: Final = ("LIVE", "REVOKED", "EXPIRED")
WAITING: Final = "outcome waiting_approval"
"""What the run of a session that asks prints: the plan before it is one that does not start."""
SAID_NO: Final = "hai risposto no: senza la policy i passi che restano non hanno niente da misurare"
NO_POLICY: Final = "senza la policy del passo 4 i passi che restano non hanno niente da misurare"


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


Session = tuple[Path, bool]
"""A plan the section sends, and whether its session asks — ``True`` — or starts."""


def sessions_by_step(todo: Mapping[int, Sequence[base.Block]]) -> dict[int, list[Session]]:
    """Every plan the section sends, step by step and in order, with whether its session asks: it
    does when the first ``atteso`` after its block, in the same step, says :data:`WAITING`."""
    found: dict[int, list[Session]] = {}
    for number, blocks in todo.items():
        for index, block in enumerate(blocks):
            if block.kind != "comando":
                continue
            plans = [p for line in block.lines for p in guided.PLAN_FILE.findall(line)]
            if not plans:
                continue
            after = next((one for one in blocks[index + 1 :] if one.kind == "atteso"), None)
            asks = after is not None and WAITING in after.lines
            found.setdefault(number, []).extend((ROOT / plan, asks) for plan in plans)
    return found


def needed_by_step(
    sessions: Mapping[int, Sequence[Session]], price: Callable[[Path], Decimal]
) -> dict[int, Decimal]:
    """What the month must have free at each step: what the step asks of it — a session's
    reservation, or a question's worst case, which is the same amount — on top of the most the
    sessions started before it may have spent."""
    started = Decimal(0)
    needed: dict[int, Decimal] = {}
    for number in sorted(sessions):
        for plan, asks in sessions[number]:
            amount = price(plan)
            needed[number] = max(needed.get(number, Decimal(0)), started + amount)
            if not asks:
                started += amount
    return needed


def the_most(needed: Mapping[int, Decimal]) -> tuple[int, Decimal]:
    """The step that asks the month for the most, and how much — the first one, on a tie."""
    number = max(sorted(needed), key=lambda one: needed[one])
    return number, needed[number]


def priced(plan: Path) -> Decimal:
    return guided.reserved(guided.arguments_of(plan))


def why_failures(expected: str, why: Sequence[str]) -> tuple[list[str], str]:
    """What ``perché`` finds wrong with the line ``why I ask``, and what it read.

    The line of :data:`NOBODY` is the first round's; **from the second round in the same month**
    the question names the policies of the rounds before, and the line is accepted only if every
    policy it names ended — revoked or expired (decision 21). Any other line of the block must be
    a run of whole words of one of the question's lines."""
    if not why:
        return ["la domanda non ha la riga why I ask"], "nessuna riga"
    if expected == NOBODY:
        if list(why) == [NOBODY]:
            return [], "al primo giro: nessuna policy"
        if all(any(word in line for word in ENDED) for line in why):
            return [], "da un giro prima: solo policy revocate o scadute"
        return [f"la domanda nomina una policy che copre o è viva: {list(why)}"], "una policy viva"
    wanted = expected.split()
    if any(base.contains(line.split(), wanted) for line in why):
        return [], "la ragione attesa"
    return [f"nessuna riga dice «{expected}»: {list(why)}"], "un'altra ragione"


def policy_line(line: str) -> tuple[str, int]:
    """A line of ``policy``: a state and a number of uses, ``LIVE 1``."""
    words = line.split()
    if len(words) != 2 or words[0] not in STATES or not words[1].isdigit():
        raise ValueError(f"{line!r} is not in the vocabulary of policy")
    return words[0], int(words[1])


def policy_failures(line: str, found: Mapping[str, Any] | None) -> list[str]:
    state, uses = policy_line(line)
    if found is None:
        return ["la policy del passo 4 non è fra quelle di ela policy list --all"]
    failures: list[str] = []
    if found.get("state") != state:
        failures.append(f"la policy è {found.get('state')}, non {state}")
    if found.get("uses") != uses:
        failures.append(f"la policy ha {found.get('uses')} usi, non {uses}")
    return failures


def live(policies: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [one for one in policies if one.get("state") == "LIVE"]


def created_short(printed: str) -> str | None:
    """The short id ``ela policy create --confirm`` printed, or ``None``."""
    found = CREATED.search(printed)
    return None if found is None else found.group(1)


def console_failures(policies: Sequence[Mapping[str, Any]], proofs: Sequence[str]) -> list[str]:
    """What ``console`` finds wrong: no policy other than the proof's own, created by a console and
    revoked."""
    others = [one for one in policies if str(one.get("id")) not in proofs]
    for one in others:
        by = one.get("created_by") or {}
        if by.get("role") == CONSOLE_ROLE and one.get("state") == "REVOKED":
            return []
    seen = "; ".join(
        f"{one.get('short')} {one.get('state')} da {(one.get('created_by') or {}).get('role')}"
        for one in others
    )
    return [f"nessuna policy creata da una console e revocata: {seen or 'nessuna'}"]


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


@dataclass
class Proof(guided.Proof):
    policy: tuple[str, str] | None = None
    """The policy of step 4: its id, and its short id — what ``<id della policy>`` stands for."""


def filled(text: str, turn: guided.Turn, proof: Proof) -> str:
    text = guided.filled(text, turn, proof)
    return text.replace(POLICY, proof.policy[1] if proof.policy else POLICY)


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    """The commands of a block, in order: ``turn.last`` is what **all** of them printed."""
    turn.last = ""
    for line in lines:
        guided.a_command(filled(line, turn, proof), turn, proof)


def policies_of(api: base.Api, *, everything: bool = False) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = api.get(
        f"{POLICIES_ROUTE}?all=true" if everything else POLICIES_ROUTE
    )["policies"]
    return found


def a_why(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    (line,) = block.lines
    question = guided.question_of(proof.api, turn.task_id)
    if question is None:
        guided.no_question(number, turn.task_id, None, proof)
    assert question is not None
    why = list(question.get("why") or [])
    for one in why:
        proof.report.say(f"    | why I ask: {one}")
    failures, read = why_failures(filled(line, turn, proof), why)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la domanda dice perché — {read}")


def a_none(number: int, proof: Proof) -> None:
    """``nessuna``: no live policy; one that was born is revoked, and the step FAILS."""
    born = live(policies_of(proof.api))
    for one in born:
        proof.api.post(f"{POLICIES_ROUTE}/{one['id']}/revoke")
        proof.report.say(f"    revocata la policy {one.get('short')}, nata dove non doveva")
    if born:
        proof.report.failure(number, f"{len(born)} policy vive: un rifiuto ha creato")
    else:
        proof.report.passed(number, NONE_LIVE)


def a_creation(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``crea``: the preview, out of a terminal and without ``--confirm``, creates nothing; Tommaso
    reads it and says yes; the same line with ``--confirm`` creates the policy of the proof."""
    (line,) = block.lines
    line = filled(line, turn, proof)
    commands([line], turn, proof)
    born = live(policies_of(proof.api))
    if NOT_CREATED not in turn.last or born:
        proof.report.failure(number, "l'anteprima ha creato una policy", turn.last)
        raise base.Stop(NO_POLICY)
    if not base.yes_or_no(proof.ask, f"[{number}] Crei la policy? (s/n) "):
        raise base.Stop(SAID_NO)
    commands([line + CONFIRM], turn, proof)
    short = created_short(turn.last)
    mine = [one for one in live(policies_of(proof.api)) if one.get("short") == short]
    if short is None or len(mine) != 1:
        proof.report.failure(number, "la policy non è nata", turn.last)
        raise base.Stop(NO_POLICY)
    proof.policy = (str(mine[0]["id"]), short)
    proof.report.passed(number, f"la policy {short}, creata dopo l'anteprima")


def a_policy(number: int, block: base.Block, proof: Proof) -> None:
    (line,) = block.lines
    if proof.policy is None:
        proof.report.failure(number, "la prova non ha la policy del passo 4")
        return
    found = next(
        (one for one in policies_of(proof.api, everything=True) if one["id"] == proof.policy[0]),
        None,
    )
    if found is not None:
        proof.report.say(
            f"    | {found.get('short')} {found.get('state')}, {found.get('uses')} usi, scade "
            f"{found.get('expires_at')}"
        )
    failures = policy_failures(line, found)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la policy {proof.policy[1]}: {line}")


def a_console(number: int, block: base.Block, proof: Proof) -> None:
    """``console``: no question waiting — a page answers and runs —; Tommaso creates a policy from
    the console and revokes it; the script finds it, created by a console, revoked."""
    if block.lines != [BY_A_CONSOLE]:
        raise ValueError(f"step {number}: {block.lines} is not in the vocabulary of console")
    waiting = proof.api.get("/approvals")
    if waiting:
        proof.report.failure(number, f"{len(waiting)} domande in attesa: la console risponderebbe")
        return
    text = (
        "Apri /console/policies sul Mac, crea una policy di un giorno su www.youtube.com, "
        "guardala nell'elenco e revocala. Fatto?"
    )
    if not base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "):
        proof.report.looked(number, text, False)
        return
    proofs = [proof.policy[0]] if proof.policy else []
    failures = console_failures(policies_of(proof.api, everything=True), proofs)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, BY_A_CONSOLE)


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
    elif kind == "no":
        guided.an_answer(number, block, turn, proof, yes=False)
    elif kind == "sfondo":
        guided.a_background(number, block, turn, proof)
    elif kind == "aspetta":
        guided.a_wait(number, block, turn, proof)
    elif kind == "fine":
        guided.an_end(number, block, turn, proof)
    elif kind == "sessione":
        guided.a_session(number, block, turn, proof)
    elif kind == "figli":
        guided.a_family(number, block, turn, proof)
    elif kind == "spesa":
        guided.a_ledger(number, block, proof)
    elif kind == "perché":
        a_why(number, block, turn, proof)
    elif kind == "nessuna":
        a_none(number, proof)
    elif kind == "crea":
        a_creation(number, block, turn, proof)
    elif kind == "policy":
        a_policy(number, block, proof)
    elif kind == "console":
        a_console(number, block, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, turn: guided.Turn | None = None
) -> None:
    """The blocks of a step in order — the walk of ``prova_m14_3``, with this section's kinds."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = guided.Turn() if turn is None else turn
    blocks = list(todo)
    index = 0
    try:
        while index < len(blocks):
            index += 1
            try:
                a_block(number, blocks[index - 1], turn, proof)
            except guided.Done:
                index = guided.next_round(blocks, index)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id
        if turn.background is not None and turn.background.poll() is None:
            report.say(
                f"    la corsa in sfondo di {turn.task_id} gira ancora: la ferma la durata della "
                f"sessione, o `uv run ela task cancel {turn.task_id}`"
            )


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def migrated() -> bool:
    printed = subprocess.run(
        ["uv", "run", "alembic", "current"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return MIGRATION in printed.stdout + printed.stderr


def margin_short(left: str | None, step: int, needed: Decimal) -> str | None:
    """Why what is left of the month is not enough for the step that asks the most of it — with
    the two numbers —, or ``None``."""
    if left is None:
        return "e ELA non ha un tetto: GET /spend dice left null"
    if Decimal(left) >= needed:
        return None
    return f"e restano {left} {CURRENCY}, mentre il passo {step} ne chiede {needed}"


def no_live_policy() -> str | None:
    found = live(policies_of(base.Api()))
    if not found:
        return None
    named = ", ".join(str(one.get("short")) for one in found)
    return f"e c'è una policy viva ({named}): revocala con uv run ela policy revoke"


def preconditions(report: base.Report, todo: Mapping[int, Sequence[base.Block]]) -> bool:
    """Step 1: what the proof requires of the world, the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    try:
        step, needed = the_most(needed_by_step(sessions_by_step(todo), priced))
    except Exception as error:  # noqa: BLE001 — the miss is reported with what it said
        report.stop(1, f"il margine non si calcola ({type(error).__name__}: {error})")
        return False
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: lo schema dell'API ha {POLICIES_ROUTE}",
            lambda: guided.so(POLICIES_ROUTE in base.Api().get("/openapi.json")["paths"]),
        ),
        (f"uv run alembic current dice {MIGRATION}", lambda: guided.so(migrated())),
        (
            f"il .env manda la rotta di una sessione a {MODEL}",
            lambda: guided.so(guided.route_model() == MODEL),
        ),
        ("il provider del modello ha una chiave", lambda: guided.so(spending.keyed())),
        ("il tetto è dichiarato", lambda: guided.so(base.Api().get("/spend")["cap"] is not None)),
        (
            f"restano almeno {needed} {CURRENCY}, ciò che chiede il passo {step}",
            lambda: margin_short(base.Api().get("/spend")["left"], step, needed),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(not guided.sites_missing(BrowserSettings().sites)),
        ),
        (
            "il binario di Claude Code che l'SDK porta c'è, e si può lanciare",
            lambda: guided.so(guided.binary_ready()),
        ),
        (f"nessuna policy viva per {GUIDED}", no_live_policy),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.12-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M13.12, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        if preconditions(report, todo):
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
