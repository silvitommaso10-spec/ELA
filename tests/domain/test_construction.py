"""Every model builds from valid data, and rejects what the spec says is not valid."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ela.domain import (
    Approval,
    ApprovalStatus,
    Authorization,
    CapabilityId,
    CapabilitySpec,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceStatus,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
    ProviderUsage,
    RiskLevel,
    Task,
    TaskState,
)
from tests.domain.examples import EXAMPLES, NOW, TASK_ID

MODELS = sorted(EXAMPLES, key=lambda model: model.__name__)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_example_is_valid(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    assert isinstance(example, model)
    assert example == model.model_validate(example.model_dump())


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_required_fields_are_enforced(model: type[BaseModel]) -> None:
    """Dropping any required field makes construction fail: no silent partial entity."""
    example = EXAMPLES[model]
    required = [name for name, field in model.model_fields.items() if field.is_required()]
    assert required, f"{model.__name__} has no required field"
    for name in required:
        payload = {key: value for key, value in example.model_dump().items() if key != name}
        with pytest.raises(ValidationError, match=name):
            model.model_validate(payload)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_extra_field_is_rejected(model: type[BaseModel]) -> None:
    payload = EXAMPLES[model].model_dump() | {"surprise": "no"}
    with pytest.raises(ValidationError, match="surprise"):
        model.model_validate(payload)


def test_task_state_is_data_not_behaviour() -> None:
    """Any state can be built: legal transitions belong to the Task Engine (M1.2)."""
    for state in TaskState:
        task = Task(id=TASK_ID, created_at=NOW, goal="g", state=state)
        assert task.state is state


@pytest.mark.parametrize(
    "value",
    ["core.echo", "workspace.write_note", "model.complete", "a.b.c", "core.echo_2"],
)
def test_capability_id_accepts_dotted_names(value: str) -> None:
    spec = CapabilitySpec(
        id=CapabilityId(value),
        created_at=NOW,
        description="d",
        risk=RiskLevel.SAFE,
        requires_authorization=False,
    )
    assert spec.id == value


@pytest.mark.parametrize(
    "value",
    ["core", "Core.Echo", "core.", ".echo", "core..echo", " core.echo", "core.echo ", "1core.echo"],
)
def test_capability_id_rejects_everything_else(value: str) -> None:
    with pytest.raises(ValidationError):
        CapabilitySpec(
            id=CapabilityId(value),
            created_at=NOW,
            description="d",
            risk=RiskLevel.SAFE,
            requires_authorization=False,
        )


@pytest.mark.parametrize("value", ["camera", "gpu.cuda", "audio.input_device"])
def test_device_capability_name_accepts_one_or_more_segments(value: str) -> None:
    assert DeviceCapability(name=DeviceCapabilityName(value), available=True).name == value


@pytest.mark.parametrize("value", ["GPU", "gpu.", "gpu..cuda", ""])
def test_device_capability_name_rejects_everything_else(value: str) -> None:
    with pytest.raises(ValidationError):
        DeviceCapability(name=DeviceCapabilityName(value), available=True)


def _device(**overrides: object) -> Device:
    fields: dict[str, object] = {
        "id": EXAMPLES[Device].id,
        "created_at": NOW,
        "name": "MacBook",
        "os": OperatingSystem.MACOS,
        "availability": DeviceAvailability.ONLINE,
        "status": DeviceStatus.IDLE,
        "privacy": PrivacyLevel.TRUSTED,
    }
    return Device.model_validate(fields | overrides)


@pytest.mark.parametrize("value", [0.0, 0.5, 1.0, None])
def test_device_workload_accepts_the_zero_to_one_range(value: float | None) -> None:
    assert _device(current_workload=value).current_workload == value


@pytest.mark.parametrize("value", [-0.1, 1.1])
def test_device_workload_rejects_values_outside_the_range(value: float) -> None:
    with pytest.raises(ValidationError):
        _device(current_workload=value)


def test_device_state_enums_default_to_unknown() -> None:
    """What is not known about a node is UNKNOWN, never a flattering guess (§16)."""
    device = _device()
    assert device.performance is PerformanceClass.UNKNOWN
    assert device.network is NetworkKind.UNKNOWN
    assert device.power_source is PowerSource.UNKNOWN


def test_device_privacy_has_no_default() -> None:
    """§33: an undeclared privacy level must never be mistaken for permission."""
    assert Device.model_fields["privacy"].is_required()


def _authorization(**overrides: object) -> Authorization:
    fields: dict[str, object] = {
        "id": EXAMPLES[Authorization].id,
        "created_at": NOW,
        "capability_id": CapabilityId("workspace.write_note"),
        "granted_by": "tommaso",
    }
    return Authorization.model_validate(fields | overrides)


def test_single_use_authorization_carries_its_approval() -> None:
    authorization = _authorization(
        approval_id=EXAMPLES[Approval].id,
        task_id=TASK_ID,
        step_id=EXAMPLES[Approval].step_id,
        max_uses=1,
    )
    assert authorization.approval_id is not None
    assert authorization.max_uses == 1


def test_policy_authorization_has_no_approval() -> None:
    authorization = _authorization(scope=("workspace/notes",))
    assert authorization.approval_id is None
    assert authorization.max_uses is None


@pytest.mark.parametrize("value", [0, -1])
def test_max_uses_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        _authorization(max_uses=value)


def test_approval_is_bound_to_task_step_and_capability() -> None:
    """§30: an out-of-context yes must not authorise something else."""
    for name in ("task_id", "step_id", "capability_id"):
        assert Approval.model_fields[name].is_required()
    assert EXAMPLES[Approval].status is ApprovalStatus.GRANTED


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
def test_token_counts_must_be_non_negative(field: str) -> None:
    with pytest.raises(ValidationError):
        ProviderUsage.model_validate({"input_tokens": 1, "output_tokens": 1, field: -1})


def test_negative_cost_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderUsage(input_tokens=1, output_tokens=1, cost=Decimal("-0.01"))


def test_negative_latency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderUsage(input_tokens=0, output_tokens=0, latency_ms=-1)


def test_ids_are_not_interchangeable_at_runtime() -> None:
    """NewType is a type-checker guarantee, not a runtime one: mypy is what enforces it."""
    task = Task(id=uuid4(), created_at=datetime.now(UTC), goal="g", state=TaskState.CREATED)  # type: ignore[arg-type]
    assert task.id is not None
