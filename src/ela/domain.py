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
    model_validator,
)

__all__ = [
    "Actor",
    "ActorKind",
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
    "FAMILY_FIELDS",
    "IdentityId",
    "IntentChannel",
    "IntentId",
    "JsonMapping",
    "JsonValue",
    "ModelRoute",
    "NAME_MAX_LENGTH",
    "NetworkKind",
    "Observation",
    "OperatingSystem",
    "PerceptionChange",
    "PerformanceClass",
    "PermissionDecision",
    "PermissionOutcome",
    "PermissionState",
    "PlanId",
    "PowerSource",
    "PrivacyLevel",
    "ProbeFamily",
    "ProviderRequest",
    "ProviderRequestId",
    "ProviderResult",
    "ProviderResultId",
    "ProviderStatus",
    "ProviderUsage",
    "RawObservation",
    "RiskLevel",
    "SensorCause",
    "SensorState",
    "SensorStatus",
    "StepId",
    "StepState",
    "SystemPermission",
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

NAME_MAX_LENGTH: Final = 255
"""Longest capability id or grantor name the domain accepts (review M2.1).

A bound lives in one place, the domain: the database columns that store these values are sized
from it, so persistence can never refuse what the domain accepted.
"""

DEVICE_CAPABILITY_NAME_PATTERN: Final = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"
"""Device trait name, one segment or more: ``camera``, ``gpu.cuda`` (§16)."""

CapabilityId = NewType("CapabilityId", str)
"""Id of a :class:`CapabilitySpec`.

The only id that is not a UUID: §29 fixes stable dotted names (``core.echo``), which *are* the
identity of a capability. See ADR 0003.
"""

DeviceCapabilityName = NewType("DeviceCapabilityName", str)
"""Name of a :class:`DeviceCapability`, the hardware/software trait of a node (§16)."""

_CapabilityIdField = Annotated[
    CapabilityId, Field(pattern=CAPABILITY_ID_PATTERN, max_length=NAME_MAX_LENGTH)
]
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


class StepState(StrEnum):
    """Where one :class:`TaskStep` of a plan stands (§13, §15; M3.2, ADR 0009).

    Data only, like :class:`TaskState`: which moves are legal is the Task Graph's business
    (``ela.tasks.graph``). The state is not stored: it is folded from the ``STEP_*`` events of
    the task's trail, which is what makes it independent of any device (§15).
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


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
    """How an execution ended (§63). Ending is not succeeding: the status says which.

    ``STARTED`` is the one value that says nothing about an ending: it records that a tool was
    *about* to act (M7.2, ADR 0021 §1). Only a tool that cannot be run twice writes one, and it
    exists so that a crash between the action and the insert of its outcome is a fact ELA can
    read — "this may have happened" — instead of an invitation to do it again (ADR 0015 §8).
    """

    STARTED = "STARTED"
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
    STEP_CANCELLED = "STEP_CANCELLED"
    """A step cancelled because a step it depends on failed (M3.2, ADR 0009)."""
    PLAN_ATTACHED = "PLAN_ATTACHED"
    HEARTBEAT = "HEARTBEAT"
    """A sign of life from whoever executes the task (M3.1): a trail entry, never an audit one."""
    NOTE = "NOTE"


class AuditEventType(StrEnum):
    """What an :class:`AuditEvent` records (§32).

    One type per operation of the Task Engine (M3.1, ADR 0008): a log queried by type — every
    denial, every approval — is worth more than one filtered on its payload.
    """

    TASK_CREATED = "TASK_CREATED"
    TASK_PLANNING_STARTED = "TASK_PLANNING_STARTED"
    PLAN_CREATED = "PLAN_CREATED"
    TASK_QUEUED = "TASK_QUEUED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_EXPIRED = "TASK_EXPIRED"
    TASK_DENIED = "TASK_DENIED"
    STEP_STARTED = "STEP_STARTED"
    STEP_COMPLETED = "STEP_COMPLETED"
    STEP_FAILED = "STEP_FAILED"
    STEP_CANCELLED = "STEP_CANCELLED"
    DEVICE_SELECTED = "DEVICE_SELECTED"
    """The Device Orchestrator chose the node a step runs on (§17; M6.2, ADR 0017)."""
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    """No node was eligible for a step, so the task waits (§17, §33; M6.2, ADR 0017 §6).

    A distinct type and not a payload of :attr:`DEVICE_SELECTED`: "every time ELA had nowhere to
    run something" is a question the log must answer by type, as ADR 0008 argues for the engine.
    """
    PERMISSION_DECIDED = "PERMISSION_DECIDED"
    AUTHORIZATION_GRANTED = "AUTHORIZATION_GRANTED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_RESOLVED = "APPROVAL_RESOLVED"
    TOOL_EXECUTED = "TOOL_EXECUTED"
    EXECUTION_VERIFIED = "EXECUTION_VERIFIED"
    """The verifier checked a SUCCEEDED result against the step's success conditions (§63,
    M5.2, ADR 0014): written whether it passed or failed."""
    PROVIDER_CALLED = "PROVIDER_CALLED"
    ERROR_RECORDED = "ERROR_RECORDED"


class ActorKind(StrEnum):
    """Who acted, in the only four shapes an audited action can have (§32).

    ``SYSTEM`` is for what no one asked for: schedulers, retries, expiries.
    """

    ELA = "ELA"
    USER = "USER"
    DEVICE = "DEVICE"
    SYSTEM = "SYSTEM"


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


class ProviderStatus(StrEnum):
    """Whether a model provider can be called at all (§25 "disponibilità", §26; ADR 0020 §2).

    Two values and no ``UNKNOWN``: a provider that cannot say it is usable is not usable, and
    ELA does not send the user's content to something it is unsure about (§33). The status is
    a property of the *configuration* — credentials present or absent — not of the network:
    a provider that is AVAILABLE can still fail a call, and says so in the result.
    """

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


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


class Actor(_DomainModel):
    """Who performed an audited action (§32).

    A free-form string would let "ela", "ELA" and "ela@macbook" mean the same actor and none of
    them be queryable: the kind says what sort of actor it is, the id says which one — an
    :class:`ELAIdentity` id, a user name, a :class:`DeviceId`, or the name of the system process
    that acted on its own.
    """

    kind: ActorKind
    id: Annotated[str, Field(min_length=1)]


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

    ``arguments`` is how the step says *what* the capability is called with (ADR 0018). It holds
    data, not a schema: that the arguments match ``CapabilitySpec.input_schema`` is the Guardian's
    check at decision time (§27), never the model's — validating twice would put the catalogue
    inside the domain.
    """

    id: StepId
    created_at: UtcDatetime
    goal: str
    required_capabilities: tuple[_CapabilityIdField, ...] = ()
    arguments: JsonMapping = _json_payload(
        "The arguments of the capability this step requires (§27; ADR 0018): what the Guardian "
        "validates against ``input_schema`` and what the scope constrains. They belong to the "
        "plan, not to the caller, so a retry runs with the arguments the run used and the "
        "targets an approval was given for stay the targets that are executed. Never in the "
        "audit (§57, architecture rule 23)."
    )
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
    scoped_arguments: tuple[str, ...] = ()
    """Names of the arguments the scope constrains (M4.1): ``("path",)`` for a note writer.

    Data, like ``scope``: that each name is a string property of ``input_schema`` and that scope
    and scoped arguments come together is the catalogue's check (ADR 0010), not the model's.
    """
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
    something else. ``targets`` are the paths the consent is about — the targets of the
    ``REQUIRES_APPROVAL`` decision that asked for it (M4.3, ADR 0012): "yes to writing this note"
    authorises that note, not the folder. Empty when the capability has no targets.
    """

    id: ApprovalId
    created_at: UtcDatetime
    task_id: TaskId
    step_id: StepId
    capability_id: _CapabilityIdField
    targets: tuple[str, ...] = ()
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
    granted_by: Annotated[str, Field(min_length=1, max_length=NAME_MAX_LENGTH)]
    approval_id: ApprovalId | None = None
    task_id: TaskId | None = None
    step_id: StepId | None = None
    expires_at: UtcDatetime | None = None
    max_uses: Annotated[int, Field(gt=0)] | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)

    @model_validator(mode="after")
    def _approval_born_grants_are_single_use_and_bound(self) -> Authorization:
        """A grant with ``approval_id`` is single use and bound to its task and step (§30).

        The invariant of the docstring, enforced (M4.3, ADR 0012 §1): a hand-built or tampered
        grant that claims an approval but is reusable or unbound is refused by the type.
        """
        if self.approval_id is None:
            return self
        for name in ("task_id", "step_id"):
            if getattr(self, name) is None:
                raise ValueError(f"an authorization born from an approval needs {name}")
        if self.max_uses != 1:
            raise ValueError(
                f"an authorization born from an approval is single use (max_uses=1), "
                f"not {self.max_uses}"
            )
        return self


class AuditEvent(_DomainModel):
    """One significant event in the append-only audit trail (§32).

    Records what ELA did, why, under which authorization and with what result. This model is the
    shape of an entry; the append-only log itself is infrastructure.
    """

    id: AuditEventId
    created_at: UtcDatetime
    event_type: AuditEventType
    actor: Actor
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


class ModelRoute(_DomainModel):
    """Which provider answers a model call, and with what profile (§25; ADR 0022).

    The decision of the Model Router, as data — the shape the Guardian's decision already has:
    the router chooses, the route *is* the choice, and the tool executes it. A datum can be
    compared, written into a result and **recomputed**, which an object cannot, and recomputing
    it from the arguments is exactly what the verifier of ``model.routed_as_asked`` does.

    ``provider`` is the **name** the :class:`~ela.ports.ProviderRegistryPort` knows, never the
    provider itself: the domain names things, it does not hold them. ``profile`` is a
    ``model_hint`` of §25 — ``quality``, ``balanced``, ``cheap``… — and never a vendor's model
    id, which only an adapter may know (§26, ADR 0020 §5). ``skipped`` are the providers of the
    route that were passed over because they were not usable, in the order the route names them:
    a choice that jumped over somebody says so (§33).
    """

    task_type: str | None
    provider: str
    profile: str
    skipped: tuple[str, ...] = ()


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
    ``decision_id`` and ``authorization_id`` say under which decision the tool ran and which
    grant that run spent (§32; M5.3, ADR 0015): a result knows where it comes from, as an
    :class:`AuditEvent` does. Both are ``None`` for a result no executor produced.
    """

    id: ExecutionId
    created_at: UtcDatetime
    capability_id: _CapabilityIdField
    status: ExecutionStatus
    task_id: TaskId | None = None
    step_id: StepId | None = None
    tool_name: str | None = None
    device_id: DeviceId | None = None
    decision_id: DecisionId | None = None
    authorization_id: AuthorizationId | None = None
    output: JsonMapping = _json_payload("What the execution produced, if anything (§63).")
    error: ErrorMetadata | None = None
    usage: ProviderUsage | None = None
    """What a provider call inside this execution consumed (§32; M7.2, ADR 0021 §3).

    ``None`` for a tool that calls no provider, which is not the same as zero: zero tokens is a
    call that cost nothing, ``None`` is a tool that never made one. It is the only route by which
    "provider usage metadata" reaches the audit trail, the executor copying it into
    :attr:`AuditEvent.usage`.
    """
    duration_ms: Annotated[int, Field(ge=0)] | None = None
    metadata: JsonMapping = _json_payload(_METADATA_DESCRIPTION)


