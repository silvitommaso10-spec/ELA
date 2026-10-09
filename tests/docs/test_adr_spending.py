"""ADR 0057 (M14.1): the spending cap, and what it names is what the code has.

The variable, the column, the route, the command and the operation are each read by the test of
their kind (``test_adr_composition``, ``test_adr_cli``, ``test_adr_persistence``,
``test_adr_engine``, ``test_adr_ports``, ``test_adr_executor``, ``test_adr_provider``); this file
holds what is only this ADR's: the four sentences of a denial with their codes, the worst cases of
its table, the revisions it writes on the ADRs it revises, the totals of today — the pin moves here
from ADR 0054, because this ADR changes them — and the state of the project in ``docs/STATO.md``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from ela.composition.settings import SpendingSettings
from ela.domain import WorstCase
from ela.executive.spending import (
    CAP_VARIABLE,
    Refusal,
    SpendingCode,
    dollars,
    judge,
    month_of,
)
from ela.ports import SPENDING_OVER_RESERVATION
from ela.providers.anthropic.models import MODELS
from ela.providers.anthropic.pricing import worst_cost
from ela.providers.anthropic.settings import DEFAULT_MAX_OUTPUT_TOKENS
from tests.contracts.protocols import port_protocols
from tests.docs.guided_ports import GUIDED_PORTS
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes, routes_after_0057
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0057-spending-cap.md"
STATO = ROOT / "docs" / "STATO.md"
INDEX_ROW = re.compile(r"^\| \[0057\]\(0057-spending-cap\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE)
WORST_ROW = re.compile(r"^\| (Opus 5\.5|Sonnet 5\.5|Haiku 4\.5) \| ([\d,]+) \$ \|$", re.MULTILINE)
REVISED = (
    "0020-provider-anthropic.md",
    "0021-started-protocol-and-model-complete.md",
    "0022-model-router.md",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def test_the_conseguenze_count_the_rules_the_ports_the_routes_and_the_commands_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0054, moved on to ADR 0058 (M14.2): what
    this ADR saw, counted without what came after it."""
    text = conseguenze()

    assert "**sessantuno**" in text
    assert len(_rules_up_to(61)) == 61  # rules 62 and 63 are ADR 0058's
    assert set(_rules_up_to(61)) - set(_rules_up_to(59)) == {
        "a-tool-that-spends-is-neither-repeated-nor-moved",
        "who-calls-the-model-bounds-the-call",
    }
    assert "**trenta**" in text
    assert len(tuple(p for p in port_protocols() if p.__name__ not in GUIDED_PORTS)) == 30
    assert "**cinquanta**" in text
    assert len(coded_routes() - routes_after_0057()) == 50
    assert "**ventotto**" in text
    assert len(coded_commands()) == 28


def test_the_rules_it_names_are_registered_with_their_numbers() -> None:
    text = adr_text()

    assert "la\nregola 60, `a-tool-that-spends-is-neither-repeated-nor-moved`" in text
    assert "la regola 61, `who-calls-the-model-bounds-the-call`" in text


def test_the_line_it_names_is_the_one_settings_read() -> None:
    (field,) = SpendingSettings.model_fields
    assert f"`{CAP_VARIABLE}`" in adr_text()
    assert f"ELA_{field.upper()}" == CAP_VARIABLE


def test_the_four_sentences_of_a_denial_are_the_gate_s_with_their_codes() -> None:
    """Each sentence of §7 begins the way the gate's reason begins, and each names its code."""
    text = " ".join(adr_text().split())
    month = month_of(datetime(2026, 10, 6, tzinfo=UTC))
    worst = WorstCase(amount=Decimal(4), currency="USD", model="m", input_tokens=1, output_tokens=1)
    no_cap = judge(cap=None, worst=worst, month=month)
    unpriced = judge(cap=Decimal(5), worst=worst.model_copy(update={"amount": None}), month=month)
    assert isinstance(no_cap, Refusal) and isinstance(unpriced, Refusal)
    assert f"`{SpendingCode.NO_CAP.value}`: «{no_cap.reason}»" in text
    said = unpriced.reason.replace("m has no price", "<modello> has no price", 1)
    assert f"`{SpendingCode.UNPRICED.value}`: «{said}»" in text
    assert f"`{SpendingCode.UNBOUNDED.value}`: «this call cannot be bounded:" in text
    assert f"`{SpendingCode.OVER_CAP.value}`: «the monthly cap would be crossed: spent S" in text
    assert f"`{SPENDING_OVER_RESERVATION}`" in text


def test_the_table_of_the_worst_cases_is_the_price_list_s() -> None:
    """Decision 1: the three costs are a declared constraint, and they are the code's numbers."""
    rows = {
        name: Decimal(amount.replace(",", ".")) for name, amount in WORST_ROW.findall(adr_text())
    }
    ids = {
        "Opus 5.5": "claude-opus-5-5",
        "Sonnet 5.5": "claude-sonnet-5-5",
        "Haiku 4.5": "claude-haiku-4-5-20251001",
    }

    assert set(rows) == set(ids)
    for name, amount in rows.items():
        model = MODELS[ids[name]]
        assert worst_cost(model, output_tokens=DEFAULT_MAX_OUTPUT_TOKENS) == amount, name
    assert dollars(rows["Opus 5.5"]) == "4.065536"


def test_the_adrs_it_revises_say_so_on_their_state_line() -> None:
    """The form of ADR 0046 and ADR 0049: an ADR is not rewritten, its «Stato:» line points on."""
    for name in REVISED:
        text = (ADR_DIR / name).read_text(encoding="utf-8")
        status = text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
        assert "ADR 0057" in status, name
        assert "(M14.1)" in status, name


def test_the_budget_lines_it_revises_are_still_there_as_they_were_written() -> None:
    for name in REVISED[1:]:
        assert "**Nessun budget**" in (ADR_DIR / name).read_text(encoding="utf-8"), name


def test_it_was_accepted_only_after_the_proof_by_hand(shown: str = "2026-10-07") -> None:
    """It stayed «Proposta» until §23 passed on the Mac and the PC, and was accepted in the same
    commit that gave the guide the proof: an ADR accepted over a guide whose proof is still to do
    would be the thing that was refused (the form of ADR 0040)."""
    (row,) = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))
    status = adr_text().split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
    guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
    section = guide.split("## 23. ", 1)[1].split("\n## ", 1)[0]

    assert row[1] == "Accettata"
    assert status.strip().startswith(f"Accettata il **{shown}**")
    assert "§23" in status and "prova-m14.1-20261007-213354.txt" in status
    assert "**Da fare.**" not in section
    assert "**Da fare.**" not in adr_text()
    assert f"**Fatta da Tommaso il {shown} sul branch**" in section


def test_stato_says_who_enforces_the_cap_now() -> None:
    text = STATO.read_text(encoding="utf-8")
    section = text.split("### 5.9 Il tetto di spesa", 1)[1].split("\n### ", 1)[0]

    assert "Oggi **nessuno lo fa rispettare**" not in section
    assert "**Da M14.1 lo fa rispettare ELA**" in section
    assert CAP_VARIABLE in section
    assert "adr/0057-spending-cap.md" in section
