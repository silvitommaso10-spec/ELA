"""La prova a mano di M13.15: le policy sul login e sui file dal browser.

La sezione 34 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m13_15.py               # contro l'ELA che gira
    uv run python scripts/prova_m13_15.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m13_14.py`` (decisione
26 del blocco di M13.15) — le policy, «crei la policy?», i gap, le viste — e ne riusa i pezzi;
prende gli scaricamenti da ``scripts/prova_m9_5.py``. Legge dalla sezione 34 i blocchi con il
marcatore sopra, ``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``. I tipi
di M13.14 con le loro parole, e i suoi:

* ``mano``: ciò che fa Tommaso — aprire o chiudere il vault, uscire da un sito —; lo script aspetta
  Invio. **Lo script non lancia mai ``bw``**;
* ``voce``: l'id della voce, chiesto senza mostrarlo e mai scritto nel file: i comandi vi si
  registrano con ``<id della voce>``; il piano che lo porta va in un file temporaneo fuori dal
  repository, ``600``, tolto alla fine del passo, anche se il passo fallisce o è interrotto;
* ``risultato``: la dimensione e lo sha256 che il risultato di un caricamento dice, confrontati con
  quelli che lo script calcola dal file;
* ``nomi``: un secondo nome del secondo file, dato al primo;
* ``assente``: parole che l'uscita del comando non deve avere;
* ``ambigua``: il login senza ``entry`` fermato prima della domanda da ``vault.entry_ambiguous`` —
  più voci per quel sito nel vault — fa il passo SALTATO, con la sua ragione (risposta 48);
* ``coperta``: lo step del task deciso «covered by policy …» da quella policy, letto nell'evento
  della sua decisione nell'audit, anche quando poi fallisce prima della spesa;
* ``ferma`` (M13.9d, decisione 94): ``ela task run`` in sfondo; quando lo step è RUNNING — letto
  dall'API — e il file dello scaricamento è comparso nella cartella, lo script manda lui ``ela task
  cancel``. Lo step deve finire entro il tempo del tool più il limite di una chiusura, con
  ``browser.stopped``; se lo scaricamento finisce prima del «ferma», o il sito non risponde, il
  passo è SALTATO con la sua ragione;
* ``intatto`` (M13.13c, decisione 118): se il profilo è com'era dal 2026-11-17 — sì, e il passo 3
  è la prova a mano del criterio 2 di M13.13c; no, e il passo è FALLITO con la sua ragione.

**Ogni** ``ela task run`` **ha un limite, 120 s** (M13.9d, decisione 84): una guardia e non una
misura. Al limite il comando della CLI è chiuso — il figlio dello script, non ELA —, il passo è
FALLITO con la sua ragione, ``ela task show`` del task va nel file, e la prova si ferma.

**Il file della prova non porta il percorso intero di un file, il nome utente né l'id di una voce**:
stanno sullo schermo. Se la prova si ferma a metà, lo script revoca le policy che ha creato e sono
ancora vive.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m13_13 as files  # noqa: E402 — the same
import prova_m13_14 as m14  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 34. "
KINDS: Final = (
    *m14.KINDS,
    "mano",
    "voce",
    "risultato",
    "nomi",
    "assente",
    "ambigua",
    "coperta",
    "ferma",
    "intatto",
)
LOOKS: Final[Mapping[str, str]] = {
    "occhio": "una domanda all'occhio di Tommaso, su ciò che ha davanti",
}
"""The kinds of block that ask Tommaso's eye (M13.10b): before each, in its step, a block of
:data:`SHOWS` (``tests/docs/test_prova_eyes.py``)."""
SHOWS: Final[Mapping[str, str]] = {
    "schermo": "stampa sullo schermo, e non nel file, l'uscita dei suoi comandi: l'anteprima",
    "console": "ti fa aprire la vista delle policy della console",
}
FOLDER: Final = "ELA/prova-m13.15"
"""The folder of the proof under the declared root: the only place the script writes in."""
SUBFOLDERS: Final = ("giu", "su", "fuori")
OWN_FILES: Final[Mapping[str, str]] = {
    "su/da-caricare.txt": (
        "Il file della prova di M13.15: un testo che non dice niente di nessuno.\n"
    ),
    "fuori/fuori.txt": "Un file di una cartella che nessuna policy della prova nomina.\n",
}
"""The two files the script writes at step 1, with their text: what the uploads give."""
SECOND_NAME: Final = "su/due-nomi.txt"
"""The second name the script gives at step 8: removed at step 1 of the next proof."""
SITES: Final = ("httpbin.org", "testpages.eviltester.com", "news.ycombinator.com")
CAPABILITIES: Final = (
    "browser.login",
    "browser.download",
    "browser.download_as_you",
    "browser.upload",
    "browser.upload_as_you",
)
"""The five M13.15 opens to the policies: no live one of them before the proof."""
PREVIEW_FIELD: Final = "by_value"
"""A field the preview of the API has since M13.15: what says the Core runs the branch's code."""
ENTRY: Final = "<id della voce>"
"""The placeholder of the id of the entry, in the commands and in the plan of the login."""
AMBIGUOUS: Final = "vault.entry_ambiguous"
SKIPPED_AMBIGUOUS: Final = (
    "il vault ha più di una voce per il sito, e il login senza entry si è fermato prima della "
    "domanda con vault.entry_ambiguous: la domanda non può nascere, e il passo non la finge"
)
NO_ENTRY: Final = "senza l'id della voce i passi del login non hanno niente da misurare"
RUN: Final = "uv run ela task run "
RUN_LIMIT: Final = 120
"""The guard of every ``ela task run`` of the proof, in seconds, counted from its launch (M13.9d,
decision 84): four times the tool's time, 30 s, and the limit of a closing, 5 s — 125 s —, rounded
down; a guard, and not a measure. A step of ELA that never ends would hold the proof for ever, as
it did on 2026-11-17."""
STOP_SECONDS: Final = 35
"""From the stop of the task to the end of its step, at most (decision 94): the tool's time, 30
s, and the limit of a closing, ``BROWSER_CLOSE_GRACE_SECONDS``. A download hears the stop at once,
and this is the bound step 14 holds it to; the worst case of ADR 0072 §1, a formula of the
constants, is wider — a tool that hears the stop only at its own point (answer 107). Read on the
clock of the script, which waits for the run to return."""
UNTOUCHED: Final = (
    "il profilo è com'era: il passo 3 è la prova a mano del criterio 2 di M13.13c (ADR 0073)"
)
TOUCHED: Final = (
    "il profilo è stato pulito a mano: il passo 3 non prova il criterio 2 di M13.13c, e ADR 0073 "
    "non si accetta con questa prova"
)
"""What ``intatto`` says (M13.13c, decision 118): the real profile is, with every likelihood, in the
state that makes the browser fall, and step 3 is the proof by hand that it works again — unless it
was cleaned by hand before."""
STOPPED: Final = "browser.stopped"
UNREACHABLE: Final = "browser.unreachable"
STOP_REASON: Final = "la prova a mano di M13.9d: il «ferma» mentre il file arriva"
LOOK: Final = 0.2
"""How often the script asks the API and the folder, while it waits for an event of theirs."""
SKIPPED_FINISHED: Final = (
    "lo step è finito prima che il «ferma» potesse arrivare mentre il file arriva: non c'è niente "
    "da fermare, e il passo non lo finge"
)
SKIPPED_UNREACHABLE: Final = (
    "il sito non ha risposto, e lo scaricamento non è cominciato: il «ferma» non ha niente da "
    "interrompere"
)

