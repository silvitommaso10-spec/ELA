"""What ADR 0066 (the branch of M13.13) adds to the browser's ports, **read from its own table** and
never listed by hand — the form of ``steps_additions.py`` for ADR 0065.

An accepted ADR is not rewritten: the tests of the older rows of a port read this beside theirs.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_0066 = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0066-browser-files.md"
EXTENDED = "Port estesi:"
REWRITTEN = "Righe dei tool, riscritte:"
REWRITTEN_VERIFIERS = "Righe dei verifier, riscritte:"
PORT_ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
TOOL_ROW = re.compile(r"^\| `([\w.]+)` \| `(\w+)` \| `([\w-]+)` \| (sì|no) \| (.+?) \| (.+?) \|$")
VERIFIER_ROW = re.compile(r"^\| `([\w.]+)` \| `(\w+)` \| `([\w-]+)` \| (.+?) \| (.+?) \|$")
NAME = re.compile(r"`([^`]+)`")


def _table_after(label: str) -> list[str]:
    """The rows of the first table after ``label``, which stands alone on its line."""
    lines = ADR_0066.read_text(encoding="utf-8").splitlines()
    assert label in lines, f"ADR 0066 must carry the label {label!r}"
    kept: list[str] = []
    for line in lines[lines.index(label) + 1 :]:
        if line.startswith("|"):
            kept.append(line)
        elif kept:
            break
    return kept


def added_members() -> dict[str, frozenset[str]]:
    """The members ADR 0066 adds to each port it extends."""
    return {
        match.group(1): frozenset(NAME.findall(match.group(4)))
        for line in _table_after(EXTENDED)
        if (match := PORT_ROW.match(line))
    }


def rewritten_rows() -> dict[str, tuple[str, ...]]:
    """For each tool whose row ADR 0066 writes again — whole, and the rewritten row wins over the
    row of the ADR that introduced the tool (the form of ADR 0065) —: the groups of that row, as
    the tests of the older ADRs read theirs: capability, class, name, idempotent, codes,
    numbers."""
    return {
        match.group(1): match.groups()
        for line in _table_after(REWRITTEN)
        if (match := TOOL_ROW.match(line))
    }


def rewritten_verifier_rows() -> dict[str, tuple[str, ...]]:
    """For each verifier whose row ADR 0066 writes again: capability, class, name, conditions,
    failures."""
    return {
        match.group(1): match.groups()
        for line in _table_after(REWRITTEN_VERIFIERS)
        if (match := VERIFIER_ROW.match(line))
    }
