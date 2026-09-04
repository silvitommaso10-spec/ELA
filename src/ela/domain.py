"""Domain model of ELA: pure entities, no I/O, no infrastructure imports (spec §49).

Every entity is an immutable pydantic model (``frozen=True``, ``extra="forbid"``) with a typed
id and an explicit UTC ``created_at``: the domain never reads the clock, so the caller decides
what "now" means (spec §51; the ``Clock`` port arrives with M1.3). Immutability is deep, not
only at field level: sequences are tuples and free-form JSON payloads are frozen mappings.

The module holds data and nothing else. Task transitions (§14) belong to the Task Engine and
permission outcomes (§27, §33) to the Guardian: a model here never decides anything.

Two shapes live side by side:

* **Entities** have identity and a life cycle, hence an id and a ``created_at``.
* **Value objects** (:class:`DeviceCapability`, :class:`ProviderUsage`, :class:`ErrorMetadata`)
  are defined entirely by their values and live inside the entity that holds them: no id.

See ``docs/adr/0003-domain-model.md`` for the decisions behind these rules.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Any, Final, NewType, cast
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    PlainSerializer,
)

__all__ = [
    "Approval",
    "ApprovalId",
    "ApprovalStatus",
    "AuditEvent",
    "AuditEventId",
    "AuditEventType",
    "Authorization",
    "AuthorizationId",
    "CAPABILITY_ID_PATTERN",
    "CapabilityId",
    "CapabilitySpec",
    "DEVICE_CAPABILITY_NAME_PATTERN",
    "DecisionId",
    "Device",
    "DeviceAvailability",
    "DeviceCapability",
    "DeviceCapabilityName",
    "DeviceId",
    "DeviceStatus",
    "ELAIdentity",
    "ErrorMetadata",
    "ExecutionId",
    "ExecutionResult",
    "ExecutionStatus",
    "IdentityId",
    "IntentChannel",
    "IntentId",
    "JsonMapping",
    "NetworkKind",
    "OperatingSystem",
    "PerformanceClass",
    "PermissionDecision",
    "PermissionOutcome",
    "PlanId",
    "PowerSource",
    "PrivacyLevel",
    "ProviderRequest",
    "ProviderRequestId",
    "ProviderResult",
    "ProviderResultId",
    "ProviderUsage",
    "RiskLevel",
    "StepId",
    "Task",
    "TaskEvent",
    "TaskEventId",
    "TaskEventType",
    "TaskId",
    "TaskPlan",
    "TaskState",
    "TaskStep",
    "UserIntent",
    "UtcDatetime",
]


# --------------------------------------------------------------------------------------
# Typed ids (§49)
# --------------------------------------------------------------------------------------

IdentityId = NewType("IdentityId", UUID)
IntentId = NewType("IntentId", UUID)
TaskId = NewType("TaskId", UUID)
StepId = NewType("StepId", UUID)
PlanId = NewType("PlanId", UUID)
TaskEventId = NewType("TaskEventId", UUID)
DeviceId = NewType("DeviceId", UUID)
DecisionId = NewType("DecisionId", UUID)
AuthorizationId = NewType("AuthorizationId", UUID)
ApprovalId = NewType("ApprovalId", UUID)
AuditEventId = NewType("AuditEventId", UUID)
ProviderRequestId = NewType("ProviderRequestId", UUID)
ProviderResultId = NewType("ProviderResultId", UUID)
ExecutionId = NewType("ExecutionId", UUID)

CAPABILITY_ID_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"
"""Dotted capability name, at least two segments: ``core.echo``, ``workspace.write_note`` (§29)."""

DEVICE_CAPABILITY_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
"""Device trait name, one segment or more: ``camera``, ``gpu.cuda`` (§16)."""

CapabilityId = NewType("CapabilityId", str)
"""Id of a :class:`CapabilitySpec`.

