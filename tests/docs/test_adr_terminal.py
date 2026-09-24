"""ADR 0047 and the running code describe the same terminal, the same rows and the same totals.

This is where the **pin on today's totals** lives since M13.2 (the precedent of M13.1 dec. K): an
ADR is immutable, so each older one keeps saying the number it saw, and the ADR that last changed a
number carries the assertion about the tree as it is now — the capabilities (eleven), the ones
that travel (four) and stay (seven), the rules, the ports (a twenty-seventh: the launcher) and the
routes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ela.tools.programs import PROGRAM_CHANGED, Programs
from ela.tools.terminal import TerminalRunTool

from ela.permissions import TERMINAL_RUN, production_catalogue
from ela.tools.verifiers import TerminalRunVerifier
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_filesystem import verifiers_today
from tests.tools.terminals import no_programs

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0047-terminal.md"
TOOL_ROW = re.compile(
    r"^\| `(terminal\.run)` \| `(\w+)` \| `([\w-]+)` \| (sì|no) \| (.+?) \| (.+?) \|$"
)
VERIFIER_ROW = re.compile(r"^\| `(terminal\.run)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$")
CODE = re.compile(r"`([^`]+)`")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def codes(cell: str) -> frozenset[str]:
    return frozenset(CODE.findall(cell))


# ----------------------------------------------------------------------------------------
# The totals of today, pinned here because this ADR is the one that changed them
# ----------------------------------------------------------------------------------------


def test_the_capabilities_of_today_are_eleven_and_four_of_them_travel(tmp_path: Path) -> None:
    catalogue = [spec.id for spec in production_catalogue().specs()]
    declared = [v.reads_the_machine for v in verifiers_today(tmp_path).verifiers()]

    assert len(catalogue) == 11
    assert sorted(declared) == [False] * 4 + [True] * 7
    assert "**undici**" in conseguenze()
    assert "**quattro viaggiano, sette no**" in conseguenze()


def test_the_conseguenze_count_the_rules_the_ports_and_the_routes_of_today() -> None:
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57
    assert "**ventisette**" in text
    assert len(tuple(port_protocols())) == 27
    assert "CommandLauncher" in {port.__name__ for port in port_protocols()}
    assert "**quarantotto**" in text
    assert len(coded_routes()) == 48


# ----------------------------------------------------------------------------------------
# The rows this ADR writes
# ----------------------------------------------------------------------------------------


def test_the_tool_row_is_the_running_tool() -> None:
    rows = [match for line in adr_text().splitlines() if (match := TOOL_ROW.match(line))]

    (row,) = rows
    _, class_name, name, idempotent, errors, numbers = row.groups()
    assert class_name == TerminalRunTool.__name__
    assert name == "terminal-run"
    assert (idempotent == "sì") is TerminalRunTool.idempotent
    assert codes(errors) == TerminalRunTool.error_codes
    assert codes(numbers) == TerminalRunTool.audit_numbers


def test_the_verifier_row_is_the_running_verifier() -> None:
    rows = [match for line in adr_text().splitlines() if (match := VERIFIER_ROW.match(line))]
    verifier = TerminalRunVerifier(no_programs())

    (row,) = [match for match in rows if match.group(2) == TerminalRunVerifier.__name__]
    _, _, name, conditions, failures = row.groups()
    assert name == verifier.name
    assert codes(conditions) == verifier.conditions
    assert codes(failures) == verifier.failure_codes - {
        code for code in verifier.failure_codes if code.startswith("verification.")
    }


def test_the_refusal_it_quotes_is_the_one_the_tool_gives(tmp_path: Path) -> None:
    """A message quoted in a document and nowhere else drifts the first time somebody edits it."""
    program = tmp_path.resolve() / "eco"
    program.write_text("#!/bin/sh\n", encoding="utf-8")
    program.chmod(0o755)
    entry = str(program).lstrip("/")
    programs = Programs.fixed([entry])
    program.write_text("#!/bin/sh\necho altro\n", encoding="utf-8")

    problem = programs.problem(entry)

    assert problem is not None and problem.code == PROGRAM_CHANGED
    assert "changed after ELA started (an update, for instance): restart ELA to accept it" in (
        problem.message
    )
    assert "changed after ELA started (an update, for instance): restart ELA to accept it" in (
        adr_text()
    )


# ----------------------------------------------------------------------------------------
# What it revises, named where it is written
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "named",
    [
        "ADR 0045 §6-bis",
        "ADR 0029 §14",
        "ADR 0040 §5",
        "ADR 0038 §11",
        "ADR 0038 §16",
        "ADR 0026 §7",
        "`docs/adr/0045-filesystem-and-high.md:140`",
    ],
)
def test_it_names_every_line_it_revises_or_corrects(named: str) -> None:
    assert named in adr_text()


def test_the_revised_adrs_say_so_on_their_status_line() -> None:
    """The form of ADR 0046: a revised ADR is not rewritten, its «Stato:» line names who revises."""
    for revised in ("0029-screen-capture.md", "0045-filesystem-and-high.md"):
        status = next(
            line
            for line in (ADR_DIR / revised).read_text(encoding="utf-8").splitlines()
            if line.startswith("- **Stato:**")
        )
        assert "ADR 0047" in status, revised


def test_it_names_the_new_channel_of_the_audit_and_says_why() -> None:
    """Domanda 2: «ADR 0047 lo nomina come canale nuovo dell'audit e dice perché»."""
    text = adr_text()

    assert "canale nuovo dell'audit" in text
    assert "solo interi" in text
    assert "fs.read" in text and "non lo adotta" in text


def test_it_writes_the_three_decided_questions_and_the_facts_found_aligning() -> None:
    text = adr_text()

    assert "un link dichiarato" in text.lower()
    assert "terminal.stopped" in text
    assert "M13.3" in text, "the debt of Windows, dated and handed on"
    assert "Misurato" in text and " ms" in text, "the time from the timeout to the empty group"


def test_the_capability_it_adds_is_the_last_of_the_catalogue() -> None:
    assert production_catalogue().specs()[-1].id == TERMINAL_RUN
