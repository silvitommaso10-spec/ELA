"""The tables of ADR 0017 and ``ela.devices.orchestrator`` say the same thing.

Same pattern as the other ADR tests: §4 (the hard filters and their refusals), §5 (the weight of
every criterion), §5-bis (the criteria of §17 the domain does not carry), §7 (the two audit event
types) and §9 (the three architecture rules) are read from the document and checked against the
code. Each table has a distinctive row shape, so no table is mistaken for another.

The weights are conventional; what is not conventional is that they be *the same* in the document
and in the module. Without this file the ADR would describe a policy the code no longer applies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ela.devices import (
    NETWORK_POINTS,
    PERFORMANCE_POINTS,
    POWER_POINTS,
    PRIVACY_ORDER,
    STATUS_POINTS,
    TRAIT_POINTS,
    UNGUARDED_RISK,
    WORKLOAD_POINTS,
    Refusal,
)
from ela.domain import (
    AuditEventType,
    DeviceStatus,
    NetworkKind,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from tests.architecture.rules import DEVICE_PORT_ALLOWED, RULES

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0017-device-orchestrator.md"

FILTER_ROW = re.compile(r"^\| F(\d) \| ([^|]+?) \| ([^|]+?) \| `(\w+)` \| ([^|]+?) \|$")
"""§4: the five hard filters, numbered — no other table in the ADR numbers its rows."""
WEIGHT_ROW = re.compile(r"^\| `([a-z_]+)` \| ([^|]+?) \| ([^|]+?) \|$")
"""§5: a component name in backticks — lower case, unlike the event types of §7."""
MISSING_ROW = re.compile(r"^\| ([^|`]+?) \| — \| non modellato: (.+?) \|$")
"""§5-bis: the criteria with no field at all — the em dash is what identifies the table."""
EVENT_ROW = re.compile(r"^\| `(DEVICE_\w+)` \| ([^|]+?) \| ([^|]+?) \|$")
"""§7: the two audit event types."""
RULE_ROW = re.compile(r"^\| (\d+) `([a-z-]+)` \| ([^|]+?) \| ([^|]+?) \|$")
"""§9: the architecture rules, by number and by the key they have in ``RULES``."""

POINTS = re.compile(r"([A-Z_]+) ([+-]?\d+)")
"""``LOCAL +20, REMOTE +5`` inside a §5 value cell."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


def rows(pattern: re.Pattern[str]) -> list[re.Match[str]]:
    found = [match for line in adr_text().splitlines() if (match := pattern.match(line))]
    assert found, f"ADR 0017 must contain the table matching {pattern.pattern}"
    return found


# ----------------------------------------------------------------------------------------
# §4 — the hard filters
# ----------------------------------------------------------------------------------------


def test_the_filter_table_names_every_refusal_exactly_once() -> None:
    documented = [match.group(4) for match in rows(FILTER_ROW)]
    assert documented == [refusal.value for refusal in Refusal]


def test_the_filters_are_numbered_from_one() -> None:
    """A gap in the numbering would mean a filter was removed from the table but not the code."""
    assert [match.group(1) for match in rows(FILTER_ROW)] == [
        str(index) for index, _ in enumerate(Refusal, start=1)
    ]


def test_the_risk_threshold_of_the_document_is_the_one_in_the_code() -> None:
    text = adr_text()
    assert f"`UNGUARDED_RISK` (`{UNGUARDED_RISK.value}`)" in text


def test_the_privacy_filter_is_documented_with_the_order_it_uses() -> None:
    ordered = sorted(PRIVACY_ORDER, key=lambda level: PRIVACY_ORDER[level])
    assert " < ".join(f"`{level.value}`" for level in ordered) in adr_text()
    assert list(ordered) == [
        PrivacyLevel.LOCAL_ONLY,
        PrivacyLevel.TRUSTED,
        PrivacyLevel.CLOUD_ALLOWED,
    ]


# ----------------------------------------------------------------------------------------
# §5 — the weights
# ----------------------------------------------------------------------------------------


def documented_weights() -> dict[str, str]:
    return {match.group(1): match.group(3) for match in rows(WEIGHT_ROW)}


def test_the_weight_table_has_one_row_per_component() -> None:
    assert set(documented_weights()) == {
        "traits",
        "network",
        "performance",
        "power",
        "workload",
        "status",
    }


@pytest.mark.parametrize(
    ("component", "table"),
    [
        ("network", NETWORK_POINTS),
        ("performance", PERFORMANCE_POINTS),
        ("power", POWER_POINTS),
        ("status", STATUS_POINTS),
    ],
)
def test_a_table_driven_component_matches_the_document(
    component: str,
    table: dict[NetworkKind | PerformanceClass | PowerSource | DeviceStatus, int],
) -> None:
    cell = documented_weights()[component]
    documented = {name: int(value) for name, value in POINTS.findall(cell)}
    assert documented == {member.name: points for member, points in table.items()}


