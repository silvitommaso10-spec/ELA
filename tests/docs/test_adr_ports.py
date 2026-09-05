"""The port tables in the ADRs and the protocols in ``ela.ports`` describe the same ports.

The ADR is the documented decision, the module is the running code. Neither may drift from the
other — members or sync/async mode — without this test noticing. An ADR is immutable, so a later
ADR that extends a port (0008: ``TaskRepository.add_plan``/``plan``; 0011: the signature of
``PermissionGuardianPort.decide``) documents the members it adds or changes in a row of its own,
and a later ADR that shrinks a port (0010: ``CapabilityRegistryPort`` without ``register``)
documents the members that remain in a replacing row. Extensions only add, replacements only
remove; extensions apply first, then replacements; the result is what the code must match. A
changed signature is checked by ``test_adr_guardian.py``, member by member here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.contracts.protocols import is_async, members, method_names, port_protocols

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0005-ports.md"
EXTENDING_ADRS = (ADR_DIR / "0008-task-engine.md", ADR_DIR / "0011-permission-guardian.md")
REPLACING_ADRS = (ADR_DIR / "0010-capability-catalogue.md",)
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


def all_documented_ports(
    base: str, extensions: tuple[str, ...] = (), replacements: tuple[str, ...] = ()
) -> dict[str, tuple[str, frozenset[str]]]:
    """ADR 0005, then every extending ADR (members joined), then every replacing ADR (members
    replaced, never more than before). Same mode throughout."""
    union = documented_ports(base)
    for text in extensions:
        for name, (mode, members_) in documented_ports(text).items():
            assert name in union, f"{name} is extended before being introduced"
            assert union[name][0] == mode, f"{name} changes mode in an extension"
            union[name] = (mode, union[name][1] | members_)
    for text in replacements:
        for name, (mode, members_) in documented_ports(text).items():
            assert name in union, f"{name} is replaced before being introduced"
            assert union[name][0] == mode, f"{name} changes mode in a replacement"
            assert members_ < union[name][1], f"a replacement of {name} only removes members"
            union[name] = (mode, members_)
    return union


def _read(paths: tuple[Path, ...]) -> tuple[str, ...]:
    return tuple(path.read_text(encoding="utf-8") for path in paths)


def documented() -> dict[str, tuple[str, frozenset[str]]]:
    return all_documented_ports(
        ADR_PATH.read_text(encoding="utf-8"), _read(EXTENDING_ADRS), _read(REPLACING_ADRS)
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


def test_the_guardian_extension_changes_a_signature_not_the_members() -> None:
    """ADR 0011 adds ``authorization_uses`` to ``decide``: same member, documented as extension."""
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    extension = documented_ports(EXTENDING_ADRS[1].read_text(encoding="utf-8"))
    assert set(extension) == {"PermissionGuardianPort"}
    assert extension["PermissionGuardianPort"] == base["PermissionGuardianPort"]


def test_each_replacing_adr_documents_a_shrunk_port() -> None:
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    replacement = documented_ports(REPLACING_ADRS[0].read_text(encoding="utf-8"))
    assert set(replacement) == {"CapabilityRegistryPort"}
    assert replacement["CapabilityRegistryPort"][1] == {"get", "specs"}
    assert base["CapabilityRegistryPort"][1] - replacement["CapabilityRegistryPort"][1] == {
        "register"
    }


@pytest.mark.parametrize(
    "path", [ADR_PATH, *EXTENDING_ADRS, *REPLACING_ADRS], ids=lambda p: p.name[:4]
)
def test_table_cites_the_spec(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            assert "§" in match.group(2), match.group(1)


def test_an_extension_of_an_unknown_port_is_detected() -> None:
    base = "| `AuditLog` | §32 | async | `append`, `read` |"
    with pytest.raises(AssertionError, match="extended before being introduced"):
        all_documented_ports(base, ("| `Other` | §1 | async | `x` |",))
    with pytest.raises(AssertionError, match="changes mode in an extension"):
        all_documented_ports(base, ("| `AuditLog` | §32 | sync | `x` |",))


def test_a_replacement_only_removes_from_a_known_port() -> None:
    """Negative cases of the replacing rows: unknown port, mode change, added member, no change."""
    base = "| `AuditLog` | §32 | async | `append`, `read` |"
    with pytest.raises(AssertionError, match="replaced before being introduced"):
        all_documented_ports(base, replacements=("| `Other` | §1 | async | `x` |",))
    with pytest.raises(AssertionError, match="changes mode in a replacement"):
        all_documented_ports(base, replacements=("| `AuditLog` | §32 | sync | `append` |",))
    with pytest.raises(AssertionError, match="only removes"):
        all_documented_ports(
            base, replacements=("| `AuditLog` | §32 | async | `append`, `read`, `clear` |",)
        )
    with pytest.raises(AssertionError, match="only removes"):
        all_documented_ports(
            base, replacements=("| `AuditLog` | §32 | async | `append`, `read` |",)
        )
    shrunk = all_documented_ports(base, replacements=("| `AuditLog` | §32 | async | `append` |",))
    assert shrunk["AuditLog"] == ("async", frozenset({"append"}))


def test_a_replacement_applies_after_an_extension() -> None:
    base = "| `AuditLog` | §32 | async | `append`, `read` |"
    extension = "| `AuditLog` | §32 | async | `clear` |"
    replacement = "| `AuditLog` | §32 | async | `append`, `clear` |"
    result = all_documented_ports(base, (extension,), (replacement,))
    assert result["AuditLog"] == ("async", frozenset({"append", "clear"}))


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
        text, (EXTENDING_ADRS[0].read_text(encoding="utf-8").replace("`add_plan`, ", "", 1),)
    )
    assert extended["TaskRepository"][1] != coded["TaskRepository"][1]
    replacing = REPLACING_ADRS[0].read_text(encoding="utf-8")
    drifted_replacement = replacing.replace(
        "| `CapabilityRegistryPort` | §28, §29 | sync | `get`, `specs` |",
        "| `CapabilityRegistryPort` | §28, §29 | sync | `get` |",
        1,
    )
    assert drifted_replacement != replacing
    replaced = all_documented_ports(text, _read(EXTENDING_ADRS), (drifted_replacement,))
    assert replaced["CapabilityRegistryPort"][1] != coded["CapabilityRegistryPort"][1]
    without_replacement = all_documented_ports(text, _read(EXTENDING_ADRS))
    assert without_replacement["CapabilityRegistryPort"][1] != coded["CapabilityRegistryPort"][1]
