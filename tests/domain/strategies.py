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
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PermissionDecision,
    PermissionOutcome,
    PowerSource,
    PrivacyLevel,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
    RiskLevel,
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
    output=json_mappings,
    error=_optional(error_metadata),
    duration_ms=_optional(counts),
    metadata=json_mappings,
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
    domain.ProviderRequest: provider_requests,
    domain.ProviderResult: provider_results,
    domain.ExecutionResult: execution_results,
}
"""One strategy per model, keyed by class."""
