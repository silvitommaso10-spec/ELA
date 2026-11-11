"""La prova a mano di M13.13: i file dal browser.

La sezione 30 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m13_13.py               # contro l'ELA che gira
    uv run python scripts/prova_m13_13.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m13_10.py`` (decisione 10
della SPEC di M13.13): legge dalla sezione 30 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``, e della sezione 29 usa
i tipi che gli servono e non uno di più — ``comando``, ``atteso``, ``occhio``, ``sì``,
``schermo`` —, il controllo del commit e dell'albero, e il «FERMATO» con chi ha risposto.
``tests/docs/test_prova_m13_13.py`` legge la sezione con lo stesso lettore e tiene allineati i due.

I tipi suoi, che la sezione spiega:

* ``piano``: il piano che il Planner ha scritto dalla frase del passo — dell'autore ``MODEL``,
  con gli step del blocco e nessun altro: per ciascuno la capability, il sito, il percorso della
  pagina e il file —; scritto nel file, step per step. Un piano diverso chiude il passo: il resto
  misurerebbe un'altra cosa;
* ``domanda``: la domanda che il task aspetta, letta dall'API e confrontata riga per riga — la
  capability, il file sotto la radice dichiarata, ciò che gli succede, il sito, e per un file che
  parte **la dimensione e l'impronta del file com'è sul disco in quell'istante** —; o ``nessuna``;
* ``file``: un file sotto la radice dichiarata — c'è, con i suoi byte e i permessi ``600``; o è
  ``assente``; o la cartella della prova tiene ``solo`` i nomi del blocco;
* ``scrive``: lo script scrive un file di testo dentro la cartella della prova, e in nessun altro
  posto.

**Il percorso intero di un file non entra nel file della prova**: è dentro la home di chi la fa.
Lo script lo scrive com'è nel piano, sotto la radice; intero lo mostra il blocco ``schermo``, sullo
schermo soltanto.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m13_10 as steps  # noqa: E402 — the same
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

from ela.executive.planner import PlanningOutcome  # noqa: E402
from ela.executive.runner import RunOutcome  # noqa: E402
from ela.permissions.capabilities import (  # noqa: E402
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
    SITE_PATTERN,
)
from ela.permissions.scope import within_scope  # noqa: E402
from ela.tools.browser_files import (  # noqa: E402
    CREATES_BY_DOWNLOAD,
    LEAVES,
    OVERWRITES_BY_DOWNLOAD,
)

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 30. "
KINDS: Final = (
    "comando",
    "atteso",
    "occhio",
    "sì",
    "schermo",
    "piano",
    "domanda",
    "file",
    "scrive",
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
its reason (M13.10b). ``sì`` prints the question in the file too, but without the whole path of
its file: what an eye of this section asks about is what ``schermo`` shows."""
ID = base.ID
APPROVAL_ID: Final = guided.APPROVAL_ID
CHILD: Final = guided.CHILD
PLACEHOLDERS: Final = (ID, APPROVAL_ID, CHILD)
FILE_CAPABILITIES: Final = (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
)
"""The four capabilities of M13.13, as the catalogue names them: the vocabulary of ``piano`` and of
``domanda``."""
SITES: Final = ("httpbin.org", "testpages.eviltester.com")
"""The site of the downloads, and the one Tommaso chose for the uploads (answer 22 of the review
of M13.13's SPEC)."""
FOLDER: Final = "ELA/prova-m13.13"
"""The folder of the proof under the declared root: the only place the script writes in, and the
only one it empties before it begins."""
OUTSIDE: Final = "fuori-dallo-scope/prova-m13.13.bin"
"""The file of step 4, under the root and outside the scope. ``ELA_FS_SCOPE`` is **one** path, and
what it admits begins with its segments: a scope that admits :data:`FOLDER` begins with ``ELA``,
and cannot admit this."""
QUESTION_FIELD: Final = "digest"
"""A field the question of the API has since M13.13: what says the Core runs the branch's code."""
MODEL: Final = planning.MODEL
CURRENCY: Final = planning.CURRENCY
NOBODY: Final = accounts.NOBODY
SITE: Final = re.compile(SITE_PATTERN)
"""A site as the catalogue's schema reads one: a host name and nothing else."""
ABSENT: Final = "assente"
ONLY: Final = "solo"
FILE_MODE: Final = 0o600
FOLDER_MODE: Final = 0o700
DOES: Final = (CREATES_BY_DOWNLOAD, OVERWRITES_BY_DOWNLOAD, LEAVES)
"""What a question says happens to its file, in the words of the tools: the vocabulary of the
``fa`` line of ``domanda``. A sentence the source changes makes the guide's line unreadable, and
the test of the section says so."""
OUTCOME_WORDS: Final = frozenset(
    outcome.value for outcomes in (RunOutcome, PlanningOutcome) for outcome in outcomes
)
"""What the row ``outcome`` may say in this section: how a run stopped, and — at step 2 — where a
planning stands."""
NOT_PLANNED: Final = "il piano non è quello della frase: il resto del passo misurerebbe altro"
NO_PLANNING: Final = "il task non ha un task di pianificazione: senza, il sì non ha una domanda"