The only id that is not a UUID: §29 fixes stable dotted names (``core.echo``), which *are* the
identity of a capability. See ADR 0003.
"""

DeviceCapabilityName = NewType("DeviceCapabilityName", str)
"""Name of a :class:`DeviceCapability`, the hardware/software trait of a node (§16)."""

_CapabilityIdField = Annotated[CapabilityId, Field(pattern=CAPABILITY_ID_PATTERN)]
_DeviceCapabilityNameField = Annotated[
    DeviceCapabilityName, Field(pattern=DEVICE_CAPABILITY_NAME_PATTERN)
]


# --------------------------------------------------------------------------------------
# Field types: UTC time and frozen JSON payloads
# --------------------------------------------------------------------------------------


def _to_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalise aware ones to UTC (§49)."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware; the domain stores instants in UTC")
    return value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_to_utc)]
"""An instant, always timezone-aware and stored in UTC."""


def _freeze(value: Any) -> Any:
    """Recursively turn JSON data into immutable data: mappings freeze, sequences become tuples."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    """Inverse of :func:`_freeze`, used to serialise back to plain JSON containers."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _freeze_mapping(value: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    return cast(Mapping[str, JsonValue], _freeze(dict(value)))


def _thaw_mapping(value: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], _thaw(dict(value)))


JsonMapping = Annotated[
    Mapping[str, JsonValue],
    AfterValidator(_freeze_mapping),
    PlainSerializer(_thaw_mapping, return_type=dict[str, JsonValue]),
]
"""Free-form JSON payload, deeply immutable.

``frozen=True`` protects the field, not what the field points at: a plain ``dict`` would still
be mutable. Values validate as JSON, are stored frozen (mappings become ``MappingProxyType``,
arrays become tuples) and serialise back to plain JSON containers.
"""

_METADATA_DESCRIPTION: Final = (
    "Free-form context; never a place for something the domain should name explicitly."
)


def _json_payload(description: str) -> Any:
    """A :data:`JsonMapping` field: empty by default, and frozen like any other value."""
    return Field(default={}, validate_default=True, description=description)


# --------------------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------------------


class TaskState(StrEnum):
    """Life cycle of a :class:`Task` (§14, verbatim).

    The legal transitions between these states are the Task Engine's business (M1.2), not the
    model's.
    """

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    QUEUED = "QUEUED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


class RiskLevel(StrEnum):
    """How dangerous an action is (§29, verbatim), ordered SAFE < LOW < MEDIUM < HIGH < CRITICAL.

    The order is part of the domain: "at most MEDIUM" is a statement about risk, not about
    strings. ``StrEnum`` would otherwise compare alphabetically — CRITICAL < HIGH < LOW —
    which is both wrong and dangerous, so the comparisons are defined explicitly and refuse
    anything that is not a :class:`RiskLevel`.
    """

    SAFE = "SAFE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    @property
    def severity(self) -> int:
        """Position in the SAFE → CRITICAL order."""
        return _RISK_ORDER.index(self)

    def _other_severity(self, other: object) -> int:
        if not isinstance(other, RiskLevel):
            raise TypeError(
                f"RiskLevel is ordered only against RiskLevel, not {type(other).__name__}"
            )
        return other.severity

    def __lt__(self, other: object) -> bool:
        return self.severity < self._other_severity(other)

    def __le__(self, other: object) -> bool:
        return self.severity <= self._other_severity(other)

    def __gt__(self, other: object) -> bool:
        return self.severity > self._other_severity(other)

    def __ge__(self, other: object) -> bool:
        return self.severity >= self._other_severity(other)


_RISK_ORDER: Final[tuple[RiskLevel, ...]] = (
    RiskLevel.SAFE,
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
)


class PermissionOutcome(StrEnum):
    """What the Guardian decided about one capability call (§27, §33)."""

    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


class ApprovalStatus(StrEnum):
    """Where a request for the user's consent stands (§14 WAITING_APPROVAL, §30)."""

    PENDING = "PENDING"
    GRANTED = "GRANTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ExecutionStatus(StrEnum):
    """How an execution ended (§63). Ending is not succeeding: the status says which."""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class TaskEventType(StrEnum):
    """What a :class:`TaskEvent` records (§14)."""

    STATE_CHANGED = "STATE_CHANGED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    PLAN_ATTACHED = "PLAN_ATTACHED"
    NOTE = "NOTE"