# --------------------------------------------------------------------------------------
# Perception (§10, §11; M10.1, ADR 0028)
# --------------------------------------------------------------------------------------


class SensorState(StrEnum):
    """The three states of §11, verbatim, for the microphone and the webcam.

    ``ACTIVE`` means **the device is in use by somebody**, not "ELA is capturing": §11 exists so
    the user knows whether their webcam is on, and ELA is only one of the programs that could have
    turned it on. Nothing widens this enum — it is the spec's, and it has three values.

    A state is never read alone. It travels inside a :class:`SensorStatus`, next to the
    :class:`SensorCause` that says whether it is an observation or a fail-safe default.
    """

    OFF = "OFF"
    AVAILABLE = "AVAILABLE"
    """Present, and not in use. *Not* "ELA may use it": whether ELA may is a permission, and
    permissions are reported separately (:class:`SystemPermission`)."""
    ACTIVE = "ACTIVE"


class SensorCause(StrEnum):
    """Why a :class:`SensorState` is what it is (M10.1, decisions 3 and 4).

    The reason this exists instead of a fourth state: §11 declares three states and they are the
    spec's, while "ELA could not look" is a different fact from "the device is off". An enum that
    absorbs two different facts and a defence that cannot fire are the same mistake.

    **Anything other than** :attr:`OBSERVED` **means the state is the fail-safe default and not a
    claim about the world.** ``OFF`` alone does not exist: there is ``OFF because there is no
    hardware`` and ``OFF because nobody looked``, and neither of them says "it is switched off".

    ``DENIED_BY_SYSTEM`` is deliberately **not** here. Under §11-as-decided no state depends on a
    permission — the microphone is observed through CoreAudio, which asks nobody, and cameras are
    enumerated without TCC — so a "the system refuses" cause would be a value that can never fire.
    It is born in the milestone where ELA first tries to *make* a device ``ACTIVE``: there
    "macOS refuses me" will explain a state instead of being a separate fact. Until then the
    refusal is a :class:`PermissionState` on the permissions map, where it fires today.
    """

    OBSERVED = "OBSERVED"
    """ELA looked, and this is what it saw. The only cause that makes the state a fact."""
    NO_HARDWARE = "NO_HARDWARE"
    """``OFF`` because the device does not exist: a Mac with no camera, or a CI runner."""
    NOT_OBSERVABLE = "NOT_OBSERVABLE"
    """The question has no answer here: the webcam's "in use by anyone" (no public API), any
    operating system that is not macOS, or a probe that timed out, died or spoke nonsense."""
    NOT_LOOKING = "NOT_LOOKING"
    """ELA has not looked — either because it is configured not to (``ELA_PERCEPTION_ENABLED``)
    or because it has not looked *yet*. Both are the absence of an observation, not an
    observation of absence."""


