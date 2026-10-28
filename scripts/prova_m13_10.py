"""La prova a mano di M13.10: più passi, una pagina, e il login da una frase.

La sezione 29 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m13_10.py               # contro l'ELA che gira
    uv run python scripts/prova_m13_10.py --out FILE

**La guida è la fonte di verità.** Lo script **parte da** ``scripts/prova_m13_9.py`` (decisione 46
della review della SPEC di M13.10): legge dalla sezione 29 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa i tipi
delle sezioni 26 e 28 — ``comando``, ``atteso``, ``occhio``, ``sì``, ``mano``, ``schermo``,
``assente``, ``sfondo``, ``aspetta``, ``fine``, ``figli`` —, il controllo del commit e
dell'albero, e il «FERMATO» con chi ha risposto. ``tests/docs/test_prova_m13_10.py`` legge la
sezione con lo stesso lettore e tiene allineati i due.

I tipi suoi, che la sezione spiega:

* ``ferma``: il «ferma» a tempo — lo script lancia lo step, aspetta i secondi del blocco, e ferma
  il task con ``ela task cancel`` mentre lo step aspetta il suo elemento;
* ``pagina``: ELA si ferma mentre una pagina del task aspetta fra due step — lo script guarda
  che lo stato del browser dica che quella pagina aspetta, manda a ELA il segnale del blocco, e
  guarda che ELA esca e che **nessun processo del browser resti**;
* ``vault``: la precondizione della ``mano`` che lo precede — il vault nello stato del blocco,
  chiesto a ELA —; se non lo è, la prova si ferma (FERMATO) con la riga da incollare, da sola
  (decisione 71 della review dopo la prova caduta al passo 4).

**Una sessione che finisce senza il gesto che il passo aspetta chiude il passo** con la riga che
``aspetta`` stampa — SALTATO per una sessione finita da sé —, i blocchi che restano di quel passo
non si fanno, e la prova va avanti al passo dopo (decisione 72).

**WhatsApp non è in questa prova** (decisione 61 della review dell'implementazione di M13.10): con
il profilo di ELA la pagina non è andata oltre la sua barra di caricamento nella prima misura (ADR
0065 §5). Con lui escono il tipo ``numero``, il riavvio e la finestra che il suo passo voleva, e il
piano, che resta in ``.git/m13.10-reference/examples/``.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

from ela.executive.runner import RunOutcome  # noqa: E402
from ela.ports import VAULT_UNLOCKED  # noqa: E402
from ela.tools.guided import SESSION_AS_YOU  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 29. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "sì",
    "mano",
    "schermo",
    "assente",
    "sfondo",
    "aspetta",
    "fine",
    "figli",
    "ferma",
    "pagina",
    "vault",
)
ID = base.ID
APPROVAL_ID: Final = guided.APPROVAL_ID
CHILD: Final = guided.CHILD
PLACEHOLDERS: Final = (ID, APPROVAL_ID, CHILD)
EXAMPLES: Final = ROOT / "docs" / "examples"
SESSION_PLAN: Final = EXAMPLES / "guided-as-you-login.json"
"""The one plan of the proof that spends: the session of step 4."""
LOGIN_PLAN: Final = EXAMPLES / "login-news-ycombinator.json"
"""The plan of the login of section 28, whose awaited text the ``assente`` of step 4 looks for."""
SITES: Final = ("httpbin.org", "news.ycombinator.com")
ROUTES: Final = ("/browser", "/vault")
SIGNALS: Final = {"SIGTERM": signal.SIGTERM, "SIGINT": signal.SIGINT}
WAIT: Final = 0.2
HOLD_SECONDS: Final = 60.0
EXIT_SECONDS: Final = 30.0
RUN_SECONDS: Final = 60.0
BROWSERS: Final = ("chrome-headless-shell", "Google Chrome for Testing")
"""What the command line of a browser of ELA's names: the empty one, and the one of the profile."""
STOP_REASON: Final = "il «ferma» della prova, mentre il gesto aspettava"
SAID_NO: Final = accounts.SAID_NO
CURRENCY: Final = guided.CURRENCY
MODEL: Final = guided.MODEL
SESSION_GESTURES: Final = SESSION_AS_YOU.gestures
"""What a gesture of the session of step 4 may ask for — a read and an act with the profile, and
the login —, **as the source gives it to that kind of session**: the vocabulary of ``aspetta`` and
``figli`` here. Until the proof of 2026-10-15 it was the list of M14.3 — the empty browser's read
and act —, and the proof fell at step 4 on ``browser.login WAITING_APPROVAL`` (decision 69)."""
OUTCOME_WORDS: Final = frozenset(outcome.value for outcome in RunOutcome)
PLACEHOLDER: Final = re.compile(r"<[^>\s][^>]*>")