Report = base.Report


@dataclass
class Proof(accounts.Proof):
    root: Path = Path()
    """The declared root, ``ELA_FS_ROOT``: where the files of the proof are, read from the same
    configuration ELA reads."""


# ----------------------------------------------------------------------------------------
# The vocabulary of every kind: what the script can read of a line
# ----------------------------------------------------------------------------------------


def relative(path: str) -> str:
    """A path as a plan writes it: relative, with no step back and no empty part."""
    parts = path.split("/")
    if path.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"{path!r} is not a path relative to the declared root")
    return path


def inside_the_folder(path: str) -> str:
    if not relative(path).startswith(f"{FOLDER}/"):
        raise ValueError(f"{path!r} is not inside the folder of the proof, {FOLDER}/")
    return path


def an_expected(line: str) -> str:
    """A line of ``atteso``: a row of what a command prints, two words — the name of the row and
    its value —; an ``outcome`` is one a run or a planning has."""
    words = line.split()
    if len(words) != 2 or (words[0] == "outcome" and words[1] not in OUTCOME_WORDS):
        raise ValueError(f"{line!r} is not in the vocabulary of atteso: «row value»")
    return line


@dataclass(frozen=True)
class Planned:
    """One step ``piano`` wants: the capability, the site, the path of the page, the file."""

    capability: str
    site: str
    path: str
    file: str


def a_planned(line: str) -> Planned:
    """A line of ``piano``: «capability site /path file»."""
    words = line.split()
    if len(words) != 4:
        raise ValueError(
            f"{line!r} is not in the vocabulary of piano: «capability site /path file»"
        )
    capability, site, path, file = words
    if capability not in FILE_CAPABILITIES:
        raise ValueError(f"{capability!r} is not one of {list(FILE_CAPABILITIES)}")
    if not SITE.fullmatch(site) or not path.startswith("/"):
        raise ValueError(f"{line!r} names no site, or no path of a page")
    return Planned(capability, site, path, relative(file))


QUESTION_WORDS: Final = ("capability", "file", "fa", "sito", "impronta")


def a_question_line(line: str) -> tuple[str, str]:
    """A line of ``domanda``: ``nessuna``, or a word of :data:`QUESTION_WORDS` and its value."""
    if line == NOBODY:
        return NOBODY, ""
    word, _, value = line.partition(" ")
    value = value.strip()
    if word not in QUESTION_WORDS or not value:
        raise ValueError(
            f"{line!r} is not in the vocabulary of domanda: {NOBODY!r}, or one of "
            f"{list(QUESTION_WORDS)} with its value"
        )
    if word == "capability" and value not in FILE_CAPABILITIES:
        raise ValueError(f"{value!r} is not one of {list(FILE_CAPABILITIES)}")
    if word in ("file", "impronta"):
        relative(value)
    if word == "fa" and value not in DOES:
        raise ValueError(f"{value!r} is not a sentence a tool of the files says: {list(DOES)}")
    if word == "sito" and not SITE.fullmatch(value):
        raise ValueError(f"{value!r} is not a site")
    return word, value


