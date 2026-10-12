"""What ADR 0064 (M13.4f) added to the browser's port and to its verifiers, **read from its own
tables** and never listed by hand.

An accepted ADR is not rewritten: the rows of ADR 0052 stay the ones of its day, and what came
after lives in the ADR that added it. The tests of the older rows read these beside them — the
form of ``guided_ports.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR_0064 = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0064-browser-boundary.md"
EXTENDED = "Port estesi:"
ADDED = "Codici aggiunti ai verifier:"
PORT_ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
CODES_ROW = re.compile(r"^\| `(browser\.\w+)` \| `(\w+Verifier)` \| (.+?) \|$")
NAME = re.compile(r"`([^`]+)`")


def _table_after(label: str) -> list[str]:
    """The rows of the first table after ``label``, which stands alone on its line."""
    lines = ADR_0064.read_text(encoding="utf-8").splitlines()
    assert label in lines, f"ADR 0064 must carry the label {label!r}"
    kept: list[str] = []
    for line in lines[lines.index(label) + 1 :]:
        if line.startswith("|"):
            kept.append(line)
        elif kept:
            break
    return kept


def added_members() -> dict[str, frozenset[str]]:
    """The members ADR 0064 adds to each port it extends."""
    return {
        match.group(1): frozenset(NAME.findall(match.group(4)))
        for line in _table_after(EXTENDED)
        if (match := PORT_ROW.match(line))
    }


def added_codes() -> dict[str, tuple[str, frozenset[str]]]:
    """For each capability of the browser: the verifier ADR 0064 names, and the failure codes
    it adds to it."""
    return {
        match.group(1): (match.group(2), frozenset(NAME.findall(match.group(3))))
        for line in _table_after(ADDED)
        if (match := CODES_ROW.match(line))
    }
