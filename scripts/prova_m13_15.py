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
  più voci per quel sito nel vault — fa il passo SALTATO, con la sua ragione (risposta 48).

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
import sys
import tempfile
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


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    **m14.READERS,
    "mano": a_hand_line,
    "voce": m14.the_words(ENTRY),
    "risultato": a_result_line,
    "nomi": a_names_line,
    "assente": m14.a_said,
    "ambigua": m14.the_words(AMBIGUOUS),
    "coperta": lambda line: _a_covering_line(line),
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


def masked(text: str, proof: Proof) -> str:
    """``text`` without the declared root, the home of whoever runs the proof, and the id of the
    entry (decision 26): a file's whole path and an id stay on the screen."""
    for one in sorted({str(proof.root), str(proof.root.resolve())}, key=len, reverse=True):
        if one not in ("", "."):
            text = text.replace(one, ROOT_WORD)
    text = m14.private(text, proof.home)
    if proof.entry:
        text = text.replace(proof.entry, ENTRY)
    return text


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


def a_command(line: str, turn: guided.Turn, proof: Proof) -> None:
    """One command: the file gets the line with the placeholder and the output masked."""
    report = proof.report
    report.say(f"    $ {masked(line, proof)}")
    sent = with_the_entry(line, proof)
    done = base.heard(sent, base.run(sent))
    printed = done.stdout + done.stderr
    turn.last += printed
    for one in printed.rstrip("\n").splitlines():
        report.say(f"    | {masked(one, proof)}")
    if guided.CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        turn.child_id = None
        report.say(f"    il task: {turn.task_id}")


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    turn.last = ""
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


def scope_admits(scope: str) -> str | None:
    from ela.permissions.scope import within_scope

    if within_scope([scope], f"{FOLDER}/su/da-caricare.txt"):
        return None
    return f"e lo scope dichiarato, {scope!r}, non ammette {FOLDER}/"


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


def a_creation(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``crea``, as M13.14's — through this script's commands, which mask the entry."""
    (line,) = block.lines
    line = m14.filled(line, turn, proof)  # type: ignore[arg-type]
    before = {str(one["id"]) for one in m14.live(m14.policies_of(proof.api))}
    commands([line], turn, proof)
    after = {str(one["id"]) for one in m14.live(m14.policies_of(proof.api))}
    if m14.NOT_CREATED not in turn.last or after != before:
        proof.report.failure(number, "l'anteprima ha creato una policy", masked(turn.last, proof))
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
