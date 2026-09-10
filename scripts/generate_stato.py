"""Generate the derived blocks of ``docs/STATO.md`` by reading the repository.

``STATO.md`` is the restart point: whoever opens it must be able to resume without any previous
conversation. That makes it the document with the most to lose from a number written by hand — a
restart point that says "forty-five architecture rules" while the suite holds forty-six is worse
than one that says nothing, because the reader has no reason to doubt it and no way to check.
So everything here that a machine can count is counted here: the milestones and their state, the
figures of the system, the phases a document names, the dated debts and whether anybody paid them,
and the sections of the spec no milestone has cited yet.

What is **not** generated is the part no code can derive: the decisions the user made that live in
no ADR because they are not technical. The document says which is which, and this script is why it
can.

Usage::

    uv run python scripts/generate_stato.py            # rewrite the generated blocks
    uv run python scripts/generate_stato.py --check    # fail if they are out of date
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

BEGIN = "<!-- generato da scripts/generate_stato.py: {name} -->"
END = "<!-- fine del blocco generato: {name} -->"

MILESTONES = "le milestone"
NUMBERS = "i numeri"
FUTURE = "le fasi che un documento nomina"
DEBTS = "i debiti datati"
UNNAMED = "le sezioni della spec che nessuna milestone ha nominato"

DOCUMENT = Path("docs") / "STATO.md"
"""The document this script writes — and the one file it must not read as evidence.

``STATO.md`` names future phases in its own prose; counting itself among the documents that name
them would make the block describe the block. The exclusion is in :func:`future_phases`.
"""

STATE = re.compile(r"^- \*\*Stato:\*\*\s*(.+)$", re.MULTILINE)
WORD = re.compile(r"[A-Za-zÀ-ÿ]+")
TITLE = re.compile(r"^# (M\d+\.\d+[a-z]?) — (.+)$")
IDENTIFIER = re.compile(r"^M(\d+)\.(\d+)([a-z]*)$")
PHASE_HEADING = re.compile(r"^### Fase (\d+) — (.+)$", re.MULTILINE)
PHASE_MENTION = re.compile(r"\bFase (\d+)\b")
SECTION_HEADING = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
SECTION_MENTION = re.compile(r"§\s?(\d+)")
DEBT_HEADING = re.compile(r"^#{2,3} (\d+)\. Un debito datato: (.+)$", re.MULTILINE)
NEXT_SECTION = re.compile(r"^#{1,2} ", re.MULTILINE)
CHARGED = re.compile(r"\*\*Debito a carico (.+?)\*\*, dichiarato il \*\*(\d{4}-\d{2}-\d{2})\*\*")
PAID = re.compile(r"[Ii]l debito di \*{0,2}ADR (\d{4}) §(\d+)\*{0,2},? saldat")
DECLARED = "### Vincoli dichiarati"
BULLET = re.compile(r"^- \*\*(.+?)\*\*")
PROPOSED = "Proposta"

CLOSING_SECTIONS = frozenset(range(66, 71))
"""§66–§70: the vision, the fundamental rule, the definition, the closing principle.

