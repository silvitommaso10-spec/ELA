"""The tables of ADR 0016 and ``ela.devices`` say the same thing.

Same pattern as the other ADR tests: §2 (the §16 vocabulary mapped onto ``DeviceAvailability``),
§3 (the setting and its default) and §4 (what ``local`` declares, and how a system name becomes an
``OperatingSystem``) are read from the document and checked against the code. Each table has a
distinctive row shape, so no table is mistaken for another — and none of them has the two cells of
a schema row, which is ``test_adr_persistence.py``'s business.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from ela.devices import (
    AVAILABLE,
    DEFAULT_HEARTBEAT_TTL_SECONDS,
    LOCAL_DEVICE_NAME,
    SYSTEMS,
    UNAVAILABLE,
    DeviceSettings,
    local_device,
)
from ela.domain import DeviceAvailability, OperatingSystem
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
