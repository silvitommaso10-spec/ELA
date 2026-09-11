"""``DeviceRegistry``: the heartbeat, its deadline, and what a reader is told (ADR 0016 §2–§3, §5).

The question §16 asks is "posso usare questo nodo adesso". The port cannot answer it — it returns
the row as stored — so every test here is about the difference between what is written and what
is read.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from ela.devices import (
    AVAILABLE,
    LOCAL_DEVICE_ID,
    UNAVAILABLE,
    DeviceRegistry,
    is_available,
)
from ela.domain import Device, DeviceId, DeviceStatus, OperatingSystem
from ela.ports import (
    DeviceRegistryPort,
    NotFoundError,
)
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeDeviceRegistry, FakeIdGenerator
from tests.devices.conftest import TTL
from tests.domain.examples import (
    DEVICE,
    MUCH_LATER,
)

OTHER_ID = DeviceId(UUID("00000000-0000-4000-8000-000000000301"))


class TickingClock:
    """A clock that moves one second every time it is read (port ``Clock``).

    Twenty concurrent heartbeats then carry twenty distinct instants, so the test can say which
    of them survived instead of comparing a value with itself.
    """

    def __init__(self, start: datetime = MUCH_LATER) -> None:
        self._now = start

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


# ----------------------------------------------------------------------------------------
# The deadline
# ----------------------------------------------------------------------------------------


async def test_heartbeat_makes_a_device_available(
    registry: DeviceRegistry, clock: FakeClock
) -> None:
    await registry.register(DEVICE)
    beaten = await registry.heartbeat(DEVICE.id)
    assert beaten.last_seen_at == clock.now()
    assert beaten.availability is AVAILABLE
    assert (await registry.get(DEVICE.id)).availability is AVAILABLE


async def test_an_expired_heartbeat_makes_it_unavailable(
    registry: DeviceRegistry, clock: FakeClock
) -> None:
    """The test §16 asks for: silence past the TTL is not availability."""
    await registry.register(DEVICE)
    await registry.heartbeat(DEVICE.id)
    clock.advance(TTL + timedelta(seconds=1))
    assert (await registry.get(DEVICE.id)).availability is UNAVAILABLE


async def test_the_deadline_is_closed(registry: DeviceRegistry, clock: FakeClock) -> None:
    """ADR 0005 §2-bis: at exactly ``last_seen_at + ttl`` the heartbeat has expired."""
    await registry.register(DEVICE)
    await registry.heartbeat(DEVICE.id)
    clock.advance(TTL - timedelta(seconds=1))
    assert (await registry.get(DEVICE.id)).availability is AVAILABLE
    clock.advance(timedelta(seconds=1))
    assert (await registry.get(DEVICE.id)).availability is UNAVAILABLE


async def test_a_device_never_seen_is_not_available(registry: DeviceRegistry) -> None:
    """Registering a node says it exists, not that it answers (§33)."""
    never_seen = DEVICE.model_copy(update={"last_seen_at": None})
    assert (await registry.register(never_seen)).availability is UNAVAILABLE
    assert (await registry.get(DEVICE.id)).availability is UNAVAILABLE


def test_is_available_reads_the_last_heartbeat_only() -> None:
    seen = DEVICE.model_copy(update={"last_seen_at": MUCH_LATER})
    assert is_available(seen, MUCH_LATER, TTL)
    assert is_available(seen, MUCH_LATER + TTL - timedelta(seconds=1), TTL)
    assert not is_available(seen, MUCH_LATER + TTL, TTL)
    assert not is_available(DEVICE.model_copy(update={"last_seen_at": None}), MUCH_LATER, TTL)


# ----------------------------------------------------------------------------------------
# What is stored is not what is read (ADR 0016 §3)
# ----------------------------------------------------------------------------------------


async def test_the_stored_row_is_not_what_a_reader_gets(
    registry: DeviceRegistry, port: DeviceRegistryPort
) -> None:
    """``DEVICE`` declares ``ONLINE`` and was last seen an hour ago: the row keeps the claim,
    the registry answers from the clock."""
    await registry.register(DEVICE)
    assert (await port.get(DEVICE.id)).availability is AVAILABLE  # the column, untouched
    assert (await registry.get(DEVICE.id)).availability is UNAVAILABLE  # the answer


async def test_devices_applies_the_deadline_to_every_node(registry: DeviceRegistry) -> None:
    stale = DEVICE.model_copy(update={"id": OTHER_ID, "name": "Windows"})
    await registry.register(DEVICE)
    await registry.register(stale)
    await registry.heartbeat(DEVICE.id)
    availabilities = {device.name: device.availability for device in await registry.devices()}
    assert availabilities == {DEVICE.name: AVAILABLE, "Windows": UNAVAILABLE}


async def test_devices_is_empty_before_anything_is_registered(registry: DeviceRegistry) -> None:
    assert await registry.devices() == ()


async def test_available_answers_which_nodes_can_be_used_now(registry: DeviceRegistry) -> None:
    """The question "which nodes can ELA use right now" belongs to the registry, where
    availability is derived: a caller filtering on the stored field would be reading a column
    that keeps saying AVAILABLE after a node went quiet (rule 20, ADR 0016 §3)."""
    stale = DEVICE.model_copy(update={"id": OTHER_ID, "name": "Windows"})
    await registry.register(DEVICE)
    await registry.register(stale)
    await registry.heartbeat(DEVICE.id)

    assert [device.name for device in await registry.available()] == [DEVICE.name]


async def test_available_is_empty_when_nobody_has_been_heard_from(
    registry: DeviceRegistry,
) -> None:
    await registry.register(DEVICE)

    assert await registry.available() == ()


# ----------------------------------------------------------------------------------------
# What a heartbeat may carry (ADR 0016 §7)
# ----------------------------------------------------------------------------------------


async def test_heartbeat_can_declare_status_and_workload(registry: DeviceRegistry) -> None:
    await registry.register(DEVICE)
    beaten = await registry.heartbeat(DEVICE.id, status=DeviceStatus.IDLE, current_workload=0.1)
    assert (beaten.status, beaten.current_workload) == (DeviceStatus.IDLE, 0.1)
    assert (await registry.get(DEVICE.id)).status is DeviceStatus.IDLE


async def test_a_silent_heartbeat_keeps_what_was_known(registry: DeviceRegistry) -> None:
    """A heartbeat that says nothing about status must not erase it."""
    await registry.register(DEVICE)
    beaten = await registry.heartbeat(DEVICE.id)
    assert (beaten.status, beaten.current_workload) == (DEVICE.status, DEVICE.current_workload)


async def test_a_workload_outside_the_range_is_refused(registry: DeviceRegistry) -> None:
    """The domain validates, because the heartbeat revalidates instead of copying."""
    await registry.register(DEVICE)
    with pytest.raises(ValidationError):
        await registry.heartbeat(DEVICE.id, current_workload=7.5)
    assert (await registry.get(DEVICE.id)).current_workload == DEVICE.current_workload


async def test_heartbeat_on_an_unknown_device_is_not_found(registry: DeviceRegistry) -> None:
    """A heartbeat never registers a node: an unknown node announcing itself is M7's business."""
    with pytest.raises(NotFoundError):
        await registry.heartbeat(DEVICE.id)


