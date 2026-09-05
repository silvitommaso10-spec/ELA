"""The catalogue table in ADR 0010 and ``catalogue_v01()`` describe the same capabilities.

Same pattern as the other ADR tests: the ADR is the documented decision, the catalogue is the
running code, and neither may drift — id, risk, scope, scoped argument, authorization flag,
required and optional arguments with their types — without this test noticing. Rows have seven
cells, so no other table test mistakes them for its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ela.domain import CapabilitySpec, RiskLevel
from ela.permissions import catalogue_v01

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0010-capability-catalogue.md"
ROW = re.compile(
    r"^\| `([a-z_.]+)` \| (SAFE|LOW|MEDIUM|HIGH|CRITICAL) \| (.+?) \| (.+?) \| (sì|no) "
    r"\| (.+?) \| (.+?) \|$"
)
CODE = re.compile(r"`([^`]+)`")
ARGUMENT = re.compile(r"`(\w+): (\w+)`")


@dataclass(frozen=True)
class Row:
    id: str
    risk: RiskLevel
    scope: tuple[str, ...]
    scoped_arguments: tuple[str, ...]
    requires_authorization: bool
    required: dict[str, str]
    optional: dict[str, str]


def _codes(cell: str) -> tuple[str, ...]:
    return () if cell.strip() == "—" else tuple(CODE.findall(cell))


def _arguments(cell: str) -> dict[str, str]:
    return {} if cell.strip() == "—" else dict(ARGUMENT.findall(cell))


def documented_catalogue(text: str) -> dict[str, Row]:
    rows: dict[str, Row] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is None:
            continue
        cid, risk, scope, scoped, auth, required, optional = match.groups()
        rows[cid] = Row(
            cid,
            RiskLevel(risk),
            _codes(scope),
            _codes(scoped),
            auth == "sì",
            _arguments(required),
            _arguments(optional),
        )
    assert rows, "ADR 0010 must contain the catalogue table"
    return rows


def coded_row(spec: CapabilitySpec) -> Row:
    schema = spec.input_schema
    properties = {name: str(prop["type"]) for name, prop in schema["properties"].items()}
    required = tuple(schema.get("required", ()))
    return Row(
        spec.id,
        spec.risk,
        spec.scope,
        spec.scoped_arguments,
        spec.requires_authorization,
        {name: kind for name, kind in properties.items() if name in required},
        {name: kind for name, kind in properties.items() if name not in required},
    )


def test_table_matches_the_code() -> None:
    documented = documented_catalogue(ADR_PATH.read_text(encoding="utf-8"))
    coded = {spec.id: coded_row(spec) for spec in catalogue_v01().specs()}
    assert list(documented) == list(coded)
    for cid, row in documented.items():
        assert row == coded[cid], cid


def test_a_drifted_table_is_detected() -> None:
    """Negative case: risk, scope, flag, a required argument, an optional one; each must show."""
    text = ADR_PATH.read_text(encoding="utf-8")
    coded = {spec.id: coded_row(spec) for spec in catalogue_v01().specs()}
    for before, after, cid in [
        ("| `core.echo` | SAFE |", "| `core.echo` | LOW |", "core.echo"),
        ("| `workspace/notes` | `path` |", "| — | `path` |", "workspace.write_note"),
        ("| MEDIUM | — | — | sì |", "| MEDIUM | — | — | no |", "model.complete"),
        ("| `message: string` | — |", "| `message: string`, `loud: boolean` | — |", "core.echo"),
        ("`parameters: object` |", "`parameters: string` |", "model.complete"),
    ]:
        drifted = text.replace(before, after, 1)
        assert drifted != text, before
        assert documented_catalogue(drifted)[cid] != coded[cid], before
