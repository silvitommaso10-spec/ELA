"""The port tables in the ADRs and the protocols in ``ela.ports`` describe the same ports.

The ADR is the documented decision, the module is the running code. Neither may drift from the
other — members or sync/async mode — without this test noticing. An ADR is immutable, so a later
ADR that extends a port (0008: ``TaskRepository.add_plan``/``plan``; 0011: the signature of
``PermissionGuardianPort.decide``) documents the members it adds or changes in a row of its own,
and a later ADR that shrinks a port (0010: ``CapabilityRegistryPort`` without ``register``)
documents the members that remain in a replacing row; an ADR that introduces whole ports (0013:
``AuthorizingGuardianPort``, ``ToolRegistryPort``) lists them under "Port introdotti:". Extensions
only add, replacements only remove, introductions only bring new names; introductions apply
first, then extensions, then replacements; the result is what the code must match. An ADR that
both extends and replaces (0012: ``AuthorizationStore`` with ``consume`` and without
``record_use``) has two tables, each under its label, and is read by section (ADR 0012 §8). A
changed signature is checked by ``test_adr_guardian.py``, member by member here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.contracts.protocols import is_async, members, method_names, port_protocols

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"
ADR_PATH = ADR_DIR / "0005-ports.md"
EXTENDING = "Port estesi:"
REPLACING = "Port sostituiti:"
INTRODUCING = "Port introdotti:"
Source = tuple[Path, str | None]
"""An ADR and the label of the table to read, or ``None`` to read the whole file."""
EXTENDING_ADRS: tuple[Source, ...] = (
    (ADR_DIR / "0008-task-engine.md", None),
    (ADR_DIR / "0011-permission-guardian.md", None),
    (ADR_DIR / "0012-authorizations.md", EXTENDING),
)
REPLACING_ADRS: tuple[Source, ...] = (
    (ADR_DIR / "0010-capability-catalogue.md", None),
    (ADR_DIR / "0012-authorizations.md", REPLACING),
)
INTRODUCING_ADRS: tuple[Source, ...] = (
    (ADR_DIR / "0013-executor.md", INTRODUCING),
    (ADR_DIR / "0014-verification.md", INTRODUCING),
)
"""ADRs that add whole ports (ADR 0013 §10, ADR 0014 §1): a port introduced must not exist
already."""
INTRODUCED_PORTS = frozenset(
    {"AuthorizingGuardianPort", "ToolRegistryPort", "VerifierPort", "VerifierRegistryPort"}
)
ROW = re.compile(r"^\| `(\w+)` \| ([^|]+) \| (sync|async) \| (.+) \|$")
MEMBER = re.compile(r"`(\w+)`")


def section_of(text: str, label: str) -> str:
    """The lines from ``label`` to the end of the first table after it (ADR 0012 §8)."""
    lines = text.splitlines()
    assert label in lines, f"the ADR must contain the label {label!r}"
    start = lines.index(label) + 1
    kept: list[str] = []
    for line in lines[start:]:
        if line.startswith("|"):
            kept.append(line)
        elif kept:
            break
    return "\n".join(kept)


def documented_ports(
    text: str, section: str | None = None
) -> dict[str, tuple[str, frozenset[str]]]:
    """Port name -> (mode, members) for every row of the table; a port appears at most once."""
    if section is not None:
        text = section_of(text, section)
    rows: dict[str, tuple[str, frozenset[str]]] = {}
    for line in text.splitlines():
        match = ROW.match(line)
        if match is not None:
            name, _, mode, cells = match.groups()
            assert name not in rows, f"{name} appears in two rows: read the tables by section"
            rows[name] = (mode, frozenset(MEMBER.findall(cells)))
    assert rows, "the ADR must contain a port table"
    return rows


def all_documented_ports(
    base: str,
    extensions: tuple[str, ...] = (),
    replacements: tuple[str, ...] = (),
    introductions: tuple[str, ...] = (),
) -> dict[str, tuple[str, frozenset[str]]]:
    """ADR 0005, then every introducing ADR (new ports only), then every extending ADR (members
    joined), then every replacing ADR (members replaced, never more than before). Same mode
    throughout."""
    union = documented_ports(base)
    for text in introductions:
        for name, row in documented_ports(text).items():
            assert name not in union, f"{name} is introduced twice"
            union[name] = row
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


def _read(sources: tuple[Source, ...]) -> tuple[str, ...]:
    """Each source as the text ``documented_ports`` should see: the whole file or one section."""
    texts = []
    for path, section in sources:
        text = path.read_text(encoding="utf-8")
        texts.append(text if section is None else section_of(text, section))
    return tuple(texts)


def _text(source: Source) -> str:
    return _read((source,))[0]


def documented() -> dict[str, tuple[str, frozenset[str]]]:
    return all_documented_ports(
        ADR_PATH.read_text(encoding="utf-8"),
        _read(EXTENDING_ADRS),
        _read(REPLACING_ADRS),
        _read(INTRODUCING_ADRS),
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
    extension = documented_ports(_text(EXTENDING_ADRS[0]))
    assert set(extension) == {"TaskRepository"}
    assert extension["TaskRepository"][1] == {"add_plan", "plan"}
    assert not (base["TaskRepository"][1] & extension["TaskRepository"][1])


def test_the_guardian_extension_changes_a_signature_not_the_members() -> None:
    """ADR 0011 adds ``authorization_uses`` to ``decide``: same member, documented as extension."""
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    extension = documented_ports(_text(EXTENDING_ADRS[1]))
    assert set(extension) == {"PermissionGuardianPort"}
    assert extension["PermissionGuardianPort"] == base["PermissionGuardianPort"]


def test_each_replacing_adr_documents_a_shrunk_port() -> None:
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    replacement = documented_ports(_text(REPLACING_ADRS[0]))
    assert set(replacement) == {"CapabilityRegistryPort"}
    assert replacement["CapabilityRegistryPort"][1] == {"get", "specs"}
    assert base["CapabilityRegistryPort"][1] - replacement["CapabilityRegistryPort"][1] == {
        "register"
    }


def test_the_authorizations_adr_extends_then_replaces_the_store() -> None:
    """ADR 0012 §4: one row adds ``consume``, the other lists what remains — no ``record_use``."""
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    extension = documented_ports(_text(EXTENDING_ADRS[2]))
    replacement = documented_ports(_text(REPLACING_ADRS[1]))
    assert set(extension) == set(replacement) == {"AuthorizationStore"}
    assert extension["AuthorizationStore"][1] == {"consume"}
    assert replacement["AuthorizationStore"][1] == {
        "grant",
        "get",
        "for_capability",
        "uses",
        "consume",
    }
    assert base["AuthorizationStore"][1] - replacement["AuthorizationStore"][1] == {"record_use"}


def test_the_executor_adr_introduces_two_ports_the_base_does_not_have() -> None:
    """ADR 0013 §10: the audited Guardian and the tool registry are new ports, not extensions."""
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    introduced = documented_ports(_text(INTRODUCING_ADRS[0]))
    assert set(introduced) == {"AuthorizingGuardianPort", "ToolRegistryPort"}
    assert not (set(introduced) & set(base))
    assert introduced["AuthorizingGuardianPort"] == ("async", frozenset({"authorize"}))
    assert introduced["ToolRegistryPort"] == ("sync", frozenset({"get", "tools"}))


def test_the_verification_adr_introduces_two_ports_the_base_does_not_have() -> None:
    """ADR 0014 §1: the verifier and its registry are new ports, mirrors of the tool ones."""
    base = documented_ports(ADR_PATH.read_text(encoding="utf-8"))
    introduced = documented_ports(_text(INTRODUCING_ADRS[1]))
    assert set(introduced) == {"VerifierPort", "VerifierRegistryPort"}
    assert not (set(introduced) & set(base))
    assert introduced["VerifierPort"] == (
        "async",
        frozenset({"capability_id", "name", "conditions", "verify"}),
    )
    assert introduced["VerifierRegistryPort"] == ("sync", frozenset({"get", "verifiers"}))


def test_an_introduction_of_a_known_port_is_detected() -> None:
    base = "| `AuditLog` | §32 | async | `append`, `read` |"
    with pytest.raises(AssertionError, match="introduced twice"):
        all_documented_ports(base, introductions=("| `AuditLog` | §32 | async | `x` |",))
    added = all_documented_ports(base, introductions=("| `Other` | §1 | sync | `x` |",))
    assert added["Other"] == ("sync", frozenset({"x"}))
    without = all_documented_ports(
        ADR_PATH.read_text(encoding="utf-8"), _read(EXTENDING_ADRS), _read(REPLACING_ADRS)
    )
    assert set(coded_ports()) - set(without) == INTRODUCED_PORTS


def test_a_file_with_two_rows_for_one_port_must_be_read_by_section() -> None:
    text = (ADR_DIR / "0012-authorizations.md").read_text(encoding="utf-8")
    with pytest.raises(AssertionError, match="two rows"):
        documented_ports(text)
    assert documented_ports(text, EXTENDING) != documented_ports(text, REPLACING)


def test_a_missing_label_is_detected() -> None:
    with pytest.raises(AssertionError, match="label"):
        section_of("| `AuditLog` | §32 | async | `append` |", EXTENDING)
    two_tables = "Port estesi:\n\n| a |\n| b |\n\ntext\n\nPort sostituiti:\n\n| c |\n"
    assert section_of(two_tables, EXTENDING) == "| a |\n| b |"
    assert section_of(two_tables, REPLACING) == "| c |"


@pytest.mark.parametrize(
    "path",
    sorted(
        {
            ADR_PATH,
            *(p for p, _ in EXTENDING_ADRS),
            *(p for p, _ in REPLACING_ADRS),
            *(p for p, _ in INTRODUCING_ADRS),
        }
    ),
    ids=lambda p: p.name[:4],
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
        text, (_text(EXTENDING_ADRS[0]).replace("`add_plan`, ", "", 1),)
    )
    assert extended["TaskRepository"][1] != coded["TaskRepository"][1]
    replacing = _text(REPLACING_ADRS[0])
    drifted_replacement = replacing.replace(
        "| `CapabilityRegistryPort` | §28, §29 | sync | `get`, `specs` |",
        "| `CapabilityRegistryPort` | §28, §29 | sync | `get` |",
        1,
    )
    assert drifted_replacement != replacing
    others = _read(REPLACING_ADRS[1:])
    replaced = all_documented_ports(text, _read(EXTENDING_ADRS), (drifted_replacement, *others))
    assert replaced["CapabilityRegistryPort"][1] != coded["CapabilityRegistryPort"][1]
    without_replacement = all_documented_ports(text, _read(EXTENDING_ADRS), others)
    assert without_replacement["CapabilityRegistryPort"][1] != coded["CapabilityRegistryPort"][1]
    without_the_store_replacement = all_documented_ports(
        text, _read(EXTENDING_ADRS), _read(REPLACING_ADRS[:1])
    )
    assert "record_use" in without_the_store_replacement["AuthorizationStore"][1]
    assert without_the_store_replacement["AuthorizationStore"][1] != coded["AuthorizationStore"][1]
