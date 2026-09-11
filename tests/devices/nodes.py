"""Nodes and steps for the Device Orchestrator tests (§16, §17; ADR 0017).

Every builder starts from the node that passes every filter and scores nothing — available,
``LOCAL_ONLY``, everything else ``UNKNOWN`` — so each test says only what it is about. Ids are a
UUIDv5 of the name, as ``local``'s is (ADR 0016 §4): a node called ``gpu`` is the same node in
every test, and the failure message says which one lost.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from uuid import uuid5

from ela.devices import AVAILABLE, DEVICE_NAMESPACE, Requirements
from ela.domain import (
    CapabilityId,
    Device,
    DeviceAvailability,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceId,
    DeviceStatus,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
    RiskLevel,
    StepId,
    TaskStep,
)
from tests.domain.examples import LATER, NOW


def device_id(name: str) -> DeviceId:
    return DeviceId(uuid5(DEVICE_NAMESPACE, name))


def trait(name: str, *, available: bool = True) -> DeviceCapability:
    return DeviceCapability(name=DeviceCapabilityName(name), available=available)


def node(
    name: str,
    *,
    availability: DeviceAvailability = AVAILABLE,
    privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    tools: tuple[str, ...] = (),
    traits: Iterable[DeviceCapability] = (),
    status: DeviceStatus = DeviceStatus.UNKNOWN,
    performance: PerformanceClass = PerformanceClass.UNKNOWN,
    network: NetworkKind = NetworkKind.UNKNOWN,
    power_source: PowerSource = PowerSource.UNKNOWN,
    workload: float | None = None,
    revoked_at: datetime | None = None,
) -> Device:
    """A node as :class:`~ela.devices.DeviceRegistry` would hand it over: availability judged."""
    return Device(
        id=device_id(name),
        created_at=NOW,
        name=name,
        os=OperatingSystem.MACOS,
        availability=availability,
        status=status,
        capabilities=tuple(traits),
        available_tools=tools,
        performance=performance,
        network=network,
        power_source=power_source,
        privacy=privacy,
        current_workload=workload,
        last_seen_at=LATER,
        revoked_at=revoked_at,
    )


def step(
    *,
    capabilities: tuple[str, ...] = (),
    traits: tuple[str, ...] = (),
    risk: RiskLevel = RiskLevel.SAFE,
    goal: str = "renderizzare il video",
) -> TaskStep:
    """A step of §13: capabilities and preferred traits, never a node."""
    return TaskStep(
        id=StepId(uuid5(DEVICE_NAMESPACE, goal)),
        created_at=NOW,
        goal=goal,
        required_capabilities=tuple(CapabilityId(name) for name in capabilities),
        preferred_device_traits=tuple(DeviceCapabilityName(name) for name in traits),
        risk=risk,
        expected_result="il video è renderizzato",
        requires_authorization=False,
    )


def needs(
    *,
    tools: Iterable[str] = (),
    traits: Iterable[str] = (),
    risk: RiskLevel = RiskLevel.SAFE,
    max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    unresolved: Iterable[str] = (),
) -> Requirements:
    """:class:`Requirements` as :meth:`DeviceOrchestrator.requirements` would have built them."""
    return Requirements(
        tools=frozenset(tools),
        traits=tuple(DeviceCapabilityName(name) for name in traits),
        risk=risk,
        max_privacy=max_privacy,
        unresolved=tuple(CapabilityId(name) for name in unresolved),
    )
