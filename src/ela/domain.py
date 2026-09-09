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
    "ContextActivity",
    "ContextApproval",
    "ContextDeadline",
    "ContextDeadlines",
    "ContextDevice",
    "ContextEvent",
    "ContextQuestion",
    "ContextQuestionStatus",
    "ContextRecent",
    "ContextSnapshot",
    "ContextSource",
    "ContextTask",
    "ContextWork",
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
    "QUESTION_SOURCES",
    "RawCapture",
    "RawObservation",
    "RawRecognition",
    "RawSpeech",
    "RawTextLine",
    "RiskLevel",
    "SOURCE_FIELDS",
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
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    """A node ELA did not know is now in the registry (§16, §32; M6.1b, ADR 0035 §3).

    The debt ADR 0016 §6 declared on 2026-09-07: registering a node is a configuration change —
    which machines ELA may use, with which tools — and it had no event because in v0.1 the only
    node was ``local``, written by the Core on its own machine, so the type would have had no real
    writer. An automatic write at start-up is that writer.
    """
    DEVICE_REFRESHED = "DEVICE_REFRESHED"
    """A node ELA already used can now do different things (§16, §32; M6.1b, ADR 0035 §3).

    A distinct type and not a payload of :attr:`DEVICE_REGISTERED`, for the reason ADR 0008 gives
    for the engine: "a machine entered ELA's world" and "a machine ELA was already using changed"
    are two questions the log must answer by type. The summary carries the whole difference and
    not a count — *which* capability was gained or lost is the diagnosis.
    """
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
    prompt_arguments: tuple[str, ...] = ()
    """Names of the arguments whose values belong in the question the user is asked (M10.2, §30).

    Empty by default, and the default is the defence: ``model.complete`` takes ``input``, which is
    the user's content, and a prompt that showed it would write it into a stored
    :class:`Approval`. **An argument is not shown unless the capability declares it.**

    What the declaration is for is the other half of §30: "un semplice 'Sì' fuori contesto non
    deve automaticamente autorizzare" — generalised, *a yes is only worth something if the
    question was complete*. ``perception.capture_screen`` declares ``purpose`` because "ELA wants
    to photograph your screen" is not a question anybody can answer; "…in order to read the
    failing test output" is.

    Data, like ``scope``: that each name is a **required** ``string`` property of ``input_schema``
    is the catalogue's check (ADR 0010, ADR 0029 §6), not the model's.
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

    The families are not a taxonomy, they are measured cost classes and frequencies of change: the
    microphone goes on while you watch, a permission changes when a human clicks in System
    Settings. Each has its own ``ELA_PERCEPTION_*_INTERVAL_SECONDS``.

    The declaration order is the measurement, cheapest and fastest first, and a test asserts that
    the default intervals ascend along it — so a family added tomorrow has to say where it belongs
    rather than landing at the end by accident.

    ``APPLICATIONS`` joined in M10.3 and is the cheapest of the four — 0,26 ms for the window
    list, 0,001 ms for the frontmost application — and, like the rest of this ring, it costs **no
    permission at all**: measured from a process that was its own TCC responsible process, the
    owners, PIDs and geometry of every on-screen window come back in full. What does *not* come
    back there is the window **title**, which needs the same Screen Recording grant a screenshot
    needs and is content rather than state — so it is not here, and architecture rule 36 keeps it
    out.
    """

    SENSORS = "SENSORS"
    APPLICATIONS = "APPLICATIONS"
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
    running_bundle_ids: tuple[str, ...] | None = None
    """Bundle identifiers of the applications with a user interface, sorted.

    The identifier and not ``localizedName``, which is a string to *show*: on an Italian system it
    answers ``Terminale`` and ``Impostazioni di Sistema``, so comparing two observations on it
    would mean a change detector that fires when the system language changes. An application with
    no bundle identifier — it happens, the property is nullable — is not carried, because there is
    nothing to name it by.
    """
    frontmost_bundle_id: str | None = None
    window_count: Annotated[int, Field(ge=0)] | None = None
    """How many windows are on screen. A count, and nothing about any one of them: no title (rule
    36), and no geometry, because nothing in this milestone reads one."""
    camera_permission: int | None = None
    """``AVAuthorizationStatus`': 0 not determined, 1 restricted, 2 denied, 3 authorized. Kept as
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
        ProbeFamily.APPLICATIONS: (
            "running_bundle_ids",
            "frontmost_bundle_id",
            "window_count",
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
    Device states, operating-system permissions, the shape of the session and which applications
    are running — the things §10 calls "local detection", and nothing that needs a permission.

    **Why the window titles are still not here, now that the windows are counted** (M10.3): a
    title is content — a browser title carries a URL or an email subject — and it costs the same
    Screen Recording grant a screenshot costs, measured. So the count is state and comes free, the
    title is content and goes through the Guardian; architecture rule 36 is what keeps the line
    from being an intention.

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
    running_bundle_ids: tuple[str, ...] | None = None
    """Which applications with a user interface are running, by bundle identifier (M10.3).

    State, not content: it says *that* Mail is open, never what is in it. It costs no permission,
    it does not leave the machine, and — like the rest of this model — it is not memory: ELA holds
    this observation and the previous one, so a restart forgets it (ADR 0028 §10)."""
    frontmost_bundle_id: str | None = None
    window_count: Annotated[int, Field(ge=0)] | None = None


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


class RawTextLine(_DomainModel):
    """One line the recognition helper read, and how sure it was (M10.3, ADR 0030).

    Primitives, like everything that crosses out of ELA's process: a string and a number. What a
    confidence of 0,5 *means* is not the adapter's to say — nothing is filtered on it, because a
    threshold is a decision and belongs to whoever decides (§45).
    """

    text: str
    confidence: Annotated[float, Field(ge=0, le=1)]


class RawRecognition(_DomainModel):
    """What the text-recognition helper did, in primitives — no verdict (M10.3, ADR 0030).

    The sibling of :class:`RawCapture` on the reading side, with one difference that was argued
    rather than assumed: **the payload travels here**, where the image's never did.

    ADR 0029 §4 kept the pixels out of the pipe because a helper killed at the timeout leaves a
    truncated base64 string that *decodes into a partial image* — a shorter answer shaped like an
    answer. JSON Lines is self-delimiting, so the same truncation is a parse error instead, and
    the failure mode that decided the image's direction does not exist here. The direction also
    gains something the image had to declare as a limit: the parent writes the file itself, so it
    is ``0o600`` from its first byte and never briefly carries the process umask.

    ``unsupported_languages`` is the reason a caller can tell "this screen has no text" from "ELA
    was configured with a language that does not exist" — measured, those two are the same answer
    from Vision, and a reading that can mean both must be split before it is handed on (ADR 0030
    §8).
    """

    exit_code: int | None = None
    killed: bool = False
    lines: tuple[RawTextLine, ...] = ()
    unsupported_languages: tuple[str, ...] = ()


class RawCapture(_DomainModel):
    """What the screen-capture helper did, in primitives — no verdict (M10.2, ADR 0029 §11).

    The mirror of :class:`RawObservation` on the acting side: it crosses the boundary out of ELA's
    process and carries **no decision**. Whether "exit code 1" means the permission is gone or the
    disk is full is not something the adapter may answer, and whether an answer is a success is
    read from the artefact, never from this.

    Deliberately without a ``bytes`` field, and without a path: the image never travels through
    this model, because the caller already owns the destination it asked the helper to write
    (ADR 0029 §4). What comes back is only how the helper ended.
    """

    exit_code: int | None = None
    """The helper's exit status; ``None`` when it never ran — no such operating system, or the
    process could not be started at all."""
    timed_out: bool = False
    """Whether the helper was killed for overstaying. Separate from ``exit_code`` because "it did
    not answer" and "it answered badly" are different facts, and only the first says nothing at
    all about the machine."""


class RawSpeech(_DomainModel):
    """What the speech helper did, in primitives — no verdict (M11.1, ADR 0033).

    The third of its kind, after :class:`RawCapture` and :class:`RawRecognition`, and the first
    on a channel that leaves no artefact at all: a spoken sentence is not a file, not a record and
    not a thing anybody can go back and look at. What comes back is only how the helper ended.

    **No text field, and that is the decision.** Architecture rule 40 keeps what ELA says off the
    disk; a model that carried the sentence back would put it into an ``ExecutionResult`` that is
    persisted, which is the same accumulation by another route (M11.1 dec. 7). What the tool
    reports about the words is their length and their digest, never the words.

    ``spoken_seconds`` is how long the helper ran. It is a **measurement and not a verdict**: it
    says the process was alive that long, never that a human heard anything — the distinction the
    verifier is built to state out loud (M11.1 dec. C).
    """

    exit_code: int | None = None
    """The helper's exit status; ``None`` when it never ran — no such operating system, or the
    process could not be started at all."""
    timed_out: bool = False
    """Whether the helper was killed for overstaying. Separate from ``exit_code`` for the reason
    :class:`RawCapture` separates them: "it did not answer" and "it answered badly" are different
    facts."""
    spoken_seconds: float | None = None
    """Wall-clock time the **sound** was being made; ``None`` when nothing was ever played.

    For the local voice that is the whole of the helper's life. For the online voice it is the
    playback alone, and never the synthesis (:attr:`synthesis_seconds`) — the verifier compares
    it against the time those words take to say, and a number that included a round-trip would
    make a sentence that was never played look like one that was (ADR 0034 §6).
    """
    synthesis_seconds: float | None = None
    """How long the audio took to arrive, when it came from somewhere. ``None`` for a voice that
    is this machine's own: there is nothing to wait for and nothing to report."""
    error: str | None = None
    """Which of :data:`~ela.ports.SPEECH_ERROR_CODES` this was, when the sound did not happen.

    The adapter names the failure and never decides what it means for the task — the same split
    ADR 0020 §7 made for the model provider, and for the same reason: whoever receives a failure
    must be able to tell a refused credential from an overload **without knowing who produced
    it**. A second implementation of :class:`~ela.ports.SpeechPort` reports these codes or it is
    not interchangeable with the first.
    """
    credits: int | None = None
    """What the provider says the sentence cost, from its own header — never an estimate.

    ADR 0020 §6 had to estimate a call's cost from a dated table, with a test that expires after
    180 days because no test notices a vendor changing its prices. This provider states the cost
    of every request, so ELA reports the number it was given (ADR 0034 §10). In credits, which
    the provider asserts; never in currency, which would depend on a plan ELA would have to keep
    up with.
    """
    history_item_id: str | None = None
    """The receipt: where the copy the provider kept can be found (ADR 0034 §10).

    Not the text and not content — an address. The retention is a cost the user accepted, and a
    cost accepted that nobody can then find again is a cost that was described rather than shown.
    """
    retryable: bool = False
    """Whether :attr:`error` is worth trying again. The **nature** of the failure and not the
    attempts left (ADR 0020 §7): a rate limit can succeed a minute later, a refused key cannot.
    ``False`` by default because a doubt is not a yes (§33)."""
    audio_bytes: int | None = None
    """How much audio arrived. ``None`` when none did, or when there was never a file to count —
    the local voice plays as it synthesises and no byte is ever ELA's to hold."""


