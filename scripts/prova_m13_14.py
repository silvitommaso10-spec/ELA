"""La prova a mano di M13.14: le policy sulle azioni HIGH.

La sezione 32 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m13_14.py               # contro l'ELA che gira
    uv run python scripts/prova_m13_14.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m14_6b.py`` (decisione 15
del prompt di M13.14): legge dalla sezione 32 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``; ne prende il controllo del
commit e dell'albero, il «FERMATO», ``LOOKS`` e ``SHOWS``; delle sezioni 27 e 30 prende i tipi che
gli servono e non uno di più — ``comando``, ``atteso``, ``occhio``, ``schermo``, ``no``, ``perché``,
``nessuna``, ``crea``, ``policy``, ``console``, ``file`` —, con le parole di questa sezione.
``tests/docs/test_prova_m13_14.py`` legge la sezione con lo stesso lettore e tiene allineati i due,
e cammina la sezione con questo script contro un'ELA vera.

I tipi, come li legge questa sezione:

* ``crea``: la riga del blocco **senza** ``--confirm`` — fuori da un terminale l'anteprima si
  stampa e non si crea niente, e lo script lo controlla —; poi «crei la policy?»; con un «s» la
  stessa riga con ``--confirm``, e la policy diventa ``<id della policy N>``, con N il passo; con
  un «n» la prova si ferma. **Le policy le crei tu**: lo script non ne crea nessuna senza il tuo sì;
* ``policy``: lo stato, gli usi, il tetto agli usi e quante azioni la policy dice, da
  ``GET /policies?all=true`` — «<id della policy 2> LIVE usi 2 senza limite azioni 2»;
* ``perché``: la riga ``why I ask`` della domanda del task del passo dice ciò che il blocco dice;
* ``no``: il no di Tommaso alla domanda del task, dopo averla vista;
* ``nessuna``: nessuna policy viva — una nata dove non doveva è revocata, e il passo è FALLITO;
* ``console``: ti chiede di aprire la vista delle policy della console sul Mac;
* ``file``: un file sotto la radice dichiarata — c'è, con i suoi byte e i permessi ``600`` —, o è
  ``assente``;
* ``schermo``: l'uscita dei suoi comandi sullo schermo soltanto — l'anteprima con la cartella
  intera, che è dentro la tua home.

**Il percorso della tua home non entra nel file della prova**: ciò che lo script scrive dice ``~``
al suo posto; intero lo mostra il blocco ``schermo``, sullo schermo soltanto.

**Se la prova si ferma a metà** — un FALLITO che la chiude, un FERMATO, un'interruzione —, lo script
revoca prima di uscire le policy che la prova ha creato e sono ancora vive, e lo dice: una prova
lasciata a metà non lascia una policy ``HIGH`` viva. E toglie i due link che ha messo nella cartella
della prova. **Lo script non tocca il ``.env``, il database né ``ela serve``**: scrive solo dentro
``ELA/prova-m13.14/``, e legge ELA attraverso l'API e la CLI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m13_13 as files  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 32. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "schermo",
    "crea",
    "policy",
    "perché",
    "no",
    "nessuna",
    "console",
    "file",
)
LOOKS: Final[Mapping[str, str]] = {
    "occhio": "una domanda all'occhio di Tommaso, su ciò che ha davanti",
}
"""The kinds of block that ask Tommaso's eye, each with its reason (M13.10b): before each of them,
in its step, ``tests/docs/test_prova_eyes.py`` wants a block of a kind of :data:`SHOWS`."""
SHOWS: Final[Mapping[str, str]] = {
    "schermo": "stampa sullo schermo, e non nel file, l'uscita dei suoi comandi: l'anteprima",
    "console": "ti fa aprire la vista delle policy della console",
}
"""The kinds of block that put in front of Tommaso what a question to his eye then asks, each with
its reason (M13.10b). ``crea`` prints the preview too, but in the file without the home: what an
eye of this section asks about — the folder as the disk names it — is what ``schermo`` shows."""
ID = base.ID
APPROVAL_ID: Final = guided.APPROVAL_ID
POLICY: Final = re.compile(r"<id della policy (\d+)>")
"""The short id of the policy the ``crea`` of step N created."""
PLACEHOLDERS: Final = (ID, APPROVAL_ID)
"""The fixed placeholders; ``<id della policy N>`` is :data:`POLICY`."""
FOLDER: Final = "ELA/prova-m13.14"
"""The folder of the proof under the declared root: the only place the script writes in."""
SUBFOLDERS: Final = ("uno", "due", "tre")
LINK_OUT: Final = "uno/fuori"
"""A link inside ``uno/`` that leads to ``tre/``: a written path inside the policy, a resolved one
outside it (step 3)."""
LINK_TREE: Final = "sorgente"
"""A link inside the folder of the proof that leads to ELA's own tree (step 6): no policy is born
on it."""
SITES: Final = ("httpbin.org", "testpages.eviltester.com")
"""The site of the covered gestures, and the one outside the policies (section 30's two)."""
CAPABILITIES: Final = ("fs.write", "browser.act", "browser.act_as_you")
"""The three ``HIGH`` M13.14 opens to the policies: no live one of them before the proof."""
PREVIEW_FIELD: Final = "resolved"
"""A field the preview of the API has since M13.14: what says the Core runs the branch's code."""
NONE_LIVE: Final = "nessuna policy viva"
CONSOLE_PAGE: Final = "/console/policies"
CONFIRM: Final = " --confirm"
CREATE_LINE: Final = "uv run ela policy create "
DENY_LINE: Final = "uv run ela task deny "
CREATED: Final = re.compile(r"created policy ([0-9a-f]{8})")
NOT_CREATED: Final = "not created"
STATES: Final = ("LIVE", "REVOKED", "EXPIRED", "EXHAUSTED")
POLICY_LINE: Final = re.compile(
    r"^<id della policy (?P<step>\d+)> (?P<state>[A-Z]+) usi (?P<uses>\d+) "
    r"(?:di (?P<most>\d+)|senza limite) azioni (?P<actions>\d+)$"
)
HOME_WORD: Final = "~"
SAID_NO: Final = "hai risposto no: senza la policy i passi che restano non hanno niente da misurare"
NO_POLICY: Final = "senza la policy del passo i passi che restano non hanno niente da misurare"

Report = base.Report


@dataclass
class Proof:
    api: base.Api
    report: base.Report
    ask: base.Ask
    root: Path = Path()
    """The declared root, ``ELA_FS_ROOT``: where the files of the proof are."""
    ids: dict[int, str] = field(default_factory=dict)
    """The task of each step: what ``<id del passo N>`` stands for."""
    policies: dict[int, tuple[str, str]] = field(default_factory=dict)
    """The policy each ``crea`` created, by its step: its id and its short id."""
    home: Path = field(default_factory=Path.home)
    """The home of whoever runs the proof: never written in the file."""
    current: int = 1
    """The step being walked: where an interruption stopped the proof."""


# ----------------------------------------------------------------------------------------
# The vocabulary of every kind: what the script can read of a line
# ----------------------------------------------------------------------------------------


def an_ela_line(line: str) -> str:
    if not line.startswith(base.ELA):
        raise ValueError(f"{line!r} is not a command of ELA: it starts with «{base.ELA}»")
    return line


def a_creation_line(line: str) -> str:
    if not line.startswith(CREATE_LINE) or CONFIRM.strip() in line.split():
        raise ValueError(f"{line!r} is not a creation: «{CREATE_LINE}…» without {CONFIRM.strip()}")
    return line


def a_denial_line(line: str) -> str:
    if not line.startswith(DENY_LINE) or APPROVAL_ID not in line:
        raise ValueError(f"{line!r} is not a no: «{DENY_LINE}<id> --approval {APPROVAL_ID}»")
    return line


@dataclass(frozen=True)
class Wanted:
    """What a line of ``policy`` asks of a policy."""

    step: int
    state: str
    uses: int
    most: int | None
    actions: int


def a_policy_line(line: str) -> Wanted:
    """«<id della policy N> STATE usi U di M azioni A», or «… usi U senza limite azioni A»."""
    found = POLICY_LINE.match(line)
    if found is None or found["state"] not in STATES:
        raise ValueError(
            f"{line!r} is not in the vocabulary of policy: «<id della policy N> STATE usi U "
            f"(di M | senza limite) azioni A», STATE one of {list(STATES)}"
        )
    most = found["most"]
    return Wanted(
        int(found["step"]),
        found["state"],
        int(found["uses"]),
        None if most is None else int(most),
        int(found["actions"]),
    )


def a_said(line: str) -> str:
    if not line.strip():
        raise ValueError("an empty line says nothing")
    return line


def the_words(wanted: str) -> Callable[[str], str]:
    def read(line: str) -> str:
        if line != wanted:
            raise ValueError(f"{line!r} is not «{wanted}»")
        return line

    return read


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    "comando": an_ela_line,
    "atteso": a_said,
    "occhio": a_said,
    "schermo": an_ela_line,
    "crea": a_creation_line,
    "policy": a_policy_line,
    "perché": a_said,
    "no": a_denial_line,
    "nessuna": the_words(NONE_LIVE),
    "console": the_words(CONSOLE_PAGE),
    "file": files.a_file_line,
}
"""The reader of each kind: what the script reads of a line, and the guide's error when it cannot.
``tests/docs/test_prova_m13_14.py`` reads every line of the section with these, and the script
reads them all before step 1."""


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
    """Every line of the section a reader of its kind cannot read: said before step 1."""
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
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def private(text: str, home: Path) -> str:
    """``text`` without the home of whoever runs the proof: ``~`` in its place."""
    for one in {str(home), str(home.resolve())}:
        text = text.replace(one, HOME_WORD)
    return text