Report = base.Report


@dataclass
class Proof(m14.Proof):
    """M13.14's proof, with the id of the entry — kept in memory, written nowhere — and the
    temporary plans, taken away at the end of their step."""

    entry: str | None = None
    temporary: list[Path] = field(default_factory=list)


class Skipped(Exception):
    """The rest of the step cannot be measured, for a reason of the world: SALTATO."""


# ----------------------------------------------------------------------------------------
# The vocabulary
# ----------------------------------------------------------------------------------------


def a_hand_line(line: str) -> str:
    if not line.strip():
        raise ValueError("an empty line says nothing")
    if " bw " in f" {line} ":
        raise ValueError(f"{line!r} names the vault's program: the script never launches it")
    return line


def a_result_line(line: str) -> str:
    if not line.startswith(f"{FOLDER}/") or " " in line:
        raise ValueError(f"{line!r} is not a file of the proof: «{FOLDER}/…»")
    return line


def _a_covering_line(line: str) -> int:
    """A line of ``coperta``: «<id della policy N>», the policy the step's decision rests on."""
    found = m14.POLICY.fullmatch(line)
    if found is None:
        raise ValueError(f"{line!r} is not «<id della policy N>»")
    return int(found.group(1))


def a_names_line(line: str) -> tuple[str, str]:
    words = line.split()
    if len(words) != 2 or not all(one.startswith(f"{FOLDER}/") for one in words):
        raise ValueError(f"{line!r} is not «{FOLDER}/the-new-name {FOLDER}/the-file»")
    return words[0], words[1]


