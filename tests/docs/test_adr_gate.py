"""ADR 0031 and the tree say the same thing about the gate (the CI fix after M10.3).

This document owns **today's** totals — the rules, the ports, the capabilities, the perception
families — because it is the one that last changed them: ADR 0030 keeps the numbers it wrote, as
history about the tree it left behind. That hand-over is what lets an ADR stay immutable while the
tree keeps growing (``test_adr_context.py`` says the same of ADR 0028 and ADR 0029).

The claim this document rests on is a claim about a **tool**, so it is measured here rather than
believed: a conditional expression costs the 100% branch gate nothing, and the same choice written
as a statement costs it a missing line and a partial arc. If coverage.py ever changes its mind,
this test says so before the rule stops making sense.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ela.permissions import catalogue_v01, production_catalogue
from tests.architecture.rules import PLATFORM_WORDS, RULES, _condition_words
from tests.architecture.violations import PACKAGE_ROOT
from tests.contracts.protocols import port_protocols

REPO_ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = REPO_ROOT / "docs" / "adr" / "0031-runner-parity.md"
TESTS_ROOT = REPO_ROOT / "tests"
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|$")
RULE = "platform-choice-is-a-statement"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def flowed() -> str:
    """The document with its line breaks collapsed, for searching a sentence that wraps."""
    plain = adr_text().replace("**", "").replace("\n> ", "\n")
    return " ".join(plain.split())


# ----------------------------------------------------------------------------------------
# §1: the measurement, reproduced instead of quoted
# ----------------------------------------------------------------------------------------

MEASURED = """
def darwin_side():
    return "mac"


def other_side():
    return "not a mac"


def pick(darwin):
    chosen = (
        darwin_side()
        if darwin
        else other_side()
    )
    return chosen


def pick_statement(darwin):
    if darwin:
        chosen = darwin_side()
    else:
        chosen = other_side()
    return chosen


if __name__ == "__main__":
    assert pick(False) == "not a mac"
    assert pick_statement(False) == "not a mac"
"""
EXPRESSION_ARM = 11
"""``darwin_side()`` inside the conditional expression: the side a Linux runner never takes."""
STATEMENT_ARM = 20
"""``chosen = darwin_side()`` inside the ``if``: the same side, written as a statement."""
CALLEE = 2
"""The body of ``darwin_side`` — the frame below, which is where ELA's missing line surfaced."""


