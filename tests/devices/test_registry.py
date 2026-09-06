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

from ela.devices import AVAILABLE, UNAVAILABLE, DeviceRegistry, is_available
from ela.domain import DeviceId, DeviceStatus
from ela.ports import DeviceRegistryPort, NotFoundError
from ela.testing.fakes import FakeClock, FakeDeviceRegistry
from tests.devices.conftest import TTL
from tests.domain.examples import DEVICE, MUCH_LATER

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
            DeviceRegistry(FakeDeviceRegistry(), FakeClock(), heartbeat_ttl=ttl)


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
    registry = DeviceRegistry(port, TickingClock(), heartbeat_ttl=TTL)
    await registry.register(DEVICE)

    beaten = await asyncio.gather(*(registry.heartbeat(DEVICE.id) for _ in range(20)))
    reported = {device.last_seen_at for device in beaten}
    assert len(reported) == 20  # the clock really did give each heartbeat its own instant

    final = await registry.get(DEVICE.id)
    assert final.last_seen_at in reported
    assert final.availability is AVAILABLE
    assert final.model_copy(update={"last_seen_at": DEVICE.last_seen_at}) == DEVICE
