"""The orchestrator with its I/O: the registry it reads, the tools it resolves, the log it writes.

Three things are being checked here that the pure tests cannot see: that availability comes from
:class:`~ela.devices.DeviceRegistry` and not from the stored row (ADR 0016 §3), that a capability
is matched to a node through the tool that implements it (ADR 0017 §3), and that every call —
choice or wait — leaves exactly one event in the audit trail (§32; ADR 0017 §6).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

import pytest

from ela.devices import (
    AVAILABLE,
    ORCHESTRATOR_ACTOR,
    DeviceOrchestrator,
    DeviceRegistry,
    Refusal,
)
from ela.domain import (
    ActorKind,
    AuditEventType,
    CapabilityId,
    Device,
    DeviceAvailability,
    PerformanceClass,
    PrivacyLevel,
    RiskLevel,
)
from ela.testing.fakes import (
    FakeAuditLog,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeTool,
    FakeToolRegistry,
)
from tests.devices.nodes import node, step, trait
from tests.domain.examples import LATER, MUCH_LATER, TASK_ID

TTL = timedelta(seconds=60)
WRITE_NOTE = CapabilityId("workspace.write_note")
COMPLETE = CapabilityId("model.complete")
GPU = "gpu.cuda"
NOTES = "workspace_notes"


@pytest.fixture
def clock() -> FakeClock:
    """An hour after the ``last_seen_at`` of the example nodes: their heartbeat is long gone."""
    return FakeClock(MUCH_LATER)


@pytest.fixture
def audit() -> FakeAuditLog:
    return FakeAuditLog()


@pytest.fixture
def port() -> FakeDeviceRegistry:
    return FakeDeviceRegistry()


@pytest.fixture
def tools(clock: FakeClock) -> FakeToolRegistry:
    """One tool for ``workspace.write_note``, named as ``available_tools`` names it."""
    return FakeToolRegistry(
        [FakeTool(WRITE_NOTE, clock, FakeIdGenerator(), name=NOTES)],
    )


@pytest.fixture
def orchestrator(
    port: FakeDeviceRegistry, tools: FakeToolRegistry, audit: FakeAuditLog, clock: FakeClock
) -> DeviceOrchestrator:
    registry = DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=TTL)
    return DeviceOrchestrator(registry, tools, audit, FakeIdGenerator(), clock)


async def register(port: FakeDeviceRegistry, nodes: Iterable[Device]) -> None:
    for device in nodes:
        await port.register(device)


def beating(device: Device, clock: FakeClock) -> Device:
    """``device`` as a node that has just reported: the row a fresh heartbeat leaves behind."""
    return device.model_copy(update={"last_seen_at": clock.now()})


# ----------------------------------------------------------------------------------------
# The registry, not the row (ADR 0016 §3, ADR 0017 §7)
# ----------------------------------------------------------------------------------------


async def test_the_stored_row_does_not_decide(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    """The row says ONLINE and the heartbeat is an hour old: the node is not used.

    The behavioural twin of architecture rules 20 and 21. An orchestrator that read the column —
    it is indexed and one ``SELECT`` away — would send work to a machine that stopped answering.
    """
    stale = node("stale", availability=DeviceAvailability.ONLINE)
    assert stale.availability is AVAILABLE  # what the row claims
    await register(port, [stale])

    placement = await orchestrator.place(step(), task_id=TASK_ID)

    assert placement.waits
    assert placement.scores[0].refusals == (Refusal.UNAVAILABLE,)


async def test_a_node_that_reported_within_the_ttl_is_used(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    fresh = beating(node("local", availability=DeviceAvailability.UNKNOWN), clock)
    await register(port, [fresh])

    placement = await orchestrator.place(step(), task_id=TASK_ID)

    assert placement.device is not None
    assert placement.device.id == fresh.id


# ----------------------------------------------------------------------------------------
# Capabilities resolved into tools (ADR 0017 §3)
# ----------------------------------------------------------------------------------------


async def test_a_required_capability_becomes_the_name_of_the_tool_that_implements_it(
    orchestrator: DeviceOrchestrator,
) -> None:
    needed = orchestrator.requirements(step(capabilities=(WRITE_NOTE,)))
    assert needed.tools == {NOTES}
    assert needed.unresolved == ()
    assert needed.max_privacy is PrivacyLevel.LOCAL_ONLY


async def test_a_capability_no_tool_implements_is_unresolved_not_an_error(
    orchestrator: DeviceOrchestrator,
) -> None:
    needed = orchestrator.requirements(step(capabilities=(COMPLETE,)))
    assert needed.tools == frozenset()
    assert needed.unresolved == (COMPLETE,)


async def test_a_step_whose_capability_nobody_implements_waits(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    await register(port, [beating(node("local", tools=(NOTES,)), clock)])

    placement = await orchestrator.place(step(capabilities=(COMPLETE,)), task_id=TASK_ID)

    assert placement.waits
    assert placement.scores[0].refusals == (Refusal.UNKNOWN_CAPABILITY,)


async def test_the_node_without_the_tool_loses_to_the_node_that_has_it(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    bare = beating(node("bare", performance=PerformanceClass.HIGH), clock)
    equipped = beating(node("equipped", tools=(NOTES,)), clock)
    await register(port, [bare, equipped])

    placement = await orchestrator.place(step(capabilities=(WRITE_NOTE,)), task_id=TASK_ID)

    assert placement.device is not None
    assert placement.device.id == equipped.id


# ----------------------------------------------------------------------------------------
# The audit trail (ADR 0017 §6)
# ----------------------------------------------------------------------------------------


async def test_a_choice_is_audited_with_every_score(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    cloud = beating(node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED), clock)
    local = beating(node("local", tools=(NOTES,), traits=[trait(GPU)]), clock)
    await register(port, [cloud, local])

    placement = await orchestrator.place(
        step(capabilities=(WRITE_NOTE,), traits=(GPU,)), task_id=TASK_ID
    )

    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_SELECTED
    assert event.actor == ORCHESTRATOR_ACTOR
    assert event.actor.kind is ActorKind.SYSTEM
    assert event.task_id == TASK_ID
    assert event.device_id == local.id
    assert placement.device is not None
    assert event.payload["required_tools"] == (NOTES,)
    assert event.payload["preferred_traits"] == (GPU,)
    assert event.payload["risk"] == RiskLevel.SAFE.value
    assert event.payload["max_privacy"] == PrivacyLevel.LOCAL_ONLY.value
    candidates = event.payload["candidates"]
    assert isinstance(candidates, tuple)
    assert [candidate["device_id"] for candidate in candidates] == [str(cloud.id), str(local.id)]
    assert candidates[0]["refusals"] == (Refusal.PRIVACY.value, Refusal.MISSING_TOOL.value)
    assert candidates[1]["refusals"] == ()
    assert candidates[1]["components"]["traits"] == 40


async def test_a_wait_is_audited_as_device_unavailable(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, audit: FakeAuditLog
) -> None:
    await register(port, [node("stale")])

    placement = await orchestrator.place(step(), task_id=TASK_ID)

    (event,) = await audit.read()
    assert placement.waits
    assert event.event_type is AuditEventType.DEVICE_UNAVAILABLE
    assert event.device_id is None
    assert "no eligible node" in event.summary


async def test_an_empty_registry_is_audited_too(
    orchestrator: DeviceOrchestrator, audit: FakeAuditLog
) -> None:
    """Nothing to choose from is still a decision ELA took and must be able to explain."""
    await orchestrator.place(step(), task_id=TASK_ID)

    (event,) = await audit.read()
    assert event.event_type is AuditEventType.DEVICE_UNAVAILABLE
    assert event.payload["candidates"] == ()


async def test_one_call_writes_exactly_one_event(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    await register(port, [beating(node("local"), clock)])

    await orchestrator.place(step(), task_id=TASK_ID)
    await orchestrator.place(step(goal="un altro step"), task_id=TASK_ID)

    assert len(await audit.read()) == 2


async def test_the_unresolved_capabilities_are_named_in_the_payload(
    orchestrator: DeviceOrchestrator, audit: FakeAuditLog
) -> None:
    await orchestrator.place(step(capabilities=(COMPLETE,)), task_id=TASK_ID)

    (event,) = await audit.read()
    assert event.payload["unresolved_capabilities"] == (COMPLETE,)


async def test_a_caller_may_widen_the_privacy_it_tolerates(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    """The default is the most restrictive level; widening it is explicit and lands in the log."""
    cloud = beating(node("cloud", privacy=PrivacyLevel.CLOUD_ALLOWED), clock)
    await register(port, [cloud])

    placement = await orchestrator.place(
        step(), task_id=TASK_ID, max_privacy=PrivacyLevel.CLOUD_ALLOWED
    )

    (event,) = await audit.read()
    assert placement.device is not None
    assert placement.device.id == cloud.id
    assert event.payload["max_privacy"] == PrivacyLevel.CLOUD_ALLOWED.value


async def test_the_event_is_timed_by_the_clock_and_carries_the_step(
    orchestrator: DeviceOrchestrator, audit: FakeAuditLog, clock: FakeClock
) -> None:
    one = step()

    await orchestrator.place(one, task_id=TASK_ID)

    (event,) = await audit.read()
    assert event.created_at == clock.now()
    assert event.created_at != LATER
    assert event.step_id == one.id


async def test_a_revoked_node_is_a_candidate_with_its_reason(
    orchestrator: DeviceOrchestrator,
    port: FakeDeviceRegistry,
    audit: FakeAuditLog,
    clock: FakeClock,
) -> None:
    """D13: a revoked node is judged, not hidden — it is in ``DEVICE_SELECTED`` with ``REVOKED``,
    beside the node that won. Taking it out of the candidates before the judgement would make it
    vanish from the payload instead of appearing with its reason (ADR 0037 §12)."""
    gone = beating(node("gone", tools=(NOTES,), revoked_at=LATER), clock)
    local = beating(node("local", tools=(NOTES,)), clock)
    await register(port, [gone, local])

    placement = await orchestrator.place(step(capabilities=(WRITE_NOTE,)), task_id=TASK_ID)

    assert placement.device is not None and placement.device.id == local.id
    (event,) = await audit.read()
    candidates = event.payload["candidates"]
    assert isinstance(candidates, tuple)
    assert [candidate["device_id"] for candidate in candidates] == [str(gone.id), str(local.id)]
    assert candidates[0]["refusals"] == (Refusal.REVOKED.value,)


async def test_a_wait_counts_the_revoked_node_by_name(
    orchestrator: DeviceOrchestrator, port: FakeDeviceRegistry, clock: FakeClock
) -> None:
    await register(port, [beating(node("gone", tools=(NOTES,), revoked_at=LATER), clock)])

    placement = await orchestrator.place(step(capabilities=(WRITE_NOTE,)), task_id=TASK_ID)

    assert placement.waits
    assert Refusal.REVOKED.value in placement.reason
