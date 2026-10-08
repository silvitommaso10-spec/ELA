"""ADR 0055 and the running code describe the same reason (M13.1c).

The operations the ADR names as who ended a task are the engine's, with the state the ADR says; the
code minted for a node that does not say why is the executor's; the tests the ADR cites exist; and
the ends that carry a reason are the runner's, every one but ``completed``.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.domain import TaskState
from ela.executive import NODE_UNEXPLAINED_FAILURE
from ela.tasks.ending import REASONED
from ela.tasks.engine import OPERATIONS, TERMINAL_STATES

ROOT = Path(__file__).resolve().parents[2]
ADR_PATH = ROOT / "docs" / "adr" / "0055-the-reason-of-an-end.md"
CITED = re.compile(r"`(test_\w+)`")


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def section(number: int) -> str:
    text = adr_text()
    start = text.index(f"\n### {number}. ")
    end = text.find("\n### ", start + 1)
    return text[start : text.index("\n## ", start) if end == -1 else end]


def test_every_end_but_completed_carries_its_reason() -> None:
    assert "**Ogni fine che non è `completed` porta la sua ragione**" in section(1)
    assert TERMINAL_STATES - {TaskState.COMPLETED} == REASONED


def test_the_operations_that_say_who_ended_a_task_are_the_engine_s() -> None:
    named = {
        "deny_by_decision": TaskState.DENIED,
        "deny_by_approval": TaskState.DENIED,
        "fail": TaskState.FAILED,
        "recover": TaskState.FAILED,
        "cancel": TaskState.CANCELLED,
        "expire": TaskState.EXPIRED,
    }
    text = section(1)

    for name, state in named.items():
        assert f"`{name}`" in text, name
        assert OPERATIONS[name].target is state, name


def test_the_transitions_to_failed_are_the_ones_the_adr_names() -> None:
    to_failed = {op.name for op in OPERATIONS.values() if op.target is TaskState.FAILED}

    assert to_failed == {"fail", "recover"}
    assert "`fail` e l'orfano di `recover`" in section(2)


def test_the_code_of_a_node_that_does_not_say_why_is_the_executor_s() -> None:
    assert f"**`{NODE_UNEXPLAINED_FAILURE}`**" in section(3)


def test_every_test_the_adr_cites_exists() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").rglob("*.py"))
    cited = CITED.findall(adr_text())

    assert cited
    for name in cited:
        assert re.search(rf"^(?:async )?def {name}\(", sources, re.MULTILINE), name


def test_the_adr_cites_the_tests_that_hold_it() -> None:
    text = adr_text()

    for path in (
        "tests/api/test_run_reasons.py",
        "tests/cli/test_run_reasons.py",
        "tests/tasks/test_failed_reason.py",
    ):
        assert f"`{path}`" in text, path
        assert (ROOT / path).is_file(), path


STATO = ROOT / "docs" / "STATO.md"
PAID_ON = "2026-10-05"
FILES = (
    "~/Downloads/prova-m6.3c-20261005-104506.txt",
    "~/Downloads/prova-m6.3c-20261005-174637.txt",
)


def test_section_7_pays_the_debt_of_step_8_with_the_file_where_step_8_passed() -> None:
    """Decisions O and P of the session: the heading ``scripts/generate_stato.py`` reads to call the
    debt paid, the day it was paid — one after the date of ADR 0054 §16 —, and the two files."""
    paid = section(7)

    assert paid.startswith(
        "\n### 7. Il debito di ADR 0054 §16, saldato: il passo 8 della prova a mano, "
        f"passato sul PC il {PAID_ON}"
    )
    assert "un giorno dopo la data di ADR 0054 §16" in paid
    for name in FILES:
        assert f"`{name}`" in paid, name
    assert "**Il criterio di ADR 0054 §16 è rivisto qui, apertamente.**" in paid


def test_the_table_of_debts_says_section_7_paid_it() -> None:
    rows = [
        line for line in STATO.read_text(encoding="utf-8").splitlines() if "ADR 0054 §16" in line
    ]

    assert len(rows) == 1, rows
    assert rows[0].endswith("| saldato da ADR 0055 §7 |"), rows[0]
