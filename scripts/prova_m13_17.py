"""La prova a mano di M13.17: i file di tutto il computer.

La sezione 35 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m13_17.py               # contro l'ELA che gira
    uv run python scripts/prova_m13_17.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m13_15.py`` (bozza della
sezione 35 nella SPEC di M13.17, decisioni 20–23) e ne riusa i pezzi: i comandi con il limite di
120 s di ogni ``ela task run``, lo ``schermo`` che si ferma su un errore, ``crea``, ``assente``;
di ``scripts/prova_m13_14.py`` usa ``occhio``, ``policy``, ``perché``, ``no``, ``nessuna``,
``console`` e ``file``. Legge dalla sezione 35 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``. I suoi tipi:

* ``sì``: la domanda del task mostrata, e il sì di Tommaso dato con la riga del blocco;
* ``fatto``: una domanda su ciò che è successo — che cosa ha chiesto macOS —, la cui risposta va nel
  file com'è: il passo non passa né fallisce per lei;
* ``muto``: la decisione dello step del task ha la regola del blocco, e per quel task l'audit non
  ha nessun ``APPROVAL_REQUESTED`` e nessun ``BELL_RUNG``;
* ``rifiuto`` (risposta 44 della review della SPEC): la riga lanciata **deve** finire in errore —
  il codice d'uscita, non una parola — e la sua ultima riga avere le parole del blocco; quella riga
  va sullo schermo, e nel file solo il codice;
* ``pulizia``: la cartella della Scrivania tolta, con i soli file dei piani della sezione; con altro
  dentro non tocca niente.

**Lo script non tocca il** ``.env``: radice ed elenco li legge da ELA, nel blocco ``files`` di
``GET /diagnostics``, che solo il codice del branch ha. **Non guarda mai dentro Library**
(risposta 45). **Il file della prova non porta il percorso intero di un file**: la radice, che è la
home, diventa ``<la radice>``.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_13 as files  # noqa: E402 — the same
import prova_m13_14 as m14  # noqa: E402 — the same
import prova_m13_15 as m15  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 35. "
KINDS: Final = (*m14.KINDS, "sì", "assente", "fatto", "muto", "rifiuto", "pulizia")
LOOKS: Final[Mapping[str, str]] = {
    "occhio": "una domanda all'occhio di Tommaso, su ciò che ha davanti",
}
"""The kinds of block that ask Tommaso's eye (M13.10b): before each, in its step, a block of
:data:`SHOWS` (``tests/docs/test_prova_eyes.py``). ``fatto`` asks too, but about what happened —
which windows macOS opened —, never about the screen: nothing could show it before."""
SHOWS: Final[Mapping[str, str]] = {
    "schermo": "stampa sullo schermo, e non nel file, l'uscita dei suoi comandi",
    "console": "ti fa aprire la vista delle policy della console",
    "rifiuto": "mette sullo schermo l'ultima riga del rifiuto: la frase di ELA",
}
FOLDERS: Final = ("Documents/ELA/prova-m13.17", "Desktop/prova-m13.17")
"""The two folders of the proof under the root, which is the home: the only places it writes in."""
SUBFOLDERS: Final[Mapping[str, tuple[str, ...]]] = {
    "Documents/ELA/prova-m13.17": (),
    "Desktop/prova-m13.17": ("policy", "altra"),
}
OUTSIDE: Final = "Library/prova-m13.17/fuori.md"
"""The write of step 7: a folder the list must not admit (answer 45), never looked inside."""
CAPABILITIES: Final = (
    "fs.write",
    "browser.download",
    "browser.download_as_you",
    "browser.upload",
    "browser.upload_as_you",
)
"""The five whose policy a root of the home would move: no live one of them before the proof."""
BRANCH_FIELD: Final = "files"
"""A field ``GET /diagnostics`` has since M13.17: what says the Core runs the branch's code."""
APPROVE_LINE: Final = "uv run ela task approve "
REFUSED_RUN: Final = re.compile(
    r"^ELA_FS_(ROOT|SCOPE)=\S+ uv run python -c "
    r'"from ela\.composition import Settings; Settings\.load\(\)"$'
)
"""A line of ``rifiuto``: one variable changed for that command alone — never the ``.env`` —, and
the configuration loaded without starting ELA (answer 44)."""
PYTHON_REMOVED: Final = (
    "(le righe di Python sopra la frase sono tolte: è l'ultima riga dell'uscita)"
)
Proof = m15.Proof
Report = base.Report


# ----------------------------------------------------------------------------------------
# The vocabulary
# ----------------------------------------------------------------------------------------