def a_run_line(line: str) -> str:
    if line != f"{RUN}<id>":
        raise ValueError(f"{line!r} is not «{RUN}<id>»")
    return line


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    **m14.READERS,
    "mano": a_hand_line,
    "voce": m14.the_words(ENTRY),
    "risultato": a_result_line,
    "nomi": a_names_line,
    "assente": m14.a_said,
    "ambigua": m14.the_words(AMBIGUOUS),
    "coperta": lambda line: _a_covering_line(line),
    "ferma": a_run_line,
    "intatto": m14.a_said,
}


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
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


# ----------------------------------------------------------------------------------------
# What never enters the file: the home, and the id of the entry
# ----------------------------------------------------------------------------------------


ROOT_WORD: Final = "<la radice>"
"""What the file says where the declared root is: a file's whole path stays on the screen."""
ENTRIES_WORD: Final = "<le voci, sullo schermo>"
"""What the file says where a command printed the entries of a policy of login — their names and
their usernames masked: the file is without the username (decision 26), and they stay on the
screen, where the preview of step 9 shows them."""
ENTRIES_LINE: Final = re.compile(r"^(\s*entry values\s+)\S.*$", re.MULTILINE)


def masked(text: str, proof: Proof) -> str:
    """``text`` without the declared root, the home of whoever runs the proof, the id of the
    entry, and the entries a command printed by name and masked username (decision 26): a file's
    whole path, an id and a username stay on the screen."""
    for one in sorted({str(proof.root), str(proof.root.resolve())}, key=len, reverse=True):
        if one not in ("", "."):
            text = text.replace(one, ROOT_WORD)
    text = m14.private(text, proof.home)
    if proof.entry:
        text = text.replace(proof.entry, ENTRY)
    return ENTRIES_LINE.sub(lambda line: line.group(1) + ENTRIES_WORD, text)


def with_the_entry(line: str, proof: Proof) -> str:
    """The line ELA receives: the id of the entry in place of :data:`ENTRY` — and the plan of a
    ``--file`` that holds it copied to a temporary file, ``600``, outside the repository."""
    if proof.entry is None:
        return line
    line = line.replace(ENTRY, proof.entry)
    if "--file" not in line:
        return line
    before, after = line.split("--file", 1)
    named, *rest = after.split()
    source = ROOT / named
    text = source.read_text(encoding="utf-8")
    if ENTRY not in text:
        return line
    handle, written = tempfile.mkstemp(prefix="prova-m13.15-", suffix=".json")
    os.close(handle)
    path = Path(written)
    path.chmod(0o600)
    path.write_text(text.replace(ENTRY, proof.entry), encoding="utf-8")
    proof.temporary.append(path)
    return " ".join([before.rstrip(), "--file", str(path), *rest])