class AuditEventType(StrEnum):
    """What an :class:`AuditEvent` records (§32)."""

    TASK_CREATED = "TASK_CREATED"
    PLAN_CREATED = "PLAN_CREATED"
    PERMISSION_DECIDED = "PERMISSION_DECIDED"
    AUTHORIZATION_GRANTED = "AUTHORIZATION_GRANTED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    PROVIDER_CALLED = "PROVIDER_CALLED"
    ERROR_RECORDED = "ERROR_RECORDED"


class IntentChannel(StrEnum):
    """How a :class:`UserIntent` reached ELA (§7, §9, §34)."""

    TEXT = "TEXT"
    VOICE = "VOICE"
    PHONE = "PHONE"
    PROACTIVE = "PROACTIVE"
    API = "API"


class OperatingSystem(StrEnum):
    """Operating system of a node (§4–§6, §16).

    No ``UNKNOWN``: a node whose OS is unknown is not a node ELA can register.
    """

    MACOS = "MACOS"
    WINDOWS = "WINDOWS"
    IOS = "IOS"
    LINUX = "LINUX"


class DeviceAvailability(StrEnum):
    """Whether a node can be reached right now (§16, "disponibilità")."""

    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


class DeviceStatus(StrEnum):
    """What a node is doing (§16, "stato"). A node can be reachable and still busy."""

    IDLE = "IDLE"
    BUSY = "BUSY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class PerformanceClass(StrEnum):
    """Rough compute power of a node (§16, "potenza")."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class NetworkKind(StrEnum):
    """How a node is connected (§16, "rete")."""

    LOCAL = "LOCAL"
    REMOTE = "REMOTE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class PowerSource(StrEnum):
    """What a node runs on (§16, "alimentazione")."""

    AC = "AC"
    BATTERY = "BATTERY"
    UNKNOWN = "UNKNOWN"


class PrivacyLevel(StrEnum):
    """What data may leave a node (§16, §57).

    No ``UNKNOWN``: an unknown privacy level must never be mistaken for permission (§33), so
    the level is always declared.
    """

    LOCAL_ONLY = "LOCAL_ONLY"
    TRUSTED = "TRUSTED"
    CLOUD_ALLOWED = "CLOUD_ALLOWED"


# --------------------------------------------------------------------------------------
# Base model
# --------------------------------------------------------------------------------------


class _DomainModel(BaseModel):
    """Immutable, closed model: no mutation after construction, no unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------------------
# Value objects
# --------------------------------------------------------------------------------------


class DeviceCapability(_DomainModel):
    """A hardware/software trait a node offers: ``camera``, ``gpu.cuda`` (§16, "capacità").

    Not to be confused with :class:`CapabilitySpec`, which describes an *action* the Guardian
    can authorise. A trait is a property of a node; a capability spec is a thing ELA may do.
    """

    name: _DeviceCapabilityNameField
    available: bool
    attributes: JsonMapping = _json_payload(
        "Extra facts about the trait, for instance how much memory a GPU has."
    )


class ProviderUsage(_DomainModel):
    """What one provider call consumed (§32, "provider usage metadata")."""

    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    cached_input_tokens: Annotated[int, Field(ge=0)] | None = None
    cost: Annotated[Decimal, Field(ge=0)] | None = None
    currency: str | None = None
    latency_ms: Annotated[int, Field(ge=0)] | None = None


class ErrorMetadata(_DomainModel):
    """A failure turned into information (§64).

    Records what happened, why, which tool, model and device were involved, what was tried and
    what worked — so that a failure can feed future decisions instead of just reading FAILED.
    """

    code: str
    message: str
    cause: str | None = None
    tool_name: str | None = None
    model: str | None = None
    device_id: DeviceId | None = None
    attempted_fix: str | None = None
    successful_fix: str | None = None
    retryable: bool = False
    details: JsonMapping = _json_payload("Everything else worth keeping about the failure (§64).")


# --------------------------------------------------------------------------------------
# Entities
# --------------------------------------------------------------------------------------