def a_yes_line(line: str) -> str:
    if not line.startswith(APPROVE_LINE) or guided.APPROVAL_ID not in line:
        raise ValueError(
            f"{line!r} is not a yes: «{APPROVE_LINE}<id> --approval {guided.APPROVAL_ID}»"
        )
    return line


def a_fact_line(line: str) -> str:
    if not line.strip().endswith("?"):
        raise ValueError(f"{line!r} is not a question about what happened")
    return line


def a_rule_line(line: str) -> str:
    from ela.permissions import Rule

    if line not in {rule.value for rule in Rule}:
        raise ValueError(f"{line!r} is not a rule of the Guardian")
    return line


def a_refusal_line(line: str) -> str:
    """A line of ``rifiuto``: the command (:data:`REFUSED_RUN`), or the words its last line has."""
    if line.startswith("ELA_"):
        if REFUSED_RUN.fullmatch(line) is None:
            raise ValueError(f"{line!r} is not a refusal: «ELA_FS_…=… uv run python -c …»")
        return line
    if not line.strip() or "uv run" in line:
        raise ValueError(f"{line!r} is not the words of a refusal")
    return line


def a_cleaning_line(line: str) -> str:
    if line not in FOLDERS or not SUBFOLDERS[line]:
        raise ValueError(f"{line!r} is not the folder of the proof on the Desktop")
    return line


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    **m14.READERS,
    "sì": a_yes_line,
    "assente": m14.a_said,
    "fatto": a_fact_line,
    "muto": a_rule_line,
    "rifiuto": a_refusal_line,
    "pulizia": a_cleaning_line,
}


def refusal_of(block: base.Block) -> tuple[str, str]:
    """A ``rifiuto`` is two lines: the command, then the words of its last line."""
    if len(block.lines) != 2 or not block.lines[0].startswith("ELA_"):
        raise ValueError(f"a rifiuto is a command and its words: {list(block.lines)}")
    return block.lines[0], block.lines[1]


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
    wrong: list[str] = []
    for number, blocks in todo.items():
        for block in blocks:
            reader = READERS.get(block.kind)
            try:
                if reader is None:
                    raise ValueError(f"{block.kind!r} is not a kind of the section")
                for line in block.lines:
                    reader(line)
                if block.kind == "rifiuto":
                    refusal_of(block)
            except ValueError as error:
                wrong.append(f"passo {number}, {block.kind}: {error}")
    return wrong


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def the_branch(diagnostics: Mapping[str, Any]) -> str | None:
    if BRANCH_FIELD in diagnostics:
        return None
    return f"e GET /diagnostics non ha «{BRANCH_FIELD}»: ELA non gira dal codice del branch"


def the_root_is_the_home(open_files: Mapping[str, Any], home: Path) -> str | None:
    """Why the root ELA declares is not the home of whoever runs the proof, or ``None``. The
    sentence names neither: they are on the screen."""
    if Path(str(open_files.get("root"))).resolve() == home.resolve():
        return None
    return "e la radice che ELA dichiara non è la tua home: lo dice ela diagnostics, a files root"


def the_list_admits(open_files: Mapping[str, Any]) -> str | None:
    """Why the list is not the one the proof needs — it admits both folders, and never Library —,
    or ``None``: read off the entries ELA said, never off the disk (answer 45)."""
    from ela.permissions.scope import within_scope

    entries = [str(one.get("entry")) for one in open_files.get("folders") or ()]
    missing = [one for one in FOLDERS if not within_scope(entries, f"{one}/x.md")]
    if missing:
        return f"e l'elenco {entries} non ammette {missing}"
    if within_scope(entries, OUTSIDE):
        return f"e l'elenco {entries} ammette Library: la prova vuole la cartella che non apri"
    return None


def the_bell_rings(diagnostics: Mapping[str, Any]) -> str | None:
    bell = diagnostics.get("bell") or {}
    if bell.get("ready") is True:
        return None
    return (
        "e il campanello non è pronto (bell, in ela diagnostics): senza, il silenzio del passo 7 "
        "non proverebbe niente — ELA_NTFY_TOPIC nel .env, e un indirizzo che il telefono apre"
    )


def live_of_the_five(policies: Sequence[Mapping[str, Any]]) -> str | None:
    found = [one for one in m14.live(policies) if one.get("capability") in CAPABILITIES]
    if not found:
        return None
    named = ", ".join(f"{one.get('short')} di {one.get('capability')}" for one in found)
    return f"e c'è una policy viva ({named}): revocala con uv run ela policy revoke"


