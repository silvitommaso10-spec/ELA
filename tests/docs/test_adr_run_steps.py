"""ADR 0051 and the code say the same thing (M6.3b).

ADR 0019 §3 named ``test_a_run_executes_each_step_at_most_once`` for the half of the loop that runs,
and the name kept the word — «executes» — for three milestones after the field it counted stopped
holding only steps that ran. ADR 0051 renames the tests — «`old` diventa `new`» — and this module
checks both halves: the old name is gone, the new one is a test that exists, and every other name
the ADR cites exists too, so a citation cannot point at nothing again. And the «Stato:» line of ADR
0019 names every ADR that revised it (decision 5 of the review): a line that names one revision and
is silent on the others reads as the whole list.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.cli.tasks import RUN_LABELS

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr" / "0051-steps-handled.md"
ADR_0019 = ROOT / "docs" / "adr" / "0019-task-runner.md"
STATE = re.compile(r"^- \*\*Stato:\*\*(.*?)^- \*\*", re.MULTILINE | re.DOTALL)
"""The whole «Stato:» item, up to the next one: it wraps, and a revision on its third line
counts."""
CITED = re.compile(r"`(test_\w+)`")
RENAMED = re.compile(r"`(test_\w+)` diventa\s+`(test_\w+)`")

REVISIONS = ("ADR 0038 §10", "ADR 0038 §16", "ADR 0051")
"""The ADRs that revised ADR 0019, as decision 5 lists them: the outcome ``ASSIGNED`` and the
termination (§10), ``max_privacy`` moved to the task (§16, D20), and the word of ``steps``."""


def sources() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "tests").rglob("*.py"))


def missing(names: list[str], text: str) -> list[str]:
    """The names that no ``def`` or ``async def`` in ``text`` defines."""
    return [
        name for name in names if not re.search(rf"^(?:async )?def {name}\(", text, re.MULTILINE)
    ]


def test_every_test_the_adr_renames_is_gone_and_its_new_name_exists() -> None:
    renamed = RENAMED.findall(ADR.read_text(encoding="utf-8"))
    text = sources()

    assert renamed
    assert missing([new for _, new in renamed], text) == []
    assert missing([old for old, _ in renamed], text) == [old for old, _ in renamed]


def test_every_other_test_the_adr_names_exists() -> None:
    adr = ADR.read_text(encoding="utf-8")
    old = {name for name, _ in RENAMED.findall(adr)}

    assert missing([name for name in CITED.findall(adr) if name not in old], sources()) == []


def test_a_name_that_points_at_nothing_is_reported() -> None:
    text = "def test_one() -> None: ...\nasync def test_two() -> None: ...\n"

    assert missing(["test_one", "test_two", "test_three"], text) == ["test_three"]


def test_a_rename_is_read_as_a_pair() -> None:
    text = "`test_old_name` diventa\n`test_new_name`, e `test_other` resta."

    assert RENAMED.findall(text) == [("test_old_name", "test_new_name")]


def test_the_adr_names_the_label_the_command_prints() -> None:
    """``steps handled``, the row ADR 0051 is about; the row after it is ADR 0054's (M6.3c)."""
    assert RUN_LABELS[3] == "steps handled"
    assert f"`{RUN_LABELS[3]}`" in ADR.read_text(encoding="utf-8")


def test_the_state_of_adr_0019_names_every_adr_that_revised_it() -> None:
    found = STATE.search(ADR_0019.read_text(encoding="utf-8"))

    assert found is not None
    state = " ".join(found.group(1).split())
    assert [revision for revision in REVISIONS if revision not in state] == []
