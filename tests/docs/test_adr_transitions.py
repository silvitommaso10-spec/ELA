"""The Mermaid diagram in ADR 0004 and ``TRANSITIONS`` describe the same graph.

The ADR is the documented decision, the table is the running code. Neither may drift from the
other without this test noticing.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.domain import TaskState
from ela.tasks.state_machine import TRANSITIONS

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0004-task-transitions.md"
MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
EDGE = re.compile(r"^\s*(\S+)\s*-->\s*(\S+?)\s*(?::.*)?$")
START_OR_END = "[*]"


def mermaid_edges(text: str) -> set[tuple[str, str]]:
    blocks = MERMAID_BLOCK.findall(text)
    assert len(blocks) == 1, "ADR 0004 must contain exactly one Mermaid diagram"
    edges: set[tuple[str, str]] = set()
    for line in blocks[0].splitlines():
        match = EDGE.match(line)
        if match is not None:
            edges.add((match.group(1), match.group(2)))
    return edges


def test_mermaid_matches_the_code() -> None:
    edges = mermaid_edges(ADR_PATH.read_text(encoding="utf-8"))
    documented = {(a, b) for a, b in edges if START_OR_END not in (a, b)}
    coded = {(a.value, b.value) for a, targets in TRANSITIONS.items() for b in targets}
    assert documented == coded


def test_mermaid_names_every_state() -> None:
    edges = mermaid_edges(ADR_PATH.read_text(encoding="utf-8"))
    entries = {b for a, b in edges if a == START_OR_END}
    exits = {a for a, b in edges if b == START_OR_END}
    assert entries == {TaskState.CREATED.value}
    assert exits == {s.value for s, targets in TRANSITIONS.items() if not targets}
    named = {name for edge in edges for name in edge} - {START_OR_END}
    assert named == {state.value for state in TaskState}


def test_a_drifted_diagram_is_detected() -> None:
    """Negative case: drop one documented edge and the comparison must fail."""
    text = ADR_PATH.read_text(encoding="utf-8")
    drifted = text.replace("    QUEUED --> EXECUTING: un nodo prende il task\n", "", 1)
    assert drifted != text
    coded = {(a.value, b.value) for a, targets in TRANSITIONS.items() for b in targets}
    documented = {(a, b) for a, b in mermaid_edges(drifted) if START_OR_END not in (a, b)}
    assert documented != coded
    assert coded - documented == {("QUEUED", "EXECUTING")}