class SystemPermission(StrEnum):
    """An operating-system permission ELA needs somebody to grant it (§10, §11, §57).

    Accessibility is not here: it gates Computer Control (§20), which is a different section and
    a different milestone. These three are the ones §10 and §11 need.
    """

    CAMERA = "CAMERA"
    MICROPHONE = "MICROPHONE"
    SCREEN_RECORDING = "SCREEN_RECORDING"


class PermissionState(StrEnum):
    """What the operating system answers about a :class:`SystemPermission`.

    Asking is not requesting: every one of these is read without showing the user anything and
    without ever raising a prompt. That is what makes "the permission is missing" a question with
    an answer rather than a failure to catch.

    :attr:`NOT_DETERMINED` is not :attr:`DENIED`. It means nobody has ever asked — and, for a
    process that is not a bundled application, nobody can: the prompt would have to be raised by
    the responsible process, and a daemon has none. The grant comes from the user in System
    Settings, or it does not come.
    """

    GRANTED = "GRANTED"
    DENIED = "DENIED"
    RESTRICTED = "RESTRICTED"
    """Refused by a policy the user cannot lift here: managed device, parental controls."""
    NOT_DETERMINED = "NOT_DETERMINED"
    NOT_OBSERVABLE = "NOT_OBSERVABLE"
    """Not read at all, or read as something this version does not understand (fail-safe: an
    unknown answer is never optimistically mapped to ``GRANTED``)."""


