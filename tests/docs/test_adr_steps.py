"""ADR 0065 — the browser in more steps (M13.10) — held to the code.

The ADR is written with the implementation, a section at a time; what this file holds to the code
grows with it. Today: the bag of what a question named, the rule it adds — the seventy-first, and
no other —, and the pin on **today's** totals, taken over from ADR 0064.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.executive import executor
from ela.permissions import production_catalogue
from ela.ports import (
    BROWSER_LOGIN_FORM_GONE,
    CONTINUES,
    LOGIN_FORM,
    LOGIN_FORM_AMBIGUOUS,
    LOGIN_FORM_NOT_FOUND,
    NO_LOGIN_FORM,
    PROFILE_TASK,
    Prospect,
)
from ela.tools.account import (
    ENTRY_NOT_NAMED,
    LOGIN_FORM_STILL_THERE,
    STOP_A_TASK,
    LoginTool,
    LoginVerifier,
)
from ela.tools.browser import (
    LEFT_WHILE_WAITING,
    NO_PAGE_TO_CONTINUE,
    BrowserActTool,
    BrowserReadTool,
)
from ela.tools.guided import LOOKS_OF_A_LOGIN, SENDS_AS_YOU, SESSION_AS_YOU
from tests.architecture.rules import NAMED_CONSTANT, RULES
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import STEPS_PORTS
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0065-browser-steps.md"
THE_RULE = "named-reaches-the-tool-only"


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


# ----------------------------------------------------------------------------------------
# §2 — what the yes named reaches the tool with the yes
# ----------------------------------------------------------------------------------------


def test_the_bag_the_adr_names_is_the_executor_s_and_the_prospect_s() -> None:
    text = adr_text()

    assert executor.NAMED == "named" and "`named`" in text
    assert "named" in Prospect.__dataclass_fields__ and "`Prospect.named`" in text
    assert f"`{ENTRY_NOT_NAMED}`" in text
    assert "`vault.entry_forgotten` è ritirato" in text


# ----------------------------------------------------------------------------------------
# §3 — the page between two steps of a task
# ----------------------------------------------------------------------------------------


def test_the_names_of_the_page_between_steps_are_the_code_s() -> None:
    text = adr_text()

    assert f"`{CONTINUES}`" in text and f"`{NO_PAGE_TO_CONTINUE}`" in text
    assert f"`{LEFT_WHILE_WAITING}`" in text and f"**`{PROFILE_TASK}`**" in text
    assert "`ela task cancel`" in text and STOP_A_TASK == "ela task cancel"
    assert NO_PAGE_TO_CONTINUE in BrowserReadTool.error_codes & BrowserActTool.error_codes
    assert NO_PAGE_TO_CONTINUE not in LoginTool.error_codes, "a login never continues"
    assert LEFT_WHILE_WAITING not in BrowserReadTool.audit_numbers | BrowserActTool.audit_numbers


# ----------------------------------------------------------------------------------------
# §4 — the login the model asks for
# ----------------------------------------------------------------------------------------


def test_the_names_of_the_login_of_the_model_are_the_code_s() -> None:
    text = adr_text()

    for name in (LOGIN_FORM, NO_LOGIN_FORM, LOGIN_FORM_NOT_FOUND, LOGIN_FORM_AMBIGUOUS):
        assert f"`{name}`" in text, name
    assert f"**`{BROWSER_LOGIN_FORM_GONE}`**" in text
    assert BROWSER_LOGIN_FORM_GONE in LoginVerifier.conditions
    assert LOGIN_FORM_STILL_THERE in LoginVerifier.failure_codes
    assert [tool.name for tool in SESSION_AS_YOU.tools] == ["read", "act", "login"]
    assert "**conta due gesti**" in text and LOOKS_OF_A_LOGIN == 2


def test_the_sentence_of_what_leaves_is_the_one_of_decision_32() -> None:
    said = (
        "the text of the pages read as you, and of a login where its page ended, its status and "
        "whether its form was still there — never the entry, the username or the password"
    )
    assert said in SENDS_AS_YOU and said in " ".join(adr_text().split())


# ----------------------------------------------------------------------------------------
# The rule it adds, and the totals of today
# ----------------------------------------------------------------------------------------


def test_the_rule_it_adds_is_the_seventy_first_and_is_anchored_to_the_constant() -> None:
    assert "**Regola di architettura 71**" in conseguenze()
    assert set(_rules_up_to(71)) - set(_rules_up_to(70)) == {THE_RULE}
    assert f"`{NAMED_CONSTANT}`" in conseguenze()
    assert getattr(executor, NAMED_CONSTANT) == executor.NAMED


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0064: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**settantuno**" in text
    assert len(RULES) == 71
    assert set(RULES) - set(_rules_up_to(70)) == {THE_RULE}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentasei**" in text and len(tuple(port_protocols())) == 36
    assert {port.__name__ for port in port_protocols()} >= STEPS_PORTS == {"TaskPages"}
    assert "**settantadue**" in text and len(coded_routes()) == 72
    assert "**trentanove**" in text and len(coded_commands()) == 39
    assert "**diciotto**" in text and len(production_catalogue().specs()) == 18
    assert "**sei**" in text and len(Kind) == 6