# ----------------------------------------------------------------------------------------
# Registration and configuration
# ----------------------------------------------------------------------------------------


async def test_update_is_a_configuration_change(registry: DeviceRegistry) -> None:
    await registry.register(DEVICE)
    renamed = DEVICE.model_copy(update={"name": "MacBook Pro"})
    assert (await registry.update(renamed)).name == "MacBook Pro"
    assert (await registry.get(DEVICE.id)).name == "MacBook Pro"


async def test_update_of_an_unknown_device_is_not_found(registry: DeviceRegistry) -> None:
    with pytest.raises(NotFoundError):
        await registry.update(DEVICE)


def test_a_non_positive_ttl_is_refused() -> None:
    """A TTL of zero would make every node unavailable the instant it reported."""
    for ttl in (timedelta(0), timedelta(seconds=-1)):
        with pytest.raises(ValueError, match="positive"):
            DeviceRegistry(
                FakeDeviceRegistry(),
                FakeClock(),
                FakeAuditLog(),
                FakeIdGenerator(),
                heartbeat_ttl=ttl,
            )


def test_the_ttl_is_readable(registry: DeviceRegistry) -> None:
    assert registry.heartbeat_ttl == TTL


# ----------------------------------------------------------------------------------------
# The declared window: read-modify-write (ADR 0016 §5)
# ----------------------------------------------------------------------------------------


