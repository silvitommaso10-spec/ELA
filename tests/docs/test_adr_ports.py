"""The table in ADR 0005 and the protocols in ``ela.ports`` describe the same ports.

The ADR is the documented decision, the module is the running code. Neither may drift from the
other — members or sync/async mode — without this test noticing.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.contracts.protocols import is_async, members, method_names, port_protocols

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0005-ports.md"
ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
MEMBER = re.compile(r"`(\w+)`")


def documented_ports(text: str) -> dict[str, tuple[str, frozenset[str]]]:
    """Port name -> (mode, members) for every row of the table."""
    rows: dict[str, tuple[str, frozenset[str]]] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            name, _, mode, cells = match.groups()
            rows[name] = (mode, frozenset(MEMBER.findall(cells)))
    assert rows, "ADR 0005 must contain the port table"
    return rows


def coded_ports() -> dict[str, tuple[str, frozenset[str]]]:
    rows: dict[str, tuple[str, frozenset[str]]] = {}
    for port in port_protocols():
        modes = {is_async(port, name) for name in method_names(port)}
        assert len(modes) == 1, f"{port.__name__} mixes sync and async members"
        rows[port.__name__] = ("async" if modes.pop() else "sync", members(port))
    return rows


def test_table_matches_the_code() -> None:
    documented = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    coded = coded_ports()
    assert set(documented) == set(coded)
    for name in coded:
        assert documented[name][1] == coded[name][1], name


def test_table_modes_match_the_code() -> None:
    documented = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    for name, (mode, _) in coded_ports().items():
        assert documented[name][0] == mode, name


def test_table_cites_the_spec() -> None:
    text = ADR_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            assert "§" in match.group(2), match.group(1)


def test_a_drifted_table_is_detected() -> None:
    """Negative case: drop one member and flip one mode; both drifts must show."""
    text = ADR_PATH.read_text(encoding="utf-8")
    drifted = text.replace(
        "| `AuditLog` | §32 | async | `append`, `read` |",
        "| `AuditLog` | §32 | sync | `append` |",
        1,
    )
    assert drifted != text
    documented = documented_ports(drifted)
    coded = coded_ports()
    assert documented["AuditLog"][1] != coded["AuditLog"][1]
    assert documented["AuditLog"][0] != coded["AuditLog"][0]