def policy_failures(wanted: Wanted, found: Mapping[str, Any] | None) -> list[str]:
    """What ``policy`` finds wrong with a policy of ``GET /policies?all=true``."""
    if found is None:
        return [f"la policy del passo {wanted.step} non è fra quelle di ela policy list --all"]
    failures: list[str] = []
    if found.get("state") != wanted.state:
        failures.append(f"la policy è {found.get('state')}, non {wanted.state}")
    if found.get("uses") != wanted.uses:
        failures.append(f"la policy ha {found.get('uses')} usi, non {wanted.uses}")
    if found.get("max_uses") != wanted.most:
        most = found.get("max_uses")
        failures.append(
            f"il tetto agli usi è {'nessuno' if most is None else most}, non "
            f"{'nessuno' if wanted.most is None else wanted.most}"
        )
    actions = len(found.get("recent") or ())
    if actions != wanted.actions:
        failures.append(f"la policy dice {actions} azioni, non {wanted.actions}")
    return failures


def why_failures(expected: str, why: Sequence[str]) -> list[str]:
    """What ``perché`` finds wrong: the words of the block are a run of whole words of one of the
    lines ``why I ask`` of the question."""
    if not why:
        return ["la domanda non ha la riga why I ask"]
    if any(base.contains(line.split(), expected.split()) for line in why):
        return []
    return [f"nessuna riga dice «{expected}»: {list(why)}"]