class ELAIdentity(_DomainModel):
    """The single logical identity of ELA (§2.1).

    Windows, macOS and iPhone are nodes ELA operates through; the identity does not belong to
    any of them.
    """

    id: IdentityId
    created_at: UtcDatetime
    name: str = "ELA"
    version: str
    owner: str
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class UserIntent(_DomainModel):
    """What the user asked, as it arrived (§12, §60).

    ``text`` is raw: interpreting it into a goal is the Executive Core's job, not the model's.
    """

    id: IntentId
    created_at: UtcDatetime
    text: str
    channel: IntentChannel
    device_id: DeviceId | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class TaskStep(_DomainModel):
    """One step of a :class:`TaskPlan` (§13, field by field).

    Device independence is the point of §13: a step says which *capabilities* it needs and, at
    most, which device *traits* it would prefer. Which node runs it is the Device Orchestrator's
    decision (§17), so no ``DeviceId`` and no ``OperatingSystem`` appear here. See ADR 0003.
    """

    id: StepId
    created_at: UtcDatetime
    goal: str
    required_capabilities: tuple[_CapabilityIdField, ...] = ()
    preferred_device_traits: tuple[_DeviceCapabilityNameField, ...] = ()
    dependencies: tuple[StepId, ...] = ()
    risk: RiskLevel
    expected_result: str
    success_conditions: tuple[str, ...] = ()
    requires_authorization: bool


class TaskPlan(_DomainModel):
    """A goal turned into steps (§13). Independent of any device, like its steps."""

    id: PlanId
    created_at: UtcDatetime
    task_id: TaskId
    goal: str
    steps: tuple[TaskStep, ...] = ()
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class Task(_DomainModel):
    """A unit of work owned by ELA, not by a device (§14, §15).

    ``state`` is data here: which transitions are legal is the Task Engine's business (M1.2).
    """

    id: TaskId
    created_at: UtcDatetime
    goal: str
    state: TaskState
    intent_id: IntentId | None = None
    plan_id: PlanId | None = None
    parent_id: TaskId | None = None
    deadline: UtcDatetime | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class TaskEvent(_DomainModel):
    """Something that happened to a task (§14): what changed, when, and from which state."""

    id: TaskEventId
    created_at: UtcDatetime
    task_id: TaskId
    event_type: TaskEventType
    step_id: StepId | None = None
    previous_state: TaskState | None = None
    new_state: TaskState | None = None
    message: str = ""
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class Device(_DomainModel):
    """A node ELA can operate through (§16).

    ``availability`` and ``status`` are different questions — a node can be reachable and busy —
    and so are ``capabilities`` (hardware/software traits) and ``available_tools`` (what is
    installed on it).
    """

    id: DeviceId
    created_at: UtcDatetime
    name: str
    os: OperatingSystem
    availability: DeviceAvailability
    status: DeviceStatus
    capabilities: tuple[DeviceCapability, ...] = ()
    available_tools: tuple[str, ...] = ()
    performance: PerformanceClass = PerformanceClass.UNKNOWN
    network: NetworkKind = NetworkKind.UNKNOWN
    power_source: PowerSource = PowerSource.UNKNOWN
    privacy: PrivacyLevel
    current_workload: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    last_seen_at: UtcDatetime | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class CapabilitySpec(_DomainModel):
    """What an action can do, and under which conditions (§28).

    A capability is a specification the Guardian reasons about; the Tool is the implementation.
    Keeping them apart is what stops a tool from bypassing the permission system. Not to be
    confused with :class:`DeviceCapability`, which is a trait of a node.
    """

    id: _CapabilityIdField
    created_at: UtcDatetime
    description: str
    risk: RiskLevel
    input_schema: JsonMapping = _json_payload(
        "JSON Schema of the arguments the capability accepts (§28)."
    )
    scope: tuple[str, ...] = ()
    requires_authorization: bool
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class PermissionDecision(_DomainModel):
    """The Guardian's answer about one capability call (§27).

    ``outcome`` has no default on purpose: the fail-safe "when in doubt, DENIED" (§33) is the
    Guardian's responsibility (M1.3). A silent default here would hide a caller's bug.
    """

    id: DecisionId
    created_at: UtcDatetime
    capability_id: _CapabilityIdField
    outcome: PermissionOutcome
    risk: RiskLevel
    reason: str
    task_id: TaskId | None = None
    step_id: StepId | None = None
    authorization_id: AuthorizationId | None = None
    approval_id: ApprovalId | None = None
    expires_at: UtcDatetime | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class Approval(_DomainModel):
    """The user's consent for one specific action (§30).

    Bound to a task, a step and a capability: an out-of-context "yes" must never authorise
    something else.
    """

    id: ApprovalId
    created_at: UtcDatetime
    task_id: TaskId
    step_id: StepId
    capability_id: _CapabilityIdField
    prompt: str
    status: ApprovalStatus
    decision_id: DecisionId | None = None
    responded_at: UtcDatetime | None = None
    responded_by: str | None = None
    expires_at: UtcDatetime | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class Authorization(_DomainModel):
    """The grant the Guardian consumes. It is born in one of two ways (§30, §59).

    * From an :class:`Approval`: single use, ``max_uses=1``, ``approval_id`` set, bound to the
      ``task_id``/``step_id`` it was granted for.
    * From a standing policy (§59): reusable, ``approval_id`` is ``None``, and the scope says
      how far it reaches.
    """

    id: AuthorizationId
    created_at: UtcDatetime
    capability_id: _CapabilityIdField
    scope: tuple[str, ...] = ()
    granted_by: str
    approval_id: ApprovalId | None = None
    task_id: TaskId | None = None
    step_id: StepId | None = None
    expires_at: UtcDatetime | None = None
    max_uses: Annotated[int, Field(gt=0)] | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class AuditEvent(_DomainModel):
    """One significant event in the append-only audit trail (§32).

    Records what ELA did, why, under which authorization and with what result. This model is the
    shape of an entry; the append-only log itself is infrastructure.
    """

    id: AuditEventId
    created_at: UtcDatetime
    event_type: AuditEventType
    actor: str
    summary: str
    task_id: TaskId | None = None
    step_id: StepId | None = None
    capability_id: _CapabilityIdField | None = None
    decision_id: DecisionId | None = None
    authorization_id: AuthorizationId | None = None
    device_id: DeviceId | None = None
    tool_name: str | None = None
    usage: ProviderUsage | None = None
    error: ErrorMetadata | None = None
    payload: JsonMapping = _json_payload(
        "What the event carried, in the detail the audit trail needs (§32)."
    )


