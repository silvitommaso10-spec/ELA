"""The tables of ADR 0016 and ADR 0035, and ``ela.devices``, say the same thing.

Same pattern as the other ADR tests. From ADR 0016: §2 (the §16 vocabulary mapped onto
``DeviceAvailability``), §3 (the setting and its default) and §4 (what ``local`` declares, and how
a system name becomes an ``OperatingSystem``). From ADR 0035, which continues it (M6.1b): §2 (the
two halves of a row), §3 (the two audit events) and §4 (the rule that keeps the halves apart).

Each table has a distinctive row shape, so no table is mistaken for another — and none of them has
the two cells of a schema row, which is ``test_adr_persistence.py``'s business. The two documents
are read through two functions rather than one, so a table that moved between them fails instead
of being found anyway.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from ela.devices import (
    AVAILABLE,
    DECLARED_FIELDS,
    DEFAULT_HEARTBEAT_TTL_SECONDS,
    LOCAL_DEVICE_NAME,
    REGISTRY_ACTOR,
    SYSTEMS,
    UNAVAILABLE,
    DeviceSettings,
    local_device,
)
from ela.domain import AuditEventType, Device, DeviceAvailability, OperatingSystem
from tests.architecture.rules import OBSERVED_FIELDS, REFRESH_MODULE, RULES
from tests.architecture.violations import PACKAGE_ROOT
from tests.domain.examples import MUCH_LATER

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0016-device-registry.md"
AVAILABILITY_ROW = re.compile(r"^\| (disponibile|non disponibile) \| `(\w+)` \| (.+) \|$")
SETTING_ROW = re.compile(r"^\| `(ELA_\w+)` \| (\d+) s \| (.+) \|$")
LOCAL_ROW = re.compile(r"^\| `([a-z_]+)` \| (`\w+`|vuoto|assente|dal chiamante) \| (.+) \|$")
"""Lower-case field names only: the systems table of the same section is capitalised."""
SYSTEM_ROW = re.compile(r"^\| `(Darwin|Windows|Linux)` \| `(\w+)` \| (.+) \|$")

ABSENT = {"vuoto": (), "assente": None}
"""Words the §4 table uses for a field that declares nothing."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §2 — the vocabulary of §16 mapped onto the domain
# ----------------------------------------------------------------------------------------


def documented_availability(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(2)
        for line in text.splitlines()
        if (match := AVAILABILITY_ROW.match(line)) is not None
    }
    assert rows, "ADR 0016 §2 must contain the availability table"
    return rows


def test_the_vocabulary_table_matches_the_constants() -> None:
    rows = documented_availability(adr_text())
    assert rows == {"disponibile": AVAILABLE.value, "non disponibile": UNAVAILABLE.value}
    assert (AVAILABLE, UNAVAILABLE) == (
        DeviceAvailability.ONLINE,
        DeviceAvailability.UNREACHABLE,
    )


def test_the_two_values_are_distinct_members_of_the_domain_enum() -> None:
    """Decision A: the mapping reuses the enum, it does not extend it."""
    assert AVAILABLE is not UNAVAILABLE
    assert {AVAILABLE, UNAVAILABLE} <= set(DeviceAvailability)
    assert not {"AVAILABLE", "UNAVAILABLE"} & {member.value for member in DeviceAvailability}


def test_a_drifted_vocabulary_row_is_detected() -> None:
    """Negative case: the ADR claiming ``OFFLINE`` where the code says ``UNREACHABLE``."""
    drifted = adr_text().replace(
        "| non disponibile | `UNREACHABLE` |", "| non disponibile | `OFFLINE` |"
    )
    assert documented_availability(drifted)["non disponibile"] != UNAVAILABLE.value


# ----------------------------------------------------------------------------------------
# §3 — the setting
# ----------------------------------------------------------------------------------------


def documented_setting(text: str) -> tuple[str, int]:
    rows = [
        (match.group(1), int(match.group(2)))
        for line in text.splitlines()
        if (match := SETTING_ROW.match(line)) is not None
    ]
    assert len(rows) == 1, "ADR 0016 §3 must document exactly one setting"
    return rows[0]


def test_the_setting_table_matches_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
    variable, default = documented_setting(adr_text())
    assert default == DEFAULT_HEARTBEAT_TTL_SECONDS
    monkeypatch.setenv(variable, "7")
    assert DeviceSettings(_env_file=None).device_heartbeat_ttl_seconds == 7


def test_a_drifted_default_is_detected() -> None:
    drifted = adr_text().replace("| 60 s |", "| 90 s |")
    assert documented_setting(drifted)[1] != DEFAULT_HEARTBEAT_TTL_SECONDS


# ----------------------------------------------------------------------------------------
# §4 — what ``local`` declares, and how a system is named
# ----------------------------------------------------------------------------------------


def documented_local(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(2).strip("`")
        for line in text.splitlines()
        if (match := LOCAL_ROW.match(line)) is not None
    }
    assert rows, "ADR 0016 §4 must contain the table of what ``local`` declares"
    return rows


def coded_local() -> dict[str, Any]:
    device = local_device(MUCH_LATER, system="Darwin")
    return {
        field: getattr(device, field)
        for field in (
            "name",
            "network",
            "privacy",
            "availability",
            "status",
            "performance",
            "power_source",
            "capabilities",
            "available_tools",
            "current_workload",
            "last_seen_at",
        )
    }


def test_the_local_table_covers_every_field_it_claims() -> None:
    assert set(documented_local(adr_text())) == set(coded_local())


