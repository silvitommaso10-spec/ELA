"""ADR 0058 says what the code does: the route, the command, the column, the operation, the codes,
the rules, the contract, the worst case and the totals of today (M14.2).

The pin on **today's** totals moves here from ADR 0057, the ADR that last changed them: the tests
of the earlier ADRs count what they saw, without what came after (ADR 0032 §17).
"""

from __future__ import annotations

import re
import tomllib
from decimal import Decimal
from pathlib import Path

from ela.executive.planner import PLANNER_CODES, PLANNING_OUTPUT_TOKENS
from ela.providers.anthropic.models import MODELS, OPUS_5_5
from ela.providers.anthropic.pricing import worst_cost
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands, documented_command_routes
from tests.docs.test_adr_composition import coded_routes, routes_after_0057
from tests.docs.test_adr_persistence import added_columns
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0058-planner.md"
PYPROJECT = ROOT / "pyproject.toml"
INDEX_ROW = re.compile(r"^\| \[0058\]\(0058-planner\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE)
CODE_ROW = re.compile(r"^\| `(planner\.\w+)` \| [^|]+ \|$", re.MULTILINE)
WORST_ROW = re.compile(r"^\| Opus 5\.5 \| ([\d,]+) \$ \|$", re.MULTILINE)
REVISED = (
    "0004-task-transitions.md",
    "0008-task-engine.md",
    "0011-permission-guardian.md",
    "0014-verification.md",
    "0022-model-router.md",
    "0023-composition-root-and-api.md",
    "0024-cli.md",
    "0032-context-core.md",
    "0052-browser.md",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def status() -> str:
    return adr_text().split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def contracts() -> list[dict[str, object]]:
    found: list[dict[str, object]] = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"][
        "importlinter"
    ]["contracts"]
    return found


def test_the_conseguenze_count_the_rules_the_contracts_the_ports_the_routes_and_the_commands() -> (
    None
):
    """The pin on today's totals, taken over from ADR 0057: it moves to the ADR that changes
    them."""
    text = conseguenze()

    assert "**sessantatré**" in text
    assert len(RULES) == 63
    assert set(RULES) - set(_rules_up_to(61)) == {
        "plans-enter-by-two-doors",
        "the-planner-names-no-device",
    }
    assert "**quindici**" in text
    assert len(contracts()) == 15
    assert "**trenta**" in text
    assert len(tuple(port_protocols())) == 30
    assert "**cinquantuno**" in text
    assert len(coded_routes()) == 51
    assert "**ventotto**" in text
    assert len(coded_commands()) == 28


def test_the_route_it_adds_is_the_planner_s_and_the_command_calls_both() -> None:
    assert routes_after_0057() == {("POST", "/tasks/{task_id}/planning")}
    assert {
        ("POST", "/tasks/{task_id}/plan"),
        ("POST", "/tasks/{task_id}/planning"),
    } <= documented_command_routes()


def test_the_column_it_adds_is_the_author_of_a_plan() -> None:
    assert added_columns()["0058"] == {"task_plans": ("author",)}


def test_the_codes_of_its_table_are_the_planner_s_and_nothing_else() -> None:
    assert set(CODE_ROW.findall(adr_text())) == PLANNER_CODES


def test_the_rules_it_names_are_registered_with_their_numbers() -> None:
    text = " ".join(adr_text().split())

    assert "**La regola 62, `plans-enter-by-two-doors`**" in text
    assert "**La regola 63, `the-planner-names-no-device`**" in text
    assert set(_rules_up_to(62)) - set(_rules_up_to(61)) == {"plans-enter-by-two-doors"}


def test_the_contract_it_names_is_the_fifteenth_and_forbids_what_it_says() -> None:
    (contract,) = [one for one in contracts() if str(one["name"]).startswith("15. ")]

    assert contract["source_modules"] == ["ela.executive"]
    assert contract["forbidden_modules"] == ["ela.context"]
    assert "**il contratto 15**" in adr_text()


def test_the_worst_case_it_writes_is_the_one_the_price_table_gives() -> None:
    """Decision 14: 16384 output tokens, and the worst case worked out by the function of the gate,
    not by hand — the figure the guide's margin is built from."""
    (written,) = WORST_ROW.findall(adr_text())
    computed = worst_cost(MODELS[OPUS_5_5], output_tokens=PLANNING_OUTPUT_TOKENS)

    assert Decimal(written.replace(",", ".")) == computed == Decimal("4.262144")
    assert f'`{{"max_output_tokens": {PLANNING_OUTPUT_TOKENS}}}`' in adr_text()


def test_every_adr_it_revises_says_so_in_its_status() -> None:
    for name in REVISED:
        text = (ADR_DIR / name).read_text(encoding="utf-8")
        revised = text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
        assert "ADR 0058" in revised, name
        assert "(M14.2)" in revised, name


def test_the_lines_it_revises_are_still_there_as_they_were_written() -> None:
    """Revised openly, never rewritten: the sentence each ADR wrote is still in it."""
    assert "**P5 DENIED solo dove qualcuno decide:**" in (
        ADR_DIR / "0004-task-transitions.md"
    ).read_text(encoding="utf-8")
    assert "produrrà tipi da un enum" in (ADR_DIR / "0022-model-router.md").read_text(
        encoding="utf-8"
    )
    assert "**Il piano resta un file scritto a mano** finché non esiste il Planner" in (
        ADR_DIR / "0024-cli.md"
    ).read_text(encoding="utf-8")


def test_it_stays_proposed_until_the_proof_by_hand_passes() -> None:
    """The form of ADR 0057: «Proposta» until section 24 of the guide passes on the Mac, and
    accepted in the commit that records it — an ADR accepted over a proof still to do is what
    ADR 0040 refused."""
    (row,) = INDEX_ROW.findall((ADR_DIR / "README.md").read_text(encoding="utf-8"))

    assert status().strip().startswith("Proposta")
    assert row[1] == "Proposta"
    assert "sezione 24" in status()