# --------------------------------------------------------------------------------------
# Context (§44, §45; M10.4, ADR 0032)
# --------------------------------------------------------------------------------------


class ContextQuestion(StrEnum):
    """The seven things §44 says ELA must try to understand, one member each, in §44's order.

    They are an enum and not a docstring because the snapshot carries **all seven, always** —
    including the ones this ELA cannot answer. A question that does not appear is a question
    nobody notices ELA is not answering, and §44 is a list of what must be understood, not of
    what happens to be available.

    ``tests/docs/test_spec_context.py`` reads §44 out of the specification and binds it to this
    enum: a bullet added there fails until a member is added here, and the other way round.
    """

    CURRENT_ACTIVITY = "CURRENT_ACTIVITY"
    """"cosa sta facendo l'utente"."""
    PREVIOUS_ACTIVITY = "PREVIOUS_ACTIVITY"
    """"cosa stava facendo prima"."""
    TASKS_IN_FLIGHT = "TASKS_IN_FLIGHT"
    """"quali task sono in corso"."""
    DEADLINES = "DEADLINES"
    """"quali scadenze esistono"."""
    DEVICE_IN_USE = "DEVICE_IN_USE"
    """"quale dispositivo sta usando"."""
    RELEVANT_INFORMATION = "RELEVANT_INFORMATION"
    """"quali informazioni sono rilevanti"."""
    PROJECT_ACTIVITY = "PROJECT_ACTIVITY"
    """"cosa sta accadendo nei progetti"."""


