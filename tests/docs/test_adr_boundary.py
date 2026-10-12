"""ADR 0064 — the boundary of the browser: look, do not redo (M13.4f) — held to the code.

What the ADR says it adds is in the code, by the names it gives; the rule it adds is the
seventieth, and no other; the ADRs it revises say so on their «Stato:» line, and no other does;
and the pin on **today's** totals is here, taken over from ADR 0063.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.infrastructure.machine import browser as adapter
from ela.permissions import production_catalogue
from ela.ports import AccountBrowser, AnotherPage, Browser, Glanced, LeftSite
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser
from ela.tools.account import (
    AccountActTool,
    AccountActVerifier,
    AccountReadTool,
    AccountReadVerifier,
    LoginTool,
    LoginVerifier,
)
from ela.tools.browser import ANOTHER_PAGE, LEFT_SITE, BrowserActTool, BrowserReadTool
from ela.tools.verifiers import (
    BROWSER_ANOTHER_PAGE,
    BROWSER_LEFT_SITE,
    BrowserActVerifier,
    BrowserReadVerifier,
)
from tests.architecture.rules import COMMANDS_NEVER_SENT, REDOING_CALLS, RULES
from tests.contracts.protocols import members, port_protocols
from tests.docs.boundary_additions import added_codes, added_members
from tests.docs.test_adr_browser import codes
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0064-browser-boundary.md"
REVISED_MARK = "**Rivista da ADR 0064 (M13.4f)**"
REVISED_ROW = re.compile(r"^- \*\*ADR (\d{4})\b")
THE_RULE = "the-gate-looks-and-does-not-redo"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def adr_0052() -> str:
    return (ADR_PATH.parent / "0052-browser.md").read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# What it adds is in the code, by the names it gives
# ----------------------------------------------------------------------------------------


def test_the_member_and_the_names_it_adds_to_the_port_are_the_port_s() -> None:
    """Its table «Port estesi» is what the port has beyond the row of ADR 0052 — and no more."""
    text = adr_text()
    row = next(line for line in adr_0052().splitlines() if line.startswith("| `Browser` |"))

    assert added_members() == {"Browser": frozenset(members(Browser)) - codes(row.split("|")[4])}
    assert added_members()["Browser"] == {"another"} <= members(AccountBrowser)
    assert f"`{LeftSite.__name__}`" in text and f"`{AnotherPage.__name__}`" in text
    assert "another" in Glanced.__dataclass_fields__


def test_the_codes_it_gives_the_verifiers_are_the_running_verifiers_and_no_other_s() -> None:
    """``browser.left_site`` for every verifier of the browser; ``browser.another_page`` for the
    ones that wait for a text after a gesture, and not for the ones that read."""
    text = adr_text()
    reading = (
        BrowserReadVerifier(FakeBrowser(), 30.0),
        AccountReadVerifier(FakeAccountBrowser(), 30.0),
    )
    acting = (
        BrowserActVerifier(FakeBrowser(), 30.0),
        AccountActVerifier(FakeAccountBrowser(), 30.0),
        LoginVerifier(FakeAccountBrowser(), 30.0),
    )

    assert f"`{BROWSER_LEFT_SITE}`" in text and f"`{BROWSER_ANOTHER_PAGE}`" in text
    assert BROWSER_LEFT_SITE == LEFT_SITE, "the tools' own code: the same refusal, met later"
    assert all(BROWSER_LEFT_SITE in verifier.failure_codes for verifier in (*reading, *acting))
    assert all(BROWSER_ANOTHER_PAGE in verifier.failure_codes for verifier in acting)
    assert not any(BROWSER_ANOTHER_PAGE in verifier.failure_codes for verifier in reading)
    # And its table says exactly that, verifier by verifier.
    assert added_codes() == {
        str(verifier.capability_id): (
            type(verifier).__name__,
            frozenset({BROWSER_LEFT_SITE})
            | (frozenset({BROWSER_ANOTHER_PAGE}) if verifier in acting else frozenset()),
        )
        for verifier in (*reading, *acting)
    }


def test_the_key_it_gives_the_results_is_in_every_tool_it_names_and_in_no_audit() -> None:
    text = adr_text()
    tools = (BrowserReadTool, BrowserActTool, AccountReadTool, AccountActTool, LoginTool)

    assert f"`{ANOTHER_PAGE}`" in text
    for tool in tools:
        assert ANOTHER_PAGE in tool.output_keys and ANOTHER_PAGE not in tool.audit_numbers


def test_the_address_of_the_check_is_the_one_the_adapter_asks_for() -> None:
    assert f"`{adapter.CHECK}`" in adr_text()


# ----------------------------------------------------------------------------------------
# The rule it adds, and the totals of today
# ----------------------------------------------------------------------------------------


def test_the_rule_it_adds_is_the_seventieth_and_says_what_it_forbids() -> None:
    assert "**Regola di architettura 70**" in conseguenze()
    assert set(_rules_up_to(70)) - set(_rules_up_to(69)) == {THE_RULE}
    assert "route" in REDOING_CALLS and "detach" in REDOING_CALLS
    for command in COMMANDS_NEVER_SENT:
        assert f"`{command}`" in conseguenze(), f"the rule of the ADR does not name {command}"


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0063: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settanta**" in text
    assert len(RULES) == 70
    assert set(RULES) - set(_rules_up_to(69)) == {THE_RULE}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentacinque**" in text and len(tuple(port_protocols())) == 35
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**diciotto**" in text and len(production_catalogue().specs()) == 18
    assert "**sei**" in text and len(Kind) == 6


# ----------------------------------------------------------------------------------------
# The ADRs it revises say so
# ----------------------------------------------------------------------------------------


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def adrs() -> dict[str, Path]:
    """Every ADR of the repository but this one, by its number."""
    return {path.name[:4]: path for path in ADR_PATH.parent.glob("[0-9]*.md") if path != ADR_PATH}


def revised_by_the_list() -> set[str]:
    """The numbers of the ADRs the list «Righe riviste» of this ADR names, one bullet each."""
    block = adr_text().split("**Righe riviste**", 1)[1].split("\n\n", 2)[1]
    return {match.group(1) for line in block.splitlines() if (match := REVISED_ROW.match(line))}


def written() -> dict[str, str]:
    """The text of every ADR of the repository but this one, by its number."""
    return {number: path.read_text(encoding="utf-8") for number, path in adrs().items()}


def revised_by_their_state(texts: dict[str, str]) -> set[str]:
    """The numbers of the ADRs whose «Stato:» line says this ADR is to be read beside them."""
    return {number for number, text in texts.items() if REVISED_MARK in status_of(text)}


def test_the_adrs_it_revises_say_so_on_their_state_line_and_no_other_does() -> None:
    """An ADR is not rewritten: its «Stato:» line points on. Closed both ways."""
    listed = revised_by_the_list()

    assert listed == {"0052", "0063"}
    assert listed == revised_by_their_state(written())


def test_a_revised_adr_that_does_not_say_so_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    silent = min(listed)
    texts[silent] = texts[silent].replace(REVISED_MARK, "", 1)

    assert revised_by_their_state(texts) == listed - {silent}


def test_an_adr_that_says_so_and_is_not_in_the_list_is_found() -> None:
    texts, listed = written(), revised_by_the_list()
    unlisted = min(set(texts) - listed)
    texts[unlisted] = texts[unlisted].replace("- **Stato:**", f"- **Stato:** {REVISED_MARK}", 1)

    assert revised_by_their_state(texts) == listed | {unlisted}


def test_it_stays_proposed_until_the_proof_of_m13_9_passes_on_this_repair() -> None:
    """Decision 130. The day the proof passes, the state changes with a commit of its own —
    and this line with it."""
    assert status_of(adr_text()).strip().startswith("Proposta")
