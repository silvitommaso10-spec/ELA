"""ADR 0009 and ``ela.tasks.graph``/``ela.tasks.engine`` describe the same step graph.

Two things are checked, as for ADR 0004 and ADR 0008: the Mermaid diagram of the step
transitions against ``STEP_TRANSITIONS``, and the table of the step operations against
``STEP_OPERATIONS``. Neither may drift from the other without this test noticing.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.domain import AuditEventType, StepState, TaskEventType
from ela.tasks.engine import STEP_OPERATIONS, StepOperation
from ela.tasks.graph import STEP_TRANSITIONS

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-task-graph.md"
MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
EDGE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+?)\s*(?::.*)?$")
START_OR_END = "[*]"
ROW = re.compile(r"^\| `(\w+)` \| ([A-Z_, ]+) \| ([A-Z_]+) \| `(\w+)` \| `(\w+)` \| (—|`\w+`) \|$")


def mermaid_edges(text: str) -> set[tuple[str, str]]:
    blocks = MERMAID_BLOCK.findall(text)
    assert len(blocks) == 1, "ADR 0009 must contain exactly one Mermaid diagram"
    edges: set[tuple[str, str]] = set()
    for line in blocks[0].splitlines():
        match = EDGE.match(line)
        if match is not None:
            edges.add((match.group(1), match.group(2)))
    return edges


def documented_operations(text: str) -> dict[str, StepOperation]:
    rows: dict[str, StepOperation] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        name, sources, target, event_type, audit_type, key = match.groups()
        rows[name] = StepOperation(
            name,
            frozenset(StepState(s.strip()) for s in sources.split(",")),
            StepState(target),
            TaskEventType(event_type),
            AuditEventType(audit_type),
            None if key == "—" else key.strip("`"),
        )
    assert rows, "ADR 0009 must contain the step operations table"
    return rows


def coded_edges() -> set[tuple[str, str]]:
    return {(a.value, b.value) for a, targets in STEP_TRANSITIONS.items() for b in targets}


def test_mermaid_matches_the_code() -> None:
    edges = mermaid_edges(ADR_PATH.read_text(encoding="utf-8"))
    documented = {(a, b) for a, b in edges if START_OR_END not in (a, b)}
    assert documented == coded_edges()


def test_mermaid_names_every_step_state() -> None:
    edges = mermaid_edges(ADR_PATH.read_text(encoding="utf-8"))
    assert {b for a, b in edges if a == START_OR_END} == {StepState.PENDING.value}
    assert {a for a, b in edges if b == START_OR_END} == {
        s.value for s, targets in STEP_TRANSITIONS.items() if not targets
    }
    named = {name for edge in edges for name in edge} - {START_OR_END}
    assert named == {state.value for state in StepState}


def test_table_matches_the_code() -> None:
    documented = documented_operations(ADR_PATH.read_text(encoding="utf-8"))
    assert list(documented) == list(STEP_OPERATIONS)
    for name, row in documented.items():
        assert row == STEP_OPERATIONS[name], name


def test_a_drifted_diagram_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    drifted = text.replace("    RUNNING --> FAILED", "    PENDING --> FAILED", 1)
    assert drifted != text
    documented = {(a, b) for a, b in mermaid_edges(drifted) if START_OR_END not in (a, b)}
    assert documented != coded_edges()


def test_a_drifted_table_is_detected() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    for before, after, name in [
        ("| `start_step` | PENDING |", "| `start_step` | PENDING, RUNNING |", "start_step"),
        (
            "| `STEP_COMPLETED` | `STEP_COMPLETED` | `result_id` |",
            "| `STEP_COMPLETED` | `STEP_COMPLETED` | — |",
            "complete_step",
        ),
        (
            "| `STEP_CANCELLED` | `STEP_CANCELLED` |",
            "| `STEP_CANCELLED` | `STEP_FAILED` |",
            "cancel_step",
        ),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_operations(drifted)[name] != STEP_OPERATIONS[name], name
