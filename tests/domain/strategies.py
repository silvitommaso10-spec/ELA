"""Hypothesis strategies, one per domain model, for the property tests.

Kept next to ``examples.py``: the examples say what an entity looks like, the strategies say what
it may look like. ``test_spec_coverage.py`` fails if a model has neither.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

from hypothesis import strategies as st
from pydantic import BaseModel

from ela import domain
from ela.domain import (
    Actor,
    ActorKind,
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    Authorization,
    CapabilityId,
    CapabilitySpec,
    ContextActivity,
    ContextApproval,
    ContextDeadline,
    ContextDeadlines,
    ContextDevice,
    ContextEvent,
    ContextQuestion,
    ContextQuestionStatus,
    ContextRecent,
    ContextSnapshot,
    ContextSource,
    ContextTask,
    ContextWork,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceStatus,
    ELAIdentity,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    IntentChannel,
    ModelRoute,
    NetworkKind,
    Observation,
    OperatingSystem,
    PerceptionChange,
    PerformanceClass,
    PermissionDecision,
    PermissionOutcome,
    PermissionState,
    PowerSource,
    PrivacyLevel,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
    RawCapture,
    RawHeardSegment,
    RawHeardToken,
    RawObservation,
    RawRecognition,
    RawSpeech,
    RawTextLine,
    RawTranscript,
    RiskLevel,
    SensorCause,
    SensorState,
    SensorStatus,
    SystemPermission,
    Task,
    TaskEvent,
    TaskEventType,
    TaskPlan,
    TaskState,
    TaskStep,
    UserIntent,
)

uuids = st.uuids(version=4)
texts = st.text(max_size=24)
utc_datetimes = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(UTC),
)

_segments = st.from_regex(r"\A[a-z][a-z0-9_]{0,7}\Z")
capability_ids = st.tuples(_segments, _segments).map(lambda parts: CapabilityId(".".join(parts)))
device_capability_names = st.one_of(
    _segments.map(DeviceCapabilityName),
    st.tuples(_segments, _segments).map(lambda parts: DeviceCapabilityName(".".join(parts))),
)

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**9), max_value=10**9),
    st.floats(allow_nan=False, allow_infinity=False, width=32),
    texts,
)
json_values = st.recursive(
    _json_scalars,
    lambda children: st.lists(children, max_size=3) | st.dictionaries(texts, children, max_size=3),
    max_leaves=4,
)
json_mappings = st.dictionaries(texts, json_values, max_size=3)

decimals = st.decimals(
    min_value=0, max_value=10**6, places=6, allow_nan=False, allow_infinity=False
)
counts = st.integers(min_value=0, max_value=10**6)


def _optional[T](strategy: st.SearchStrategy[T]) -> st.SearchStrategy[T | None]:
    return st.none() | strategy


actors = st.builds(
    Actor,
    kind=st.sampled_from(ActorKind),
    id=st.text(min_size=1, max_size=24),
)

device_capabilities = st.builds(
    DeviceCapability,
    name=device_capability_names,
    available=st.booleans(),
    attributes=json_mappings,
)

provider_usages = st.builds(
    ProviderUsage,
    input_tokens=counts,
    output_tokens=counts,
    cached_input_tokens=_optional(counts),
    cost=_optional(decimals),
    currency=_optional(texts),
    latency_ms=_optional(counts),
)

error_metadata = st.builds(
    ErrorMetadata,
    code=texts,
    message=texts,
    cause=_optional(texts),
    tool_name=_optional(texts),
    model=_optional(texts),
    device_id=_optional(uuids),
    attempted_fix=_optional(texts),
    successful_fix=_optional(texts),
    retryable=st.booleans(),
    details=json_mappings,
)

ela_identities = st.builds(
    ELAIdentity,
    id=uuids,
    created_at=utc_datetimes,
    name=texts,
    version=texts,
    owner=texts,
    metadata=json_mappings,
)

user_intents = st.builds(
    UserIntent,
    id=uuids,
    created_at=utc_datetimes,
    text=texts,
    channel=st.sampled_from(IntentChannel),
    device_id=_optional(uuids),
    metadata=json_mappings,
)

task_steps = st.builds(
    TaskStep,
    id=uuids,
    created_at=utc_datetimes,
    goal=texts,
    required_capabilities=st.lists(capability_ids, max_size=3).map(tuple),
    preferred_device_traits=st.lists(device_capability_names, max_size=3).map(tuple),
    dependencies=st.lists(uuids, max_size=3).map(tuple),
    risk=st.sampled_from(RiskLevel),
    expected_result=texts,
    success_conditions=st.lists(texts, max_size=3).map(tuple),
    requires_authorization=st.booleans(),
)

task_plans = st.builds(
    TaskPlan,
    id=uuids,
    created_at=utc_datetimes,
    task_id=uuids,
    goal=texts,
    steps=st.lists(task_steps, max_size=3).map(tuple),
    metadata=json_mappings,
)

tasks = st.builds(
    Task,
    id=uuids,
    created_at=utc_datetimes,
    goal=texts,
    state=st.sampled_from(TaskState),
    intent_id=_optional(uuids),
    plan_id=_optional(uuids),
    parent_id=_optional(uuids),
    deadline=_optional(utc_datetimes),
    metadata=json_mappings,
)

task_events = st.builds(
    TaskEvent,
    id=uuids,
    created_at=utc_datetimes,
    task_id=uuids,
    event_type=st.sampled_from(TaskEventType),
    step_id=_optional(uuids),
    previous_state=_optional(st.sampled_from(TaskState)),
    new_state=_optional(st.sampled_from(TaskState)),
    message=texts,
    metadata=json_mappings,
)

devices = st.builds(
    Device,
    id=uuids,
    created_at=utc_datetimes,
    name=texts,
    os=st.sampled_from(OperatingSystem),
    availability=st.sampled_from(DeviceAvailability),
    status=st.sampled_from(DeviceStatus),
    capabilities=st.lists(device_capabilities, max_size=3).map(tuple),
    available_tools=st.lists(texts, max_size=3).map(tuple),
    performance=st.sampled_from(PerformanceClass),
    network=st.sampled_from(NetworkKind),
    power_source=st.sampled_from(PowerSource),
    privacy=st.sampled_from(PrivacyLevel),
    current_workload=_optional(st.floats(min_value=0.0, max_value=1.0, width=32)),
    last_seen_at=_optional(utc_datetimes),
    metadata=json_mappings,
)

capability_specs = st.builds(
    CapabilitySpec,
    id=capability_ids,
    created_at=utc_datetimes,
    description=texts,
    risk=st.sampled_from(RiskLevel),
    input_schema=json_mappings,
    scope=st.lists(texts, max_size=3).map(tuple),
    scoped_arguments=st.lists(texts, max_size=3).map(tuple),
    requires_authorization=st.booleans(),
    metadata=json_mappings,
)

permission_decisions = st.builds(
    PermissionDecision,
    id=uuids,
    created_at=utc_datetimes,
    capability_id=capability_ids,
    outcome=st.sampled_from(PermissionOutcome),
    risk=st.sampled_from(RiskLevel),
    reason=texts,
    task_id=_optional(uuids),
    step_id=_optional(uuids),
    authorization_id=_optional(uuids),
    approval_id=_optional(uuids),
    expires_at=_optional(utc_datetimes),
    metadata=json_mappings,
)

approvals = st.builds(
    Approval,
    id=uuids,
    created_at=utc_datetimes,
    task_id=uuids,
    step_id=uuids,
    capability_id=capability_ids,
    targets=st.lists(texts, max_size=3).map(tuple),
    prompt=texts,
    status=st.sampled_from(ApprovalStatus),
    decision_id=_optional(uuids),
    responded_at=_optional(utc_datetimes),
    responded_by=_optional(texts),
    expires_at=_optional(utc_datetimes),
    metadata=json_mappings,
)

policy_authorizations = st.builds(
    Authorization,
    id=uuids,
    created_at=utc_datetimes,
    capability_id=capability_ids,
    scope=st.lists(texts, max_size=3).map(tuple),
    granted_by=st.text(min_size=1, max_size=24),
    approval_id=st.none(),
    task_id=_optional(uuids),
    step_id=_optional(uuids),
    expires_at=_optional(utc_datetimes),
    max_uses=_optional(st.integers(min_value=1, max_value=100)),
    metadata=json_mappings,
)
"""A grant from a standing policy (§59): no approval, any binding, any use limit."""

approval_authorizations = st.builds(
    Authorization,
    id=uuids,
    created_at=utc_datetimes,
    capability_id=capability_ids,
    scope=st.lists(texts, max_size=3).map(tuple),
    granted_by=st.text(min_size=1, max_size=24),
    approval_id=uuids,
    task_id=uuids,
    step_id=uuids,
    expires_at=_optional(utc_datetimes),
    max_uses=st.just(1),
    metadata=json_mappings,
)
"""A grant born from an approval (§30): single use, bound to a task and a step (ADR 0012 §1)."""

authorizations = st.one_of(policy_authorizations, approval_authorizations)

audit_events = st.builds(
    AuditEvent,
    id=uuids,
    created_at=utc_datetimes,
    event_type=st.sampled_from(AuditEventType),
    actor=actors,
    summary=texts,
    task_id=_optional(uuids),
    step_id=_optional(uuids),
    capability_id=_optional(capability_ids),
    decision_id=_optional(uuids),
    authorization_id=_optional(uuids),
    device_id=_optional(uuids),
    tool_name=_optional(texts),
    usage=_optional(provider_usages),
    error=_optional(error_metadata),
    payload=json_mappings,
)

model_routes = st.builds(
    ModelRoute,
    task_type=_optional(texts),
    provider=texts,
    profile=texts,
    skipped=st.tuples(),
)

provider_requests = st.builds(
    ProviderRequest,
    id=uuids,
    created_at=utc_datetimes,
    purpose=texts,
    input=texts,
    instructions=_optional(texts),
    task_id=_optional(uuids),
    model_hint=_optional(texts),
    parameters=json_mappings,
    metadata=json_mappings,
)

provider_results = st.builds(
    ProviderResult,
    id=uuids,
    created_at=utc_datetimes,
    request_id=uuids,
    provider=texts,
    model=texts,
    output=texts,
    usage=provider_usages,
    finish_reason=_optional(texts),
    error=_optional(error_metadata),
    metadata=json_mappings,
)

execution_results = st.builds(
    ExecutionResult,
    id=uuids,
    created_at=utc_datetimes,
    capability_id=capability_ids,
    status=st.sampled_from(ExecutionStatus),
    task_id=_optional(uuids),
    step_id=_optional(uuids),
    tool_name=_optional(texts),
    device_id=_optional(uuids),
    decision_id=_optional(uuids),
    authorization_id=_optional(uuids),
    output=json_mappings,
    error=_optional(error_metadata),
    duration_ms=_optional(counts),
    metadata=json_mappings,
)

sensor_statuses = st.builds(
    SensorStatus, state=st.sampled_from(SensorState), cause=st.sampled_from(SensorCause)
)

_counts = _optional(st.integers(min_value=0, max_value=8))
_flags = _optional(st.booleans())

raw_observations = st.builds(
    RawObservation,
    camera_count=_counts,
    microphone_count=_counts,
    microphone_in_use=_flags,
    display_count=_counts,
    display_asleep=_flags,
    screen_locked=_flags,
    on_console=_flags,
    idle_seconds=_optional(st.floats(min_value=0, max_value=1e6, allow_nan=False)),
    camera_permission=_optional(st.integers(min_value=-2, max_value=9)),
    microphone_permission=_optional(st.integers(min_value=-2, max_value=9)),
    screen_recording_permission=_flags,
)
"""The permission integers deliberately range outside 0-3: a value this version does not
understand must map to ``NOT_OBSERVABLE`` and never to ``GRANTED`` (§33)."""

raw_captures = st.builds(
    RawCapture,
    exit_code=_optional(st.integers(min_value=-8, max_value=8)),
    timed_out=st.booleans(),
)
"""Negative exit codes are generated on purpose: a child killed by a signal reports one, and
:data:`~ela.infrastructure.machine.darwin.TIMED_OUT` is itself ``-1``."""

raw_speeches = st.builds(
    RawSpeech,
    exit_code=_optional(st.integers(min_value=-8, max_value=8)),
    timed_out=st.booleans(),
    spoken_seconds=_optional(st.floats(min_value=0, max_value=120, allow_nan=False)),
)
"""Zero seconds is generated on purpose: it is what a helper that never spoke reports, and it is
the case the verifier's floor exists to catch."""