Left out of "what no milestone has named yet" because they are not features anybody can build —
listing them as missing would make the block noise, and a block nobody reads is a block that stops
being true without anyone noticing. That they are genuinely uncited is asserted in
``tests/docs/test_stato.py``: the day one of them is cited, the exclusion is reconsidered instead
of hiding the citation.
"""


# ----------------------------------------------------------------------------------------
# The milestones
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Milestone:
    """One file of ``docs/milestones/``: which phase it belongs to, its state, its title."""

    identifier: str
    phase: int
    order: tuple[int, int, str]
    state: str
    title: str


def milestones(root: Path) -> list[Milestone]:
    """Every milestone document, in phase order, with the letter of a repair in its place.

    The ordering key is the changelog's (``tests/docs/test_changelog.py``): phase, number, and the
    letter that says when a defect was repaired, so M6.1b sits between M6.1 and M6.2 — where
    somebody looking for the defect will look.
    """
    found: list[Milestone] = []
    for path in sorted((root / "docs" / "milestones").glob("M*.md")):
        text = path.read_text(encoding="utf-8")
        number = IDENTIFIER.match(path.stem)
        title = TITLE.match(text.splitlines()[0])
        state = STATE.search(text)
        if number is None or title is None or state is None:
            raise ValueError(f"{path.name}: needs a `# M<id> — <titolo>` line and a Stato line")
        word = WORD.search(state.group(1))
        if word is None:
            raise ValueError(f"{path.name}: the Stato line names no state")
        found.append(
            Milestone(
                identifier=number.group(0),
                phase=int(number.group(1)),
                order=(int(number.group(1)), int(number.group(2)), number.group(3)),
                state=word.group(0),
                title=title.group(2),
            )
        )
    return sorted(found, key=lambda milestone: milestone.order)


def phase_names(root: Path) -> dict[int, str]:
    """Phase number -> the name the changelog gives it.

    The changelog is the place a phase gets a name, and it gets one when the phase delivers its
    first milestone out of ``Proposta``. A phase that has milestones and no name here is therefore
    a phase in progress — which is a fact worth showing, not a gap to fill in.
    """
    text = (root / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    return {int(match.group(1)): match.group(2) for match in PHASE_HEADING.finditer(text)}


def render_milestones(found: Iterable[Milestone], names: dict[int, str]) -> str:
    lines = ["| Fase | Milestone | Stato | Che cosa porta |", "|---|---|---|---|"]
    for milestone in found:
        phase = f"{milestone.phase} — {names.get(milestone.phase, '*senza nome*')}"
        lines.append(
            f"| {phase} | `{milestone.identifier}` | {milestone.state} | {milestone.title} |"
        )
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------
# The figures
# ----------------------------------------------------------------------------------------


def adrs(root: Path) -> list[Path]:
    return sorted((root / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))


def rules_count(root: Path) -> int:
    """How many architecture rules the suite holds, read off ``RULES`` with ``ast``.

    Read, not imported: a script does not depend on the test suite (the criterion
    ``scripts/generate_architecture.py`` set for ``INFRA_LIBRARIES``). That this number is the one
    ``len(rules.RULES)`` answers is asserted in ``tests/docs/test_stato.py``, which may import
    both.
    """
    path = root / "tests" / "architecture" / "rules.py"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RULES"
            and isinstance(node.value, ast.Dict)
        ):
            return len(node.value.keys)
    raise ValueError(f"{path}: no `RULES: dict[...] = {{...}}` to count")


def contracts_count(root: Path) -> int:
    configuration = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return len(configuration["tool"]["importlinter"]["contracts"])


def ports_count(root: Path) -> int:
    """The ``Protocol`` classes of ``src/ela/ports.py`` — the interfaces, not the error codes."""
    path = root / "src" / "ela" / "ports.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and any(isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases)
    )


def constraints_count(root: Path) -> int:
    """Every bullet of every "Vincoli dichiarati" section of every ADR (M9.4, decisione 10a)."""
    found: set[str] = set()
    for path in adrs(root):
        text = path.read_text(encoding="utf-8")
        if DECLARED not in text:
            continue
        block = re.split(r"\n#+ ", text.split(DECLARED, 1)[1])[0]
        found |= {match.group(1) for line in block.splitlines() if (match := BULLET.match(line))}
    return len(found)


def surface() -> list[tuple[str, str, str]]:
    """The three figures that can only be answered by the running code, asked of the code.

    A capability, a route and a command are not text in a file: they are what the composition root
    builds, what the routers carry and what the Typer tree offers. ``test_v01_surface.py`` asks the
    same three questions of the same three things, and this asks them again rather than reading its
    answers — a count copied from a test is a count written by hand once removed.
    """
    import importlib
    import pkgutil

    import ela.api
    from ela.cli.app import app as cli_app
    from ela.permissions.capabilities import production_catalogue

    routes: set[tuple[str, str]] = set()
    for info in pkgutil.iter_modules(ela.api.__path__):
        if info.name.startswith("_"):
            continue
        router = getattr(importlib.import_module(f"ela.api.{info.name}"), "router", None)
        if router is None:
            continue
        routes |= {
            (method, route.path)
            for route in router.routes
            for method in getattr(route, "methods", set())
            if method not in {"HEAD", "OPTIONS"}
        }

    def commands(app: object, prefix: str = "") -> list[str]:
        found = [
            prefix + (command.name or command.callback.__name__)
            for command in getattr(app, "registered_commands", [])
            if command.callback is not None or command.name is not None
        ]
        for group in getattr(app, "registered_groups", []):
            found += commands(group.typer_instance, f"{group.name} ")
        return found

    return [
        (
            "Capability di produzione",
            str(len(production_catalogue().specs())),
            "`production_catalogue()`",
        ),
        ("Rotte dell'API", str(len(routes)), "i `router` di `ela.api`"),
        ("Comandi della CLI", str(len(commands(cli_app))), "l'albero Typer di `ela.cli`"),
    ]


def figures(root: Path) -> list[tuple[str, str, str]]:
    """What ELA is made of today, counted: the label, the number, and what was counted."""
    found = milestones(root)
    done = [milestone for milestone in found if milestone.state != PROPOSED]
    return [
        ("ADR scritti", str(len(adrs(root))), "`docs/adr/NNNN-*.md`"),
        (
            "Milestone",
            f"{len(found)}, di cui {len(done)} non più `Proposta`",
            "la riga `- **Stato:**` di ogni documento",
        ),
        ("Regole di architettura", str(rules_count(root)), "`RULES` in `tests/architecture/`"),
        ("Contratti import-linter", str(contracts_count(root)), "`pyproject.toml`"),
        ("Port", str(ports_count(root)), "i `Protocol` di `src/ela/ports.py`"),
        *surface(),
        (
            "Vincoli dichiarati negli ADR",
            str(constraints_count(root)),
            "le sezioni «Vincoli dichiarati»",
        ),
    ]


def render_figures(rows: Iterable[tuple[str, str, str]]) -> str:
    lines = ["| Che cosa | Quanti | Contati leggendo |", "|---|---|---|"]
    lines += [f"| {label} | **{value}** | {source} |" for label, value, source in rows]
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------
# The phases nobody has built yet
# ----------------------------------------------------------------------------------------


def documents(root: Path) -> Iterator[tuple[Path, str]]:
    """Every markdown document of ``docs/``, except the one this script writes."""
    for path in sorted((root / "docs").rglob("*.md")):
        if path.relative_to(root) == DOCUMENT:
            continue
        yield path, path.read_text(encoding="utf-8")


def future_phases(root: Path) -> list[tuple[int, int]]:
    """Phases past the last one with a milestone -> how many documents name them.

    A phase named by a document is a phase somebody has already written something about; a number
    that appears here with no milestone is work that has been decided and not started. A number
    that appears **nowhere** is the honest answer to "what comes after": nothing written yet.
    """
    last = max((milestone.phase for milestone in milestones(root)), default=-1)
    counted: dict[int, int] = {}
    for _, text in documents(root):
        for phase in {int(match) for match in PHASE_MENTION.findall(text) if int(match) > last}:
            counted[phase] = counted.get(phase, 0) + 1
    return sorted(counted.items())


def render_future(rows: Iterable[tuple[int, int]]) -> str:
    lines = ["| Fase | Documenti che la nominano |", "|---|---|"]
    lines += [f"| {phase} | {count} |" for phase, count in rows]
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------
# The dated debts
# ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Debt:
    """A debt an ADR dated, charged to somebody, and either paid or still open."""

    adr: str
    section: str
    title: str
    charged: str
    declared: str
    paid_by: str | None

    @property
    def open(self) -> bool:
        return self.paid_by is None


def payments(root: Path) -> dict[tuple[str, str], str]:
    """``(ADR, §)`` -> the document that declares that debt paid.

    A debt that does not know it has been paid is the same species of lie as the numbers it
    describes (ADR 0035 §7), so the payment is read from whoever wrote it down: an ADR section
    titled "Il debito di ADR NNNN §N, saldato", or the milestone that says it saldò it there.
    """
    found: dict[tuple[str, str], str] = {}
    for path, text in documents(root):
        for match in PAID.finditer(text):
            adr, section = match.groups()
            if path.parent.name != "adr" or path.stem[:4] != adr:
                found.setdefault((adr, section), _name_of(path, text, match.start()))
    return found


def _name_of(path: Path, text: str, at: int) -> str:
    """Who paid, and where: ``ADR 0036 §10`` when the payment is a section, else the document.

    A debt is paid in a section of its own — that is the shape ADR 0036 §10 used — so the section
    number is part of the answer: "saldato da ADR 0036" sends the reader to a whole document.
    """
    name = f"ADR {path.stem[:4]}" if path.parent.name == "adr" else path.stem
    line = text[text.rfind("\n", 0, at) + 1 :].split("\n", 1)[0]
    heading = re.match(r"#{2,3} (\d+)\.", line)
    return f"{name} §{heading.group(1)}" if heading else name


def _section_body(text: str, start: int) -> str:
    """The text of a section, from the end of its heading to the next section that ends it.

    Bounded by the next debt heading **and** by the next heading of level 1 or 2, so that the
    "a carico di / dichiarato il" line a debt must carry is read from that debt's own section and
    never borrowed from the one below it.
    """
    tail = text[start:]
    ends = [
        match.start()
        for match in (DEBT_HEADING.search(tail), NEXT_SECTION.search(tail))
        if match is not None
    ]
    return tail[: min(ends)] if ends else tail


def dated_debts(root: Path) -> list[Debt]:
    """Every "Un debito datato" section of every ADR, open ones first."""
    paid = payments(root)
    found: list[Debt] = []
    for path in adrs(root):
        text = path.read_text(encoding="utf-8")
        for heading in DEBT_HEADING.finditer(text):
            charged = CHARGED.search(_section_body(text, heading.end()))
            if charged is None:
                raise ValueError(
                    f"{path.name} §{heading.group(1)}: a dated debt must say who it is charged to "
                    "and when it was declared"
                )
            adr = path.stem[:4]
            found.append(
                Debt(
                    adr=adr,
                    section=heading.group(1),
                    title=heading.group(2),
                    charged=charged.group(1),
                    declared=charged.group(2),
                    paid_by=paid.get((adr, heading.group(1))),
                )
            )
    return sorted(found, key=lambda debt: (not debt.open, debt.adr, int(debt.section)))


def render_debts(found: Iterable[Debt]) -> str:
    lines = ["| Debito | Dichiarato | A carico | Stato |", "|---|---|---|---|"]
    for debt in found:
        state = "**aperto**" if debt.open else f"saldato da {debt.paid_by}"
        lines.append(
            f"| ADR {debt.adr} §{debt.section} — {debt.title} | {debt.declared} "
            f"| {debt.charged} | {state} |"
        )
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------
# The spec nobody has cited yet
# ----------------------------------------------------------------------------------------


def unnamed_sections(root: Path) -> list[tuple[int, str]]:
    """The sections of the spec no milestone document has ever cited.

    Not "what is missing" — §22 and §56 are cited by milestones that did not build them — but the
    weaker and checkable thing: the parts of the source of truth that no milestone has so much as
    named. It is the list somebody restarting should read before deciding what comes next.
    """
    spec = (root / "docs" / "spec" / "ELA_spec.md").read_text(encoding="utf-8")
    headings = {int(match.group(1)): match.group(2) for match in SECTION_HEADING.finditer(spec)}
    cited: set[int] = set()
    for path in sorted((root / "docs" / "milestones").glob("M*.md")):
        cited |= {int(number) for number in SECTION_MENTION.findall(path.read_text("utf-8"))}
    return [
        (number, title)
        for number, title in sorted(headings.items())
        if number not in cited and number not in CLOSING_SECTIONS
    ]


def render_unnamed(rows: Iterable[tuple[int, str]]) -> str:
    lines = ["| Sezione | Titolo |", "|---|---|"]
    lines += [f"| §{number} | {title} |" for number, title in rows]
    return "\n".join(lines)


# ----------------------------------------------------------------------------------------
# The document
# ----------------------------------------------------------------------------------------


def blocks(root: Path) -> dict[str, str]:
    """The generated blocks by name: what the document must contain, byte for byte."""
    return {
        MILESTONES: render_milestones(milestones(root), phase_names(root)),
        NUMBERS: render_figures(figures(root)),
        FUTURE: render_future(future_phases(root)),
        DEBTS: render_debts(dated_debts(root)),
        UNNAMED: render_unnamed(unnamed_sections(root)),
    }


def replace(document: str, name: str, body: str) -> str:
    """The document with the block ``name`` replaced by ``body``; the markers stay."""
    begin, end = BEGIN.format(name=name), END.format(name=name)
    start, stop = document.find(begin), document.find(end)
    if start < 0 or stop < 0 or stop < start:
        raise ValueError(f"{name}: the markers are missing or out of order")
    return document[: start + len(begin)] + "\n\n" + body + "\n\n" + document[stop:]


def generate(document: str, root: Path) -> str:
    for name, body in blocks(root).items():
        document = replace(document, name, body)
    return document


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / DOCUMENT
    current = target.read_text(encoding="utf-8")
    wanted = generate(current, root)
    if current == wanted:
        print(f"{target}: up to date")
        return 0
    if "--check" in argv:
        print(
            f"{target} is out of date: the repository changed and the restart point did not.\n"
            "Rigenera con: uv run python scripts/generate_stato.py",
            file=sys.stderr,
        )
        return 1
    target.write_text(wanted, encoding="utf-8")
    print(f"{target}: rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
