"""The domain models obey the rules of M1.1, and the rules fail when a model breaks them.

A rule that only ever passes proves nothing (CLAUDE.md, "Qualità"), so every rule is also run
against a model written on purpose to violate it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ela import domain
from ela.domain import (
    Device,
    DeviceAvailability,
    DeviceId,
    DeviceStatus,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    TaskPlan,
    TaskStep,
    UtcDatetime,
)
from tests.architecture.model_rules import (
    clock_default_violations,
    device_reference_violations,
    frozen_violations,
    mutable_collection_violations,
)

#: Everything that would tie a plan to a physical node (§13: the plan is device-independent).
DEVICE_TYPES = frozenset(
    {
        DeviceId,
        Device,
        OperatingSystem,
        DeviceAvailability,
        DeviceStatus,
        PerformanceClass,
        NetworkKind,
        PowerSource,
    }
)

PLAN_MODELS = (TaskPlan, TaskStep)


def domain_models() -> tuple[type[BaseModel], ...]:
    """Every pydantic model defined in :mod:`ela.domain`, private base included."""
    return tuple(
        value
        for value in vars(domain).values()
        if isinstance(value, type)
        and issubclass(value, BaseModel)
        and value.__module__ == domain.__name__
    )


def test_the_domain_actually_has_models() -> None:
    """A rule applied to an empty list would hold vacuously."""
    assert len(domain_models()) == 45  # 44 entities and value objects, plus the private base


def test_plan_is_device_independent() -> None:
    violations = device_reference_violations(PLAN_MODELS, DEVICE_TYPES)
    assert violations == [], "\n".join(violations)


def test_plan_can_still_name_capabilities_and_traits() -> None:
    """The rule must not be vacuous the other way: the allowed references are really there."""
    assert TaskStep.model_fields["required_capabilities"] is not None
    assert TaskStep.model_fields["preferred_device_traits"] is not None


def test_all_models_are_frozen() -> None:
    violations = frozen_violations(domain_models())
    assert violations == [], "\n".join(violations)


def test_no_model_reads_the_clock() -> None:
    violations = clock_default_violations(domain_models())
    assert violations == [], "\n".join(violations)


def test_no_model_uses_a_mutable_collection() -> None:
    violations = mutable_collection_violations(domain_models())
    assert violations == [], "\n".join(violations)


# ----------------------------------------------------------------------------------------
# The same rules, applied to models written to break them.
# ----------------------------------------------------------------------------------------


class _StepOnADevice(BaseModel):
    """A step that names a node: exactly what §13 forbids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    device_id: DeviceId | None = None


class _PlanWithADeviceStep(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    steps: tuple[_StepOnADevice, ...] = ()


class _PlanOnAnOperatingSystem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    os: OperatingSystem = OperatingSystem.MACOS


class _MutableModel(BaseModel):
    value: str = ""


class _OpenModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str = ""


def _now() -> datetime:
    return datetime.now(UTC)


class _ModelWithAClock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    created_at: UtcDatetime = Field(default_factory=_now)


class _ModelWithAFixedDate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    created_at: UtcDatetime = datetime(2026, 1, 1, tzinfo=UTC)


class _ModelWithAList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[str] = []


class _ModelWithADict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: dict[str, JsonValue] = {}


class _ModelWithAMapping(BaseModel):
    """The allowed shape: a mapping annotation, not a dict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    payload: Mapping[str, JsonValue] = {}


@pytest.mark.parametrize(
    "model",
    [_PlanWithADeviceStep, _PlanOnAnOperatingSystem],
    ids=["device_id_in_a_nested_step", "operating_system_in_the_plan"],
)
def test_device_rule_reports_a_plan_that_names_a_node(model: type[BaseModel]) -> None:
    assert device_reference_violations((model,), DEVICE_TYPES) != []


@pytest.mark.parametrize("model", [_MutableModel, _OpenModel], ids=["not_frozen", "extra_allowed"])
def test_frozen_rule_reports_a_mutable_or_open_model(model: type[BaseModel]) -> None:
    assert frozen_violations((model,)) != []


@pytest.mark.parametrize(
    "model", [_ModelWithAClock, _ModelWithAFixedDate], ids=["default_factory", "fixed_default"]
)
def test_clock_rule_reports_an_invented_timestamp(model: type[BaseModel]) -> None:
    assert clock_default_violations((model,)) != []


@pytest.mark.parametrize("model", [_ModelWithAList, _ModelWithADict], ids=["list", "dict"])
def test_mutable_rule_reports_a_mutable_collection(model: type[BaseModel]) -> None:
    assert mutable_collection_violations((model,)) != []


def test_mutable_rule_accepts_a_mapping_annotation() -> None:
    """No false positive on the shape the domain actually uses."""
    assert mutable_collection_violations((_ModelWithAMapping,)) == []


def test_device_rule_accepts_the_device_model_itself() -> None:
    """The rule is about plans, not about the registry: ``Device`` may name device types."""
    assert device_reference_violations(PLAN_MODELS, DEVICE_TYPES) == []
    assert device_reference_violations((Device,), DEVICE_TYPES) != []


def test_annotation_walk_reaches_nested_arguments() -> None:
    from tests.architecture.model_rules import annotation_parts

    parts: list[Any] = list(annotation_parts(tuple[DeviceId | None, ...]))
    assert DeviceId in parts