async def test_twenty_concurrent_heartbeats_lose_nothing_but_last_seen_at(
    port: DeviceRegistryPort,
) -> None:
    """The whole risk of not making the heartbeat one atomic statement, measured.

    Twenty heartbeats race on one node, each carrying its own instant. Whichever write lands
    last, every field other than ``last_seen_at`` must come out identical to what was
    registered, the surviving ``last_seen_at`` must be one of the twenty instants actually
    reported, and the node must be available: the only possible damage is keeping the older of
    two recent instants.
    """
    registry = DeviceRegistry(
        port, TickingClock(), FakeAuditLog(), FakeIdGenerator(), heartbeat_ttl=TTL
    )
    await registry.register(DEVICE)

    beaten = await asyncio.gather(*(registry.heartbeat(DEVICE.id) for _ in range(20)))
    reported = {device.last_seen_at for device in beaten}
    assert len(reported) == 20  # the clock really did give each heartbeat its own instant

    final = await registry.get(DEVICE.id)
    assert final.last_seen_at in reported
    assert final.availability is AVAILABLE
    assert final.model_copy(update={"last_seen_at": DEVICE.last_seen_at}) == DEVICE


# ----------------------------------------------------------------------------------------
# The reconciliation: a row that learns what this process declares (M6.1b, ADR 0035 §2)
# ----------------------------------------------------------------------------------------

FIRST = ("core-echo", "workspace-notes")
"""What an ELA of an earlier day declared."""

SECOND = ("core-echo", "voice-speak-online", "workspace-notes")
"""The same ELA after a capability was added: one name more, and nothing else different."""


class CountingRegistry:
    """Every write counted, everything else passed through (port ``DeviceRegistryPort``).

    Criterion 4 is about a write that must **not** happen, and a test that looked at the row
    afterwards could not tell "nothing was written" from "the same thing was written again".
    """

    def __init__(self, inner: DeviceRegistryPort) -> None:
        self._inner = inner
        self.writes = 0

    async def register(self, device: Device) -> None:
        self.writes += 1
        await self._inner.register(device)

    async def update(self, device: Device) -> None:
        self.writes += 1
        await self._inner.update(device)

    async def get(self, device_id: DeviceId) -> Device:
        return await self._inner.get(device_id)

    async def devices(self) -> tuple[Device, ...]:
        return await self._inner.devices()


async def test_a_node_that_is_not_there_is_registered_with_what_it_declares(
    registry: DeviceRegistry,
) -> None:
    """The first of the four cases: nothing to reconcile, so the declaration *is* the row."""
    node = await registry.ensure_local(system="Darwin", available_tools=FIRST)

    assert node.id == LOCAL_DEVICE_ID
    assert node.available_tools == FIRST
    assert node.os is OperatingSystem.MACOS


