"""La prova a mano di M13.1c, M13.1d e M9.6 (``docs/GETTING_STARTED.md`` §22).

    uv run python scripts/prova_m13_1c_m13_1d_m9_6.py              # contro l'ELA che gira
    uv run python scripts/prova_m13_1c_m13_1d_m9_6.py --out FILE   # l'uscita in un altro file

**La guida è la fonte di verità.** Lo script legge da §22 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e ne usa il confronto
«a parole intere e in ordine», il rapporto e il client dell'API: i tipi sono ``comando``, ``atteso``
e ``occhio``. ``tests/docs/test_prova_m13_1c_m13_1d_m9_6.py`` legge §22 con lo stesso lettore e
tiene allineati i due.

**In più fa tre confronti suoi** (la SPEC di M13.1c, «La prova a mano»):

* **le ragioni**: in un passo le cui corse finiscono in uno stato che porta una ragione — gli
  stati finali dell'engine tranne ``completed`` —, le righe ``reason`` di quelle corse sono la
  stessa e non sono ``—``, e sono almeno due: la corsa che chiude il task e quella che lo trova
  chiuso;
* **il blocco di** ``ela approvals``: il blocco la cui riga ``task`` è il task del passo ha le
  etichette del blocco di §6, nello stesso ordine, e i valori alla stessa colonna (M13.1d). Il suo
  ``approval`` è ciò che ``<approval-id>`` riempie;
* **l'uscita di** ``uv run ela voice`` è ``0`` (M9.6): il catalogo vuoto non è un errore.

I segnaposto sono ``<id>`` — il task creato nel passo —, ``<approval-id>`` e ``<id della voce
configurata>``, letto da ``GET /voice``. Un comando che chiede ``--help`` si confronta con gli spazi
riuniti, come la suite: l'help va a capo alla larghezza del terminale. Per ogni confronto stampa
**PASSATO** o **FALLITO** con l'uscita vera, e l'uscita di ogni comando; ciò che serve l'occhio di
Tommaso lo chiede finché la risposta è s o n. **Il passo 1 controlla ciò che la prova richiede al
mondo** — ELA acceso, lo shell di Chromium, i siti dichiarati e che rispondono, la voce configurata
—, con il lettore del passo 1 di M6.3c: la prima cosa che manca fa il passo 1 **SALTATO** con ciò
che manca, e lo script si ferma lì; mai un FALLITO, che sembrerebbe di ELA (decisione 2-bis della
review, 2026-10-02). **Se ELA smette di rispondere a metà giro** — un comando di ``ela`` che esce
con il codice della CLI per «nessuno risponde» —, il passo è INTERROTTO nel file, i passi che
restano non si fanno, e l'ultima riga lo dice: il ciclo dei passi è quello di M6.3c (decisione R,
2026-10-05). La riga finale è quella di M6.3c: «La prova è passata» solo senza FALLITO,
senza SALTATO e con ogni GUARDATO un sì. Tutto va anche nel file, in ``~/Downloads``.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package

from ela.cli.output import EMPTY, GAP  # noqa: E402
from ela.cli.tasks import RUN_LABELS  # noqa: E402
from ela.domain import TaskState  # noqa: E402
from ela.executive.runner import OUTCOMES  # noqa: E402
from ela.tasks.engine import TERMINAL_STATES  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 22. "
QUESTION_HEADING = "## 6. "
KINDS = ("comando", "atteso", "occhio")
ID = base.ID
APPROVAL_ID = "<approval-id>"
VOICE_ID = "<id della voce configurata>"
CREATE = " task create "
RUN = " task run "
HELP = "--help"
APPROVALS = "uv run ela approvals"
VOICE = "uv run ela voice"
SITES = base.SITES
REASONED = frozenset(OUTCOMES[state].value for state in TERMINAL_STATES - {TaskState.COMPLETED})
"""The outcomes whose run says why: every end of the engine but ``completed`` (ADR 0055 §1)."""
REACHED_WITHIN = 30.0
"""How long a site may take to answer before step 1 says it does not: a door, not a measure."""
WIDTH = max(map(len, RUN_LABELS))


# ----------------------------------------------------------------------------------------
# What the output says: a row of ``run``, the blocks of ``approvals``
# ----------------------------------------------------------------------------------------


def run_row(output: str, label: str) -> str | None:
    """The value of one row of ``ela task run``, read at the command's column."""
    for line in output.splitlines():
        if line.startswith(label.ljust(WIDTH) + GAP):
            return line[WIDTH + len(GAP) :].strip()
    return None


