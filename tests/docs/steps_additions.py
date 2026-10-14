"""What ADR 0065 (M13.10) adds to the browser's port, and the rows of the tools it rewrites,
**read from its own tables** and never listed by hand — the form of ``boundary_additions.py``.

An accepted ADR is not rewritten: a tool whose codes or audit numbers M13.10 changes has its whole
row written again in ADR 0065, and **the rewritten row wins** over the row of the ADR that
introduced the tool (decision 44 of the review of M13.10's SPEC). The tests of the older rows read
these beside them.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_0065 = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0065-browser-steps.md"
EXTENDED = "Port estesi:"
REWRITTEN = "Righe dei tool, riscritte:"
PORT_ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
TOOL_ROW = re.compile(
    r"^\| `(browser\.\w+)` \| `(\w+)` \| `([\w-]+)` \| (sì|no) \| (.+?) \| (.+?) \|$"
)
NAME = re.compile(r"`([^`]+)`")


def _table_after(label: str) -> list[str]:
    """The rows of the first table after ``label``, which stands alone on its line."""
    lines = ADR_0065.read_text(encoding="utf-8").splitlines()
    assert label in lines, f"ADR 0065 must carry the label {label!r}"
    kept: list[str] = []
    for line in lines[lines.index(label) + 1 :]:
        if line.startswith("|"):
            kept.append(line)
        elif kept:
            break
    return kept


def added_members() -> dict[str, frozenset[str]]:
    """The members ADR 0065 adds to each port it extends."""
    return {
        match.group(1): frozenset(NAME.findall(match.group(4)))
        for line in _table_after(EXTENDED)
        if (match := PORT_ROW.match(line))
    }


def rewritten_rows() -> dict[str, tuple[str, ...]]:
    """For each tool whose row ADR 0065 writes again: the groups of that row, as the tests of the
    older ADRs read theirs — capability, class, name, idempotent, codes, numbers."""
    return {
        match.group(1): match.groups()
        for line in _table_after(REWRITTEN)
        if (match := TOOL_ROW.match(line))
    }