@dataclass(frozen=True)
class Looked:
    """What a line of ``file`` asks of the disk."""

    path: str
    size: int | None = None
    """The bytes a file that is there must have; ``None`` for the other two forms."""
    only: tuple[str, ...] | None = None
    """The names a folder must hold, and no other; ``None`` for a file."""


def a_file_line(line: str) -> Looked:
    """A line of ``file``: «path bytes 600», «path assente», or «folder/ solo name…»."""
    words = line.split()
    if len(words) >= 3 and words[0].endswith("/") and words[1] == ONLY:
        return Looked(relative(words[0].rstrip("/")), only=tuple(words[2:]))
    if len(words) == 2 and words[1] == ABSENT:
        return Looked(relative(words[0]))
    if len(words) == 3 and words[1].isdigit() and words[2] == f"{FILE_MODE:o}":
        return Looked(relative(words[0]), size=int(words[1]))
    raise ValueError(
        f"{line!r} is not in the vocabulary of file: «path bytes {FILE_MODE:o}», "
        f"«path {ABSENT}», or «folder/ {ONLY} name…»"
    )


def a_writing(line: str) -> tuple[str, str]:
    """A line of ``scrive``: a file inside the folder of the proof, and the text it gets."""
    path, _, text = line.partition(" ")
    if not text.strip():
        raise ValueError(f"{line!r} is not in the vocabulary of scrive: «path text»")
    return inside_the_folder(path), text.strip()


READERS: Final[Mapping[str, Callable[[str], object]]] = {
    "comando": steps.a_command,
    "atteso": an_expected,
    "occhio": steps.a_question,
    "sì": steps.an_answer_line,
    "schermo": steps.a_command,
    "piano": a_planned,
    "domanda": a_question_line,
    "file": a_file_line,
    "scrive": a_writing,
}
"""The reader of each kind: what the script reads of a line, and the guide's error when it cannot.
``tests/docs/test_prova_m13_13.py`` reads every line of the section with these, and the script
reads them all before step 1."""


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


# ----------------------------------------------------------------------------------------
# The comparisons: pure, so that each has its negative case in the suite
# ----------------------------------------------------------------------------------------


def under(root: Path, target: object) -> str:
    """A resolved path as the plan wrote it, under the declared root — never whole: it is inside
    the home of whoever runs the proof."""
    try:
        return Path(str(target)).relative_to(root.resolve()).as_posix()
    except ValueError:
        return "un percorso fuori dalla radice dichiarata"


def measured(path: Path) -> tuple[int, str]:
    """The size and the sha256 of a file as it is on the disk now."""
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def plan_failures(task: Mapping[str, Any], wanted: Sequence[Planned]) -> list[str]:
    """What ``piano`` finds wrong with the plan of ``task``, one sentence each; ``[]`` if none."""
    failures: list[str] = []
    if task.get("state") != "QUEUED":
        failures.append(f"il task è {task.get('state')}, non QUEUED")
    author = task.get("plan_author") or {}
    if author.get("by") != "MODEL" or not author.get("result_id"):
        failures.append(f"l'autore del piano è {author.get('by')}, non MODEL con un risultato")
    elif author.get("model") != MODEL:
        failures.append(f"il modello dell'autore è {author.get('model')!r}, non {MODEL!r}")
    written: Sequence[Mapping[str, Any]] = task.get("steps") or []
    if len(written) != len(wanted):
        failures.append(f"il piano ha {len(written)} step, non {len(wanted)}")
        return failures
    for index, (step, want) in enumerate(zip(written, wanted, strict=True), start=1):
        arguments: Mapping[str, Any] = step.get("arguments") or {}
        found = (
            list(step.get("required_capabilities") or []),
            arguments.get("site"),
            arguments.get("path"),
            arguments.get("file"),
        )
        if found != ([want.capability], want.site, want.path, want.file):
            failures.append(
                f"lo step {index} è {found[0]} su {found[1]}{found[2]} verso {found[3]}, non "
                f"{want.capability} su {want.site}{want.path} verso {want.file}"
            )
    return failures