Report = accounts.Report
Proof = accounts.Proof


# ----------------------------------------------------------------------------------------
# The vocabulary of every kind: what the script can read of a line (decision 69)
# ----------------------------------------------------------------------------------------


def a_command(line: str) -> str:
    """A line the script runs: a command of ELA's, whose placeholders are all ones it fills."""
    if not line.startswith("uv run ela "):
        raise ValueError(f"{line!r} is not in the vocabulary of a command: `uv run ela …`")
    unknown = sorted(set(PLACEHOLDER.findall(line)) - set(PLACEHOLDERS))
    if unknown:
        raise ValueError(f"{line!r} has placeholders the script does not fill: {unknown}")
    return line


ANSWER: Final = re.compile(
    r"uv run ela task (approve <[^>]+> --approval <approval-id>|run <[^>]+>)"
)


def an_answer_line(line: str) -> str:
    """A line of ``sì``: the yes to a question, or the run of the task that had it."""
    if not ANSWER.fullmatch(a_command(line)):
        raise ValueError(f"{line!r} is not in the vocabulary of sì: approve, or run")
    return line


def an_expected(line: str) -> str:
    """A line of ``atteso`` and ``fine``: a row of what a command prints, two words — the name of
    the row and its value —; an ``outcome`` is one :class:`RunOutcome` has."""
    words = line.split()
    if len(words) != 2 or (words[0] == "outcome" and words[1] not in OUTCOME_WORDS):
        raise ValueError(f"{line!r} is not in the vocabulary of atteso: «row value»")
    return line


def a_question(line: str) -> str:
    """A line of ``occhio``: a question for Tommaso's eye."""
    if not line.strip().endswith("?"):
        raise ValueError(f"{line!r} is not in the vocabulary of occhio: a question")
    return line


def a_sentence(line: str) -> str:
    """A line of ``mano``: what Tommaso does himself, said."""
    if not line.strip():
        raise ValueError("an empty line is not in the vocabulary of mano")
    return line


def seconds(line: str) -> float:
    """A line of ``ferma``: the seconds before the stop, inside the thirty of the step."""
    try:
        said = float(line)
    except ValueError:
        raise ValueError(f"{line!r} is not in the vocabulary of ferma: seconds") from None
    if not 0 < said < 30:
        raise ValueError(f"{line!r} is not inside the thirty seconds of the step")
    return said


def a_signal(line: str) -> str:
    """A line of ``pagina``: the signal ELA is stopped with."""
    if line not in SIGNALS:
        raise ValueError(f"{line!r} is not in the vocabulary of pagina: {sorted(SIGNALS)}")
    return line


def an_open_vault(line: str) -> str:
    """A line of ``vault``: the state the human step before it leaves the vault in — the open one,
    as the source names it."""
    if line != VAULT_UNLOCKED:
        raise ValueError(f"{line!r} is not in the vocabulary of vault: {VAULT_UNLOCKED!r}")
    return line


