"""ADR 0051 and the code say the same thing (M6.3b).

ADR 0019 §3 named ``test_a_run_executes_each_step_at_most_once`` for the half of the loop that runs,
and the name kept the word — «executes» — for three milestones after the field it counted stopped
holding only steps that ran. ADR 0051 renames the tests and names the new ones; this module checks
that each name it cites is a test that exists, so a citation cannot point at nothing again. And the
«Stato:» line of ADR 0019 names every ADR that revised it (decision 5 of the review): a line that
names one revision and is silent on the others reads as the whole list.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.cli.tasks import RUN_LABELS

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "adr" / "0051-steps-handled.md"
ADR_0019 = ROOT / "docs" / "adr" / "0019-task-runner.md"
STATE = re.compile(r"^- \*\*Stato:\*\*\s*(.+)$", re.MULTILINE)
CITED = re.compile(r"`(test_\w+)`")

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


def test_every_test_the_adr_names_exists() -> None:
    names = CITED.findall(ADR.read_text(encoding="utf-8"))

    assert names
    assert missing(names, sources()) == []


def test_a_name_that_points_at_nothing_is_reported() -> None:
    text = "def test_one() -> None: ...\nasync def test_two() -> None: ...\n"

    assert missing(["test_one", "test_two", "test_three"], text) == ["test_three"]


def test_the_adr_names_the_label_the_command_prints() -> None:
    assert f"`{RUN_LABELS[-1]}`" in ADR.read_text(encoding="utf-8")


def test_the_state_of_adr_0019_names_every_adr_that_revised_it() -> None:
    found = STATE.search(ADR_0019.read_text(encoding="utf-8"))

    assert found is not None
    assert [revision for revision in REVISIONS if revision not in found.group(1)] == []