async def test_a_capability_added_after_the_first_start_reaches_the_row(
    registry: DeviceRegistry,
) -> None:
    """The reproduction of 2026-09-08: an ELA that had been running learns a new tool.

    Before M6.1b the second call returned the first row unchanged, so a step needing
    ``voice-speak-online`` answered ``waiting_device`` for ever on a database that had been
    written before the capability existed — and ran at once on a fresh one.
    """
    await registry.ensure_local(system="Darwin", available_tools=FIRST)

    again = await registry.ensure_local(system="Darwin", available_tools=SECOND)

    assert again.available_tools == SECOND
    assert (await registry.get(LOCAL_DEVICE_ID)).available_tools == SECOND


async def test_a_capability_withdrawn_leaves_the_row_at_the_same_start(
    registry: DeviceRegistry,
) -> None:
    """The negative, and the interesting one: a shorter list is an answer too (dec. D).

    A capability that was taken out of the code stops being runnable at the very next start. A
    step that asks for it waits, and that is the behaviour wanted: deciding to withdraw a
    capability belongs to whoever changed the code.
    """
    await registry.ensure_local(system="Darwin", available_tools=SECOND)

    again = await registry.ensure_local(system="Darwin", available_tools=FIRST)

    assert again.available_tools == FIRST
    assert "voice-speak-online" not in (await registry.get(LOCAL_DEVICE_ID)).available_tools


async def test_a_row_that_says_the_wrong_system_is_corrected(registry: DeviceRegistry) -> None:
    """Not only the tools (dec. B): a database copied onto another machine says ``MACOS`` on it.

    The row would be a lie the orchestrator decides on, which is the same defect wearing a
    different field — and repairing one field only would mean coming back for the others.
    """
    await registry.ensure_local(system="Darwin", available_tools=FIRST)

    again = await registry.ensure_local(system="Linux", available_tools=FIRST)

    assert again.os is OperatingSystem.LINUX


async def test_a_declaration_that_did_not_change_writes_nothing(
    port: DeviceRegistryPort, clock: FakeClock, audit: FakeAuditLog
) -> None:
    """Criterion 4, counted rather than looked at: one write for the birth and no other."""
    counting = CountingRegistry(port)
    registry = DeviceRegistry(counting, clock, audit, FakeIdGenerator(), heartbeat_ttl=TTL)
    await registry.ensure_local(system="Darwin", available_tools=FIRST)
    assert counting.writes == 1

    await registry.ensure_local(system="Darwin", available_tools=FIRST)

    assert counting.writes == 1
    assert len(await audit.read()) == 1


async def test_the_observed_half_survives_a_reconciliation(
    registry: DeviceRegistry, clock: FakeClock
) -> None:
    """Criterion 3, and the reason rule 44 exists: no window of unavailability is opened here.

    The node is reconciled *after* it has reported, and what the heartbeat wrote comes out the
    other side untouched — including the availability, so a node that was usable an instant
    before the start-up write is still usable an instant after it.
    """
    await registry.ensure_local(system="Darwin", available_tools=FIRST)
    beaten = await registry.heartbeat(
        LOCAL_DEVICE_ID, status=DeviceStatus.IDLE, current_workload=0.25
    )
    assert beaten.availability is AVAILABLE

    again = await registry.ensure_local(system="Darwin", available_tools=SECOND)

    assert again.last_seen_at == beaten.last_seen_at == clock.now()
    assert again.status is DeviceStatus.IDLE
    assert again.current_workload == 0.25
    assert again.availability is AVAILABLE


async def test_a_revoked_node_is_not_available_whatever_its_heartbeat(
    registry: DeviceRegistry, port: DeviceRegistryPort
) -> None:
    """ADR 0037 §12: ``available()`` reads the revocation and ``seen()`` does not — two facts, two
    names. The node still reads ``ONLINE``, which is what its heartbeat said; it is not usable,
    which is what the user said."""
    await registry.register(DEVICE)
    await registry.heartbeat(DEVICE.id)
    await port.revoke(DEVICE.id, at=MUCH_LATER)

    assert await registry.available() == ()
    seen = await registry.get(DEVICE.id)
    assert seen.availability is AVAILABLE
    assert seen.revoked_at == MUCH_LATER