def a_wait_line(line: str) -> str:
    return guided.waited(line, SESSION_GESTURES)


def a_child(line: str) -> object:
    return line if line == guided.INSIDE else guided.wanted(line, SESSION_GESTURES)


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    "comando": a_command,
    "atteso": an_expected,
    "occhio": a_question,
    "sì": an_answer_line,
    "mano": a_sentence,
    "schermo": a_command,
    "assente": a_command,
    "sfondo": a_command,
    "aspetta": a_wait_line,
    "fine": an_expected,
    "figli": a_child,
    "ferma": seconds,
    "pagina": a_signal,
    "vault": an_open_vault,
}
"""The reader of each kind: what the script reads of a line, and the guide's error when it cannot.
``tests/docs/test_prova_m13_10.py`` reads every line of the section with these, and the script reads
them all before step 1."""


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
    """Every line of the section a reader of its kind cannot read: said before step 1, so that the
    proof never falls in the middle of a step on a line of the guide."""
    wrong: list[str] = []
    for number, blocks in todo.items():
        for block in blocks:
            reader = READERS.get(block.kind)
            for line in block.lines:
                try:
                    if reader is None:
                        raise ValueError(f"{block.kind!r} is not a kind of the section")
                    reader(line)
                except ValueError as error:
                    wrong.append(f"passo {number}, {block.kind}: {error}")
    return wrong


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    turn.last = ""
    for line in lines:
        guided.a_command(accounts.filled(line, turn, proof), turn, proof)


# ----------------------------------------------------------------------------------------
# The kinds of this section
# ----------------------------------------------------------------------------------------