class ContextSource(StrEnum):
    """A place a context answer could come from — the ones ELA has, and the ones it has not.

    The five that do not exist are members with the same standing as the five that do, because
    naming an absence is the only way it can be reported. Which is which is **never written
    down**: it is derived from :data:`SOURCE_FIELDS` against the fields
    :class:`ContextSnapshot` actually has (ADR 0032 §3), so a source whose field arrives stops
    being missing in the same commit that adds it.
    """

    PERCEPTION = "PERCEPTION"
    """What ELA sees of this machine (§10, §11): the first ring."""
    CHANGES = "CHANGES"
    """What changed since the previous observation, and how far back that reaches."""
    TASKS = "TASKS"
    """The tasks ELA owns (§14, §15), their state and the step under way."""
    TASK_DEADLINES = "TASK_DEADLINES"
    """The deadlines of those tasks — the ones ELA holds, never every deadline there is."""
    DEVICES = "DEVICES"
    """The registry of nodes (§16)."""
    CALENDAR = "CALENDAR"
    """**Absent.** §44's own worked example starts here. Belongs with §39."""
    MAIL = "MAIL"
    """**Absent.** §39."""
    DOCUMENTS = "DOCUMENTS"
    """**Absent.** §23."""
    PROJECTS = "PROJECTS"
    """**Absent.** No Project entity exists; §21 lists projects among the kinds of memory."""
    RELEVANCE = "RELEVANCE"
    """**Absent.** Relevance is a judgement: §45, or §21's importance. Not composable."""


