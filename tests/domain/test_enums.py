"""The enums say exactly what the spec says, no more (§14, §27, §29, §30, §63)."""

from __future__ import annotations

from enum import StrEnum

import pytest

from ela import domain
from ela.domain import (
    ApprovalStatus,
    ExecutionStatus,
    OperatingSystem,
    PermissionOutcome,
    PrivacyLevel,
    TaskState,
)


def test_task_state_matches_section_14() -> None:
    assert [state.value for state in TaskState] == [
        "CREATED",
        "PLANNING",
        "WAITING_APPROVAL",
        "QUEUED",
        "EXECUTING",
        "COMPLETED",
        "FAILED",
        "CANCELLED",
        "DENIED",
        "EXPIRED",
    ]


def test_permission_outcome_covers_the_three_answers() -> None:
    assert [outcome.value for outcome in PermissionOutcome] == [
        "ALLOWED",
        "DENIED",
        "REQUIRES_APPROVAL",
    ]


def test_approval_status_covers_the_life_of_a_request() -> None:
    assert set(ApprovalStatus) == {
        ApprovalStatus.PENDING,
        ApprovalStatus.GRANTED,
        ApprovalStatus.REJECTED,
        ApprovalStatus.EXPIRED,
    }


def test_execution_status_distinguishes_ending_from_succeeding() -> None:
    assert ExecutionStatus.SUCCEEDED != ExecutionStatus.FAILED
    assert len(set(ExecutionStatus)) == 5


def _enums() -> list[type[StrEnum]]:
    return [
        value
        for name, value in vars(domain).items()
        if isinstance(value, type)
        and issubclass(value, StrEnum)
        and value.__module__ == domain.__name__
    ]


def test_the_domain_declares_exactly_these_enums() -> None:
    assert sorted(enum.__name__ for enum in _enums()) == [
        "ActorKind",
        "ApprovalStatus",
        "AuditEventType",
        "DeviceAvailability",
        "DeviceStatus",
        "ExecutionStatus",
        "IntentChannel",
        "NetworkKind",
        "OperatingSystem",
        "PerformanceClass",
        "PermissionOutcome",
        "PowerSource",
        "PrivacyLevel",
        "ProviderStatus",
        "RiskLevel",
        "StepState",
        "TaskEventType",
        "TaskState",
    ]


@pytest.mark.parametrize("enum", _enums(), ids=lambda enum: enum.__name__)
def test_member_name_equals_its_value(enum: type[StrEnum]) -> None:
    """Serialisation is the member name: a rename is visible in the JSON, never silent."""
    for member in enum:
        assert member.name == member.value


DEVICE_STATE_ENUMS = frozenset(
    {"DeviceAvailability", "DeviceStatus", "PerformanceClass", "NetworkKind", "PowerSource"}
)


def test_device_state_enums_have_an_unknown_value() -> None:
    for enum in _enums():
        if enum.__name__ in DEVICE_STATE_ENUMS:
            assert "UNKNOWN" in enum.__members__, enum.__name__


def test_privacy_and_os_have_no_unknown_value() -> None:
    """§33: unknown privacy must never read as permission; an OS-less node is not a node."""
    assert "UNKNOWN" not in PrivacyLevel.__members__
    assert "UNKNOWN" not in OperatingSystem.__members__