def removed(proof: Proof) -> None:
    """The temporary plans taken away: at the end of every step, whatever happened in it."""
    while proof.temporary:
        path = proof.temporary.pop()
        path.unlink(missing_ok=True)


def ran(line: str) -> Any:
    """A command of the section: ``ela task run`` with its guard (decision 84), the rest as ever."""
    return base.run(line, RUN_LIMIT) if line.startswith(RUN) else base.run(line)


def overdue(late: base.Overdue, turn: guided.Turn, proof: Proof) -> None:
    """A run past its guard: FALLITO with its reason, the state of the task in the file — what
    ELA was doing —, and the proof stops: the steps after would measure something else."""
    proof.report.failure(proof.current, masked(str(late), proof))
    if turn.task_id is not None:
        shown = base.run(f"uv run ela task show {turn.task_id}")
        for one in (shown.stdout + shown.stderr).rstrip("\n").splitlines():
            proof.report.say(f"    | {masked(one, proof)}")
    raise base.Stop(masked(str(late), proof))


def a_command(line: str, turn: guided.Turn, proof: Proof) -> None:
    """One command: the file gets the line with the placeholder and the output masked."""
    report = proof.report
    report.say(f"    $ {masked(line, proof)}")
    sent = with_the_entry(line, proof)
    try:
        done = base.heard(sent, ran(sent))
    except base.Overdue as late:
        overdue(late, turn, proof)
    printed = done.stdout + done.stderr
    turn.last += printed
    turn.code = done.returncode or turn.code
    for one in printed.rstrip("\n").splitlines():
        report.say(f"    | {masked(one, proof)}")
    if guided.CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        turn.child_id = None
        report.say(f"    il task: {turn.task_id}")


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    turn.last, turn.code = "", 0
    for line in lines:
        a_command(m14.filled(line, turn, proof), turn, proof)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def measured(path: Path) -> tuple[int, str]:
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def result_failures(output: Mapping[str, Any] | None, size: int, digest: str) -> list[str]:
    """What ``risultato`` finds wrong with the output of an upload: the size and the sha256 it says
    against the ones the script computed from the file."""
    if output is None:
        return ["il task non ha il risultato di un caricamento"]
    failures = []
    if output.get("size") != size:
        failures.append(f"il risultato dice {output.get('size')} byte, il file ne ha {size}")
    if output.get("digest") != digest:
        failures.append("lo sha256 del risultato non è quello del file")
    return failures


def absent_failures(words: Sequence[str], printed: str) -> list[str]:
    return [f"l'uscita dice «{one}»" for one in words if one in printed]


def live_of_the_five(policies: Sequence[Mapping[str, Any]]) -> str | None:
    found = [one for one in m14.live(policies) if one.get("capability") in CAPABILITIES]
    if not found:
        return None
    named = ", ".join(f"{one.get('short')} di {one.get('capability')}" for one in found)
    return f"e c'è una policy viva ({named}): revocala con uv run ela policy revoke"


def scope_admits(scope: Sequence[str]) -> str | None:
    from ela.permissions.scope import within_scope

    if within_scope(list(scope), f"{FOLDER}/su/da-caricare.txt"):
        return None
    return f"e nessuna cartella dello scope dichiarato, {list(scope)!r}, ammette {FOLDER}/"


# ----------------------------------------------------------------------------------------
# The folder of the proof
# ----------------------------------------------------------------------------------------


def planned_files(todo: Mapping[int, Sequence[base.Block]]) -> frozenset[str]:
    """The files of the folder of the proof the plans of the section name, relative to it — read
    from the plans, never written here — and the script's own."""
    named = {*OWN_FILES, SECOND_NAME}
    for blocks in todo.values():
        for block in blocks:
            for line in block.lines:
                if block.kind != "comando" or "--file" not in line:
                    continue
                sent = ROOT / line.split("--file", 1)[1].split()[0]
                for step in json.loads(sent.read_text(encoding="utf-8"))["steps"]:
                    path = str(step["arguments"].get("file", ""))
                    if path.startswith(f"{FOLDER}/"):
                        named.add(path.removeprefix(f"{FOLDER}/"))
    return frozenset(named)