SOURCE_FIELDS: Final[Mapping[ContextSource, str]] = MappingProxyType(
    {
        ContextSource.PERCEPTION: "activity",
        ContextSource.CHANGES: "recent",
        ContextSource.TASKS: "work",
        ContextSource.TASK_DEADLINES: "deadlines",
        ContextSource.DEVICES: "device",
        ContextSource.CALENDAR: "calendar",
        ContextSource.MAIL: "mail",
        ContextSource.DOCUMENTS: "documents",
        ContextSource.PROJECTS: "projects",
        ContextSource.RELEVANCE: "relevance",
    }
)
"""Which field of :class:`ContextSnapshot` carries each source — including the ones with none.

This is the whole mechanism of ADR 0032 §3. A source is *held* exactly when the field it names
is a field of the snapshot, so the day somebody adds ``calendar`` the absence disappears by
construction and there is no second list to remember. The direction is the fail-safe one: a
source whose field does not exist is **missing**, never quietly answered.
"""

QUESTION_SOURCES: Final[Mapping[ContextQuestion, tuple[ContextSource, ...]]] = MappingProxyType(
    {
        ContextQuestion.CURRENT_ACTIVITY: (ContextSource.PERCEPTION,),
        ContextQuestion.PREVIOUS_ACTIVITY: (ContextSource.CHANGES,),
        ContextQuestion.TASKS_IN_FLIGHT: (ContextSource.TASKS,),
        ContextQuestion.DEADLINES: (ContextSource.TASK_DEADLINES, ContextSource.CALENDAR),
        ContextQuestion.DEVICE_IN_USE: (ContextSource.DEVICES,),
        ContextQuestion.RELEVANT_INFORMATION: (
            ContextSource.RELEVANCE,
            ContextSource.MAIL,
            ContextSource.DOCUMENTS,
        ),
        ContextQuestion.PROJECT_ACTIVITY: (
            ContextSource.PROJECTS,
            ContextSource.MAIL,
            ContextSource.DOCUMENTS,
        ),
    }
)
"""What would answer each question of §44 — everything, not only what exists.

``DEADLINES`` is the row that decided the shape: ELA knows the deadlines of its own tasks and
not the ones in a calendar, so the question is answered *and* incomplete at once. A partition
into answered/unanswered would have had to pick one, and either pick is a lie.
"""


def _freeze_state_counts(value: Mapping[TaskState, int]) -> Mapping[TaskState, int]:
    return MappingProxyType(dict(value))


