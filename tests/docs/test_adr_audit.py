"""The hashed-columns table in ADR 0007 and ``HASHED_COLUMNS`` list the same columns, in order.

The chain hashes what this table says and nothing else: a column added to the row without a
line here, or a line here without a column, is a drift between the decision and the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.infrastructure.persistence.orm import HASHED_COLUMNS, AuditEventRow

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0007-audit-log.md"
HASHED_ROW = re.compile(r"^\| (\d+) \| `(\w+)` \|$")


def documented_hashed_columns(text: str) -> tuple[str, ...]:
    rows = [
        (int(match.group(1)), match.group(2))
        for line in text.splitlines()
        if (match := HASHED_ROW.match(line)) is not None
    ]
    assert rows, "ADR 0007 must contain the hashed-columns table"
    assert [number for number, _ in rows] == list(range(1, len(rows) + 1)), "numbering"
    return tuple(name for _, name in rows)


def test_hashed_columns_match_the_code() -> None:
    assert documented_hashed_columns(ADR_PATH.read_text(encoding="utf-8")) == HASHED_COLUMNS


def test_hashed_columns_are_every_column_but_seq_and_the_chain() -> None:
    columns = tuple(column.name for column in AuditEventRow.__table__.columns)
    assert columns == ("seq", *HASHED_COLUMNS, "prev_hash", "row_hash")


def test_a_drifted_list_is_detected() -> None:
    """Negative case: a column renamed in the table, or one dropped (which breaks numbering)."""
    text = ADR_PATH.read_text(encoding="utf-8")
    renamed = text.replace("| 6 | `summary` |", "| 6 | `result` |", 1)
    assert renamed != text
    assert documented_hashed_columns(renamed) != HASHED_COLUMNS
    dropped = text.replace("| 13 | `tool_name` |\n", "", 1)
    assert dropped != text
    with pytest.raises(AssertionError, match="numbering"):
        documented_hashed_columns(dropped)
    renumbered = dropped.replace("| 14 |", "| 13 |").replace("| 15 |", "| 14 |")
    assert documented_hashed_columns(renumbered.replace("| 16 |", "| 15 |")) != HASHED_COLUMNS