def asked_failures(
    lines: Sequence[str], question: Mapping[str, Any] | None, root: Path
) -> list[str]:
    """What ``domanda`` finds wrong with the question a task waits with, line by line; the
    ``nessuna`` form is :func:`prova_m13_9.question_failures`'s."""
    if question is None:
        return ["il task non ha una domanda in attesa"]
    failures: list[str] = []
    for line in lines:
        word, value = a_question_line(line)
        if word == "capability" and question.get("capability_id") != value:
            failures.append(f"la domanda è di {question.get('capability_id')}, non di {value}")
        elif word == "file" and under(root, question.get("target")) != value:
            failures.append(f"la domanda nomina {under(root, question.get('target'))}, non {value}")
        elif word == "fa" and question.get("does") != value:
            failures.append(f"del file la domanda dice «{question.get('does')}», non «{value}»")
        elif word == "sito" and question.get("site") != value:
            failures.append(f"la domanda nomina il sito {question.get('site')}, non {value}")
        elif word == "impronta":
            now = measured(root / value)
            named = (question.get("size"), question.get("digest"))
            if named != now:
                failures.append(
                    f"la domanda dice {named[0]} byte e l'impronta {named[1]}; il file sul disco "
                    f"ne ha {now[0]}, con l'impronta {now[1]}"
                )
    return failures


def file_failures(looked: Looked, root: Path) -> list[str]:
    """What ``file`` finds wrong on the disk, under the declared root."""
    target = root / looked.path
    if looked.only is not None:
        there = sorted(one.name for one in target.iterdir()) if target.is_dir() else None
        if there != sorted(looked.only):
            return [f"{looked.path}/ tiene {there}, non solo {sorted(looked.only)}"]
        return []
    if looked.size is None:
        return [f"{looked.path} c'è, e non doveva"] if os.path.lexists(target) else []
    try:
        found = os.lstat(target)
    except FileNotFoundError:
        return [f"{looked.path} non c'è"]
    failures: list[str] = []
    if not stat.S_ISREG(found.st_mode):
        failures.append(f"{looked.path} non è un file regolare")
    if found.st_size != looked.size:
        failures.append(f"{looked.path} ha {found.st_size} byte, non {looked.size}")
    if stat.S_IMODE(found.st_mode) != FILE_MODE:
        failures.append(
            f"{looked.path} ha i permessi {stat.S_IMODE(found.st_mode):o}, non {FILE_MODE:o}"
        )
    return failures


# ----------------------------------------------------------------------------------------
# What a question shows before the answer
# ----------------------------------------------------------------------------------------

QUESTION: Final = (
    ("capability_id", "capability"),
    ("description", "che cosa"),
    ("does", "che cosa succede al file"),
    ("site", "sito"),
    ("visits", "che cosa fa sul sito"),
    ("size", "dimensione in byte"),
    ("digest", "impronta sha256"),
    ("worst_case", "caso peggiore"),
    ("left", "resta nel mese"),
)
"""What the script writes of a question before Tommaso answers, in this order: words of ELA's and
numbers of the proof's own file. **The path of the file is written as the plan has it**, right
under the capability (:func:`shown`); the sentence of the question, which names the path whole,
is not written."""


def shown(question: Mapping[str, Any], root: Path) -> list[str]:
    lines = [
        f"    | {label}: {question[key]}"
        for key, label in QUESTION
        if question.get(key) not in (None, "", [])
    ]
    if question.get("target"):
        lines.insert(1, f"    | file, sotto la radice: {under(root, question['target'])}")
    return lines


# ----------------------------------------------------------------------------------------
# The kinds of this section
# ----------------------------------------------------------------------------------------


