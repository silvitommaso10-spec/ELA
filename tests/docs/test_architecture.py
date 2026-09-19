"""``docs/ARCHITECTURE.md`` says what the code does, and cannot say otherwise for long.

Two of its three blocks are generated from ``src/ela`` by ``scripts/generate_architecture.py``:
they are compared here byte for byte, so an import added between two packages fails ``make check``
until the diagram is regenerated. The third — the path a call takes from a ``POST`` to an effect —
is written by hand, says so in the document, and is checked for what can be checked: every module
it names exists, and every arrow is a road that exists in the code, in the shape the "come" column
declares.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

import ela.ports
from ela.composition import Ela
from tests.architecture.rules import INFRA_LIBRARIES, INFRA_PACKAGES

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = ROOT / "docs" / "ARCHITECTURE.md"
STATO = ROOT / "docs" / "STATO.md"
SCRIPT = ROOT / "scripts" / "generate_architecture.py"
PACKAGE_ROOT = ROOT / "src" / "ela"
ARROW = re.compile(r"^\| `(ela[\w.]+)` \| `(ela[\w.]+)` \| (.+?) \|$")
PORT = re.compile(r"^port `(\w+)`$")
COUNT = re.compile(
    r"\b\d+\*{0,2}\s+"
    r"(?:adr|milestone|regol[ae]|contratt[io]|port|capability|rott[ae]|comand[io]|vincol[io])\b",
    re.IGNORECASE,
)
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
NUMBERS = re.compile(
    r"<!-- generato da scripts/generate_stato.py: i numeri -->\n(.*?)"
    r"<!-- fine del blocco generato: i numeri -->",
    re.DOTALL,
)
COUNTED = re.compile(r"^\| ([^|]+?) \| \*\*", re.MULTILINE)


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_architecture", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def document() -> str:
    return DOCUMENT.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# The two generated blocks
# ----------------------------------------------------------------------------------------


def test_the_generated_blocks_are_the_ones_the_code_produces(generator: ModuleType) -> None:
    """Byte for byte. A diagram that can be right by accident is not a diagram of anything."""
    assert generator.generate(document(), PACKAGE_ROOT) == document()


def test_the_document_declares_which_blocks_are_generated_and_which_is_not() -> None:
    text = document()
    assert "**Due dei tre blocchi sono generati leggendo il codice**" in text
    assert "**Questo blocco non è generato.**" in text
    assert "scripts/generate_architecture.py" in text


def test_the_edges_that_may_name_a_library_are_exactly_the_allowlist(
    generator: ModuleType,
) -> None:
    """Decision 14a: the block is read from what the code does, and *then* held to the rule.

    The document shows who names one of the nine libraries; ``INFRA_PACKAGES`` is who was allowed
    to. Printing the allowlist would have made the diagram unable to notice it had become false —
    a fifth package importing ``httpx`` would simply not appear.
    """
    assert set(generator.infra_edges(PACKAGE_ROOT)) == set(INFRA_PACKAGES)
    assert set(generator.INFRA_LIBRARIES) == set(INFRA_LIBRARIES)


def test_every_package_of_ela_is_a_node_even_the_empty_ones(generator: ModuleType) -> None:
    """An empty package is a node with no edges, not an absence: §48 promised those folders.

    ``context`` left this set in M10.4, which is what the set is for: a package that receives
    code stops being an empty promise, and the day it does the change is visible here rather than
    silent. Three remain, and each is a milestone that has not happened.
    """
    graph = generator.package_graph(PACKAGE_ROOT)
    empty = {"evolution", "identity", "memory"}
    assert empty <= set(graph)
    assert all(graph[package] == set() for package in empty)
    assert graph["context"] == {"devices", "domain", "perception", "ports"}
    assert graph["domain"] == set()  # not even ports
    assert graph["ports"] == {"domain"}


# ----------------------------------------------------------------------------------------
# The block that is written by hand
# ----------------------------------------------------------------------------------------


def arrows() -> list[tuple[str, str, str]]:
    rows = [m.groups() for line in document().splitlines() if (m := ARROW.match(line))]
    assert rows, "the call path must list its arrows"
    return rows


def module_path(dotted: str) -> Path:
    parts = dotted.split(".")[1:]
    single = PACKAGE_ROOT.joinpath(*parts).with_suffix(".py")
    return single if single.exists() else PACKAGE_ROOT.joinpath(*parts, "__init__.py")


def imports_of(dotted: str) -> set[str]:
    tree = ast.parse(module_path(dotted).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            found.add(node.module)
            found |= {f"{node.module}.{alias.name}" for alias in node.names}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
    return found


def members(obj: object) -> set[str]:
    """Public members a class or protocol has, annotations included.

    ``Tool.idempotent`` is a ``ClassVar[bool]`` **without a default** on purpose (ADR 0021 §1), so
    it exists only as an annotation: a check that read ``dir()`` alone would call the tool port
    unsatisfied for the very reason it is written that way.
    """
    names = {name for name in dir(obj) if not name.startswith("_")}
    for klass in getattr(obj, "__mro__", [obj]):
        annotated = getattr(klass, "__annotations__", {})
        names |= {name for name in annotated if not name.startswith("_")}
    return names


def test_every_module_the_call_path_names_exists() -> None:
    for source, target, _ in arrows():
        for dotted in (source, target):
            assert module_path(dotted).exists(), dotted
            assert importlib.import_module(dotted) is not None


def test_every_arrow_is_a_road_that_exists_in_the_code() -> None:
    """The three shapes the document declares, each verified the way it is written.

    A direct import is the easy one. A port is the interesting one: the caller names a
    ``Protocol`` and nothing else, and whoever answers satisfies it structurally, without
    inheriting anything — so the check is that the class on the other side really has every
    member of the protocol. Composition is the third: ``ela.api`` builds nothing (rule 27) and
    receives an ``Ela`` that already holds the object.
    """
    fields = set(Ela.__annotations__.values()) | {
        name.__name__ if isinstance(name, type) else str(name)
        for name in Ela.__annotations__.values()
    }
    for source, target, how in arrows():
        if how == "import":
            assert any(name.startswith(target) for name in imports_of(source)), (source, target)
        elif how == "composizione":
            classes = {
                klass.__name__
                for klass in vars(importlib.import_module(target)).values()
                if isinstance(klass, type)
            }
            assert classes & fields, (source, target)
            assert "ela.composition" in imports_of(source) or "ela.api.deps" in imports_of(source)
        elif (port := PORT.match(how)) is not None:
            name = port.group(1)
            assert name in ela.ports.__all__, name
            assert f"ela.ports.{name}" in imports_of(source), (source, name)
            protocol = getattr(ela.ports, name)
            answers = [
                klass
                for klass in vars(importlib.import_module(target)).values()
                if isinstance(klass, type) and members(protocol) <= members(klass)
            ]
            assert answers, (target, sorted(members(protocol)))
        else:
            pytest.fail(f"unknown shape {how!r} for {source} -> {target}")


def test_the_document_says_what_it_does_not_verify() -> None:
    """The declared limit of the third block, in the document and not only here."""
    text = document()
    assert "Ciò che **non** è verificato" in text
    assert "un passaggio dimenticato" in text
    assert "il prezzo dichiarato del terzo blocco" in text


# ----------------------------------------------------------------------------------------
# The counts, which live somewhere else
# ----------------------------------------------------------------------------------------


def counts_written_by_hand(text: str) -> list[str]:
    """Every figure the prose puts in front of something ``docs/STATO.md`` §3 counts.

    A digit, bold or not, followed by the first word of a row of that table, in any case: the
    two are held together by ``test_every_row_of_the_numbers_is_a_noun_the_check_knows``. «36
    regole», «27 ADR» and «13 contratti» were written here by hand and had all expired when they
    were taken out: the number lives in the generated block, and this document sends the reader
    there. Code blocks are not prose and are left out. The limit, declared: a number written in
    words is not seen.
    """
    return COUNT.findall(FENCE.sub("", text))


def test_the_prose_writes_no_count_by_hand() -> None:
    assert counts_written_by_hand(document()) == []


@pytest.mark.parametrize(
    ("prose", "count"),
    [
        ("le direzioni che le 36 regole di architettura impongono", "36 regole"),
        ("una regola sola: 1 regola", "1 regola"),
        ("`docs/adr/` — 27 ADR, dal primo sullo stack", "27 ADR"),
        ("47 milestone, di cui 44 non più `Proposta`", "47 milestone"),
        ("i 13 contratti `import-linter`", "13 contratti"),
        ("1 contratto", "1 contratto"),
        ("i 25 port di `ela.ports`", "25 port"),
        ("8 capability di produzione", "8 capability"),
        ("29 rotte dell'API", "29 rotte"),
        ("1 rotta", "1 rotta"),
        ("25 comandi della CLI", "25 comandi"),
        ("1 comando", "1 comando"),
        ("200 vincoli dichiarati negli ADR", "200 vincoli"),
        ("1 vincolo", "1 vincolo"),
        ("le **54** regole", "54** regole"),
    ],
)
def test_a_count_written_by_hand_is_caught(prose: str, count: str) -> None:
    """The negative case: a defence that cannot fire is worse than none."""
    assert counts_written_by_hand(prose) == [count]


@pytest.mark.parametrize(
    "prose",
    [
        "`composition` è l'unico che nomina i concreti (regola 27, ADR 0023 §12)",
        "Regola 3 (ADR 0002 §3): il Core non importa mai `anthropic`",
        "le porte e le rotte, senza cifre",
        "```\n36 regole\n```",
    ],
)
def test_what_is_not_a_count_is_left_alone(prose: str) -> None:
    """A rule is cited by its number, which comes after the noun; a code block is not prose."""
    assert counts_written_by_hand(prose) == []


def test_every_row_of_the_numbers_is_a_noun_the_check_knows() -> None:
    """A row added to ``docs/STATO.md`` §3 fails here until ``COUNT`` learns its noun.

    The first word of each label, in lower case, after «2 ». Without this the docstring above
    could become false the way the counts did: by a line added somewhere else.
    """
    block = NUMBERS.search(STATO.read_text(encoding="utf-8"))
    assert block is not None, "docs/STATO.md must keep its generated block «i numeri»"
    nouns = [label.split()[0].lower() for label in COUNTED.findall(block.group(1))]
    assert nouns, "the block «i numeri» must list its rows"
    assert [noun for noun in nouns if counts_written_by_hand(f"2 {noun}") != [f"2 {noun}"]] == []


def test_the_document_sends_the_reader_to_the_one_place_that_counts() -> None:
    assert "`docs/STATO.md` §3" in " ".join(document().split())
    assert "\n## 3. I numeri\n" in STATO.read_text(encoding="utf-8")
