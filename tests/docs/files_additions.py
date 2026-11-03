"""What ADR 0066 (the branch of M13.13) adds to the browser's ports, **read from its own table** and
never listed by hand — the form of ``steps_additions.py`` for ADR 0065.

An accepted ADR is not rewritten: the tests of the older rows of a port read this beside theirs.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_0066 = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0066-browser-files.md"
EXTENDED = "Port estesi:"
PORT_ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
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