def test_the_trait_and_workload_weights_match_the_document() -> None:
    weights = documented_weights()
    assert f"{TRAIT_POINTS} ×" in weights["traits"]
    assert f"{WORKLOAD_POINTS} ×" in weights["workload"]


def test_the_document_states_the_ceiling_the_weights_produce() -> None:
    """``40 su 105 possibili``: the sentence that makes the traits "the heaviest component" true."""
    ceiling = (
        TRAIT_POINTS
        + max(NETWORK_POINTS.values())
        + max(PERFORMANCE_POINTS.values())
        + max(POWER_POINTS.values())
        + WORKLOAD_POINTS
        + max(STATUS_POINTS.values())
    )
    assert f"{TRAIT_POINTS} su {ceiling} possibili" in adr_text()
    others = [
        max(NETWORK_POINTS.values()),
        max(PERFORMANCE_POINTS.values()),
        max(POWER_POINTS.values()),
        WORKLOAD_POINTS,
        max(STATUS_POINTS.values()),
    ]
    assert max(others) < TRAIT_POINTS, "the traits must outweigh any single other criterion"


# ----------------------------------------------------------------------------------------
# §5-bis — what the domain does not carry
# ----------------------------------------------------------------------------------------


def test_the_criteria_the_domain_does_not_carry_are_declared_not_invented() -> None:
    documented = [match.group(1).strip() for match in rows(MISSING_ROW)]
    assert documented == ["presenza dell'utente", "costo", "affidabilità"]


def test_every_criterion_of_the_spec_is_either_scored_filtered_or_declared_missing() -> None:
    """§17 lists twelve criteria; none of them may be silently ignored."""
    criteria = {
        "capacità richiesta",
        "CPU",
        "GPU",
        "RAM",
        "disponibilità",
        "latenza",
        "consumo energetico",
        "privacy",
        "presenza dell'utente",
        "software installato",
        "costo",
        "affidabilità",
    }
    text = adr_text()
    filters = " ".join(match.group(0) for match in rows(FILTER_ROW))
    weights = " ".join(match.group(0) for match in rows(WEIGHT_ROW))
    missing = " ".join(match.group(0) for match in rows(MISSING_ROW))
    for criterion in criteria:
        assert criterion in filters + weights + missing, criterion
    assert "§17" in text


# ----------------------------------------------------------------------------------------
# §7 — the audit events
# ----------------------------------------------------------------------------------------


def test_the_event_table_names_the_two_new_types() -> None:
    documented = [match.group(1) for match in rows(EVENT_ROW)]
    assert documented == [
        AuditEventType.DEVICE_SELECTED.value,
        AuditEventType.DEVICE_UNAVAILABLE.value,
    ]


def test_the_two_types_are_the_only_device_events_in_the_domain() -> None:
    assert {t.value for t in AuditEventType if t.name.startswith("DEVICE_")} == {
        AuditEventType.DEVICE_SELECTED.value,
        AuditEventType.DEVICE_UNAVAILABLE.value,
    }


# ----------------------------------------------------------------------------------------
# §9 — the architecture rules
# ----------------------------------------------------------------------------------------


def test_the_rule_table_names_rules_that_exist() -> None:
    documented = {match.group(2): match.group(1) for match in rows(RULE_ROW)}
    assert documented == {
        "device-availability-readers": "20",
        "device-port-readers": "21",
        "devices-isolation": "22",
    }
    for name in documented:
        assert name in RULES, name


def test_the_documented_exemptions_of_rule_21_are_the_ones_the_rule_has() -> None:
    """Review of M6.2: three exemptions, one per module that names the port today.

    The composition root of M8.1 will probably need a fourth. It is not here in advance, and this
    test is what makes adding it a deliberate act — the ADR row has to change with the code.
    """
    (row,) = [match for match in rows(RULE_ROW) if match.group(1) == "21"]
    documented = row.group(4)
    assert len(DEVICE_PORT_ALLOWED) == 3
    assert "`ela.ports`" in documented
    assert "`ela.devices`" in documented
    assert "ela.api" not in documented


def test_the_weights_are_declared_provisional() -> None:
    """§5: the weights are a stated policy, not a measurement, and say when they get one."""
    text = adr_text()
    assert "da ritarare in Fase 12" in text
    assert "non a occhio" in text


def test_the_waiting_contract_for_the_next_milestone_is_written_down() -> None:
    """§6 is the constraint M6.3 must not reinvent: QUEUED, no failure, no second audit event."""
    text = adr_text()
    assert "Vincolo per M6.3" in text
    assert "il task resta `QUEUED`" in text
    assert "il task non fallisce e lo step non fallisce" in text
