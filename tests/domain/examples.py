"""One readable, fully populated instance of every domain model, shared by the tests.

The instances are hand-written on purpose: they are the "identity card" of each entity and make
a failing round-trip readable, where a generated value would not. The property tests in
``test_properties.py`` cover the rest of the value space.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Final
from uuid import UUID

from pydantic import BaseModel

from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEvent,
    AuditEventId,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    DecisionId,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceId,
    DeviceStatus,
    ELAIdentity,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    IdentityId,
    IntentChannel,
    IntentId,
    ModelRoute,
    NetworkKind,
    Observation,
    OperatingSystem,
    PerceptionChange,
    PerformanceClass,
    PermissionDecision,
    PermissionOutcome,
    PermissionState,
    PlanId,
    PowerSource,
    PrivacyLevel,
    ProviderRequest,
    ProviderRequestId,
    ProviderResult,
    ProviderResultId,
    ProviderUsage,
    RawObservation,
    RiskLevel,
    SensorCause,
    SensorState,
    SensorStatus,
    StepId,
    SystemPermission,
    Task,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
    UserIntent,
)


def _uuid(tail: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-{tail:012d}")


NOW: Final = datetime(2026, 9, 4, 10, 30, tzinfo=UTC)
LATER: Final = datetime(2026, 9, 4, 11, 0, tzinfo=UTC)
MUCH_LATER: Final = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

IDENTITY_ID: Final = IdentityId(_uuid(1))
INTENT_ID: Final = IntentId(_uuid(2))
TASK_ID: Final = TaskId(_uuid(3))
STEP_ID: Final = StepId(_uuid(4))
OTHER_STEP_ID: Final = StepId(_uuid(5))
PLAN_ID: Final = PlanId(_uuid(6))
TASK_EVENT_ID: Final = TaskEventId(_uuid(7))
DEVICE_ID: Final = DeviceId(_uuid(8))
DECISION_ID: Final = DecisionId(_uuid(9))
AUTHORIZATION_ID: Final = AuthorizationId(_uuid(10))
APPROVAL_ID: Final = ApprovalId(_uuid(11))
AUDIT_EVENT_ID: Final = AuditEventId(_uuid(12))
PROVIDER_REQUEST_ID: Final = ProviderRequestId(_uuid(13))
PROVIDER_RESULT_ID: Final = ProviderResultId(_uuid(14))
EXECUTION_ID: Final = ExecutionId(_uuid(15))

WRITE_NOTE: Final = CapabilityId("workspace.write_note")
MODEL_COMPLETE: Final = CapabilityId("model.complete")

DEVICE_CAPABILITY: Final = DeviceCapability(
    name=DeviceCapabilityName("gpu.cuda"),
    available=True,
    attributes={"vram_gb": 24, "families": ["ada", "hopper"]},
)

ELA_ACTOR: Final = Actor(kind=ActorKind.ELA, id="ela")

PROVIDER_USAGE: Final = ProviderUsage(
    input_tokens=1_200,
    output_tokens=340,
    cached_input_tokens=800,
    cost=Decimal("0.0123"),
    currency="EUR",
    latency_ms=1_450,
)

ERROR_METADATA: Final = ErrorMetadata(
    code="tool.timeout",
    message="the note was not written",
    cause="the workspace was locked by another process",
    tool_name="workspace_notes",
    model="model-large",
    device_id=DEVICE_ID,
    attempted_fix="retry after 2s",
    successful_fix="retry after releasing the lock",
    retryable=True,
    details={"attempts": 2},
)

ELA_IDENTITY: Final = ELAIdentity(
    id=IDENTITY_ID,
    created_at=NOW,
    version="0.1.0",
    owner="tommaso",
    metadata={"note": "una sola identità logica"},
)

USER_INTENT: Final = UserIntent(
    id=INTENT_ID,
    created_at=NOW,
    text="Preparami tutto per la riunione di domani.",
    channel=IntentChannel.VOICE,
    device_id=DEVICE_ID,
    metadata={"locale": "it-IT"},
)

OTHER_STEP: Final = TaskStep(
    id=OTHER_STEP_ID,
    created_at=NOW,
    goal="raccogliere l'agenda e i partecipanti",
    required_capabilities=(MODEL_COMPLETE,),
    risk=RiskLevel.SAFE,
    expected_result="agenda e lista dei partecipanti",
    requires_authorization=False,
)

TASK_STEP: Final = TaskStep(
    id=STEP_ID,
    created_at=NOW,
    goal="scrivere il briefing della riunione",
    required_capabilities=(WRITE_NOTE, MODEL_COMPLETE),
    preferred_device_traits=(DeviceCapabilityName("gpu.cuda"), DeviceCapabilityName("keyboard")),
    dependencies=(OTHER_STEP_ID,),
    risk=RiskLevel.LOW,
    expected_result="una nota con i punti principali",
    success_conditions=("la nota esiste", "contiene i partecipanti"),
    requires_authorization=False,
)

TASK_PLAN: Final = TaskPlan(
    id=PLAN_ID,
    created_at=NOW,
    task_id=TASK_ID,
    goal="preparare la riunione di domani",
    steps=(OTHER_STEP, TASK_STEP),  # a valid DAG: TASK_STEP depends on OTHER_STEP (M3.2)
    metadata={"planner": "executive-core"},
)

TASK: Final = Task(
    id=TASK_ID,
    created_at=NOW,
    goal="preparare la riunione di domani",
    state=TaskState.PLANNING,
    intent_id=INTENT_ID,
    plan_id=PLAN_ID,
    parent_id=None,
    deadline=LATER,
    metadata={"priority": "high"},
)

TASK_EVENT: Final = TaskEvent(
    id=TASK_EVENT_ID,
    created_at=NOW,
    task_id=TASK_ID,
    event_type=TaskEventType.STATE_CHANGED,
    step_id=STEP_ID,
    previous_state=TaskState.CREATED,
    new_state=TaskState.PLANNING,
    message="il planner ha preso in carico il task",
    metadata={"source": "task-engine"},
)

DEVICE: Final = Device(
    id=DEVICE_ID,
    created_at=NOW,
    name="MacBook",
    os=OperatingSystem.MACOS,
    availability=DeviceAvailability.ONLINE,
    status=DeviceStatus.BUSY,
    capabilities=(DEVICE_CAPABILITY,),
    available_tools=("workspace_notes", "browser"),
    performance=PerformanceClass.HIGH,
    network=NetworkKind.LOCAL,
    power_source=PowerSource.AC,
    privacy=PrivacyLevel.TRUSTED,
    current_workload=0.35,
    last_seen_at=LATER,
    metadata={"role": "work node"},
)

CAPABILITY_SPEC: Final = CapabilitySpec(
    id=WRITE_NOTE,
    created_at=NOW,
    description="scrive una nota dentro uno scope autorizzato",
    risk=RiskLevel.LOW,
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "body": {"type": "string"}},
        "required": ["path", "body"],
    },
    scope=("workspace/notes",),
    scoped_arguments=("path",),
    requires_authorization=True,
    metadata={"introduced_in": "0.1"},
)

PERMISSION_DECISION: Final = PermissionDecision(
    id=DECISION_ID,
    created_at=NOW,
    capability_id=WRITE_NOTE,
    outcome=PermissionOutcome.REQUIRES_APPROVAL,
    risk=RiskLevel.LOW,
    reason="lo scope richiesto non è coperto da nessuna autorizzazione attiva",
    task_id=TASK_ID,
    step_id=STEP_ID,
    authorization_id=None,
    approval_id=APPROVAL_ID,
    expires_at=LATER,
    metadata={"guardian": "v0"},
)

APPROVAL: Final = Approval(
    id=APPROVAL_ID,
    created_at=NOW,
    task_id=TASK_ID,
    step_id=STEP_ID,
    capability_id=WRITE_NOTE,
    targets=("workspace/notes/briefing.md",),
    prompt="Posso scrivere il briefing in workspace/notes?",
    status=ApprovalStatus.GRANTED,
    decision_id=DECISION_ID,
    responded_at=LATER,
    responded_by="tommaso",
    expires_at=MUCH_LATER,
    metadata={"channel": "phone"},
)

SINGLE_USE_AUTHORIZATION: Final = Authorization(
    id=AUTHORIZATION_ID,
    created_at=NOW,
    capability_id=WRITE_NOTE,
    scope=("workspace/notes",),
    granted_by="tommaso",
    approval_id=APPROVAL_ID,
    task_id=TASK_ID,
    step_id=STEP_ID,
    expires_at=LATER,
    max_uses=1,
    metadata={"origin": "approval"},
)

POLICY_AUTHORIZATION: Final = Authorization(
    id=AuthorizationId(_uuid(16)),
    created_at=NOW,
    capability_id=WRITE_NOTE,
    scope=("workspace/notes",),
    granted_by="tommaso",
    approval_id=None,
    metadata={"origin": "policy"},
)

AUDIT_EVENT: Final = AuditEvent(
    id=AUDIT_EVENT_ID,
    created_at=NOW,
    event_type=AuditEventType.TOOL_EXECUTED,
    actor=ELA_ACTOR,
    summary="nota scritta in workspace/notes/briefing.md",
    task_id=TASK_ID,
    step_id=STEP_ID,
    capability_id=WRITE_NOTE,
    decision_id=DECISION_ID,
    authorization_id=AUTHORIZATION_ID,
    device_id=DEVICE_ID,
    tool_name="workspace_notes",
    usage=PROVIDER_USAGE,
    error=None,
    payload={"path": "workspace/notes/briefing.md", "bytes": 2048},
)

MODEL_ROUTE: Final = ModelRoute(
    task_type="reasoning",
    provider="provider-a",
    profile="quality",
    skipped=("provider-b",),
)

PROVIDER_REQUEST: Final = ProviderRequest(
    id=PROVIDER_REQUEST_ID,
    created_at=NOW,
    purpose="briefing",
    input="Riassumi le email correlate alla riunione di domani.",
    instructions="Rispondi in italiano, per punti.",
    task_id=TASK_ID,
    model_hint="reasoning",
    parameters={"max_output_tokens": 800},
    metadata={"router": "quality"},
)

PROVIDER_RESULT: Final = ProviderResult(
    id=PROVIDER_RESULT_ID,
    created_at=LATER,
    request_id=PROVIDER_REQUEST_ID,
    provider="provider-a",
    model="model-large",
    output="Tre punti principali: ...",
    usage=PROVIDER_USAGE,
    finish_reason="end_turn",
    error=None,
    metadata={"attempt": 1},
)

EXECUTION_RESULT: Final = ExecutionResult(
    id=EXECUTION_ID,
    created_at=LATER,
    capability_id=WRITE_NOTE,
    status=ExecutionStatus.FAILED,
    task_id=TASK_ID,
    step_id=STEP_ID,
    tool_name="workspace_notes",
    device_id=DEVICE_ID,
    decision_id=DECISION_ID,
    authorization_id=AUTHORIZATION_ID,
    output={"written": False},
    error=ERROR_METADATA,
    usage=PROVIDER_USAGE,
    duration_ms=2_400,
    metadata={"verified": False},
)

# Perception (M10.1): what this Mac looked like while M10.1 was written — a webcam present but
# never observable as in use, a microphone observed idle, and Screen Recording denied. The
# example of a milestone about missing permissions should show one missing.
SENSOR_STATUS: Final = SensorStatus(state=SensorState.AVAILABLE, cause=SensorCause.OBSERVED)

RAW_OBSERVATION: Final = RawObservation(
    camera_count=2,
    microphone_count=2,
    microphone_in_use=False,
    display_count=1,
    display_asleep=False,
    screen_locked=False,
    on_console=True,
    idle_seconds=0.2,
    camera_permission=0,
    microphone_permission=0,
    screen_recording_permission=False,
)

OBSERVATION: Final = Observation(
    observed_at=datetime(2026, 9, 8, 15, 0, tzinfo=UTC),
    microphone=SENSOR_STATUS,
    camera=SensorStatus(state=SensorState.AVAILABLE, cause=SensorCause.NOT_OBSERVABLE),
    permissions={
        SystemPermission.CAMERA: PermissionState.NOT_DETERMINED,
        SystemPermission.MICROPHONE: PermissionState.NOT_DETERMINED,
        SystemPermission.SCREEN_RECORDING: PermissionState.DENIED,
    },
    display_count=1,
    display_asleep=False,
    screen_locked=False,
    on_console=True,
    idle_seconds=0.2,
)

PERCEPTION_CHANGE: Final = PerceptionChange(
    field="microphone", before="AVAILABLE (OBSERVED)", after="ACTIVE (OBSERVED)"
)

EXAMPLES: Final[dict[type[BaseModel], BaseModel]] = {
    type(example): example
    for example in (
        ELA_ACTOR,
        DEVICE_CAPABILITY,
        PROVIDER_USAGE,
        ERROR_METADATA,
        ELA_IDENTITY,
        USER_INTENT,
        TASK_STEP,
        TASK_PLAN,
        TASK,
        TASK_EVENT,
        DEVICE,
        CAPABILITY_SPEC,
        PERMISSION_DECISION,
        APPROVAL,
        SINGLE_USE_AUTHORIZATION,
        AUDIT_EVENT,
        MODEL_ROUTE,
        PROVIDER_REQUEST,
        PROVIDER_RESULT,
        EXECUTION_RESULT,
        SENSOR_STATUS,
        RAW_OBSERVATION,
        OBSERVATION,
        PERCEPTION_CHANGE,
    )
}
"""One example per model, keyed by class: the parametrisation used by most tests."""