raw_heard_tokens = st.builds(
    RawHeardToken,
    text=st.text(max_size=24),
    probability=st.floats(min_value=0, max_value=1, allow_nan=False),
)
"""A probability of zero is generated: nothing is filtered on it, so nothing may assume a floor."""

raw_heard_segments = st.builds(
    RawHeardSegment,
    text=st.text(max_size=120),
    start_ms=st.integers(min_value=0, max_value=60_000),
    end_ms=st.integers(min_value=0, max_value=60_000),
    tokens=st.tuples(),
)

raw_transcripts = st.builds(
    RawTranscript,
    exit_code=_optional(st.integers(min_value=-8, max_value=8)),
    timed_out=st.booleans(),
    recorded_seconds=_optional(st.floats(min_value=0, max_value=60, allow_nan=False)),
    peak=_optional(st.integers(min_value=0, max_value=32767)),
    segments=st.tuples(),
)
"""A peak of zero is generated on purpose, and it is the case the whole milestone turns on: it is
what a refused microphone produces, and what must never reach a transcriber."""

raw_text_lines = st.builds(
    RawTextLine,
    text=st.text(max_size=120),
    confidence=st.floats(min_value=0, max_value=1, allow_nan=False),
)
"""Empty text is generated: a recognised region with nothing readable in it is a real answer."""