def strangers(folder: Path, planned: frozenset[str]) -> list[str]:
    found: list[str] = []
    for one in sorted(folder.iterdir()):
        if one.name in SUBFOLDERS and one.is_dir() and not one.is_symlink():
            for inner in sorted(one.iterdir()):
                mine = f"{one.name}/{inner.name}"
                if mine in planned and inner.is_file() and not inner.is_symlink():
                    continue
                found.append(mine)
            continue
        found.append(one.name)
    return found


def prepared(root: Path, report: base.Report, planned: frozenset[str]) -> str | None:
    """The folder as step 1 wants it: what a proof before left — **the files the plans name, and
    the script's own** — removed one by one and said; anything else stops the proof before anything
    is touched. Then the three subfolders, ``700``, and the two files of the script."""
    folder = root / FOLDER
    if os.path.lexists(folder):
        if folder.is_symlink() or not folder.is_dir():
            return f"e {FOLDER} non è una cartella: la prova non tocca niente, guardala tu"
        others = strangers(folder, planned)
        if others:
            return (
                f"e {FOLDER}/ tiene {others}, che non sono file dei piani della prova: la prova "
                "non tocca niente, guardali tu"
            )
        for name in sorted(planned):
            target = folder / name
            if target.is_file():
                target.unlink()
                report.say(f"    tolto {FOLDER}/{name}, di una prova di prima")
    for sub in SUBFOLDERS:
        (folder / sub).mkdir(mode=files.FOLDER_MODE, parents=True, exist_ok=True)
    for name, text in OWN_FILES.items():
        (folder / name).write_text(text, encoding="utf-8")
    report.say(
        f"    {FOLDER}/: {', '.join(f'{one}/' for one in SUBFOLDERS)}, e i due file della prova"
    )
    return None


# ----------------------------------------------------------------------------------------
# The kinds of this section
# ----------------------------------------------------------------------------------------


def a_hand(number: int, block: base.Block, proof: Proof) -> None:
    proof.report.say(f"[{number}] A TE: {' '.join(block.lines)}")
    proof.ask(f"[{number}] Premi Invio quando hai fatto. ")


def untouched(number: int, block: base.Block, proof: Proof) -> None:
    """``intatto`` (M13.13c, decision 118): whether the profile is as it was. Yes, and the step is
    the proof by hand of criterion 2; no, and the script says the proof cannot be that."""
    question = " ".join(block.lines)
    if base.yes_or_no(proof.ask, f"[{number}] {question} (s/n) "):
        proof.report.passed(number, UNTOUCHED)
    else:
        proof.report.failure(number, TOUCHED)


def an_entry(number: int, proof: Proof, secret: Callable[[str], str]) -> None:
    """``voce``: the id, asked without echo, kept in memory; the file says only that it was
    given."""
    given = secret(f"[{number}] L'id della voce di news.ycombinator.com (non si vede): ").strip()
    if not given:
        raise base.Stop(NO_ENTRY)
    proof.entry = given
    proof.report.passed(number, "l'id della voce è dato: sta in memoria, e non in questo file")


def a_result(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    (line,) = block.lines
    size, digest = measured(proof.root / line)
    results = proof.api.get(f"/tasks/{turn.task_id}/results")
    uploads = [one for one in results if one.get("output", {}).get("digest") is not None]
    output = uploads[-1]["output"] if uploads else None
    said = None if output is None else output.get("size")
    proof.report.say(f"    | il file: {size} byte; il risultato: {said} byte")
    failures = result_failures(output, size, digest)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"il risultato dice la dimensione e lo sha256 di {line}")


