"""The schema table in ADR 0006 and ``Base.metadata`` describe the same tables.

Same pattern as ``test_adr_ports.py``: the ADR is the documented decision, the metadata is the
running code, and neither may drift from the other without this test noticing.
"""

from __future__ import annotations

import re
from pathlib import Path

from ela.infrastructure.persistence.orm import Base

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0006-persistence.md"
ROW = re.compile(r"^\| `(\w+)` \| (.+) \|$")
COLUMN = re.compile(r"`(\w+)`")


def documented_tables(text: str) -> dict[str, tuple[str, ...]]:
    """Table name -> column names, in the order the ADR lists them."""
    rows: dict[str, tuple[str, ...]] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None and match.group(1) != "Tabella":
            rows[match.group(1)] = tuple(COLUMN.findall(match.group(2)))
    assert rows, "ADR 0006 must contain the schema table"
    return rows


def coded_tables() -> dict[str, tuple[str, ...]]:
    return {
        name: tuple(column.name for column in table.columns)
        for name, table in Base.metadata.tables.items()
    }


def test_table_matches_the_metadata() -> None:
    documented = documented_tables(ADR_PATH.read_text(encoding="utf-8"))
    coded = coded_tables()
    assert set(documented) == set(coded)
    for name in coded:
        assert documented[name] == coded[name], name


def test_a_drifted_table_is_detected() -> None:
    """Negative case: drop a column from one row and add a column to another."""
    text = ADR_PATH.read_text(encoding="utf-8")
    drifted = text.replace("`max_uses`, `metadata`, `uses` |", "`max_uses`, `metadata` |", 1)
    drifted = drifted.replace("`deadline`, `metadata` |", "`deadline`, `metadata`, `colour` |", 1)
    assert drifted != text
    documented = documented_tables(drifted)
    coded = coded_tables()
    assert documented["authorizations"] != coded["authorizations"]
    assert documented["tasks"] != coded["tasks"]