class ProbeFamily(StrEnum):
    """A group of readings that share a cadence (M10.1, decision 6).

    The three families are not a taxonomy, they are three measured cost classes and three
    frequencies of change: the microphone goes on while you watch, a permission changes when a
    human clicks in System Settings. Each has its own ``ELA_PERCEPTION_*_INTERVAL_SECONDS``.
    """

    SENSORS = "SENSORS"
    SESSION = "SESSION"
    PERMISSIONS = "PERMISSIONS"


class SensorStatus(_DomainModel):
    """A §11 state and the reason it says what it says — the two never separate (M10.1).

    Nothing anywhere holds a bare :class:`SensorState`: not a field, not an API schema, not a line
    of the CLI. ``OFF (NOT_OBSERVABLE)`` and ``OFF (NO_HARDWARE)`` are different answers, and a
    reader shown only ``OFF`` has been told something ELA does not know.

    Same trade as :attr:`Device.privacy` starting at ``LOCAL_ONLY``: an undeclared value must never
    be read as a permission — here, an unobserved value must never be read as an observation.
    """

    state: SensorState
    cause: SensorCause


class RawObservation(_DomainModel):
    """What the operating system answered, in primitives — no domain vocabulary (M10.1, dec. 1).

    This is what crosses the boundary out of ELA's process, and it deliberately carries **no
    decision**: an ``int`` for an ``AVAuthorizationStatus``, a ``bool`` for "in use", ``None`` for
    "not read". Turning any of it into a :class:`SensorState` or a :class:`PermissionState` is
    :func:`ela.perception.interpret`, inside the package the coverage gate covers — which is what
    lets the adapter stay outside it honestly (architecture rule 34).

    ``None`` is the only way absence is expressed, and it means exactly one thing: *this was not
    read*. Whether that is because there is no hardware, because the probe timed out, or because
    this family was not due, the answer is the same shape and the core decides what it means.
    """

    camera_count: Annotated[int, Field(ge=0)] | None = None
    microphone_count: Annotated[int, Field(ge=0)] | None = None
    microphone_in_use: bool | None = None
    display_count: Annotated[int, Field(ge=0)] | None = None
    display_asleep: bool | None = None
    screen_locked: bool | None = None
    on_console: bool | None = None
    idle_seconds: Annotated[float, Field(ge=0)] | None = None
    camera_permission: int | None = None
    """``AVAuthorizationStatus``: 0 not determined, 1 restricted, 2 denied, 3 authorized. Kept as
    the integer the framework returned — naming it is the core's job, and an integer this version
    does not know becomes :attr:`PermissionState.NOT_OBSERVABLE` rather than a guess."""
    microphone_permission: int | None = None
    screen_recording_permission: bool | None = None