def two_names(number: int, block: base.Block, proof: Proof) -> None:
    (line,) = block.lines
    new, existing = a_names_line(line)
    target = proof.root / new
    target.unlink(missing_ok=True)
    os.link(proof.root / existing, target)
    names = os.lstat(target).st_nlink
    if names == 2:
        proof.report.passed(number, f"{new} è un secondo nome di {existing}")
    else:
        proof.report.failure(number, f"{new} ha {names} nomi, non 2")


def an_absence(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    failures = absent_failures(block.lines, turn.last)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"l'uscita non dice {block.lines}")


def covered(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``coperta``: the Guardian allowed the step of this task **on that policy** — read from the
    audit, the event of its decision —, even when the step then failed before the spend: what says
    a refusal came on the road of the policy, and not on the road of a question (decision 50)."""
    (line,) = block.lines
    step = _a_covering_line(line)
    mine = proof.policies.get(step)
    if mine is None:
        proof.report.failure(number, f"la prova non ha la policy del passo {step}")
        return
    events = proof.api.get(f"/audit?task_id={turn.task_id}")
    decided = [
        one
        for one in events
        if one.get("event_type") == "PERMISSION_DECIDED"
        and one.get("authorization_id") == mine[0]
        and "covered by policy" in str(one.get("summary"))
    ]
    if decided:
        proof.report.passed(number, f"lo step è coperto dalla policy {mine[1]}")
    else:
        proof.report.failure(number, f"nessuna decisione dice «covered by policy {mine[1]}»")


def step_state(task: Mapping[str, Any]) -> str | None:
    """The state of the one step of a task, as the API says it."""
    steps = task.get("steps") or ()
    return str(steps[0].get("state")) if steps else None


def arrived(folder: Path, before: frozenset[str]) -> list[str]:
    """What appeared in ``folder`` since ``before``: the file of a download that has begun."""
    return sorted(set(os.listdir(folder)) - before)


def stop_failures(result: Mapping[str, Any] | None, seconds: float) -> list[str]:
    """What ``ferma`` finds wrong once the step has ended: its code, and how long it took from
    the stop — the tool's time and the limit of a closing at most."""
    failures: list[str] = []
    code = None if result is None else (result.get("error") or {}).get("code")
    if code != STOPPED:
        failures.append(f"lo step è finito con {code}, non con {STOPPED}")
    if seconds > STOP_SECONDS:
        failures.append(
            f"lo step è finito {seconds:.1f} s dopo il «ferma», non entro {STOP_SECONDS}"
        )
    return failures


def skipped_because(result: Mapping[str, Any] | None) -> str | None:
    """Why a step that ended before the stop came is SALTATO: it finished, or the site did not
    answer; ``None`` when it ended in any other way — which is a failure, said by the caller."""
    if result is None:
        return None
    if result.get("status") == "SUCCEEDED":
        return SKIPPED_FINISHED
    if (result.get("error") or {}).get("code") == UNREACHABLE:
        return SKIPPED_UNREACHABLE
    return None


def stopped_while_arriving(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``ferma`` (decision 94): the run in the background; **the events it waits for are the
    API's and the folder's** — the step RUNNING, and the file of the download in the folder —, and
    then the stop of the task, sent by the script. The step must end with ``browser.stopped``,
    within :data:`STOP_SECONDS` of the stop."""
    (line,) = block.lines
    report = proof.report
    folder = proof.root / FOLDER / "giu"
    before = frozenset(os.listdir(folder))
    sent = m14.filled(line, turn, proof)  # type: ignore[arg-type]
    report.say(f"    $ {masked(sent, proof)} — in sfondo")
    # The guard of every run, counted once from the launch, and the run in a group of its own:
    # at the guard it is closed with what it started (the re-read of M13.9d).
    running = base.started(sent, alone=True)
    deadline = time.monotonic() + RUN_LIMIT
    began = False
    while running.poll() is None and time.monotonic() < deadline:
        if not began:
            began = step_state(proof.api.get(f"/tasks/{turn.task_id}")) == "RUNNING"
        if began and arrived(folder, before):
            break
        time.sleep(LOOK)
    if running.poll() is None and time.monotonic() >= deadline:
        base.closed(running)
        overdue(base.Overdue(sent, RUN_LIMIT), turn, proof)
    if running.poll() is not None:
        printed, _ = running.communicate()
        turn.last = printed or ""
        result = last_result(proof, turn)
        why = skipped_because(result)
        if why is None:
            report.failure(
                number, "lo step è finito da sé prima del «ferma»", masked(turn.last, proof)
            )
            return
        report.skipped(number, why)
        raise Skipped
    report.say(
        f"    lo step è RUNNING e il file è nella cartella: {', '.join(arrived(folder, before))}"
    )
    stop = f"uv run ela task cancel {turn.task_id} --reason {shlex.quote(STOP_REASON)}"
    asked = time.monotonic()
    cancelled = base.heard(stop, base.run(stop))
    report.say(f"    $ uv run ela task cancel {turn.task_id} — il «ferma» dello script")
    printed = ""
    try:
        printed = base.collected(running, sent, RUN_LIMIT, deadline - time.monotonic())
    except base.Overdue as late:
        overdue(late, turn, proof)
    seconds = time.monotonic() - asked
    turn.last = (printed or "") + cancelled.stdout
    for one in turn.last.rstrip("\n").splitlines():
        report.say(f"    | {masked(one, proof)}")
    failures = stop_failures(last_result(proof, turn), seconds)
    if failures:
        report.failure(number, "; ".join(failures))
    else:
        report.passed(
            number, f"fermato mentre il file arrivava: {STOPPED}, {seconds:.1f} s dopo il «ferma»"
        )


def last_result(proof: Proof, turn: guided.Turn) -> Mapping[str, Any] | None:
    results = proof.api.get(f"/tasks/{turn.task_id}/results")
    return results[-1] if results else None


def ambiguous(number: int, turn: guided.Turn, proof: Proof) -> None:
    if AMBIGUOUS in turn.last:
        proof.report.skipped(number, SKIPPED_AMBIGUOUS)
        raise Skipped


def a_block(
    number: int, block: base.Block, turn: guided.Turn, proof: Proof, secret: Callable[[str], str]
) -> None:
    kind = block.kind
    if kind == "comando":
        commands(block.lines, turn, proof)
    elif kind == "atteso":
        absent = base.missing([m14.filled(one, turn, proof) for one in block.lines], turn.last)  # type: ignore[arg-type]
        if absent:
            proof.report.failure(number, f"mancano {absent}", masked(turn.last, proof))
        else:
            proof.report.passed(number, "l'uscita è quella attesa")
    elif kind == "schermo":
        on_the_screen(number, block, turn, proof)
    elif kind == "crea":
        a_creation(number, block, turn, proof)
    elif kind == "mano":
        a_hand(number, block, proof)
    elif kind == "voce":
        an_entry(number, proof, secret)
    elif kind == "risultato":
        a_result(number, block, turn, proof)
    elif kind == "nomi":
        two_names(number, block, proof)
    elif kind == "assente":
        an_absence(number, block, turn, proof)
    elif kind == "ambigua":
        ambiguous(number, turn, proof)
    elif kind == "coperta":
        covered(number, block, turn, proof)
    elif kind == "ferma":
        stopped_while_arriving(number, block, turn, proof)
    elif kind == "intatto":
        untouched(number, block, proof)
    else:
        m14.a_block(number, block, turn, proof)  # type: ignore[arg-type]


def on_the_screen(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``schermo``: on the screen alone, whole — the id of the entry in the command, and the
    preview, which shows the entry by name; the file says which command, with the placeholder."""
    for line in block.lines:
        asked = m14.filled(line, turn, proof)  # type: ignore[arg-type]
        sent = with_the_entry(asked, proof)
        done = base.heard(sent, base.run(sent))
        print(f"    $ {masked(asked, proof)}", flush=True)
        for one in (done.stdout + done.stderr).rstrip("\n").splitlines():
            print(f"    | {one}", flush=True)
        proof.report.say(
            f"    $ {masked(asked, proof)} — l'uscita è sullo schermo, non in questo file"
        )
        m14.screen_failed(number, done, turn, proof, lambda text: masked(text, proof))  # type: ignore[arg-type]


def a_creation(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``crea``, as M13.14's — through this script's commands, which mask the entry."""
    (line,) = block.lines
    line = m14.filled(line, turn, proof)  # type: ignore[arg-type]
    before = {str(one["id"]) for one in m14.live(m14.policies_of(proof.api))}
    commands([line], turn, proof)
    after = {str(one["id"]) for one in m14.live(m14.policies_of(proof.api))}
    failed = m14.a_creation_failure(turn.code, turn.last, after != before)
    if failed is not None:
        proof.report.failure(number, masked(failed, proof), masked(turn.last, proof))
        raise base.Stop(m14.NO_POLICY)
    if not base.yes_or_no(proof.ask, f"[{number}] Crei la policy? (s/n) "):
        raise base.Stop(m14.SAID_NO)
    commands([line + m14.CONFIRM], turn, proof)
    short = m14.created_short(turn.last)
    mine = [one for one in m14.live(m14.policies_of(proof.api)) if one.get("short") == short]
    if short is None or len(mine) != 1:
        proof.report.failure(number, "la policy non è nata", masked(turn.last, proof))
        raise base.Stop(m14.NO_POLICY)
    proof.policies[number] = (str(mine[0]["id"]), short)
    proof.report.passed(number, f"la policy {short}, creata dopo l'anteprima")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, secret: Callable[[str], str]
) -> None:
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    proof.current = number
    turn = guided.Turn()
    try:
        for block in todo:
            a_block(number, block, turn, proof, secret)
    except Skipped:
        pass
    finally:
        removed(proof)
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def preconditions(report: base.Report) -> bool:
    planned = planned_files(base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING)))
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: l'anteprima dell'API ha «{PREVIEW_FIELD}»",
            lambda: guided.so(
                PREVIEW_FIELD
                in base.Api().get("/openapi.json")["components"]["schemas"]["PreviewOut"][
                    "properties"
                ]
            ),
        ),
        (
            f"la radice e lo scope sono dichiarati, e lo scope ammette {FOLDER}/",
            lambda: scope_admits(m14.declared_root()[1]),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(all(site in m14.declared_sites() for site in SITES)),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            accounts.profile_ready,
        ),
        (
            f"nessuna policy viva di {', '.join(CAPABILITIES)}",
            lambda: live_of_the_five(m14.policies_of(base.Api())),
        ),
        (
            f"la cartella della prova, {FOLDER}/, pronta: niente di una prova di prima, le tre "
            "cartelle e i due file",
            lambda: prepared(m14.declared_root()[0], report, planned),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.15-{datetime.now():%Y%m%d-%H%M%S}.txt"


def walked(
    report: base.Report,
    todo: Mapping[int, list[base.Block]],
    proof: Proof,
    secret: Callable[[str], str],
) -> None:
    try:
        base.walk(report, todo, lambda number, its: a_step(number, its, proof, secret))
    except KeyboardInterrupt:
        report.say()
        report.stop(proof.current, "la prova è stata interrotta a metà")
    finally:
        removed(proof)
        report.say()
        report.say("—— dopo ——")
        m14.leftovers(proof)  # type: ignore[arg-type]


def main(
    argv: Sequence[str] | None = None,
    ask: base.Ask = input,
    secret: Callable[[str], str] = getpass.getpass,
) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.15, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {m14.private(str(out), Path.home())}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
            api = base.Api()
            proof = Proof(api, report, ask, root=m14.declared_root()[0])
            try:
                walked(report, todo, proof, secret)
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {m14.private(str(out), Path.home())}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
