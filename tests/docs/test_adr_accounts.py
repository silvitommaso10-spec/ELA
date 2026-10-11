"""ADR 0063 against the code (M13.9): the browser with your accounts, and the session's cover.

The ADR is written with the implementation, a section at a time; what this file holds to the code
grows with it. Today: the totals of today, which this ADR is the last to change.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.permissions import (
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ_AS_YOU,
    POLICY_VERSION,
    production_catalogue,
)
from ela.ports import AccountBrowser
from ela.testing.fakes import FakeAccountBrowser
from ela.tools.account import (
    AccountActTool,
    AccountActVerifier,
    AccountReadTool,
    AccountReadVerifier,
    LoginTool,
    LoginVerifier,
)
from tests.architecture.rules import RULES
from tests.contracts.protocols import members, port_protocols
from tests.docs.test_adr_browser import CODE, TOOL_ROW, VERIFIER_ROW, codes
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0063-browser-with-your-accounts.md"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0062: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**sessantanove**" in text
    assert len(RULES) == 69
    assert set(RULES) - set(_rules_up_to(66)) == {
        "the-room-s-word-is-the-room-s",
        "a-secret-is-opened-only-by-an-adapter",
        "the-profile-s-folder-is-its-adapter-s",
    }
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentacinque**" in text and len(tuple(port_protocols())) == 35
    assert "**sessantatré**" in text and len(coded_routes()) == 63
    assert "**trentaquattro**" in text.split("i port diventano", 1)[1].split("le rotte", 1)[1]
    assert len(coded_commands()) == 34
    assert "**diciassette**" in text and len(production_catalogue().specs()) == 17
    assert "**sei**" in text and len(Kind) == 6


def test_the_version_of_the_policy_is_the_one_this_adr_gives_it() -> None:
    assert f"`POLICY_VERSION` diventa `{POLICY_VERSION}`" in adr_text()


# ----------------------------------------------------------------------------------------
# §5 — the rows this ADR writes: the tools and the verifiers
# ----------------------------------------------------------------------------------------


def test_the_tool_rows_are_the_running_tools() -> None:
    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := TOOL_ROW.match(line))
    }
    running = {
        BROWSER_READ_AS_YOU: AccountReadTool,
        BROWSER_ACT_AS_YOU: AccountActTool,
        BROWSER_LOGIN: LoginTool,
    }

    assert set(rows) == set(running)
    for capability, tool in running.items():
        _, class_name, name, idempotent, errors, numbers = rows[capability]
        assert class_name == tool.__name__
        assert name == capability.replace(".", "-").replace("_", "-")
        assert (idempotent == "sì") is tool.idempotent
        assert codes(errors) == tool.error_codes
        assert codes(numbers) == tool.audit_numbers


def test_the_verifier_rows_are_the_running_verifiers() -> None:
    rows = {
        match.group(1): match.groups()
        for line in adr_text().splitlines()
        if (match := VERIFIER_ROW.match(line)) and match.group(2).endswith("Verifier")
    }
    running = (
        AccountReadVerifier(FakeAccountBrowser(), 30.0),
        AccountActVerifier(FakeAccountBrowser(), 30.0),
        LoginVerifier(FakeAccountBrowser(), 30.0),
    )

    assert set(rows) == {verifier.capability_id for verifier in running}
    for verifier in running:
        _, class_name, name, conditions, failures = rows[verifier.capability_id]
        assert class_name == type(verifier).__name__
        assert name == verifier.name
        assert codes(conditions) == verifier.conditions
        assert codes(failures) == {
            code for code in verifier.failure_codes if not code.startswith("verification.")
        }


def test_the_port_row_is_the_running_port() -> None:
    line = next(line for line in adr_text().splitlines() if line.startswith("| `AccountBrowser` |"))

    assert frozenset(CODE.findall(line.split("|")[4])) == frozenset(members(AccountBrowser))


def test_a_tool_row_that_forgets_a_code_is_found() -> None:
    """The negative case of the comparison above: one code less in a row is one code less read."""
    row = next(line for line in adr_text().splitlines() if TOOL_ROW.match(line))
    match = TOOL_ROW.match(row.replace("`browser.profile_busy`, ", "", 1))

    assert match is not None
    assert codes(match.group(5)) == AccountReadTool.error_codes - {"browser.profile_busy"}