def missing_lines(tmp_path: Path) -> set[int]:
    """Run the module under ``coverage --branch`` in the *false* direction only, out of process.

    A subprocess and not the coverage instance pytest is already running under: measuring the
    measurer from inside itself is how you get an answer about the harness instead of the tool.
    """
    module = tmp_path / "tern.py"
    module.write_text(MEASURED.lstrip("\n"), encoding="utf-8")
    run = subprocess.run(  # noqa: S603 — the interpreter running this suite, on a file we wrote
        [sys.executable, "-m", "coverage", "run", "--branch", module.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert run.returncode == 0
    report = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "coverage", "report", "-m"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    row = next(line for line in report.stdout.splitlines() if line.startswith("tern.py"))
    columns = row.split()
    percent = next(index for index, cell in enumerate(columns) if cell.endswith("%"))
    numbers: set[int] = set()
    for part in " ".join(columns[percent + 1 :]).split(","):
        entry = part.strip()
        if "->" in entry:  # a partial arc, reported as ``19->22``: not a missing *line*
            continue
        first, _, last = entry.partition("-")
        if not first.isdigit():
            continue
        numbers.update(range(int(first), int(last or first) + 1))
    return numbers


def test_a_conditional_expression_costs_the_branch_gate_nothing(tmp_path: Path) -> None:
    """§1, the whole reason rule 37 exists — and the failure it protects against, in one file.

    Same choice, same single direction taken, two forms: the statement leaves a missing line, the
    expression leaves nothing at all. What the expression *does* leave is the body of the function
    the untaken arm would have called — a pure line, elsewhere, with nothing to do with the
    platform. In ELA that line was ``src/ela/tools/settings.py:171``.
    """
    missing = missing_lines(tmp_path)

    assert STATEMENT_ARM in missing, "the statement's untaken arm must be reported"
    assert EXPRESSION_ARM not in missing, "coverage.py now sees a ternary: ADR 0031 §1 needs a look"
    assert CALLEE in missing, "the frame below is the only trace the expression leaves"


# ----------------------------------------------------------------------------------------
# §4: the rule, registered under the name the document gives it
# ----------------------------------------------------------------------------------------


def test_the_rule_this_adr_adds_is_registered_under_the_name_it_gives_it() -> None:
    documented = [
        match.groups() for line in adr_text().splitlines() if (match := RULE_ROW.match(line))
    ]

    assert [number for number, *_ in documented] == ["37"]
    assert documented[0][1] == RULE
    assert RULE in RULES


def test_the_rule_holds_on_the_real_tree() -> None:
    assert RULES[RULE](PACKAGE_ROOT) == []


def test_the_rule_would_have_caught_the_line_that_started_this(tmp_path: Path) -> None:
    """The negative case against the shape M10.3 actually shipped, not against a paraphrase."""
    root = tmp_path / "ela" / "composition"
    root.mkdir(parents=True)
    (tmp_path / "ela" / "__init__.py").touch()
    (root / "__init__.py").touch()
    (root / "root.py").write_text(
        "import platform\n"
        "def build(settings, adapters):\n"
        "    darwin = platform.system() == 'Darwin'\n"
        "    return (\n"
        "        adapters.vision(timeout=settings.captures.ocr_timeout)\n"
        "        if darwin\n"
        "        else adapters.unsupported()\n"
        "    )\n",
        encoding="utf-8",
    )

    reported = RULES[RULE](tmp_path / "ela")

    assert [(v.module, v.imported) for v in reported] == [("ela.composition.root", "darwin")]


def test_no_test_asks_the_machine_what_to_expect() -> None:
    """§6, as a closed world over the suite: the family the rule cannot reach.

    Rule 37 reads ``src/ela``; this is the same question asked of ``tests/``, where the shape was
    a test that computed its own expectation from ``platform.system()`` and therefore verified
    half of the wiring on each machine and failed on neither.
    """
    found = [
        f"{path.relative_to(REPO_ROOT)}:{node.lineno}"
        for path in sorted(TESTS_ROOT.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.IfExp) and _condition_words(node.test) & PLATFORM_WORDS
    ]

    assert found == []


# ----------------------------------------------------------------------------------------
# The criteria that must survive this document, written down and not only applied
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "Il risultato del gate non dipende dal runner",
        "Una riga coperta da chi passa di lì non è coperta",
        "Un test che chiede alla macchina cosa aspettarsi verifica metà su ognuna",
        "Uno skip dichiarato è visibile, un `if` dentro un test no",
    ],
)
def test_the_general_criteria_are_written_and_not_only_applied(sentence: str) -> None:
    """A criterion nobody can read is one the next milestone re-derives or contradicts (M9.2)."""
    assert sentence in flowed()


def test_the_extended_criterion_quotes_the_one_it_extends() -> None:
    """§3 is ADR 0028 §1 plus a clause: the first half is quoted so the two cannot drift apart."""
    section = adr_text().split("## 3.", 1)[1].split("\n## ", 1)[0]
    original = (
        "Un package entra in `cov-critical` quando ogni suo ramo può essere eseguito in CI. "
        "Dove questo è falso, il package non deve contenere nessun ramo che decida qualcosa."
    )

    assert original in " ".join(section.replace("\n> ", "\n").split())
    assert "ADR 0028" in adr_text()


# ----------------------------------------------------------------------------------------
# §Conseguenze: today's totals, pinned here until the next ADR changes them
# ----------------------------------------------------------------------------------------


def test_the_conseguenze_count_the_rules_the_ports_and_the_capabilities() -> None:
    """The totals this document pinned, kept as history rather than as today's count.

    The pin on **today's** numbers moved to ADR 0032 (``tests/docs/test_adr_context_core.py``)
    the moment M10.4 added two rules and a contract. What ADR 0031 wrote stays what it wrote — an
    ADR is immutable — and what stays asserted here is that the tree only ever grew past it.
    """
    conseguenze = adr_text().split("## Conseguenze", 1)[1]

    assert "**trentasette**" in conseguenze
    assert len(RULES) >= 37
    assert "**tredici**" in conseguenze
    assert "**ventuno**" in conseguenze
    assert len(tuple(port_protocols())) == 21
    assert "**cinque**" in conseguenze
    assert len(production_catalogue().specs()) == 5
    assert "**tre**" in conseguenze
    assert len(catalogue_v01().specs()) == 3
    assert "**quattro**" in conseguenze
