"""ADR 0059 says what the code does: the one reading, the field, who said no, the ceiling, the rule,
the cost and the totals of today (M13.1e).

The pin on **today's** totals moves here from ADR 0058, the ADR that last changed them: the tests
of the earlier ADRs count what they saw, without what came after (ADR 0032 §17).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from ela.api.companion import ROLE_WORDS as PAGE_ROLE_WORDS
from ela.api.schemas import AnswererOut, EndOut
from ela.api.tasks import LOCAL_ANSWERER
from ela.cli.tasks import ROLE_WORDS as CLI_ROLE_WORDS
from ela.cli.tasks import WHY_HEADERS
from tests.architecture.rules import END_KEY, END_MODULES, RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to

ROOT = Path(__file__).resolve().parents[2]
ADR_DIR = ROOT / "docs" / "adr"
ADR_PATH = ADR_DIR / "0059-the-reason-on-every-route.md"
PYPROJECT = ROOT / "pyproject.toml"
INDEX_ROW = re.compile(
    r"^\| \[0059\]\(0059-the-reason-on-every-route\.md\) \| (.+?) \| (.+?) \|$", re.MULTILINE
)
REVISED = (
    "0045-filesystem-and-high.md",
    "0054-stopped-midway.md",
    "0055-the-reason-of-an-end.md",
)


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def flat() -> str:
    return " ".join(adr_text().split())


def conseguenze() -> str:
    return adr_text().split("## Conseguenze", 1)[1]


def test_the_conseguenze_count_the_rules_the_contracts_the_ports_the_routes_and_the_commands() -> (
    None
):
    """The pin on today's totals, taken over from ADR 0058: it moves to the ADR that changes
    them."""
    text = conseguenze()
    contracts = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["importlinter"][
        "contracts"
    ]

    assert "**sessantaquattro**" in text
    assert len(RULES) == 64
    assert set(RULES) - set(_rules_up_to(63)) == {"the-end-has-one-reader"}
    assert "**quindici**" in text
    assert len(contracts) == 15
    assert "**trenta**" in text
    assert len(tuple(port_protocols())) == 30
    assert "**cinquantuno**" in text
    assert len(coded_routes()) == 51
    assert "**ventotto**" in text
    assert len(coded_commands()) == 28


def test_the_rule_it_names_is_registered_with_its_number_and_reads_what_it_says() -> None:
    assert "**La regola 64, `the-end-has-one-reader`**" in flat()
    assert END_KEY == "new_state"
    assert {str(path) for path in END_MODULES} == {"tasks/engine.py", "tasks/ending.py"}


def test_the_fixed_name_of_the_core_s_token_is_the_route_s() -> None:
    assert f"**`{LOCAL_ANSWERER}`**" in flat()


def test_the_words_of_the_roles_are_the_pages_and_the_cli_s() -> None:
    """§4 and §5: the pages say the role in their words under every ceiling, the CLI in its own."""
    text = flat()

    assert all(f"`{role}` «{words}»" in text for role, words in PAGE_ROLE_WORDS.items())
    assert "`<nome> (console)` o `<nome> (phone)`" in text
    assert set(CLI_ROLE_WORDS.values()) == {"console", "phone"}


def test_the_fields_it_names_are_the_schema_s() -> None:
    text = flat()

    assert set(EndOut.model_fields) == {"reason", "operation", "reason_code", "answered_by"}
    assert all(f"`{field}`" in text for field in EndOut.model_fields)
    assert set(AnswererOut.model_fields) == {"identity", "name", "role"}
    assert "**`TaskOut.end: EndOut | None`**" in text
    assert "la tabella **`why`**" in text
    assert WHY_HEADERS == ("id", "reason", "answered by")


def test_the_ceiling_rule_is_written_in_its_own_words() -> None:
    assert "### 4. Sotto il tetto solo parole di ELA, mai parole scritte da qualcuno" in adr_text()


def test_the_cost_is_written_with_its_answer_if_too_heavy_and_that_answer_is_not_built() -> None:
    text = flat()

    assert "circa **1,9 ms per ragione**" in text
    assert "`task_ids`" in text
    assert "**Non è costruito.**" in text


def test_the_measure_on_the_mac_closes_the_question_of_the_cost_for_today() -> None:
    """Decision 11: the numbers of step 10, written as measures; ``task_ids`` stays the written
    answer, not built."""
    text = flat()

    assert "168 task, 72 con una ragione, mediana 39,8 ms, 0,55 ms per ragione" in text
    assert "mediana 9,3 ms, 1,56 ms per ragione" in text
    assert "**La domanda del costo, per oggi, è chiusa**" in text


def test_the_adrs_it_revises_say_so_in_their_state() -> None:
    for name in REVISED:
        text = (ADR_DIR / name).read_text(encoding="utf-8")
        revised = text.split("- **Stato:**", 1)[1].split("\n- **", 1)[0]
        assert "ADR 0059" in revised, name
        assert "(M13.1e)" in revised, name


def test_the_lines_it_revises_are_still_there_as_they_were_written() -> None:
    """Revised openly, never rewritten: the sentence each ADR wrote is still in it."""
    assert "**Una fonte sola**, `TaskRunner._reason`" in (
        ADR_DIR / "0055-the-reason-of-an-end.md"
    ).read_text(encoding="utf-8")


def status() -> str:
    return adr_text().split("- **Stato:**", 1)[1].split("\n- **", 1)[0]


def test_it_was_accepted_only_after_the_proof_by_hand(shown: str = "2026-10-08") -> None:
    """The form of ADR 0058: «Proposta» until section 25 of the guide passed on the Mac and on the
    phone, then «Accettata» with the file and the commit, in the index too (decision 11 of the
    review of the proof)."""
    found = INDEX_ROW.search((ADR_DIR / "README.md").read_text(encoding="utf-8"))
    guide = (ROOT / "docs" / "GETTING_STARTED.md").read_text(encoding="utf-8")
    section = guide.split("## 25. ", 1)[1].split("\n## ", 1)[0]

    assert found is not None
    assert found.group(2) == "Accettata"
    assert status().strip().startswith(f"Accettata il **{shown}**")
    assert "sezione 25" in status() and "prova-m13.1e-20261008-124455.txt" in status()
    assert "`b5a8d7a`" in status()
    assert "**Da fare.**" not in adr_text()
    assert "**Da fare.**" not in section
    assert f"**Fatta da Tommaso il {shown} sul" in section