raw_recognitions = st.builds(
    RawRecognition,
    exit_code=_optional(st.integers(min_value=-8, max_value=8)),
    killed=st.booleans(),
    lines=st.lists(raw_text_lines, max_size=4).map(tuple),
    unsupported_languages=st.lists(st.text(min_size=1, max_size=8), max_size=3).map(tuple),
)
"""Both empty ``lines`` and non-empty ``unsupported_languages`` are generated, including
together: that pair is exactly the ambiguity the tool has to split, so it must be reachable."""

observations = st.builds(
    Observation,
    observed_at=utc_datetimes,
    microphone=sensor_statuses,
    camera=sensor_statuses,
    permissions=st.fixed_dictionaries(
        dict.fromkeys(SystemPermission, st.sampled_from(PermissionState))
    ),
    display_count=_counts,
    display_asleep=_flags,
    screen_locked=_flags,
    on_console=_flags,
    idle_seconds=_optional(st.floats(min_value=0, max_value=1e6, allow_nan=False)),
)

perception_changes = st.builds(PerceptionChange, field=texts, before=texts, after=texts)

# --- Context (M10.4, ADR 0032) -------------------------------------------------------------

context_activities = st.builds(
    ContextActivity,
    observed_at=utc_datetimes,
    microphone=sensor_statuses,
    camera=sensor_statuses,
    permissions=st.dictionaries(
        st.sampled_from(SystemPermission), st.sampled_from(PermissionState)
    ),
    display_count=_optional(st.integers(min_value=0, max_value=8)),
    display_asleep=_optional(st.booleans()),
    screen_locked=_optional(st.booleans()),
    on_console=_optional(st.booleans()),
    idle_seconds=_optional(st.floats(min_value=0, max_value=86400, allow_nan=False)),
    running_bundle_ids=_optional(st.lists(texts, max_size=4).map(tuple)),
    frontmost_bundle_id=_optional(texts),
    window_count=_optional(st.integers(min_value=0, max_value=64)),
)