def _thaw_state_counts(value: Mapping[TaskState, int]) -> dict[str, int]:
    return {state.value: total for state, total in value.items()}


_StateCounts = Annotated[
    Mapping[TaskState, int],
    AfterValidator(_freeze_state_counts),
    PlainSerializer(_thaw_state_counts, return_type=dict[str, int]),
]
"""How many live tasks are in each state — frozen like every mapping in the domain."""


class ContextQuestionStatus(_DomainModel):
    """One question of §44, what answers it here, and what is missing from the answer.

    Both lists can be empty; never both at once, and never overlapping — the two are the halves
    of one partition computed by ``ela.context.held``. A question with sources and missing
    sources at the same time is not a defect: it is ``DEADLINES``.
    """

    question: ContextQuestion
    answered_by: tuple[ContextSource, ...] = ()
    missing: tuple[ContextSource, ...] = ()


class ContextActivity(_DomainModel):
    """What the user is doing, as far as state can say it (§44, first line).

    Straight from :class:`Observation`, and stopping exactly where it stops: which applications
    are running, which is frontmost, how many windows, how long since an input. No window title
    (rule 36), no screen text, no pixel — answering "what is the user doing" by reading the
    screen costs a capability, and what costs a capability is not context (rule 38).

    ``observed_at`` is the one age that differs from the snapshot's ``at``: the cadence means a
    family inside its interval answers with what it last saw (ADR 0028 §6).
    """

    observed_at: UtcDatetime
    microphone: SensorStatus
    camera: SensorStatus
    permissions: _PermissionMap
    display_count: Annotated[int, Field(ge=0)] | None = None
    display_asleep: bool | None = None
    screen_locked: bool | None = None
    on_console: bool | None = None
    idle_seconds: Annotated[float, Field(ge=0)] | None = None
    running_bundle_ids: tuple[str, ...] | None = None
    frontmost_bundle_id: str | None = None
    window_count: Annotated[int, Field(ge=0)] | None = None


class ContextDevice(_DomainModel):
    """The node ELA is running on (§44, "quale dispositivo sta usando").

    One node in v0.1, and ``is_local`` says which one rather than leaving it implied.

    ``available`` is a **boolean and not a** :class:`DeviceAvailability`, and that is architecture
    rule 20 rather than a preference: availability is derived from the heartbeat by the registry,
    and nobody outside ``ela.devices`` may read the field. What a composer is entitled to is the
    registry's answer, which is what this carries — the same shape ``/diagnostics`` already uses.
    """

    device_id: DeviceId
    name: str
    os: OperatingSystem
    available: bool
    status: DeviceStatus
    is_local: bool
    last_seen_at: UtcDatetime | None = None


class ContextTask(_DomainModel):
    """One live task, and the step under way if there is one (§44, "quali task sono in corso").

    ``goal`` is the user's own words, and it is here by decision (ADR 0032 §5): ``GET /tasks``
    already returns it to the same reader under the same token, and "three tasks" without saying
    which does not answer §44. It is the only user content in the whole snapshot, and rule 39 is
    what keeps it out of an audit event and out of a provider request.
    """

    task_id: TaskId
    goal: str
    state: TaskState
    deadline: UtcDatetime | None = None
    current_step_id: StepId | None = None
    current_step_goal: str | None = None


class ContextApproval(_DomainModel):
    """A request waiting for the user's answer (§30) — that it waits, and for what.

    No ``prompt``: it may carry a declared ``purpose`` (ADR 0029 §6), and an argument is shown
    where the capability declares it, for the question it declares it for. A composed picture is
    not that question.
    """

    approval_id: ApprovalId
    task_id: TaskId
    capability_id: _CapabilityIdField
    expires_at: UtcDatetime | None = None


