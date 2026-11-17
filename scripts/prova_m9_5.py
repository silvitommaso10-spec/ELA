"""La prova a mano di M13.13b e M9.5: la porta degli scaricamenti.

La sezione 33 di ``GETTING_STARTED.md``.

    uv run python scripts/prova_m9_5.py               # contro l'ELA che gira
    uv run python scripts/prova_m9_5.py --out FILE

**La guida è la fonte di verità.** Lo script **nasce da** ``scripts/prova_m13_14.py`` (la decisione
27 del prompt della sessione) e cammina con le funzioni di ``scripts/prova_m13_13.py``, la prova
degli scaricamenti: legge dalla sezione 33 i blocchi con il marcatore sopra,
``<!-- prova: N.tipo -->``, con il lettore di ``scripts/prova_m6_3c.py``; della sezione 30 usa i
tipi che gli servono e non uno di più — ``comando``, ``atteso``, ``occhio``, ``sì``,
``schermo``, ``domanda``, ``file`` —, con le stesse parole. ``tests/docs/test_prova_m9_5.py`` legge
la sezione con lo stesso lettore e tiene allineati i due, e ne cammina i passi 2 e 3 con questo
script contro un'ELA vera.

**Nessuna chiamata al modello, nessun login e nessun vault**: i piani sono scritti
(``docs/examples/``). **Lo script non tocca il ``.env``, il database né ``ela serve``**: scrive solo
dentro ``ELA/prova-m9.5/``, e legge ELA attraverso l'API e la CLI. **Che l'ELA che risponde giri dal
codice del branch non lo può guardare**: nessun campo dell'API distingue questo branch, e la guida
lo scrive come condizione di chi fa la prova.

**Il percorso intero di un file non entra nel file della prova**: è dentro la home di chi la fa;
intero lo mostra il blocco ``schermo``, sullo schermo soltanto.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prova_m6_3c as base  # noqa: E402 — a sibling in scripts/, which is not a package
import prova_m13_9 as accounts  # noqa: E402 — the same
import prova_m13_13 as files  # noqa: E402 — the same
import prova_m14_1 as spending  # noqa: E402 — the same
import prova_m14_2 as planning  # noqa: E402 — the same
import prova_m14_3 as guided  # noqa: E402 — the same

from ela.permissions.scope import within_scope  # noqa: E402

ROOT = base.ROOT
GUIDE = base.GUIDE
HEADING = "## 33. "
KINDS: Final = ("comando", "atteso", "occhio", "sì", "schermo", "domanda", "file")
LOOKS: Final[Mapping[str, str]] = files.LOOKS
"""The kinds of block that ask Tommaso's eye, each with its reason — the section 30's."""
SHOWS: Final[Mapping[str, str]] = files.SHOWS
"""The kinds of block that put in front of Tommaso what a question to his eye then asks."""
PLACEHOLDERS: Final = files.PLACEHOLDERS
SITES: Final = ("httpbin.org",)
"""The site of the downloads of section 30, already declared: no new line in the ``.env``
(decision 63 of the review at ``ad1826c``)."""
FOLDER: Final = "ELA/prova-m9.5"
"""The folder of the proof under the declared root: the only place the proof writes in, and the
only one it empties before it begins."""

Report = base.Report
Proof = files.Proof


def outside_vocabulary(todo: Mapping[int, Sequence[base.Block]]) -> list[str]:
    """Every line of the section a reader of its kind cannot read, and every kind that is not of
    this section: said before step 1."""
    wrong = files.outside_vocabulary(todo)
    for number, blocks in todo.items():
        wrong += [
            f"passo {number}: {block.kind!r} is not a kind of the section"
            for block in blocks
            if block.kind not in KINDS
        ]
    return wrong


def scope_admits(scope: str) -> str | None:
    """Why the declared scope does not admit the folder of the proof, or ``None``."""
    if within_scope([scope], f"{FOLDER}/vuoto.bin"):
        return None
    return f"e lo scope dichiarato, {scope!r}, non ammette {FOLDER}/"


def planned_names(todo: Mapping[int, Sequence[base.Block]]) -> frozenset[str]:
    """The names of the files the plans of the section name inside the folder of the proof —
    **read from the plans the section sends with** ``--file``, never written here."""
    named: list[str] = []
    for blocks in todo.values():
        for block in blocks:
            for line in block.lines:
                if block.kind == "comando" and "--file" in line:
                    sent = ROOT / line.split("--file", 1)[1].split()[0]
                    plan = json.loads(sent.read_text(encoding="utf-8"))
                    named.extend(str(step["arguments"].get("file", "")) for step in plan["steps"])
    return frozenset(Path(one).name for one in named if str(Path(one).parent) == FOLDER)


def emptied(root: Path, report: base.Report, names: frozenset[str]) -> str | None:
    """The folder of the proof without what a proof before this one left in it: **the regular
    files with the names the plans of the proof create**, removed one by one, and each said.
    Anything else — a name no plan has, a ``.crdownload``, a folder, a link — stops the proof
    before anything is touched: it is Tommaso's to look at."""
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


def preconditions(report: base.Report) -> bool:
    """Step 1: what the proof requires of the world; the first one missing stops it (FERMATO)."""
    from ela.composition.settings import BrowserSettings

    names = planned_names(base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING)))
    checks: list[tuple[str, guided.Why]] = [
        (
            "il Mac è sull'ultimo commit del branch su origin, con l'albero pulito",
            lambda: planning.on_origin(),
        ),
        ("ELA risponde", lambda: guided.so(base.Api().get("/health") is not None)),
        (
            f"{', '.join(SITES)} è fra i siti dichiarati",
            lambda: guided.so(all(site in BrowserSettings().sites for site in SITES)),
        ),
        (
            f"la radice e lo scope sono dichiarati, e lo scope ammette {FOLDER}/",
            lambda: scope_admits(files.declared_root()[1]),
        ),
        (
            "il profilo del browser è dichiarato, il browser è installato, e nessuno lo tiene",
            accounts.profile_ready,
        ),
        (
            f"la cartella della prova, {FOLDER}/, non tiene niente di una prova di prima",
            lambda: emptied(files.declared_root()[0], report, names),
        ),
    ]
    return guided.stopping(report, checks)


def default_out() -> Path:
    return Path.home() / "Downloads" / f"prova-m9.5-{datetime.now():%Y%m%d-%H%M%S}.txt"


def main(argv: Sequence[str] | None = None, ask: base.Ask = input) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--out", type=Path, default=None, help="il file dell'uscita")
    arguments = parser.parse_args(argv)
    out = arguments.out or default_out()
    todo = base.steps(base.blocks(GUIDE.read_text(encoding="utf-8"), HEADING))
    with out.open("w", encoding="utf-8") as written:
        report = Report(written)
        report.say(f"La prova a mano di M13.13b e M9.5, {datetime.now():%Y-%m-%d %H:%M:%S}")
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
                root=files.declared_root()[0],
            )
            try:
                base.walk(report, todo, lambda number, its: files.a_step(number, its, proof))
            finally:
                proof.api.close()
        report.say()
        report.verdict()
        report.say(f"Il file: {out}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