def a_stop(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``ferma``: the step of the turn runs in the background; after the seconds of the block the
    task is stopped — while its gesture waits for an element that is not there."""
    (seconds,) = block.lines
    running = base.started(f"uv run ela task run {turn.task_id}")
    time.sleep(float(seconds))
    line = f"uv run ela task cancel {turn.task_id} --reason {shlex.quote(STOP_REASON)}"
    cancelled = base.heard(line, base.run(line))
    try:
        printed, _ = running.communicate(timeout=RUN_SECONDS)
    except Exception:  # noqa: BLE001 — a run that does not end is the failure said below
        running.kill()
        proof.report.failure(number, f"lo step non è finito {RUN_SECONDS:.0f} s dopo il «ferma»")
        return
    turn.last = (printed or "") + cancelled.stdout
    proof.report.say(f"    «ferma» dato dopo {seconds} s, mentre lo step aspettava")
    if cancelled.returncode != 0:
        proof.report.failure(number, "il «ferma» non è stato accettato", cancelled.stdout)
    else:
        proof.report.passed(number, "il task è stato fermato mentre lo step aspettava")


def waiting_page(task_id: str | None, said: dict[str, Any]) -> bool:
    """Whether the state of the browser says a page of ``task_id`` waits between two steps."""
    return any(one.get("task") == task_id for one in said.get("waiting") or ())


def browsers_left(listing: dict[int, str]) -> list[str]:
    """The processes whose command line is a browser of ELA's: what an ELA that stopped must not
    leave behind."""
    return sorted(
        command[:80] for command in listing.values() if any(name in command for name in BROWSERS)
    )


def a_page_that_waits(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``pagina``: ELA is stopped while a page of the task waits, and nothing of it is left."""
    report = proof.report
    (name,) = block.lines
    if name not in SIGNALS:
        raise ValueError(f"{name!r} is not in the vocabulary of pagina")
    pid = accounts.ela_pid()
    if pid is None:
        report.failure(
            number,
            "sulla porta di ELA non ascolta un processo `ela serve`, o ne ascolta più d'uno: "
            "il segnale non si manda a un processo che lo script non sa nominare",
        )
        return
    if not waiting_page(turn.task_id, proof.api.get("/browser")):
        report.failure(
            number, "lo stato del browser non dice che una pagina di questo task aspetta"
        )
        return
    os.kill(pid, SIGNALS[name])
    report.say(f"    {name} a ELA (processo {pid}), con una pagina del task che aspetta")
    deadline = time.monotonic() + EXIT_SECONDS
    while accounts.alive(pid) and time.monotonic() < deadline:
        time.sleep(WAIT)
    if accounts.alive(pid):
        report.failure(number, f"ELA non è uscita entro {EXIT_SECONDS:.0f} s")
        return
    left = browsers_left(base.processes())
    if left:
        report.failure(number, f"dopo ELA restano processi del browser: {left}")
    else:
        report.passed(number, "ELA è uscita, e del browser non resta niente")


def the_vault(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``vault``: the precondition of the human step before it — the vault in the state of the
    block, asked of ELA. Not met, the proof stops (FERMATO), with the line to paste **on a line of
    its own**, to be copied whole; or, when ELA gives no line, with what ELA says to do. On
    2026-10-15 nothing looked: the vault was closed, and the session of step 4 ended on
    ``vault.locked`` (decision 71)."""
    (wanted,) = block.lines
    found = proof.api.get("/vault")
    state = found.get("state")
    if state == wanted:
        proof.report.passed(number, "il vault è aperto")
        return
    line = found.get("opens_with")
    if not line:
        raise base.Stop(f"il vault è {state}, non aperto: {found.get('message')}")
    proof.report.say("    la riga da incollare nel tuo terminale, intera:")
    proof.report.say(str(line))
    raise base.Stop(
        f"il vault è {state}, non aperto: incolla nel tuo terminale la riga qui sopra, intera, "
        "e rilancia la prova da capo"
    )


def a_block(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    kind = block.kind
    if kind == "comando":
        commands(block.lines, turn, proof)
    elif kind in ("atteso", "occhio", "sì", "mano", "schermo", "assente"):
        accounts.a_block(number, block, turn, proof)
    elif kind == "sfondo":
        guided.a_background(number, block, turn, proof)
    elif kind == "aspetta":
        guided.a_wait(number, block, turn, proof, SESSION_GESTURES)
    elif kind == "fine":
        guided.an_end(number, block, turn, proof)
    elif kind == "figli":
        guided.a_family(number, block, turn, proof, SESSION_GESTURES)
    elif kind == "ferma":
        a_stop(number, block, turn, proof)
    elif kind == "pagina":
        a_page_that_waits(number, block, turn, proof)
    elif kind == "vault":
        the_vault(number, block, turn, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, turn: guided.Turn | None = None
) -> None:
    """The blocks of a step in order. A session that ends without the gesture ``aspetta`` waits
    for closes the step with the line ``aspetta`` printed — SALTATO, for one that ended by
    itself —: the blocks left of the step have nothing to look at, and the proof goes on to the
    next one. On 2026-10-15 ``Done`` went out of the step and out of the walk, and the file had no
    verdict (decision 72)."""
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = guided.Turn() if turn is None else turn
    try:
        for block in todo:
            a_block(number, block, turn, proof)
    except guided.Done:
        return
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def vault_declared() -> str | None:
    found = base.Api().get("/vault")
    if found.get("program"):
        return None
    return f"e il vault non ha un programma dichiarato: {found.get('message')}"


def preconditions(report: base.Report) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    needed = guided.reserved(accounts.arguments_of(SESSION_PLAN))
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
            f"restano almeno {needed} {CURRENCY}, ciò che chiede la sessione del passo 4",
            lambda: accounts.margin_short(base.Api().get("/spend")["left"], needed),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(all(site in BrowserSettings().sites for site in SITES)),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            accounts.profile_ready,
        ),
        ("il vault è dichiarato", vault_declared),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.10-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.10, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
            api = base.Api()
            proof = Proof(api, report, ask, spending.Ledger.of(api.get("/spend")), login=LOGIN_PLAN)
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