def a_plan(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``piano``: the plan the Planner wrote from the sentence of the step, written in the file
    and compared with the lines of the block. Another plan closes the step."""
    task = proof.api.get(f"/tasks/{turn.task_id}")
    for index, step in enumerate(task.get("steps") or [], start=1):
        capability = ", ".join(step.get("required_capabilities") or [])
        arguments = json.dumps(step.get("arguments") or {}, ensure_ascii=False)
        proof.report.say(f"    step {index}: {capability} — {step.get('goal')}")
        proof.report.say(f"      argomenti: {arguments}")
    failures = plan_failures(task, [a_planned(line) for line in block.lines])
    if failures:
        proof.report.failure(number, "; ".join(failures))
        proof.report.say(f"    {NOT_PLANNED}")
        raise guided.Done
    proof.report.passed(number, f"il piano è di {MODEL}, ed è quello della frase")


def a_question(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """``domanda``: the question the task waits with, compared line by line — or none."""
    if block.lines == [NOBODY]:
        accounts.a_question(number, block, turn, proof)
        return
    failures = asked_failures(block.lines, guided.question_of(proof.api, turn.task_id), proof.root)
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"la domanda dice: {'; '.join(block.lines)}")


def a_file(number: int, block: base.Block, proof: Proof) -> None:
    """``file``: every line asked of the disk, under the declared root."""
    failures = [
        failure for line in block.lines for failure in file_failures(a_file_line(line), proof.root)
    ]
    if failures:
        proof.report.failure(number, "; ".join(failures))
    else:
        proof.report.passed(number, f"sul disco: {'; '.join(block.lines)}")


def a_write(number: int, block: base.Block, proof: Proof) -> None:
    """``scrive``: a file of text inside the folder of the proof, ``600`` in a folder ``700``."""
    for line in block.lines:
        path, text = a_writing(line)
        target = proof.root / path
        target.parent.mkdir(mode=FOLDER_MODE, parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        with os.fdopen(descriptor, "w", encoding="utf-8") as written:
            written.write(text + "\n")
        size, digest = measured(target)
        proof.report.say(f"    scritto {path}: {size} byte, sha256 {digest}")


def the_planning_child(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    """A ``sì`` to ``<id del figlio>``: the child is the planning task of the step's task, whose
    question is the call of the Planner."""
    if CHILD not in block.lines[0]:
        return
    turn.child_id = proof.api.get(f"/tasks/{turn.task_id}").get("planning_task_id")
    if turn.child_id is None:
        proof.report.failure(number, f"il task {turn.task_id} non ha un task di pianificazione")
        raise base.Stop(NO_PLANNING)


def a_block(number: int, block: base.Block, turn: guided.Turn, proof: Proof) -> None:
    kind = block.kind
    if kind == "comando":
        steps.commands(block.lines, turn, proof)
    elif kind in ("atteso", "occhio", "schermo"):
        accounts.a_block(number, block, turn, proof)
    elif kind == "sì":
        the_planning_child(number, block, turn, proof)
        guided.an_answer(
            number, block, turn, proof, yes=True, shown=lambda asked: shown(asked, proof.root)
        )
    elif kind == "piano":
        a_plan(number, block, turn, proof)
    elif kind == "domanda":
        a_question(number, block, turn, proof)
    elif kind == "file":
        a_file(number, block, proof)
    elif kind == "scrive":
        a_write(number, block, proof)
    else:
        raise ValueError(f"step {number}: {kind!r} is not a kind of the section")


def a_step(
    number: int, todo: Sequence[base.Block], proof: Proof, turn: guided.Turn | None = None
) -> None:
    """The blocks of a step in order. A plan that is not the sentence's closes its step — the
    failure is written —, and the proof goes on to the next one."""
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


def scope_admits(scope: str) -> str | None:
    """Why the declared scope is not the one the proof needs — it admits the folder of the
    proof —, or ``None``. A scope is one path (:data:`OUTSIDE`): the one that admits the folder
    does not admit the file of step 4, and nothing here asks it twice."""
    if within_scope([scope], f"{FOLDER}/da-una-frase.bin"):
        return None
    return f"e lo scope dichiarato, {scope!r}, non ammette {FOLDER}/"


def planned_names(todo: Mapping[int, Sequence[base.Block]]) -> frozenset[str]:
    """The names of the files the plans of the section name inside the folder of the proof —
    **read from the plans, never written here** (decision 46): every plan the section sends with
    ``--file``, from its file, and the plan the Planner is asked to write, from ``piano``."""
    named: list[str] = []
    for blocks in todo.values():
        for block in blocks:
            for line in block.lines:
                if block.kind == "comando" and "--file" in line:
                    sent = ROOT / line.split("--file", 1)[1].split()[0]
                    plan = json.loads(sent.read_text(encoding="utf-8"))
                    named.extend(str(step["arguments"].get("file", "")) for step in plan["steps"])
                elif block.kind == "piano":
                    named.append(a_planned(line).file)
    return frozenset(Path(one).name for one in named if str(Path(one).parent) == FOLDER)


def emptied(root: Path, report: base.Report, names: frozenset[str]) -> str | None:
    """The folder of the proof without what a proof before this one left in it (decision 46):
    **the regular files with the names the plans of the proof create**, removed one by one, and
    each said. Anything else in the folder — a name no plan has, a folder, a link — stops the
    proof before anything is touched: it is Tommaso's to look at."""
    folder = root / FOLDER
    if not os.path.lexists(folder):
        return None
    if folder.is_symlink() or not folder.is_dir():
        return f"e {FOLDER} non è una cartella: la prova non tocca niente, guardala tu"
    found = sorted(folder.iterdir())
    others = [one.name for one in found if one.is_symlink() or not one.is_file()]
    others += [one.name for one in found if one.name not in names and one.name not in others]
    if others:
        return (
            f"e {FOLDER}/ tiene {sorted(others)}, che non sono file dei piani della prova: "
            "la prova non tocca niente, guardali tu"
        )
    for one in found:
        one.unlink()
        report.say(f"    tolto {FOLDER}/{one.name}, di una prova di prima")
    return None


def declared_root() -> tuple[Path, str]:
    from ela.composition.settings import FilesystemSettings

    declared = FilesystemSettings()
    return declared.root, declared.scope


def preconditions(report: base.Report) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    names = planned_names(base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING)))

    needed = planning.margin(1)
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"il Core gira dal codice del branch: la domanda dell'API ha «{QUESTION_FIELD}»",
            lambda: guided.so(
                QUESTION_FIELD
                in base.Api().get("/openapi.json")["components"]["schemas"]["ApprovalOut"][
                    "properties"
                ]
            ),
        ),
        ("il provider del modello ha una chiave", lambda: guided.so(spending.keyed())),
        ("il tetto è dichiarato", lambda: guided.so(base.Api().get("/spend")["cap"] is not None)),
        (
            f"restano almeno {needed} {CURRENCY}, una pianificazione al caso peggiore",
            lambda: planning.enough_left(base.Api().get("/spend")["left"], needed),
        ),
        (
            f"{', '.join(SITES)} sono fra i siti dichiarati",
            lambda: guided.so(all(site in BrowserSettings().sites for site in SITES)),
        ),
        (
            f"la radice e lo scope sono dichiarati, e lo scope ammette {FOLDER}/",
            lambda: scope_admits(declared_root()[1]),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            accounts.profile_ready,
        ),
        (
            f"la cartella della prova, {FOLDER}/, non tiene niente di una prova di prima",
            lambda: emptied(declared_root()[0], report, names),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m13.13-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.13, {datetime.now():%Y-%m-%d %H:%M:%S}")
        report.say(f"il file: {out}")
        report.say()
        report.say("—— passo 1 ——")
        wrong = outside_vocabulary(todo)
        if wrong:
            report.stop(1, f"righe della sezione fuori dal vocabolario del loro tipo: {wrong}")
        elif preconditions(report):
            api = base.Api()
            proof = Proof(
                api,
                report,
                ask,
                spending.Ledger.of(api.get("/spend")),
                root=declared_root()[0],
            )
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