context_devices = st.builds(
    ContextDevice,
    device_id=uuids,
    name=texts,
    os=st.sampled_from(OperatingSystem),
    available=st.booleans(),
    status=st.sampled_from(DeviceStatus),
    is_local=st.booleans(),
    last_seen_at=_optional(utc_datetimes),
)

context_tasks_ = st.builds(
    ContextTask,
    task_id=uuids,
    goal=texts,
    state=st.sampled_from(TaskState),
    deadline=_optional(utc_datetimes),
    current_step_id=_optional(uuids),
    current_step_goal=_optional(texts),
)

context_approvals = st.builds(
    ContextApproval,
    approval_id=uuids,
    task_id=uuids,
    capability_id=capability_ids,
    expires_at=_optional(utc_datetimes),
)


@st.composite
def _context_works(draw: st.DrawFn) -> ContextWork:
    """``shown`` is never drawn: it is what is shown, and ``total`` is never below it.

    Generating the three independently would generate mostly invalid work — the model refuses a
    ``shown`` that is not the length of ``tasks`` — so the strategy builds the relationship the
    model states rather than fighting it.
    """
    drawn = draw(st.lists(context_tasks_, max_size=3))
    return ContextWork(
        tasks=tuple(drawn),
        shown=len(drawn),
        total=len(drawn) + draw(st.integers(min_value=0, max_value=20)),
        states=draw(st.dictionaries(st.sampled_from(TaskState), st.integers(min_value=1))),
        pending_approvals=tuple(draw(st.lists(context_approvals, max_size=2))),
    )


