"""What a context test needs: the four ports, the clock, and a perception view to hand over."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ela.context import ContextCore, ContextSettings
from ela.devices import DeviceRegistry
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import (
    Observation,
    PerceptionChange,
    SensorCause,
    TaskState,
)
from ela.perception import PerceptionView, unobserved
from ela.tasks.engine import LIVE_STATES
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuditLog,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTaskRepository,
)

NOW = datetime(2026, 9, 8, 15, 0, tzinfo=UTC)
EARLIER = NOW - timedelta(seconds=2)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def repository() -> FakeTaskRepository:
    return FakeTaskRepository()


@pytest.fixture
def approvals() -> FakeApprovalStore:
    return FakeApprovalStore()


@pytest.fixture
def registry() -> FakeDeviceRegistry:
    return FakeDeviceRegistry()


@pytest.fixture
def devices(registry: FakeDeviceRegistry, clock: FakeClock) -> DeviceRegistry:
    return DeviceRegistry(
        registry, clock, FakeAuditLog(), FakeIdGenerator(), heartbeat_ttl=timedelta(minutes=1)
    )


@pytest.fixture
def settings() -> ContextSettings:
    return ContextSettings(context_tasks_limit=2, context_deadlines_limit=2, context_events_limit=3)


@pytest.fixture
def core(
    repository: FakeTaskRepository,
    approvals: FakeApprovalStore,
    devices: DeviceRegistry,
    clock: FakeClock,
    settings: ContextSettings,
) -> ContextCore:
    return ContextCore(
        repository=repository,
        approvals=approvals,
        devices=devices,
        clock=clock,
        settings=settings,
        live_states=LIVE_STATES,
        local_device_id=LOCAL_DEVICE_ID,
    )


@pytest.fixture
def observation() -> Observation:
    return unobserved(SensorCause.NOT_LOOKING, at=NOW)


@pytest.fixture
def view(observation: Observation) -> PerceptionView:
    """A view with a horizon and one change: the shape ``/context`` really hands over."""
    return PerceptionView(
        observation,
        (PerceptionChange(field="frontmost_bundle_id", before="None", after="com.apple.mail"),),
        EARLIER,
    )


LIVE = TaskState.QUEUED