@dataclass(frozen=True)
class Question:
    """One block of ``ela approvals``: its labels in order, and the column its values start at."""

    labels: tuple[str, ...]
    column: int
    values: dict[str, str]


def question_of(lines: Sequence[str]) -> Question | None:
    """A block of ``label  value`` lines, or ``None`` if its values do not share a column."""
    columns: set[int] = set()
    labels: list[str] = []
    values: dict[str, str] = {}
    for line in lines:
        gap = line.find(GAP)
        if gap <= 0:
            return None
        column = len(line) - len(line[gap:].lstrip(" "))
        columns.add(column)
        labels.append(line[:gap])
        values[line[:gap]] = line[column:].strip()
    if len(columns) != 1:
        return None
    return Question(tuple(labels), columns.pop(), values)


def questions(output: str) -> list[Question]:
    """The blocks ``ela approvals`` printed, one per question, a blank line between two."""
    found: list[Question] = []
    for chunk in output.strip("\n").split("\n\n"):
        lines = [line for line in chunk.splitlines() if line.strip()]
        question = question_of(lines) if lines else None
        if question is not None:
            found.append(question)
    return found


def the_guides_question(text: str) -> Question:
    """The block of ``ela approvals`` §6 shows: its first fence that opens with ``approval``."""
    section = base.section(text, QUESTION_HEADING)
    for fenced in section.split("```")[1::2]:
        lines = [line for line in fenced.splitlines() if line.strip()]
        if lines and lines[0].startswith("approval" + GAP):
            question = question_of(lines)
            if question is not None:
                return question
    raise ValueError("§6 has no block of ela approvals")


def unlike(found: Question, guide: Question) -> list[str]:
    """How the task's question differs from the block of §6, in labels, order and column."""
    differences: list[str] = []
    if found.labels != guide.labels:
        differences.append(f"le etichette sono {list(found.labels)}, in §6 {list(guide.labels)}")
    if found.column != guide.column:
        differences.append(f"i valori cominciano alla colonna {found.column}, in §6 {guide.column}")
    return differences


def same_reason(reasons: Sequence[str]) -> str | None:
    """Why the reasons of a step's ending runs are not one reason, or ``None`` if they are."""
    if len(reasons) < 2:
        return f"le corse che finiscono con una ragione sono {len(reasons)}, non due"
    if EMPTY in reasons:
        return f"una ragione è {EMPTY}"
    if len(set(reasons)) != 1:
        return "le ragioni non sono la stessa"
    return None


def joined(text: str) -> str:
    return " ".join(text.split())


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


@dataclass
class Turn:
    """What a step has done so far: its task, its question, the last output, the reasons."""

    task_id: str | None = None
    approval_id: str | None = None
    last: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    question: Question
    """The block of §6, read once: what the task's question is compared with."""
    voice_id: str


def filled(text: str, turn: Turn, proof: Proof) -> str:
    text = text.replace(ID, turn.task_id or ID)
    text = text.replace(APPROVAL_ID, turn.approval_id or APPROVAL_ID)
    return text.replace(VOICE_ID, proof.voice_id)


