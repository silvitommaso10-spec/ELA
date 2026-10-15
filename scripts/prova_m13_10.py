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
  guarda che ELA esca e che **nessun processo del browser resti**.

**WhatsApp non è in questa prova** (decisione 61 della review dell'implementazione di M13.10): con
il profilo di ELA la pagina non è andata oltre la sua barra di caricamento nella prima misura (ADR
0065 §5). Con lui escono il tipo ``numero``, il riavvio e la finestra che il suo passo voleva, e il
piano, che resta in ``.git/m13.10-reference/examples/``.
"""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import sys
import time
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

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


Report = accounts.Report
Proof = accounts.Proof


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


def a_block(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    kind = block.kind
    if kind == "comando":
        commands(block.lines, turn, proof)
    elif kind in ("atteso", "occhio", "sì", "mano", "schermo", "assente"):
        accounts.a_block(number, block, turn, proof)
    elif kind == "sfondo":
        guided.a_background(number, block, turn, proof)
    elif kind == "aspetta":
        guided.a_wait(number, block, turn, proof)
    elif kind == "fine":
        guided.an_end(number, block, turn, proof)
    elif kind == "figli":
        guided.a_family(number, block, turn, proof)
    elif kind == "ferma":
        a_stop(number, block, turn, proof)
    elif kind == "pagina":
        a_page_that_waits(number, block, turn, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, turn: guided.Turn | None = None
) -> None:
    """The blocks of a step in order."""
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
        if preconditions(report):
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