FAMILY_FIELDS: Final[Mapping[ProbeFamily, tuple[str, ...]]] = MappingProxyType(
    {
        ProbeFamily.SENSORS: ("camera_count", "microphone_count", "microphone_in_use"),
        ProbeFamily.SESSION: (
            "display_count",
            "display_asleep",
            "screen_locked",
            "on_console",
            "idle_seconds",
        ),
        ProbeFamily.PERMISSIONS: (
            "camera_permission",
            "microphone_permission",
            "screen_recording_permission",
        ),
    }
)
"""Which field of :class:`RawObservation` belongs to which family.

One table, read by both sides: the probe to know what to read, the core to know what a refresh of
one family may overwrite. Two tables would drift, and the drift would show up as a phantom change
— a permission "changing" because the tick that refreshed the microphone did not read it.

A test asserts that this partitions :attr:`RawObservation.model_fields` **exactly**, so a field
added tomorrow cannot quietly belong to no family.
"""


def _freeze_permissions(
    value: Mapping[SystemPermission, PermissionState],
) -> Mapping[SystemPermission, PermissionState]:
    return MappingProxyType(dict(value))


def _thaw_permissions(
    value: Mapping[SystemPermission, PermissionState],
) -> dict[str, str]:
    return {permission.value: state.value for permission, state in value.items()}


_PermissionMap = Annotated[
    Mapping[SystemPermission, PermissionState],
    AfterValidator(_freeze_permissions),
    PlainSerializer(_thaw_permissions, return_type=dict[str, str]),
]
"""The permissions map, deeply immutable, serialising to plain strings like every other payload."""


class Observation(_DomainModel):
    """What ELA believes about this machine at one instant (§10, first ring; M10.1).

    Not a snapshot of the user's world: no screen content, no window titles, no audio, no image.
    Device states, operating-system permissions, and the shape of the session — the things §10
    calls "local detection", and nothing that a later milestone will have to ask permission for.

    ``idle_seconds`` is the one behavioural datum, and it is carried **as a number**: turning it
    into "present" or "away" is a threshold, and a threshold is a decision that belongs to whoever
    decides (§45), not to whoever observes. It is also the one continuous field, so it is excluded
    from the fingerprint the change detector compares — see :func:`ela.perception.fingerprint`.
    """

    observed_at: UtcDatetime
    """When ELA formed this view. On the very first one, before any probe has run, this is the
    instant of the belief and not of an observation — every cause says so."""
    microphone: SensorStatus
    camera: SensorStatus
    permissions: _PermissionMap
    display_count: Annotated[int, Field(ge=0)] | None = None
    display_asleep: bool | None = None
    screen_locked: bool | None = None
    on_console: bool | None = None
    idle_seconds: Annotated[float, Field(ge=0)] | None = None


class PerceptionChange(_DomainModel):
    """One thing that is no longer what it was, between two observations (§10; M10.1).

    Deliberately flat and stringly-typed: a change is something to *show*, and the observation
    next to it is where the values live with their types. It is not an audit event, and the
    distinction is the criterion of ADR 0028 — the audit records what ELA decides, not what the
    world does.
    """

    field: str
    """The fingerprint key, e.g. ``microphone`` or ``permissions.CAMERA``."""
    before: str
    after: str
