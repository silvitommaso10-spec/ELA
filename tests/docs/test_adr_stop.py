"""ADR 0054 and the running code describe the same stop (M6.3c).

§1 — the debt of the CI runner — has its own file, ``test_adr_ci_runner.py``. Here the rest: the two
halves of ``stop_point`` against production, the values of ``halt`` and their words, the rules the
ADR names against ``RULES``, the three exceptions of decision 1 against the test that holds them,
the measure of §13, and the totals of the Conseguenze — the pin on *today's* totals, taken over from
ADR 0052.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.cli.tasks import HALT_WORDS
from ela.domain import Halt
from ela.ports import ENVELOPE
from tests.architecture.rules import RULES
from tests.contracts.protocols import port_protocols
from tests.docs.test_adr_cli import coded_commands
from tests.docs.test_adr_composition import coded_routes
from tests.docs.test_adr_placement import _rules_up_to
from tests.executive.test_stop import EXCEPTIONS
from tests.tools.test_registry import _production

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0054-stopped-midway.md"
ROW = re.compile(r"^\| `([a-z_.]+)` \| (`[^`]+`|`None`) \| (la busta|`None`) \|$")
HALT_ROW = re.compile(r"^\| `([A-Z_]+)` \| [^|]+ \| `([^`]+)` \|$")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def section(number: int) -> str:
    text = adr_text()
    start = text.index(f"\n### {number}. ")
    end = text.find("\n### ", start + 1)
    return text[start : text.index("\n## ", start) if end == -1 else end]


def conseguenze() -> str:
    text = adr_text()
    return text[text.index("## Conseguenze") :]


def test_the_table_of_the_two_halves_is_production(tmp_path: Path) -> None:
    rows = {
        match.group(1): (match.group(2), match.group(3))
        for line in section(3).splitlines()
        if (match := ROW.match(line))
    }
    tools, _, _ = _production(tmp_path)

    def written(half: str | None, *, node: bool) -> str:
        if half is None:
            return "`None`"
        return "la busta" if node and half == ENVELOPE else f"`{half}`"

    assert rows == {
        str(tool.capability_id): (
            written(tool.stop_point.here, node=False),
            written(tool.stop_point.on_a_node, node=True),
        )
        for tool in tools.tools()
    }


def test_the_values_of_halt_and_their_words_are_the_code_s() -> None:
    rows = {
        match.group(1): match.group(2)
        for line in section(7).splitlines()
        if (match := HALT_ROW.match(line))
    }

    assert rows == {value.value: HALT_WORDS[value] for value in Halt}


def test_the_rules_it_names_are_registered_with_their_numbers() -> None:
    assert "la regola 58,\n`only-the-engine-raises-a-stop`" in section(2)
    assert "la regola 59, `a-stop-arrives-per-call`" in section(3)
    assert "la regola 17,\n`step-completers`, si estende" in section(4)
    assert {"only-the-engine-raises-a-stop", "a-stop-arrives-per-call", "step-completers"} <= set(
        RULES
    )
    assert set(RULES) - set(_rules_up_to(57)) == {
        "only-the-engine-raises-a-stop",
        "a-stop-arrives-per-call",
    }


def test_the_exceptions_of_decision_1_are_the_three_the_test_holds() -> None:
    text = section(12)

    assert "**alla lettera è falsa**" in text
    assert "lo step di un tool sul\nCore oltre il punto che non è ancora tornato" in text
    assert "quello di un nodo con la presa viva" in text
    assert "quello di una presa scaduta\nfino al primo avvio o al primo `run` del task" in text
    assert len(EXCEPTIONS) == 3


def test_the_conseguenze_count_the_rules_the_ports_the_routes_and_the_commands_of_today() -> None:
    """The pin on today's totals, taken over from ADR 0052: it moves to the ADR that changes
    them."""
    text = conseguenze()

    assert "**cinquantanove**" in text
    assert len(RULES) == 59
    assert "**trenta**" in text
    assert len(tuple(port_protocols())) == 30
    assert "**quarantanove**" in text
    assert len(coded_routes()) == 49
    assert "**ventisette**" in text
    assert len(coded_commands()) == 27


def test_the_measure_of_the_start_up_is_written_with_its_file_and_its_numbers() -> None:
    """Decision 2 of the review: how many ended tasks the start-up reads, closes, and how long."""
    text = section(13)

    assert "Si scrive qui quando c'è" not in text
    assert "`~/Downloads/m6.3c-misura-avvio.txt`" in text
    assert "**letti**" in text and "**chiusi**" in text
    assert "**160 ms**" in text
    assert "il difetto del §15 di ADR 0052" in text
