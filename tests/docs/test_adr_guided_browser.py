"""ADR 0060 (M14.3): the browser guided by a model, and what it names is what the code has.

The capability, the ports, the route, the routing row and the stop point are read by the test of
their kind (``test_adr_catalogue``, ``test_adr_ports``, ``test_adr_composition``,
``test_adr_routing``, ``test_adr_stop``); this file holds what is only this ADR's: the rows of its
tool and its verifier, the codes of the budget, rule 65, the revisions it writes on the ADRs it
revises, the state it is in — and **the pin on today's totals**, taken over from ADR 0059, because
this ADR changes them.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ela.api.security import Kind
from ela.executive.spending import BudgetCode
from ela.permissions import BROWSER_GUIDED, production_catalogue
from ela.tools.guided import BrowserGuidedTool, BrowserGuidedVerifier
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import GUIDED_PORTS
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to
from tests.tools.test_remote_verification import STAYS, TRAVELS

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0060-guided-browser.md"
INDEX_ROW = re.compile(
    r"^\| \[0060\]\(0060-guided-browser\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE
)
TOOL_ROW = re.compile(
    r"^\| `(browser\.guided)` \| `(\w+)` \| `([\w-]+)` \| (sì|no) \| (.+?) \| (.+?) \|$"
)
VERIFIER_ROW = re.compile(
    r"^\| `(browser\.guided)` \| `(\w+Verifier)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$"
)
REFUSAL_ROW = re.compile(r"^\| [^|]+ \| `(guided\.\w+)` \|$", re.MULTILINE)
CODE = re.compile(r"`([\w.]+)`")
REVISED = (
    "0026-placement-as-data.md",
    "0052-browser.md",
    "0057-spending-cap.md",
    "0058-planner.md",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def flat() -> str:
    return " ".join(adr_text().split())


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def status_of(text: str) -> str:
    return text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def test_the_conseguenze_count_the_totals_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0059: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]

    assert "**sessantacinque**" in text
    assert len(RULES) == 65
    assert set(RULES) - set(_rules_up_to(64)) == {"who-spends-passes-the-gate"}
    assert "**quindici**" in text and len(contracts) == 15
    assert "**trentatré**" in text and len(tuple(port_protocols())) == 33
    assert {port.__name__ for port in port_protocols()} >= GUIDED_PORTS
    assert "**cinquantadue**" in text and len(coded_routes()) == 52
    assert "**ventotto**" in text and len(coded_commands()) == 28
    assert "**quattordici**" in text and len(production_catalogue().specs()) == 14
    assert "**quattro**" in text and len(TRAVELS) == 4 and BROWSER_GUIDED in STAYS
    assert "**sei**" in text and len(Kind) == 6


def test_the_rule_it_writes_is_registered_with_its_number() -> None:
    assert "**La regola 65, `who-spends-passes-the-gate`**" in flat()
    assert "the other road is rule 65's" in flat()


def test_the_row_of_the_tool_is_the_tool_s() -> None:
    (row,) = [match.groups() for line in adr_text().splitlines() if (match := TOOL_ROW.match(line))]
    capability, klass, name, idempotent, errors, numbers = row

    assert (capability, klass, name) == (
        BROWSER_GUIDED,
        BrowserGuidedTool.__name__,
        "browser-guided",
    )
    assert (idempotent == "sì") is BrowserGuidedTool.idempotent
    assert frozenset(CODE.findall(errors)) == BrowserGuidedTool.error_codes
    assert frozenset(CODE.findall(numbers)) == BrowserGuidedTool.audit_numbers


def test_the_row_of_the_verifier_is_the_verifier_s() -> None:
    (row,) = [
        match.groups() for line in adr_text().splitlines() if (match := VERIFIER_ROW.match(line))
    ]
    capability, klass, name, conditions, failures = row

    assert (capability, klass, name) == (
        BROWSER_GUIDED,
        BrowserGuidedVerifier.__name__,
        "browser-guided-verifier",
    )
    assert frozenset(CODE.findall(conditions)) == BrowserGuidedVerifier.conditions
    assert frozenset(CODE.findall(failures)) == BrowserGuidedVerifier.failure_codes - frozenset(
        code for code in BrowserGuidedVerifier.failure_codes if code.startswith("verification.")
    )


def test_the_refusals_of_the_budget_are_the_budget_s_codes() -> None:
    assert set(REFUSAL_ROW.findall(adr_text())) == {code.value for code in BudgetCode}


def test_it_is_proposed_until_the_proof_by_hand() -> None:
    (row,) = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))

    assert row[1] == "Proposta"
    assert status_of(adr_text()).strip().startswith("Proposta il **2026-10-09**")
    assert "sezione 26" in status_of(adr_text())


def test_the_adrs_it_revises_say_so_on_their_state_line() -> None:
    """The form of ADR 0046 and ADR 0049: an ADR is not rewritten, its «Stato:» line points on."""
    for name in REVISED:
        status = status_of((ADR_DIR / name).read_text(encoding="utf-8"))
        assert "**Riletta da ADR 0060 (M14.3)**" in status, name


def test_the_four_answers_of_section_57_are_written() -> None:
    text = flat()
    for answer in ("**Il fornitore**", "**I dati**", "**Il perché**", "**La policy**"):
        assert answer in text


def test_it_writes_no_section_of_declared_constraints() -> None:
    """Its constraints go under «Conseguenze», not under a heading another test counts."""
    assert "### Vincoli dichiarati" not in adr_text()