def silent_failures(events: Sequence[Mapping[str, Any]], rule: str) -> list[str]:
    """What ``muto`` finds wrong in the audit of a task: the decision of another rule, a question,
    a bell."""
    decided = [one for one in events if one.get("event_type") == "PERMISSION_DECIDED"]
    failures: list[str] = []
    if not any((one.get("payload") or {}).get("rule") == rule for one in decided):
        rules = [(one.get("payload") or {}).get("rule") for one in decided]
        failures.append(f"nessuna decisione ha la regola {rule}: {rules}")
    for kind, said in (("APPROVAL_REQUESTED", "una domanda"), ("BELL_RUNG", "un campanello")):
        if any(one.get("event_type") == kind for one in events):
            failures.append(f"il task ha {said}: {kind} è nell'audit")
    return failures


def last_line(printed: str) -> str:
    lines = [one.strip() for one in printed.splitlines() if one.strip()]
    return lines[-1] if lines else ""


def refusal_failures(code: int, printed: str, words: str) -> list[str]:
    """What ``rifiuto`` finds wrong: a line that succeeded — it loaded a configuration that had to
    be refused —, or a last line without the words. **The exit decides**, never a word."""
    if code == 0:
        return ["la riga è riuscita: ha caricato una configurazione che doveva essere rifiutata"]
    if not base.contains(last_line(printed).split(), words.split()):
        return [f"l'ultima riga dell'uscita non dice «{words}»"]
    return []


# ----------------------------------------------------------------------------------------
# The folders of the proof
# ----------------------------------------------------------------------------------------


def planned_files(todo: Mapping[int, Sequence[base.Block]]) -> frozenset[str]:
    """The files the plans of the section name inside the two folders, relative to the root —
    read from the plans, never written here."""
    import json

    named: set[str] = set()
    for blocks in todo.values():
        for block in blocks:
            for line in block.lines:
                if block.kind != "comando" or "--file" not in line:
                    continue
                sent = ROOT / line.split("--file", 1)[1].split()[0]
                for step in json.loads(sent.read_text(encoding="utf-8"))["steps"]:
                    path = str(step["arguments"].get("path", ""))
                    if any(path.startswith(f"{one}/") for one in FOLDERS):
                        named.add(path)
    return frozenset(named)


def strangers(root: Path, folder: str, planned: frozenset[str]) -> list[str]:
    """What the folder holds that is neither a file of the plans nor one of its subfolders."""
    found: list[str] = []
    here = root / folder
    for one in sorted(here.iterdir()):
        mine = f"{folder}/{one.name}"
        if one.name in SUBFOLDERS[folder] and one.is_dir() and not one.is_symlink():
            for inner in sorted(one.iterdir()):
                if f"{mine}/{inner.name}" in planned and inner.is_file() and not inner.is_symlink():
                    continue
                found.append(f"{mine}/{inner.name}")
            continue
        if mine in planned and one.is_file() and not one.is_symlink():
            continue
        found.append(mine)
    return found


def prepared(root: Path, report: base.Report, planned: frozenset[str]) -> str | None:
    """The two folders as step 1 wants them: what a proof before left — **the files the plans
    name** — removed one by one and said; anything else stops the proof before anything is
    touched. Then the folders and their subfolders, ``700``."""
    for folder in FOLDERS:
        here = root / folder
        if not os.path.lexists(here):
            continue
        if here.is_symlink() or not here.is_dir():
            return f"e {folder} non è una cartella: la prova non tocca niente, guardala tu"
        others = strangers(root, folder, planned)
        if others:
            return (
                f"e {folder}/ tiene {others}, che non sono file dei piani della prova: la prova "
                "non tocca niente, guardali tu"
            )
    for name in sorted(planned):
        if (root / name).is_file():
            (root / name).unlink()
            report.say(f"    tolto {name}, di una prova di prima")
    for folder in FOLDERS:
        (root / folder).mkdir(mode=files.FOLDER_MODE, parents=True, exist_ok=True)
        for sub in SUBFOLDERS[folder]:
            (root / folder / sub).mkdir(mode=files.FOLDER_MODE, exist_ok=True)
    report.say(f"    pronte: {', '.join(f'{one}/' for one in FOLDERS)}")
    return None


def cleaned(root: Path, folder: str, planned: frozenset[str]) -> list[str]:
    """``pulizia``: the folder taken away with its subfolders and the files of the plans — or,
    with anything else inside, nothing touched and what is there said."""
    here = root / folder
    if not os.path.lexists(here):
        return []
    if here.is_symlink() or not here.is_dir():
        return [f"{folder} non è una cartella: non la tocco"]
    others = strangers(root, folder, planned)
    if others:
        return [f"{folder}/ tiene {others}: non tocco niente"]
    shutil.rmtree(here)
    return []