class ContextWork(_DomainModel):
    """What ELA has under way (§44, third line), and how much of it is being shown.

    ``shown`` and ``total`` are the criterion of ADR 0032 §9-bis: a live task outside the limit
    must not vanish quietly, because "there are no more" and "I am not showing you the rest" are
    different facts. ``total`` comes from ``TaskRepository.count``, never from loading.
    """

    shown: Annotated[int, Field(ge=0)]
    """How many live tasks this section carries."""
    total: Annotated[int, Field(ge=0)]
    """How many there are. ``shown < total`` is a truncation, and it is said out loud."""
    tasks: tuple[ContextTask, ...] = ()
    states: _StateCounts = Field(default_factory=dict)
    pending_approvals: tuple[ContextApproval, ...] = ()

    @model_validator(mode="after")
    def _shown_is_what_is_shown(self) -> ContextWork:
        if self.shown != len(self.tasks):
            raise ValueError("shown must be the number of tasks carried")
        if self.total < self.shown:
            raise ValueError("total cannot be smaller than what is shown")
        return self


class ContextDeadline(_DomainModel):
    """One deadline ELA holds — the instant, and nothing derived from it.

    No ``overdue``: comparing the instant with the snapshot's ``at`` is the reader's, and a
    derived judgement here would be deciding for whoever decides (§45; ADR 0028 §5 did the same
    for ``idle_seconds``).
    """

    task_id: TaskId
    goal: str
    state: TaskState
    deadline: UtcDatetime


class ContextDeadlines(_DomainModel):
    """The deadlines ELA holds, and how many of them are being shown (ADR 0032 §9-bis)."""

    shown: Annotated[int, Field(ge=0)]
    total: Annotated[int, Field(ge=0)]
    deadlines: tuple[ContextDeadline, ...] = ()

    @model_validator(mode="after")
    def _shown_is_what_is_shown(self) -> ContextDeadlines:
        if self.shown != len(self.deadlines):
            raise ValueError("shown must be the number of deadlines carried")
        if self.total < self.shown:
            raise ValueError("total cannot be smaller than what is shown")
        return self


class ContextEvent(_DomainModel):
    """One state change of a live task, for "cosa stava facendo prima" (§44, second line).

    A task event and never an audit event: the audit is the trail of what **ELA decided** (§32),
    and reading it back into a composed picture is a second use of the log that deserves its own
    decision rather than a side effect (ADR 0032 §11). Rule 39 makes that structural.
    """

    task_id: TaskId
    event_type: TaskEventType
    at: UtcDatetime
    previous_state: TaskState | None = None
    new_state: TaskState | None = None


class ContextRecent(_DomainModel):
    """How far back ELA can see, and what changed in that window (§44, second line).

    ``since`` is not decoration. Without it "what was the user doing before" means two things at
    once — *little happened* and *I have not been looking long* — which is the ambiguity ADR 0030
    §8 says to split before handing a reading on. With it, the horizon is a fact: here it is
    seconds, because ELA keeps the current observation and the previous one and nothing else
    (ADR 0028 §10). On the very first tick ``since`` equals the observation's own instant and
    ``changes`` is empty, which is a true answer and not a missing one.
    """

    since: UtcDatetime
    changes: tuple[PerceptionChange, ...] = ()
    events: tuple[ContextEvent, ...] = ()


class ContextSnapshot(_DomainModel):
    """The answer to §44 at one instant: what ELA can say, and what it cannot (M10.4, ADR 0032).

    Composed on read and never stored. It is context and not memory, and the line is the test of
    ADR 0032 §4: **if the fact can be recomputed it is context; if losing it loses information it
    is memory.** So there is no importance here, no confidence, no expiry and no privacy level —
    those four fields of §21 govern something that is *kept*, and this keeps nothing. A restart
    loses nothing because there was nothing to lose.

    No ``JsonMapping`` on this model or on any of its sections, for the reason ADR 0028 §11 gives
    the perception models: a free-form bag is exactly where a window title, a file name or a
    fragment of recognised text would end up "just for context".

    ``questions`` carries all seven of §44 — see :class:`ContextQuestion`.
    """

    at: UtcDatetime
    """The one instant. Every age in the snapshot is relative to this; four routes joined by a
    caller would be four instants, which is one of the four things this model adds."""
    activity: ContextActivity
    device: ContextDevice | None = None
    """``None`` only when the registry does not hold the local node — a composition ELA can be
    in, and one that must be visible rather than guessed at."""
    work: ContextWork
    deadlines: ContextDeadlines
    recent: ContextRecent
    questions: tuple[ContextQuestionStatus, ...] = ()
