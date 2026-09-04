"""The schema tables in the ADRs and ``Base.metadata`` describe the same tables.

Same pattern as ``test_adr_ports.py``: the ADR is the documented decision, the metadata is the
running code, and neither may drift from the other without this test noticing. An ADR is
immutable, so each ADR documents the tables it introduces (0006: tasks, task events,
authorizations; 0007: audit events) and the union is what the metadata must match.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.infrastructure.persistence.orm import Base

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATHS = {
    "0006": ADR_DIR / "0006-persistence.md",
    "0007": ADR_DIR / "0007-audit-log.md",
}
ROW = re.compile(r"^\| `(\w+)` \| (.+) \|$")
COLUMN = re.compile(r"`(\w+)`")


def documented_tables(text: str) -> dict[str, tuple[str, ...]]:
    """Table name -> column names, in the order the ADR lists them."""
    rows: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None and match.group(1) != "Tabella":
            rows[match.group(1)] = tuple(COLUMN.findall(match.group(2)))
    assert rows, "the ADR must contain a schema table"
    return rows


def all_documented_tables(texts: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """The union over every ADR; a table documented twice would be a drift of its own."""
    union: dict[str, tuple[str, ...]] = {}
    for adr, text in texts.items():
        for name, columns in documented_tables(text).items():
            assert name not in union, f"{name} is documented in more than one ADR ({adr})"
            union[name] = columns
    return union


def adr_texts() -> dict[str, str]:
    return {adr: path.read_text(encoding="utf-8") for adr, path in ADR_PATHS.items()}


def coded_tables() -> dict[str, tuple[str, ...]]:
    return {
        name: tuple(column.name for column in table.columns)
        for name, table in Base.metadata.tables.items()
    }


def test_tables_match_the_metadata() -> None:
    documented = all_documented_tables(adr_texts())
    coded = coded_tables()
    assert set(documented) == set(coded)
    for name in coded:
        assert documented[name] == coded[name], name


def test_each_adr_documents_its_own_tables() -> None:
    texts = adr_texts()
    assert set(documented_tables(texts["0006"])) == {"tasks", "task_events", "authorizations"}
    assert set(documented_tables(texts["0007"])) == {"audit_events"}


@pytest.mark.parametrize(
    ("adr", "table", "before", "after"),
    [
        ("0006", "authorizations", "`max_uses`, `metadata`, `uses` |", "`max_uses`, `metadata` |"),
        ("0006", "tasks", "`deadline`, `metadata` |", "`deadline`, `metadata`, `colour` |"),
        ("0007", "audit_events", "`prev_hash`, `row_hash` |", "`prev_hash` |"),
    ],
)
def test_a_drifted_table_is_detected(adr: str, table: str, before: str, after: str) -> None:
    """Negative case: drop a column from a row, or add one, in either ADR."""
    texts = adr_texts()
    drifted = texts[adr].replace(before, after, 1)
    assert drifted != texts[adr]
    documented = all_documented_tables({**texts, adr: drifted})
    assert documented[table] != coded_tables()[table]


def test_a_table_documented_twice_is_detected() -> None:
    texts = adr_texts()
    duplicated = texts["0006"] + "\n| `audit_events` | `seq` |\n"
    with pytest.raises(AssertionError, match="more than one ADR"):
        all_documented_tables({**texts, "0006": duplicated})