context_works = _context_works()

context_deadline_rows = st.builds(
    ContextDeadline,
    task_id=uuids,
    goal=texts,
    state=st.sampled_from(TaskState),
    deadline=utc_datetimes,
)


@st.composite
def _context_deadlines(draw: st.DrawFn) -> ContextDeadlines:
    drawn = draw(st.lists(context_deadline_rows, max_size=3))
    return ContextDeadlines(
        deadlines=tuple(drawn),
        shown=len(drawn),
        total=len(drawn) + draw(st.integers(min_value=0, max_value=20)),
    )


context_deadlines = _context_deadlines()

context_events = st.builds(
    ContextEvent,
    task_id=uuids,
    event_type=st.sampled_from(TaskEventType),
    at=utc_datetimes,
    previous_state=_optional(st.sampled_from(TaskState)),
    new_state=_optional(st.sampled_from(TaskState)),
)

context_recents = st.builds(
    ContextRecent,
    since=utc_datetimes,
    changes=st.lists(perception_changes, max_size=3).map(tuple),
    events=st.lists(context_events, max_size=3).map(tuple),
)

context_question_statuses = st.builds(
    ContextQuestionStatus,
    question=st.sampled_from(ContextQuestion),
    answered_by=st.lists(st.sampled_from(ContextSource), max_size=3, unique=True).map(tuple),
    missing=st.lists(st.sampled_from(ContextSource), max_size=3, unique=True).map(tuple),
)

context_snapshots = st.builds(
    ContextSnapshot,
    at=utc_datetimes,
    activity=context_activities,
    device=st.none() | context_devices,
    work=context_works,
    deadlines=context_deadlines,
    recent=context_recents,
    questions=st.lists(context_question_statuses, max_size=3).map(tuple),
)

MODEL_STRATEGIES: Final[dict[type[BaseModel], st.SearchStrategy[BaseModel]]] = {
    domain.Actor: actors,
    domain.DeviceCapability: device_capabilities,
    domain.ProviderUsage: provider_usages,
    domain.ErrorMetadata: error_metadata,
    domain.ELAIdentity: ela_identities,
    domain.UserIntent: user_intents,
    domain.TaskStep: task_steps,
    domain.TaskPlan: task_plans,
    domain.Task: tasks,
    domain.TaskEvent: task_events,
    domain.Device: devices,
    domain.CapabilitySpec: capability_specs,
    domain.PermissionDecision: permission_decisions,
    domain.Approval: approvals,
    domain.Authorization: authorizations,
    domain.AuditEvent: audit_events,
    domain.ModelRoute: model_routes,
    domain.ProviderRequest: provider_requests,
    domain.ProviderResult: provider_results,
    domain.ExecutionResult: execution_results,
    domain.SensorStatus: sensor_statuses,
    domain.RawObservation: raw_observations,
    domain.RawCapture: raw_captures,
    domain.RawHeardSegment: raw_heard_segments,
    domain.RawHeardToken: raw_heard_tokens,
    domain.RawSpeech: raw_speeches,
    domain.RawTranscript: raw_transcripts,
    domain.RawRecognition: raw_recognitions,
    domain.RawTextLine: raw_text_lines,
    domain.Observation: observations,
    domain.PerceptionChange: perception_changes,
    domain.ContextActivity: context_activities,
    domain.ContextDevice: context_devices,
    domain.ContextTask: context_tasks_,
    domain.ContextApproval: context_approvals,
    domain.ContextWork: context_works,
    domain.ContextDeadline: context_deadline_rows,
    domain.ContextDeadlines: context_deadlines,
    domain.ContextEvent: context_events,
    domain.ContextRecent: context_recents,
    domain.ContextQuestionStatus: context_question_statuses,
    domain.ContextSnapshot: context_snapshots,
}
"""One strategy per model, keyed by class."""