def live(policies: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [one for one in policies if one.get("state") == "LIVE"]


def live_of_the_three(policies: Sequence[Mapping[str, Any]]) -> str | None:
    """Why the proof cannot start: a live policy of one of :data:`CAPABILITIES`, named — or
    ``None``. It would change what the steps measure."""
    found = [one for one in live(policies) if one.get("capability") in CAPABILITIES]
    if not found:
        return None
    named = ", ".join(f"{one.get('short')} di {one.get('capability')}" for one in found)
    return f"e c'è una policy viva ({named}): revocala con uv run ela policy revoke"


def created_short(printed: str) -> str | None:
    found = CREATED.search(printed)
    return None if found is None else found.group(1)


def scope_admits(scope: str) -> str | None:
    """Why the declared scope does not admit the folder of the proof, or ``None``."""
    from ela.permissions.scope import within_scope

    if within_scope([scope], f"{FOLDER}/uno/prova.md"):
        return None
    return f"e lo scope dichiarato, {scope!r}, non ammette {FOLDER}/"


# ----------------------------------------------------------------------------------------
# The folder of the proof: what a proof before left, and what this one needs
# ----------------------------------------------------------------------------------------


def planned_files(todo: Mapping[int, Sequence[base.Block]]) -> dict[str, frozenset[str]]:
    """The files the plans of the section write inside the folder of the proof, by subfolder —
    **read from the plans, never written here**."""
    named: dict[str, set[str]] = {one: set() for one in SUBFOLDERS}
    for blocks in todo.values():
        for block in blocks:
            for line in block.lines:
                if block.kind != "comando" or "--file" not in line:
                    continue
                sent = ROOT / line.split("--file", 1)[1].split()[0]
                plan = json.loads(sent.read_text(encoding="utf-8"))
                for step in plan["steps"]:
                    path = str(step["arguments"].get("path", ""))
                    parts = path.removeprefix(f"{FOLDER}/").split("/")
                    if path.startswith(f"{FOLDER}/") and len(parts) == 2 and parts[0] in named:
                        named[parts[0]].add(parts[1])
    return {key: frozenset(value) for key, value in named.items()}


def strangers(folder: Path, planned: Mapping[str, frozenset[str]]) -> list[str]:
    """What the folder of the proof holds that is neither a file of its plans nor its own two
    links nor its three subfolders: Tommaso's to look at."""
    found: list[str] = []
    for one in sorted(folder.iterdir()):
        if one.name == LINK_TREE and one.is_symlink():
            continue
        if one.name in SUBFOLDERS and one.is_dir() and not one.is_symlink():
            for inner in sorted(one.iterdir()):
                mine = f"{one.name}/{inner.name}"
                if mine == LINK_OUT and inner.is_symlink():
                    continue
                if inner.name in planned[one.name] and inner.is_file() and not inner.is_symlink():
                    continue
                found.append(mine)
            continue
        found.append(one.name)
    return found


def prepared(root: Path, report: base.Report, planned: Mapping[str, frozenset[str]]) -> str | None:
    """The folder of the proof as step 1 wants it: what a proof before left — **the files the
    plans name**, and the script's own links — removed one by one, and each said; anything else
    stops the proof before anything is touched. Then the three subfolders, ``700``, and the two
    links: ``uno/fuori`` to ``tre/``, ``sorgente`` to ELA's tree."""
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
        for sub, names in planned.items():
            for name in sorted(names):
                target = folder / sub / name
                if target.is_file():
                    target.unlink()
                    report.say(f"    tolto {FOLDER}/{sub}/{name}, di una prova di prima")
    unlinked(root, report)
    for sub in SUBFOLDERS:
        (folder / sub).mkdir(mode=files.FOLDER_MODE, parents=True, exist_ok=True)
    (folder / LINK_OUT).symlink_to(folder / "tre", target_is_directory=True)
    (folder / LINK_TREE).symlink_to(ROOT, target_is_directory=True)
    made = ", ".join(f"{one}/" for one in SUBFOLDERS)
    report.say(f"    {FOLDER}/: {made}, e i due link della prova")
    return None


def unlinked(root: Path, report: base.Report) -> None:
    """The two links of the proof, taken away when they are there: they are the script's own."""
    for one in (LINK_OUT, LINK_TREE):
        link = root / FOLDER / one
        if link.is_symlink():
            link.unlink()
            report.say(f"    tolto il link {FOLDER}/{one}")


# ----------------------------------------------------------------------------------------
# One step
# ----------------------------------------------------------------------------------------


def filled(text: str, turn: guided.Turn, proof: Proof) -> str:
    text = guided.filled(text, turn, proof)  # type: ignore[arg-type]
    return POLICY.sub(
        lambda found: proof.policies.get(int(found.group(1)), ("", found.group(0)))[1], text
    )


def a_command(line: str, turn: guided.Turn, proof: Proof) -> None:
    """One command: what it printed is ``turn.last``; what the file and the screen get has no
    home in it."""
    report = proof.report
    report.say(f"    $ {line}")
    done = base.heard(line, base.run(line))
    printed = done.stdout + done.stderr
    turn.last += printed
    for one in printed.rstrip("\n").splitlines():
        report.say(f"    | {private(one, proof.home)}")
    if guided.CREATE in f" {line} ":
        turn.task_id = base.created_id(done.stdout)
        turn.child_id = None
        report.say(f"    il task: {turn.task_id}")


def commands(lines: Sequence[str], turn: guided.Turn, proof: Proof) -> None:
    turn.last = ""
    for line in lines:
        a_command(filled(line, turn, proof), turn, proof)


def policies_of(api: base.Api, *, everything: bool = False) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = api.get("/policies?all=true" if everything else "/policies")[
        "policies"
    ]
    return found


def on_the_screen(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``schermo``: what the eye has to look at, put in front of it — on the screen alone, whole.
    The file says which command was shown."""
    for line in block.lines:
        asked = filled(line, turn, proof)
        done = base.heard(asked, base.run(asked))
        print(f"    $ {asked}", flush=True)
        for one in (done.stdout + done.stderr).rstrip("\n").splitlines():
            print(f"    | {one}", flush=True)
        proof.report.say(f"    $ {asked} — l'uscita è sullo schermo, non in questo file")


def a_creation(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``crea``: the preview, out of a terminal and without ``--confirm``, creates nothing; Tommaso
    says yes; the same line with ``--confirm`` creates the policy of the step."""
    (line,) = block.lines
    line = filled(line, turn, proof)
    before = {str(one["id"]) for one in live(policies_of(proof.api))}
    commands([line], turn, proof)
    after = {str(one["id"]) for one in live(policies_of(proof.api))}
    if NOT_CREATED not in turn.last or after != before:
        printed = private(turn.last, proof.home)
        proof.report.failure(number, "l'anteprima ha creato una policy", printed)
        raise base.Stop(NO_POLICY)
    if not base.yes_or_no(proof.ask, f"[{number}] Crei la policy? (s/n) "):
        raise base.Stop(SAID_NO)
    commands([line + CONFIRM], turn, proof)
    short = created_short(turn.last)
    mine = [one for one in live(policies_of(proof.api)) if one.get("short") == short]
    if short is None or len(mine) != 1:
        proof.report.failure(number, "la policy non è nata", private(turn.last, proof.home))
        raise base.Stop(NO_POLICY)
    proof.policies[number] = (str(mine[0]["id"]), short)
    proof.report.passed(number, f"la policy {short}, creata dopo l'anteprima")


def a_policy(number: int, block: base.Block, proof: Proof) -> None:
    for line in block.lines:
        wanted = a_policy_line(line)
        mine = proof.policies.get(wanted.step)
        if mine is None:
            proof.report.failure(number, f"la prova non ha la policy del passo {wanted.step}")
            continue
        found = next(
            (one for one in policies_of(proof.api, everything=True) if str(one["id"]) == mine[0]),
            None,
        )
        if found is not None:
            most = found.get("max_uses")
            proof.report.say(
                f"    | {found.get('short')} {found.get('state')}, {found.get('uses')} usi, "
                f"{'senza limite' if most is None else f'al più {most}'}, "
                f"{len(found.get('recent') or ())} azioni"
            )
        failures = policy_failures(wanted, found)
        if failures:
            proof.report.failure(number, "; ".join(failures))
        else:
            proof.report.passed(number, f"la policy {mine[1]}: {POLICY.sub(mine[1], line)}")


def a_why(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    (line,) = block.lines
    question = guided.question_of(proof.api, turn.task_id)
    if question is None:
        guided.no_question(number, turn.task_id, None, proof)  # type: ignore[arg-type]
    assert question is not None
    why = list(question.get("why") or [])
    for one in why:
        proof.report.say(f"    | why I ask: {one}")
    failures = why_failures(filled(line, turn, proof), why)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la domanda dice perché: {filled(line, turn, proof)}")


def a_none(number: int, proof: Proof) -> None:
    """``nessuna``: no live policy; one that was born is revoked, and the step FAILS."""
    born = live(policies_of(proof.api))
    for one in born:
        proof.api.post(f"/policies/{one['id']}/revoke")
        proof.report.say(f"    revocata la policy {one.get('short')}, nata dove non doveva")
    if born:
        proof.report.failure(number, f"{len(born)} policy vive: un rifiuto ha creato")
    else:
        proof.report.passed(number, NONE_LIVE)


def a_console(number: int, block: base.Block, proof: Proof) -> None:
    (page,) = block.lines
    text = f"Apri {page} sul Mac, e guarda le policy. Fatto?"
    if base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "):
        proof.report.passed(number, f"la vista {page} è aperta")
    else:
        proof.report.looked(number, text, False)


def a_file(number: int, block: base.Block, proof: Proof) -> None:
    failures = [
        failure
        for line in block.lines
        for failure in files.file_failures(files.a_file_line(line), proof.root)
    ]
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"sul disco: {'; '.join(block.lines)}")


def a_block(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    report = proof.report
    kind = block.kind
    if kind == "comando":
        commands(block.lines, turn, proof)
    elif kind == "atteso":
        absent = base.missing([filled(line, turn, proof) for line in block.lines], turn.last)
        if absent:
            report.failure(number, f"mancano {absent}", private(turn.last, proof.home))
        else:
            report.passed(number, "l'uscita è quella attesa")
    elif kind == "occhio":
        text = filled(block.body, turn, proof)
        report.looked(number, text, base.yes_or_no(proof.ask, f"[{number}] {text} (s/n) "))
    elif kind == "schermo":
        on_the_screen(number, block, turn, proof)
    elif kind == "crea":
        a_creation(number, block, turn, proof)
    elif kind == "policy":
        a_policy(number, block, proof)
    elif kind == "perché":
        a_why(number, block, turn, proof)
    elif kind == "no":
        guided.an_answer(number, block, turn, proof, yes=False)  # type: ignore[arg-type]
    elif kind == "nessuna":
        a_none(number, proof)
    elif kind == "console":
        a_console(number, block, proof)
    elif kind == "file":
        a_file(number, block, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(number: int, todo: Sequence[base.Block], proof: Proof) -> None:
    report = proof.report
    report.say()
    report.say(f"—— passo {number} ——")
    proof.current = number
    turn = guided.Turn()
    try:
        for block in todo:
            a_block(number, block, turn, proof)
    finally:
        if turn.task_id is not None:
            proof.ids[number] = turn.task_id


# ----------------------------------------------------------------------------------------
# After: what a proof stopped midway leaves is taken back
# ----------------------------------------------------------------------------------------


def leftovers(proof: Proof) -> None:
    """The policies this proof created that are still live, revoked, and each said: a proof left
    midway leaves no ``HIGH`` policy alive. If ELA does not answer, the line says how to do it."""
    if not proof.policies:
        return
    try:
        everything = {str(one["id"]): one for one in policies_of(proof.api, everything=True)}
    except Exception as error:  # noqa: BLE001 — what failed is said, with what to do
        for _, short in proof.policies.values():
            proof.report.say(
                f"    non so se la policy {short} è viva ({type(error).__name__}): revocala tu, "
                f"uv run ela policy revoke {short}"
            )
        return
    for number, (policy_id, short) in sorted(proof.policies.items()):
        if everything.get(policy_id, {}).get("state") != "LIVE":
            continue
        try:
            proof.api.post(f"/policies/{policy_id}/revoke")
        except Exception as error:  # noqa: BLE001 — as above
            proof.report.say(
                f"    la policy {short} del passo {number} è viva, e non sono riuscito a revocarla "
                f"({type(error).__name__}): revocala tu, uv run ela policy revoke {short}"
            )
            continue
        proof.report.say(
            f"    revocata la policy {short} del passo {number}: la prova l'aveva creata, ed era "
            "ancora viva"
        )


# ----------------------------------------------------------------------------------------
# Step 1, and the whole
# ----------------------------------------------------------------------------------------


def declared_root() -> tuple[Path, str]:
    from ela.composition.settings import FilesystemSettings

    declared = FilesystemSettings()
    return declared.root, declared.scope


def declared_sites() -> Sequence[str]:
    from ela.composition.settings import BrowserSettings

    return tuple(BrowserSettings().sites)


def preconditions(report: base.Report) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO)."""
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
            lambda: scope_admits(declared_root()[1]),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(all(site in declared_sites() for site in SITES)),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            accounts.profile_ready,
        ),
        (
            f"nessuna policy viva di {', '.join(CAPABILITIES)}",
            lambda: live_of_the_three(policies_of(base.Api())),
        ),
        (
            f"la cartella della prova, {FOLDER}/, pronta: niente di una prova di prima, le tre "
            "cartelle e i due link",
            lambda: prepared(declared_root()[0], report, planned),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.14-{datetime.now():%Y%m%d-%H%M%S}.txt"


def walked(report: base.Report, todo: Mapping[int, list[base.Block]], proof: Proof) -> None:
    """Every step, and then — always — what a proof stopped midway leaves: its live policies
    revoked, its two links taken away. An interruption is written, never a traceback."""
    try:
        base.walk(report, todo, lambda number, its: a_step(number, its, proof))
    except KeyboardInterrupt:
        report.say()
        report.stop(proof.current, "la prova è stata interrotta a metà")
    finally:
        report.say()
        report.say("—— dopo ——")
        leftovers(proof)
        unlinked(proof.root, report)


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.14, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {private(str(out), Path.home())}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
            api = base.Api()
            proof = Proof(api, report, ask, root=declared_root()[0])
            try:
                walked(report, todo, proof)
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {private(str(out), Path.home())}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
