"""Every model builds from valid data, and rejects what the spec says is not valid."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from ela.domain import (
    NAME_MAX_LENGTH,
    Actor,
    ActorKind,
    Approval,
    ApprovalStatus,
    AuditEvent,
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
from tests.domain.examples import (
    CAPABILITY_SPEC,
    EXAMPLES,
    NOW,
    POLICY_AUTHORIZATION,
    TASK_ID,
)

MODELS = sorted(EXAMPLES, key=lambda model: model.__name__)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_example_is_valid(model: type[BaseModel]) -> None:
    example = EXAMPLES[model]
    assert isinstance(example, model)
    assert example == model.model_validate(example.model_dump())


NOTHING_REQUIRED = frozenset(
    {"RawObservation", "RawCapture", "RawRecognition", "RawSpeech", "RawTranscript"}
)
"""The two models that are legally empty, and why (M10.1, ADR 0028 §1; M10.2, ADR 0029 §11).

``RawObservation()`` — every field ``None`` — is not a partial entity, it is *the* value for "the
operating system was not asked, or could not answer". It is what a timeout returns, what a dead
helper returns, and what ELA reads on Linux. Requiring a field would mean inventing a reading in
order to say that there was none.

``RawSpeech()`` says the same about a sentence nobody spoke: the helper never ran.

``RawCapture()`` is the same shape on the acting side: no exit code and not timed out is "nothing
ran", which is what an operating system with no capture helper answers. Both are the fail-safe
value of a port that promises never to raise, and in both cases requiring a field would force an
adapter to invent one in order to report that there was none.

The list is short on purpose: a third model that needs nothing has to argue here.
"""


def test_the_only_model_with_nothing_required_is_the_declared_one() -> None:
    """The list above is not a habit: no other model may quietly become fully optional."""
    empty = sorted(
        model.__name__
        for model in MODELS
        if not any(field.is_required() for field in model.model_fields.values())
    )
    assert empty == sorted(NOTHING_REQUIRED)


@pytest.mark.parametrize("model", MODELS, ids=lambda model: model.__name__)
def test_required_fields_are_enforced(model: type[BaseModel]) -> None:
    """Dropping any required field makes construction fail: no silent partial entity."""
    example = EXAMPLES[model]
    required = [name for name, field in model.model_fields.items() if field.is_required()]
    assert required or model.__name__ in NOTHING_REQUIRED, f"{model.__name__} has no required field"
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


def test_capability_spec_scoped_arguments_default_to_none_and_freeze() -> None:
    """M4.1: which arguments the scope constrains; data only, a tuple like ``scope``."""
    bare = CapabilitySpec(**{**CAPABILITY_SPEC.model_dump(), "scoped_arguments": []})
    assert bare.scoped_arguments == ()
    assert CAPABILITY_SPEC.scoped_arguments == ("path",)
    assert isinstance(CAPABILITY_SPEC.scoped_arguments, tuple)
    with pytest.raises(ValidationError):
        CapabilitySpec(**{**CAPABILITY_SPEC.model_dump(), "scoped_arguments": [1]})


def test_capability_id_is_bounded() -> None:
    """The bound lives in the domain (review M2.1): 255 fits, 256 does not."""
    longest = "a." + "b" * (NAME_MAX_LENGTH - 2)
    assert len(longest) == NAME_MAX_LENGTH
    CapabilitySpec(**{**CAPABILITY_SPEC.model_dump(), "id": longest})
    with pytest.raises(ValidationError):
        CapabilitySpec(**{**CAPABILITY_SPEC.model_dump(), "id": longest + "b"})


@pytest.mark.parametrize("value", ["", "x" * (NAME_MAX_LENGTH + 1)])
def test_granted_by_is_bounded_and_not_empty(value: str) -> None:
    with pytest.raises(ValidationError):
        Authorization.model_validate({**POLICY_AUTHORIZATION.model_dump(), "granted_by": value})


def test_granted_by_accepts_the_longest_name() -> None:
    name = "x" * NAME_MAX_LENGTH
    grant = Authorization.model_validate({**POLICY_AUTHORIZATION.model_dump(), "granted_by": name})
    assert grant.granted_by == name


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


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"max_uses": None}, "single use"),
        ({"max_uses": 2}, "single use"),
        ({"task_id": None}, "task_id"),
        ({"step_id": None}, "step_id"),
        ({"task_id": None, "step_id": None}, "task_id"),
    ],
    ids=["reusable", "two-uses", "no-task", "no-step", "unbound"],
)
def test_an_approval_born_authorization_is_single_use_and_bound(
    overrides: dict[str, object], message: str
) -> None:
    """ADR 0012 §1: a grant that claims an approval cannot be reusable or unbound (§30)."""
    fields = {
        "approval_id": EXAMPLES[Approval].id,
        "task_id": TASK_ID,
        "step_id": EXAMPLES[Approval].step_id,
        "max_uses": 1,
    }
    with pytest.raises(ValidationError, match=message):
        _authorization(**(fields | overrides))


def test_a_policy_authorization_is_not_bound_by_the_invariant() -> None:
    assert _authorization(max_uses=None).approval_id is None
    assert _authorization(max_uses=3, task_id=TASK_ID).step_id is None


def test_the_invariant_survives_a_round_trip() -> None:
    """``model_copy`` does not validate; ``model_validate`` of the dump does (ADR 0003 §3)."""
    tampered = EXAMPLES[Authorization].model_copy(update={"max_uses": None})
    with pytest.raises(ValidationError, match="single use"):
        Authorization.model_validate(tampered.model_dump())


def test_approval_is_bound_to_task_step_and_capability() -> None:
    """§30: an out-of-context yes must not authorise something else."""
    for name in ("task_id", "step_id", "capability_id"):
        assert Approval.model_fields[name].is_required()
    assert EXAMPLES[Approval].status is ApprovalStatus.GRANTED


def test_approval_targets_default_to_empty_and_freeze() -> None:
    """ADR 0012: ``targets`` is additive — an approval without targets is still valid."""
    payload = {k: v for k, v in EXAMPLES[Approval].model_dump().items() if k != "targets"}
    assert Approval.model_validate(payload).targets == ()
    assert isinstance(EXAMPLES[Approval].targets, tuple)
    assert EXAMPLES[Approval].targets == ("workspace/notes/briefing.md",)


def test_audit_actor_says_what_kind_of_actor_it_is() -> None:
    """§32: knowing that "ela" acted is useless if it could also be a user called ela."""
    assert AuditEvent.model_fields["actor"].annotation is Actor
    for kind in ActorKind:
        assert Actor(kind=kind, id="x").kind is kind


def test_audit_actor_cannot_be_anonymous() -> None:
    with pytest.raises(ValidationError):
        Actor(kind=ActorKind.USER, id="")


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