class ProviderRequest(_DomainModel):
    """A request to a model provider, in vendor-independent terms (§26, §50).

    Single text in, no provider-specific message format: the Core talks to an abstraction, and a
    multi-turn shape can be added later without changing what exists.
    """

    id: ProviderRequestId
    created_at: UtcDatetime
    purpose: str
    input: str
    instructions: str | None = None
    task_id: TaskId | None = None
    model_hint: str | None = None
    parameters: JsonMapping = _json_payload(
        "Provider-independent knobs, for instance the output budget (§50)."
    )
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class ProviderResult(_DomainModel):
    """What a model provider answered, plus what the call cost (§32, §50)."""

    id: ProviderResultId
    created_at: UtcDatetime
    request_id: ProviderRequestId
    provider: str
    model: str
    output: str
    usage: ProviderUsage
    finish_reason: str | None = None
    error: ErrorMetadata | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


class ExecutionResult(_DomainModel):
    """The outcome of running one capability through a tool on a device (§63).

    Execution is not proof of success: ``status`` says how it ended and ``error`` says why.
    """

    id: ExecutionId
    created_at: UtcDatetime
    capability_id: _CapabilityIdField
    status: ExecutionStatus
    task_id: TaskId | None = None
    step_id: StepId | None = None
    tool_name: str | None = None
    device_id: DeviceId | None = None
    output: JsonMapping = _json_payload("What the execution produced, if anything (§63).")
    error: ErrorMetadata | None = None
    duration_ms: Annotated[int, Field(ge=0)] | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)
