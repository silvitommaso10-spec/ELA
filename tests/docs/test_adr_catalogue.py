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
from ela.permissions import catalogue_v01, production_catalogue

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0010-capability-catalogue.md"
EXTENDING = "Capability estese:"
ADDING = "Capability aggiunte:"
EXTENDING_ADRS = ((ADR_DIR / "0022-model-router.md", EXTENDING),)
"""ADRs that give a capability a new argument (ADR 0022 §2: ``task_type`` on ``model.complete``),
under a label, with the whole row rewritten."""
ADDING_ADRS = (
    (ADR_DIR / "0029-screen-capture.md", ADDING),
    (ADR_DIR / "0030-screen-text.md", ADDING),
    (ADR_DIR / "0033-voice-out.md", ADDING),
    (ADR_DIR / "0034-voice-online.md", ADDING),
)
"""ADRs that add a capability the catalogue did not have (ADR 0029 §6: ``perception.capture_
screen``), under a label of their own. An addition must be new, the way an extension must not be:
the shape ADR 0005's port tables already use, applied to the catalogue."""
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


def section(path: Path, label: str) -> str:
    """The text after ``label`` in ``path``, up to the next heading: the table it introduces."""
    text = path.read_text(encoding="utf-8")
    assert label in text, f"{path.name} must carry the label {label!r}"
    return text.split(label, 1)[1].split("\n#", 1)[0]


def all_documented_capabilities() -> dict[str, Row]:
    """ADR 0010's catalogue, the rows later ADRs replace, and the capabilities they add.

    An ADR is immutable and the catalogue is one table, so a capability that gains an argument
    later is documented again, in full, by the ADR that gave it: the last row wins, and a row
    that replaces a capability nobody declared is a drift. A capability *added* later is the
    mirror: it must not exist already, or the ADR is redeclaring somebody else's row.
    """
    union = documented_catalogue(ADR_PATH.read_text(encoding="utf-8"))
    for path, label in EXTENDING_ADRS:
        for cid, row in documented_catalogue(section(path, label)).items():
            assert cid in union, f"{cid} is extended before being declared ({path.name})"
            union[cid] = row
    for path, label in ADDING_ADRS:
        for cid, row in documented_catalogue(section(path, label)).items():
            assert cid not in union, f"{cid} is added twice ({path.name})"
            union[cid] = row
    return union


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
    """Against the **production** catalogue: the documents describe what ELA runs (ADR 0029 §13).

    ``catalogue_v01()`` is checked separately and stays three; the union of the ADR tables is the
    four the composition root builds.
    """
    documented = all_documented_capabilities()
    coded = {spec.id: coded_row(spec) for spec in production_catalogue().specs()}
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
