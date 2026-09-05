"""The operations table in ADR 0008 and ``OPERATIONS`` describe the same operations.

Same pattern as the other ADR tests: the ADR is the documented decision, the table is the running
code, and neither may drift from the other — names, sources, targets, audit types or keys —
without this test noticing. Rows have five cells, so the schema test never mistakes them for a
table of the database.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.domain import AuditEventType, TaskState
from ela.tasks.engine import OPERATIONS, Operation

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0008-task-engine.md"
ROW = re.compile(r"^\| `(\w+)` \| ([A-Z_, ]+) \| ([A-Z_]+) \| `(\w+)` \| (—|`\w+`) \|$")


def documented_operations(text: str) -> dict[str, Operation]:
    """Operation name -> row, in the order of the table."""
    rows: dict[str, Operation] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        name, sources, target, audit_type, key = match.groups()
        rows[name] = Operation(
            name,
            frozenset(TaskState(s.strip()) for s in sources.split(",")),
            TaskState(target),
            AuditEventType(audit_type),
            None if key == "—" else key.strip("`"),
        )
    assert rows, "ADR 0008 must contain the operations table"
    return rows


def test_table_matches_the_code() -> None:
    documented = documented_operations(ADR_PATH.read_text(encoding="utf-8"))
    assert list(documented) == list(OPERATIONS)
    for name, row in documented.items():
        assert row == OPERATIONS[name], name


def test_a_drifted_table_is_detected() -> None:
    """Negative case: a source dropped, a type renamed, a key removed; each must show."""
    text = ADR_PATH.read_text(encoding="utf-8")
    coded = dict(OPERATIONS)
    for before, after, name in [
        ("| `queue` | PLANNING, EXECUTING |", "| `queue` | PLANNING |", "queue"),
        ("| `TASK_STARTED` |", "| `TASK_QUEUED` |", "start"),
        (
            "| `complete` | EXECUTING | COMPLETED | `TASK_COMPLETED` | `result_id` |",
            "| `complete` | EXECUTING | COMPLETED | `TASK_COMPLETED` | — |",
            "complete",
        ),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_operations(drifted)[name] != coded[name], before