# ----------------------------------------------------------------------------------------
# The kinds of this section
# ----------------------------------------------------------------------------------------


def a_fact(number: int, block: base.Block, proof: Proof) -> None:
    question = " ".join(block.lines)
    answer = proof.ask(f"[{number}] {question} ").strip()
    proof.report.say(f"[{number}] FATTO: {question}")
    proof.report.say(f"    la risposta: {answer or '(nessuna)'}")


def silent(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    (rule,) = block.lines
    events = proof.api.get(f"/audit?task_id={turn.task_id}")
    failures = silent_failures(events, rule)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la regola {rule}, nessuna domanda e nessun campanello")


def a_refusal(number: int, block: base.Block, proof: Proof) -> None:
    """``rifiuto``: the line run; on the screen its last line, the sentence of ELA — with the whole
    path it names —; in the file the command and its exit code only."""
    line, words = refusal_of(block)
    done = base.heard(line, base.run(line))
    printed = done.stdout + done.stderr
    print(f"    | {last_line(printed)}", flush=True)
    print(f"    {PYTHON_REMOVED}", flush=True)
    proof.report.say(f"    $ {line}")
    proof.report.say(
        f"    uscita {done.returncode}; l'ultima riga è sullo schermo, non in questo file"
    )
    failures = refusal_failures(done.returncode, printed, words)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"rifiutata all'avvio: «{words}»")


def a_cleaning(number: int, block: base.Block, proof: Proof, planned: frozenset[str]) -> None:
    (folder,) = block.lines
    failures = cleaned(proof.root, folder, planned)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"tolta {folder}/, con i soli file della prova")


def a_block(
    number: int,
    block: base.Block,
    turn: guided.Turn,
    proof: Proof,
    planned: frozenset[str] = frozenset(),
) -> None:
    kind = block.kind
    if kind in ("comando", "atteso", "schermo", "crea", "assente"):
        m15.a_block(number, block, turn, proof, lambda _: "")
    elif kind == "sì":
        guided.an_answer(number, block, turn, proof, yes=True)  # type: ignore[arg-type]
    elif kind == "fatto":
        a_fact(number, block, proof)
    elif kind == "muto":
        silent(number, block, turn, proof)
    elif kind == "rifiuto":
        a_refusal(number, block, proof)
    elif kind == "pulizia":
        a_cleaning(number, block, proof, planned)
    else:
        m14.a_block(number, block, turn, proof)  # type: ignore[arg-type]


def a_step(number: int, todo: Sequence[base.Block], proof: Proof, planned: frozenset[str]) -> None:
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    proof.current = number
    turn = guided.Turn()
    try:
        for block in todo:
            a_block(number, block, turn, proof, planned)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def diagnostics() -> Mapping[str, Any]:
    found: Mapping[str, Any] = base.Api().get("/diagnostics")
    return found


def open_files() -> Mapping[str, Any]:
    found: Mapping[str, Any] = diagnostics().get(BRANCH_FIELD) or {}
    return found


def preconditions(report: base.Report) -> bool:
    planned = planned_files(base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING)))
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: GET /diagnostics ha «{BRANCH_FIELD}»",
            lambda: the_branch(diagnostics()),
        ),
        ("la radice è la tua home", lambda: the_root_is_the_home(open_files(), Path.home())),
        (
            f"l'elenco ammette {' e '.join(f'{one}/' for one in FOLDERS)}, e non Library",
            lambda: the_list_admits(open_files()),
        ),
        ("il campanello è pronto", lambda: the_bell_rings(diagnostics())),
        (
            f"nessuna policy viva di {', '.join(CAPABILITIES)}",
            lambda: live_of_the_five(m14.policies_of(base.Api())),
        ),
        (
            "le due cartelle della prova, pronte: niente di una prova di prima",
            lambda: prepared(Path(str(open_files().get("root"))), report, planned),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.17-{datetime.now():%Y%m%d-%H%M%S}.txt"


def walked(
    report: base.Report,
    todo: Mapping[int, list[base.Block]],
    proof: Proof,
) -> None:
    planned = planned_files(todo)
    try:
        base.walk(report, todo, lambda number, its: a_step(number, its, proof, planned))
    except KeyboardInterrupt:
        report.say()
        report.stop(proof.current, "la prova è stata interrotta a metà")
    finally:
        report.say()
        report.say("—— dopo ——")
        m14.leftovers(proof)  # type: ignore[arg-type]


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.17, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {m14.private(str(out), Path.home())}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
            api = base.Api()
            proof = Proof(api, report, ask, root=Path(str(open_files().get("root"))))
            try:
                walked(report, todo, proof)
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {m14.private(str(out), Path.home())}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