def test_every_documented_value_is_what_local_declares() -> None:
    coded = coded_local()
    for field, documented in documented_local(adr_text()).items():
        value = coded[field]
        if documented in ABSENT:
            assert value == ABSENT[documented], field
        elif documented == "dal chiamante":
            assert value == (), field  # nothing by default; the caller supplies the names
        elif field == "name":
            assert value == documented == LOCAL_DEVICE_NAME, field
        else:
            assert value.value == documented, field


def test_a_drifted_local_row_is_detected() -> None:
    """Negative case: the ADR promising ``TRUSTED`` where the code is fail-safe."""
    drifted = adr_text().replace("| `privacy` | `LOCAL_ONLY` |", "| `privacy` | `TRUSTED` |")
    assert documented_local(drifted)["privacy"] != coded_local()["privacy"].value


def documented_systems(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(2)
        for line in text.splitlines()
        if (match := SYSTEM_ROW.match(line)) is not None
    }
    assert rows, "ADR 0016 §4 must contain the operating systems table"
    return rows


def test_the_systems_table_matches_the_mapping() -> None:
    documented = documented_systems(adr_text())
    assert documented == {name: system.value for name, system in SYSTEMS.items()}


def test_ios_is_not_detected_locally() -> None:
    """ADR 0016 §4: no Core runs on an iPhone; that node registers itself over the network."""
    assert OperatingSystem.IOS.value not in documented_systems(adr_text()).values()
    assert OperatingSystem.IOS not in SYSTEMS.values()


# ----------------------------------------------------------------------------------------
# ADR 0035 — the two halves of a row, the two events, the rule (M6.1b)
# ----------------------------------------------------------------------------------------

REFRESH_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0035-node-refresh.md"
HALF_ROW = re.compile(r"^\| (Dichiarato|Osservato) \| (`.+`) \| (.+?) \| (.+?) \|$")
EVENT_ROW = re.compile(r"^\| `(DEVICE_\w+)` \| (.+?) \| `(\w+)` \|$")
RULE_ROW = re.compile(r"^\| (\d+) \| `([a-z-]+)` \| `(devices/\w+\.py)` \|$")
NAMED = re.compile(r"`(\w+)`")


def refresh_text() -> str:
    return REFRESH_PATH.read_text(encoding="utf-8")


def documented_halves(text: str) -> dict[str, tuple[str, ...]]:
    rows = {
        match.group(1): tuple(NAMED.findall(match.group(2)))
        for line in text.splitlines()
        if (match := HALF_ROW.match(line)) is not None
    }
    assert rows, "ADR 0035 §2 must contain the table of the two halves"
    return rows


def test_the_declared_half_is_the_one_the_reconciliation_replaces() -> None:
    assert documented_halves(refresh_text())["Dichiarato"] == DECLARED_FIELDS


def test_the_observed_half_is_the_one_rule_44_forbids() -> None:
    """The document and the rule say the same four names, or one of them is decoration."""
    assert set(documented_halves(refresh_text())["Osservato"]) == OBSERVED_FIELDS


def test_the_two_halves_are_disjoint_and_are_fields_of_a_device() -> None:
    """A field in both halves would be a field two writers own, which is the defect itself."""
    halves = documented_halves(refresh_text())
    declared, observed = set(halves["Dichiarato"]), set(halves["Osservato"])

    assert not declared & observed
    assert declared | observed <= set(Device.model_fields)


def test_a_drifted_half_is_detected() -> None:
    """Negative case: the document promising that the availability is re-declared."""
    drifted = refresh_text().replace("`privacy`, `capabilities`", "`privacy`, `availability`")
    assert documented_halves(drifted)["Dichiarato"] != DECLARED_FIELDS


def documented_events(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := EVENT_ROW.match(line)) is not None
    }
    assert rows, "ADR 0035 §3 must contain the table of the two events"
    return rows


def test_the_event_table_names_types_that_exist_and_an_actor_that_is_the_registrys() -> None:
    documented = documented_events(refresh_text())

    assert set(documented) == {
        AuditEventType.DEVICE_REGISTERED.value,
        AuditEventType.DEVICE_REFRESHED.value,
    }
    assert set(documented.values()) == {REGISTRY_ACTOR.kind.value}


def test_a_drifted_event_row_is_detected() -> None:
    """Negative case: the document claiming the actor is the node announcing itself."""
    drifted = refresh_text().replace(
        "| `DEVICE_REFRESHED` | la metà dichiarata è cambiata | `SYSTEM` |",
        "| `DEVICE_REFRESHED` | la metà dichiarata è cambiata | `DEVICE` |",
    )
    assert set(documented_events(drifted).values()) != {REGISTRY_ACTOR.kind.value}


def documented_rules(text: str) -> dict[str, str]:
    rows = {
        match.group(2): match.group(3)
        for line in text.splitlines()
        if (match := RULE_ROW.match(line)) is not None
    }
    assert rows, "ADR 0035 §4 must contain the rule table"
    return rows


def test_the_rule_table_names_a_rule_that_exists_and_the_module_it_reads() -> None:
    ((name, module),) = documented_rules(refresh_text()).items()

    assert name in RULES
    assert Path(module) == REFRESH_MODULE
    assert (PACKAGE_ROOT / module).is_file()


def test_a_drifted_rule_row_is_detected() -> None:
    drifted = refresh_text().replace("`devices/refresh.py`", "`devices/registry.py`")
    assert Path(next(iter(documented_rules(drifted).values()))) != REFRESH_MODULE