def a_command(number: int, line: str, turn: Turn, proof: Proof) -> None:
    report = proof.report
    report.say(f"    $ {line}")
    done = base.heard(line, base.run(line))
    output = done.stdout + done.stderr
    turn.last = joined(output) if line.endswith(HELP) else output
    for printed in output.rstrip("\n").splitlines():
        report.say(f"    | {printed}")
    if CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        report.say(f"    il task: {turn.task_id}")
    if RUN in f" {line} " and run_row(output, "outcome") in REASONED:
        turn.reasons.append(run_row(output, "reason") or EMPTY)
    if line == APPROVALS:
        compared(number, output, turn, proof)
    if line == VOICE:
        if done.returncode == 0:
            report.passed(number, f"«{VOICE}» esce con 0")
        else:
            report.failure(number, f"«{VOICE}» esce con {done.returncode}, non con 0", output)


def compared(number: int, output: str, turn: Turn, proof: Proof) -> None:
    """The question of the step's task, against the block of §6; its id for ``<approval-id>``."""
    report = proof.report
    mine = [one for one in questions(output) if one.values.get("task") == turn.task_id]
    if len(mine) != 1:
        report.failure(number, f"il task {turn.task_id} ha {len(mine)} domande, non una", output)
        return
    turn.approval_id = mine[0].values.get("approval")
    differences = unlike(mine[0], proof.question)
    if differences:
        report.failure(number, "; ".join(differences), output)
    else:
        report.passed(number, "la domanda del task ha la forma del blocco di §6")


def a_step(number: int, todo: Sequence[base.Block], proof: Proof) -> None:
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    turn = Turn()
    for block in todo:
        if block.kind == "comando":
            for line in block.lines:
                a_command(number, filled(line, turn, proof), turn, proof)
        elif block.kind == "atteso":
            wanted = [filled(line, turn, proof) for line in block.lines]
            absent = base.missing(wanted, turn.last)
            if absent:
                report.failure(number, f"mancano {absent}", turn.last)
            else:
                report.passed(number, "l'uscita è quella attesa")
        elif block.kind == "occhio":
            text = filled(block.body, turn, proof)
            report.looked(number, text, base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
    if turn.reasons:
        why = same_reason(turn.reasons)
        if why is None:
            report.passed(number, f"le corse dicono la stessa ragione: {turn.reasons[0]}")
        else:
            report.failure(number, why, "\n".join(turn.reasons))


# ----------------------------------------------------------------------------------------
# Step 1: the preconditions
# ----------------------------------------------------------------------------------------


def answers(site: str) -> bool:
    with urllib.request.urlopen(f"https://{site}", timeout=REACHED_WITHIN) as answered:  # noqa: S310
        return bool(answered.status < 400)


def preconditions(report: base.Report) -> str | None:
    """What §22 needs of the world, read where ELA reads it; the configured voice's id, or ``None``.

    Through the reader of M6.3c's step 1: the first thing missing makes step 1 SKIPPED with what is
    missing, and the script stops there — never a FAILED, which would read as ELA's (dec. 2-bis).
    """
    from ela.composition.settings import BrowserSettings
    from ela.infrastructure.machine.browser import shell_folder

    def voice() -> dict[str, Any]:
        online: dict[str, Any] = base.Api().get("/voice")["voice"]["online"]
        return online

    def reached(site: str) -> Callable[[], bool]:
        return lambda: answers(site)

    checks: list[tuple[str, base.Check]] = [
        ("ELA risponde", lambda: base.Api().get("/health") is not None),
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
        *((f"{site} risponde", reached(site)) for site in SITES),
        ("la voce online è configurata", lambda: bool(voice()["configured"])),
    ]
    if not base.required(report, checks):
        return None
    voice_id: str = voice()["voice_id"]
    report.say(f"    la voce configurata: {voice_id}")
    return voice_id


# ----------------------------------------------------------------------------------------
# The whole
# ----------------------------------------------------------------------------------------


def default_out() -> Path:
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    return Path.home() / "Downloads" / f"prova-m13.1c-m13.1d-m9.6-{stamp}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    text = GUIDE.read_text(encoding="utf-8")
    todo = base.steps(base.blocks(text, HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = base.Report(written)
        report.say(f"La prova a mano di M13.1c, M13.1d e M9.6, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        voice_id = preconditions(report)
        if voice_id is not None:
            proof = Proof(base.Api(), report, ask, the_guides_question(text), voice_id)
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
