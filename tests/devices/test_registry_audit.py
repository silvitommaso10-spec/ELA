"""What the registry writes down when a node arrives or changes (§32; M6.1b, ADR 0035 §3).

The debt ADR 0016 §6 declared on 2026-09-07 and left to "the milestone of remote nodes": the
registration of a device **must** become an audit event the moment ``register``/``update`` stop
being called only by the Core on its own machine. An automatic write at start-up is that moment,
and §32 gives the reason it matters — whoever investigates an action has to be able to reconstruct
which nodes could do what *then*.

Three things are checked here that ``test_registry.py`` cannot see: that the two events are two
types and not one with a flag, that the summary carries the whole difference and not a count, and
that a start-up which changes nothing writes nothing at all. The heartbeat stays out of the log,
as ADR 0016 §6 decided and this milestone confirms: a sign of life is not an act.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from ela.devices import LOCAL_DEVICE_ID, REGISTRY_ACTOR, DeviceRegistry, local_device
from ela.domain import (
    ActorKind,
    AuditEvent,
    AuditEventType,
    DeviceCapability,
    DeviceCapabilityName,
    DeviceStatus,
)
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeDeviceRegistry, FakeIdGenerator
from tests.domain.examples import DEVICE, MUCH_LATER

TTL = timedelta(seconds=60)

BEFORE = ("core-echo", "workspace-notes")
AFTER = ("core-echo", "voice-speak-online")
"""One name gained and one lost in the same start-up: the summary must say both."""


@pytest.fixture
def audit() -> FakeAuditLog:
    return FakeAuditLog()


@pytest.fixture
def port() -> FakeDeviceRegistry:
    return FakeDeviceRegistry()


@pytest.fixture
def registry(port: FakeDeviceRegistry, audit: FakeAuditLog) -> DeviceRegistry:
    return DeviceRegistry(port, FakeClock(MUCH_LATER), audit, FakeIdGenerator(), heartbeat_ttl=TTL)


async def written(audit: FakeAuditLog) -> tuple[AuditEvent, ...]:
    return await audit.read()


# ----------------------------------------------------------------------------------------
# The two events
# ----------------------------------------------------------------------------------------


async def test_a_node_ela_did_not_know_is_a_registration(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    (event,) = await written(audit)
    assert event.event_type is AuditEventType.DEVICE_REGISTERED
    assert event.device_id == LOCAL_DEVICE_ID
    assert event.actor == REGISTRY_ACTOR and event.actor.kind is ActorKind.SYSTEM
    assert "core-echo, workspace-notes" in event.summary
    assert event.payload["tools_added"] == BEFORE


async def test_a_node_ela_already_used_that_changed_is_a_refresh(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """A type of its own, not a payload of the registration (ADR 0008's argument, ADR 0035 §3)."""
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    await registry.ensure_local(system="Darwin", available_tools=AFTER)

    kinds = [event.event_type for event in await written(audit)]
    assert kinds == [AuditEventType.DEVICE_REGISTERED, AuditEventType.DEVICE_REFRESHED]


async def test_the_summary_names_what_was_gained_and_what_was_lost(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """ "One tool more" is not a diagnosis: with seven of them, *which* one is the whole of it."""
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    await registry.ensure_local(system="Darwin", available_tools=AFTER)

    event = (await written(audit))[-1]
    assert "+voice-speak-online" in event.summary
    assert "-workspace-notes" in event.summary
    assert event.payload["tools_added"] == ("voice-speak-online",)
    assert event.payload["tools_removed"] == ("workspace-notes",)
    assert event.payload["changed"] == ("available_tools",)


async def test_the_summary_of_a_field_that_is_not_the_tools_says_before_and_after(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """The database copied onto another machine, in the log: ``os MACOS -> LINUX``."""
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    await registry.ensure_local(system="Linux", available_tools=BEFORE)

    event = (await written(audit))[-1]
    assert "os MACOS -> LINUX" in event.summary
    assert event.payload["changed"] == ("os",)
    assert event.payload["tools_added"] == () and event.payload["tools_removed"] == ()


async def test_a_start_up_that_changes_nothing_writes_nothing(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """The oscillation of two ELAs on one database is readable *because* silence is silence."""
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    await registry.ensure_local(system="Darwin", available_tools=BEFORE)
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    assert len(await written(audit)) == 1


# ----------------------------------------------------------------------------------------
# What stays out of the log
# ----------------------------------------------------------------------------------------


async def test_a_heartbeat_is_not_an_event(registry: DeviceRegistry, audit: FakeAuditLog) -> None:
    """ADR 0016 §6, confirmed: a sign of life has no actor to answer for it (M6.1b, out of scope).

    Sixty seconds apart per node, it would fill the hash chain of §32 with rows that say nothing,
    and its absence is already visible in ``last_seen_at``.
    """
    await registry.ensure_local(system="Darwin", available_tools=BEFORE)
    before = len(await written(audit))

    await registry.heartbeat(LOCAL_DEVICE_ID, status=DeviceStatus.IDLE, current_workload=0.5)

    assert len(await written(audit)) == before


async def test_an_insert_that_was_refused_leaves_no_event(
    registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """The event comes after the port answered: a node that was not added did not enter anything."""
    await registry.register(DEVICE)
    written_once = len(await written(audit))

    with pytest.raises(Exception, match="already exists"):
        await registry.register(DEVICE)

    assert len(await written(audit)) == written_once


async def test_the_traits_of_a_row_are_reconciled_by_name(
    port: FakeDeviceRegistry, registry: DeviceRegistry, audit: FakeAuditLog
) -> None:
    """A declared field nobody declares in v0.1, and the summary still has to read like words.

    ``local_device`` claims no trait — detecting RAM or a GPU needs system libraries and ADR 0016
    refused to invent them — so this is the row of an ELA that once claimed one, meeting a
    process that claims none. The summary says which trait went, not that one did.
    """
    trait = DeviceCapability(name=DeviceCapabilityName("gpu.cuda"), available=True)
    await port.register(
        local_device(MUCH_LATER, system="Darwin").model_copy(
            update={"capabilities": (trait,), "available_tools": BEFORE}
        )
    )

    await registry.ensure_local(system="Darwin", available_tools=BEFORE)

    event = (await written(audit))[-1]
    assert "capabilities gpu.cuda -> none" in event.summary
    assert event.payload["changed"] == ("capabilities",)
