"""The port tables in the ADRs and the protocols in ``ela.ports`` describe the same ports.

The ADR is the documented decision, the module is the running code. Neither may drift from the
other — members or sync/async mode — without this test noticing. An ADR is immutable, so a later
ADR that extends a port (0008: ``TaskRepository.add_plan``/``plan``) documents the members it
adds in a row of its own, and the union of the rows is what the code must match.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.contracts.protocols import is_async, members, method_names, port_protocols

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0005-ports.md"
EXTENDING_ADRS = (ADR_DIR / "0008-task-engine.md",)
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
    assert rows, "the ADR must contain a port table"
    return rows


def all_documented_ports(base: str, *extensions: str) -> dict[str, tuple[str, frozenset[str]]]:
    """ADR 0005 plus every extending ADR: same mode, members joined."""
    union = documented_ports(base)
    for text in extensions:
        for name, (mode, members_) in documented_ports(text).items():
            assert name in union, f"{name} is extended before being introduced"
            assert union[name][0] == mode, f"{name} changes mode in an extension"
            union[name] = (mode, union[name][1] | members_)
    return union


def documented() -> dict[str, tuple[str, frozenset[str]]]:
    return all_documented_ports(
        ADR_PATH.read_text(encoding="utf-8"),
        *(path.read_text(encoding="utf-8") for path in EXTENDING_ADRS),
    )


def coded_ports() -> dict[str, tuple[str, frozenset[str]]]:
    rows: dict[str, tuple[str, frozenset[str]]] = {}
    for port in port_protocols():
        modes = {is_async(port, name) for name in method_names(port)}
        assert len(modes) == 1, f"{port.__name__} mixes sync and async members"
        rows[port.__name__] = ("async" if modes.pop() else "sync", members(port))
    return rows


def test_table_matches_the_code() -> None:
    rows = documented()
    coded = coded_ports()
    assert set(rows) == set(coded)
    for name in coded:
        assert rows[name][1] == coded[name][1], name


def test_table_modes_match_the_code() -> None:
    rows = documented()
    for name, (mode, _) in coded_ports().items():
        assert rows[name][0] == mode, name


def test_each_adr_documents_its_own_members() -> None:
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    extension = documented_ports(EXTENDING_ADRS[0].read_text(encoding="utf-8"))
    assert set(extension) == {"TaskRepository"}
    assert extension["TaskRepository"][1] == {"add_plan", "plan"}
    assert not (base["TaskRepository"][1] & extension["TaskRepository"][1])


@pytest.mark.parametrize("path", [ADR_PATH, *EXTENDING_ADRS], ids=lambda p: p.name[:4])
def test_table_cites_the_spec(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            assert "§" in match.group(2), match.group(1)


def test_an_extension_of_an_unknown_port_is_detected() -> None:
    base = "| `AuditLog` | §32 | async | `append`, `read` |"
    with pytest.raises(AssertionError, match="before being introduced"):
        all_documented_ports(base, "| `Other` | §1 | async | `x` |")
    with pytest.raises(AssertionError, match="changes mode"):
        all_documented_ports(base, "| `AuditLog` | §32 | sync | `x` |")


def test_a_drifted_table_is_detected() -> None:
    """Negative case: drop one member and flip one mode; both drifts must show."""
    text = ADR_PATH.read_text(encoding="utf-8")
    drifted = text.replace(
        "| `AuditLog` | §32 | async | `append`, `read` |",
        "| `AuditLog` | §32 | sync | `append` |",
        1,
    )
    assert drifted != text
    rows = all_documented_ports(drifted)
    coded = coded_ports()
    assert rows["AuditLog"][1] != coded["AuditLog"][1]
    assert rows["AuditLog"][0] != coded["AuditLog"][0]
    extended = all_documented_ports(
        text, EXTENDING_ADRS[0].read_text(encoding="utf-8").replace("`add_plan`, ", "", 1)
    )
    assert extended["TaskRepository"][1] != coded["TaskRepository"][1]
