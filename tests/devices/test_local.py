"""The ``local`` node: deterministic id, nothing claimed that was not observed (ADR 0016 §4)."""

from __future__ import annotations

import platform
from uuid import NAMESPACE_DNS, uuid5

import pytest

from ela.devices import (
    DEVICE_NAMESPACE,
    LOCAL_DEVICE_ID,
    LOCAL_DEVICE_NAME,
    SYSTEMS,
    UNAVAILABLE,
    DeviceRegistry,
    UnsupportedOperatingSystemError,
    local_device,
    operating_system,
)
from ela.domain import (
    Device,
    DeviceAvailability,
    DeviceStatus,
    NetworkKind,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.ports import AlreadyExistsError, DeviceRegistryPort
from ela.testing.fakes import (
    FakeAuditLog,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeModelProvider,
)
from ela.tools import tools_v01
from tests.devices.conftest import TTL
from tests.domain.examples import MUCH_LATER
from tests.routing.support import routing_for

_ROUTER, _PROVIDERS = routing_for(FakeModelProvider(FakeClock(), FakeIdGenerator()))
V01_TOOL_NAMES = tuple(
    tool.name
    for tool in tools_v01(
        root="/tmp/ela-m6.1",
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        router=_ROUTER,
        providers=_PROVIDERS,
    ).tools()
)
"""What the composition root (M8.1) will pass to ``ensure_local`` (ADR 0016 §4)."""


def test_the_local_id_is_deterministic() -> None:
    """The same id in every process and on every run: ``ensure_local`` registers one node ever."""
    assert uuid5(uuid5(NAMESPACE_DNS, "devices.ela"), "local") == LOCAL_DEVICE_ID
    assert uuid5(DEVICE_NAMESPACE, LOCAL_DEVICE_NAME) == LOCAL_DEVICE_ID


@pytest.mark.parametrize(
    ("system", "expected"),
    [
        ("Darwin", OperatingSystem.MACOS),
        ("Windows", OperatingSystem.WINDOWS),
        ("Linux", OperatingSystem.LINUX),
    ],
)
def test_every_system_platform_reports_is_mapped(system: str, expected: OperatingSystem) -> None:
    assert operating_system(system) is expected
    assert local_device(MUCH_LATER, system=system).os is expected


def test_an_unknown_operating_system_is_refused() -> None:
    """``OperatingSystem`` has no ``UNKNOWN``: a node ELA cannot name is not registered."""
    with pytest.raises(UnsupportedOperatingSystemError, match="FreeBSD") as raised:
        operating_system("FreeBSD")
    assert raised.value.system == "FreeBSD"
    with pytest.raises(UnsupportedOperatingSystemError):
        local_device(MUCH_LATER, system="FreeBSD")


@pytest.mark.parametrize("system", sorted(SYSTEMS))
def test_the_system_defaults_to_the_running_one(
    monkeypatch: pytest.MonkeyPatch, system: str
) -> None:
    """No ``system`` given: ``platform.system()`` — asserted by naming it, not by being it.

    ``SYSTEMS[platform.system()]`` on both sides would have been a test that verifies one entry
    per machine and never fails on any: a default hard-coded to ``"Darwin"`` passes on a Mac and
    is caught only by the runner (ADR 0031). Named, every entry is checked everywhere.
    """
    monkeypatch.setattr(platform, "system", lambda: system)

    assert local_device(MUCH_LATER).os is SYSTEMS[system]


def test_local_declares_only_what_can_be_known() -> None:
    device = local_device(MUCH_LATER, system="Darwin")
    assert device.name == LOCAL_DEVICE_NAME == "local"
    assert device.network is NetworkKind.LOCAL
    assert device.privacy is PrivacyLevel.LOCAL_ONLY  # fail-safe, §33 and §57
    assert device.availability is DeviceAvailability.UNKNOWN
    assert device.status is DeviceStatus.UNKNOWN
    assert device.performance is PerformanceClass.UNKNOWN
    assert device.power_source is PowerSource.UNKNOWN
    assert device.capabilities == ()
    assert device.current_workload is None
    assert device.last_seen_at is None
    assert device.created_at == MUCH_LATER


def test_local_declares_the_tools_it_is_given() -> None:
    """The v0.1 tool names, passed in by whoever composes the system (ADR 0016 §4)."""
    device = local_device(MUCH_LATER, system="Darwin", available_tools=V01_TOOL_NAMES)
    assert device.available_tools == V01_TOOL_NAMES
    assert local_device(MUCH_LATER, system="Darwin").available_tools == ()


# ----------------------------------------------------------------------------------------
# ensure_local
# ----------------------------------------------------------------------------------------


async def test_ensure_local_registers_once_and_is_idempotent(registry: DeviceRegistry) -> None:
    first = await registry.ensure_local(system="Darwin")
    second = await registry.ensure_local(system="Darwin")
    assert first.id == second.id == LOCAL_DEVICE_ID
    assert first == second
    assert len(await registry.devices()) == 1


async def test_local_starts_unavailable(registry: DeviceRegistry) -> None:
    """It exists; nothing has been heard from it yet."""
    assert (await registry.ensure_local(system="Darwin")).availability is UNAVAILABLE
    beaten = await registry.heartbeat(LOCAL_DEVICE_ID)
    assert beaten.availability is not UNAVAILABLE


async def test_ensure_local_does_not_register_a_second_node(registry: DeviceRegistry) -> None:
    """A second call reconciles the row the first one wrote; it never adds a node beside it.

    *What* it reconciles is ``test_registry.py``'s business: here the claim is only that the
    deterministic id keeps the registry at one node, which is what §54 asks for.
    """
    await registry.ensure_local(system="Darwin", available_tools=V01_TOOL_NAMES)
    await registry.ensure_local(system="Darwin", available_tools=())

    assert len(await registry.devices()) == 1


class RacingRegistry(FakeDeviceRegistry):
    """A port where another caller wins the insert between the read and the write."""

    def __init__(self, winner: Device) -> None:
        super().__init__()
        self._winner = winner

    async def register(self, device: Device) -> None:
        await super().register(self._winner)
        raise AlreadyExistsError("device", device.id)


async def test_ensure_local_survives_a_race(clock: FakeClock) -> None:
    """Two callers between the read and the insert: both get the node, nobody gets an error.

    The loser does not walk away with the row as the winner left it — it **reconciles** it, like
    any other call that finds a node already there (ADR 0035 §2). Which is the right answer and
    not a lucky one: the row of ``local`` describes the machine this process is running on, and
    the loser is a process on that machine too.
    """
    winner = local_device(MUCH_LATER, system="Windows", available_tools=("browser",))
    port: DeviceRegistryPort = RacingRegistry(winner)
    registry = DeviceRegistry(port, clock, FakeAuditLog(), FakeIdGenerator(), heartbeat_ttl=TTL)

    device = await registry.ensure_local(system="Darwin")

    assert device.id == LOCAL_DEVICE_ID
    assert device.os is OperatingSystem.MACOS
    assert device.available_tools == ()
