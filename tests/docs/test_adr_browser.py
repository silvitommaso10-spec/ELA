"""ADR 0052 and the running code describe the same browser, the same rows and the same totals.

This is where the **pin on today's totals** lives since M13.4: an ADR is immutable, so each older
one keeps saying the number it saw, and the ADR that last changed a number carries the assertion
about the tree as it is now — the capabilities (thirteen), the ones that travel (four) and stay
(nine), the rules (unchanged), the ports (a twenty-ninth: the browser) and the routes (unchanged).
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.permissions import BROWSER_ACT, BROWSER_READ, production_catalogue
from ela.ports import Browser
from ela.testing.fakes import FakeBrowser
from ela.tools.browser import BrowserActTool, BrowserReadTool
from ela.tools.verifiers import BrowserActVerifier, BrowserReadVerifier
from tests.architecture.rules import MACHINE_LIBRARIES, RULES
from tests.contracts.protocols import members, port_protocols
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_filesystem import verifiers_today

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0052-browser.md"
SPEC_PATH = ROOT / "docs" / "milestones" / "M13.4.md"
TOOL_ROW = re.compile(
    r"^\| `(browser\.\w+)` \| `(\w+)` \| `([\w-]+)` \| (sì|no) \| (.+?) \| (.+?) \|$"
)
VERIFIER_ROW = re.compile(r"^\| `(browser\.\w+)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$")
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


def test_the_capabilities_of_today_are_thirteen_and_four_of_them_travel(tmp_path: Path) -> None:
    catalogue = [spec.id for spec in production_catalogue().specs()]
    declared = [v.reads_the_machine for v in verifiers_today(tmp_path).verifiers()]

    assert len(catalogue) == 13
    assert catalogue[-2:] == [BROWSER_READ, BROWSER_ACT]
    assert sorted(declared) == [False] * 4 + [True] * 9
    assert "**tredici**" in conseguenze()
    assert "**quattro viaggiano, nove no**" in conseguenze()


def test_the_conseguenze_count_the_rules_the_ports_and_the_routes_of_today() -> None:
    text = conseguenze()

    assert "**cinquantasette**" in text
    assert len(RULES) == 57, "no rule is new: rule 32 names playwright among its ways out"
    assert "**ventinove**" in text
    assert len(tuple(port_protocols())) == 29
    assert "**quarantanove**" in text
    assert len(coded_routes()) == 49


# ----------------------------------------------------------------------------------------
# The rows this ADR writes
# ----------------------------------------------------------------------------------------


def test_the_tool_rows_are_the_running_tools() -> None:
    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := TOOL_ROW.match(line))
    }

    assert set(rows) == {BROWSER_READ, BROWSER_ACT}
    for tool in (BrowserReadTool, BrowserActTool):
        capability = BROWSER_READ if tool is BrowserReadTool else BROWSER_ACT
        _, class_name, name, idempotent, errors, numbers = rows[capability]
        assert class_name == tool.__name__
        assert name == ("browser-read" if tool is BrowserReadTool else "browser-act")
        assert (idempotent == "sì") is tool.idempotent
        assert codes(errors) == tool.error_codes
        assert codes(numbers) == tool.audit_numbers


def test_the_verifier_rows_are_the_running_verifiers() -> None:
    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := VERIFIER_ROW.match(line)) and match.group(2).endswith("Verifier")
    }

    for verifier in (
        BrowserReadVerifier(FakeBrowser(), 30.0),
        BrowserActVerifier(FakeBrowser(), 30.0),
    ):
        _, class_name, name, conditions, failures = rows[verifier.capability_id]
        assert class_name == type(verifier).__name__
        assert name == verifier.name
        assert codes(conditions) == verifier.conditions
        assert codes(failures) == {
            code for code in verifier.failure_codes if not code.startswith("verification.")
        }


def test_the_port_row_is_the_running_port() -> None:
    line = next(line for line in adr_text().splitlines() if line.startswith("| `Browser` |"))

    assert frozenset(CODE.findall(line.split("|")[4])) == frozenset(members(Browser))


def test_playwright_is_one_of_the_ways_out_of_rule_32() -> None:
    assert "playwright" in MACHINE_LIBRARIES
    assert "MACHINE_LIBRARIES" in adr_text()


# ----------------------------------------------------------------------------------------
# What the ADR declares, and where it points
# ----------------------------------------------------------------------------------------


def test_the_debt_of_the_stop_given_halfway_has_an_owner_a_day_and_its_defence() -> None:
    text = adr_text()
    section = text.split("### 15. Un debito datato:", 1)[1].split("\n### ", 1)[0]

    assert "**Debito a carico di M6.3c**, dichiarato il **2026-09-29**" in section
    assert "prima milestone dopo M13.4" in section
    defence = "tests/api/test_browser_stopped_midway.py"
    test = "test_a_browser_step_stopped_midway_is_the_defect_of_m6_3c"
    assert f"`{defence}::{test}`" in section.replace("\n", "")
    assert f"def {test}(" in (ROOT / defence).read_text(encoding="utf-8")


def test_the_answer_to_the_fingerprint_is_written_in_the_milestone_before_regenerating() -> None:
    spec = SPEC_PATH.read_text(encoding="utf-8")

    assert "La risposta all'impronta di ADR 0044 §6, scritta qui come il file esige:" in spec
    assert "`browser.read` e\n`browser.act` non hanno una vista propria" in spec


def test_it_writes_no_constraint_heading_and_no_table_of_consumption() -> None:
    """Census C10: either would break a count that is not this milestone's."""
    text = adr_text()

    assert "### Vincoli dichiarati" not in text
    assert "| Regola | Consuma |" not in text
