"""Contract of ``DeviceRegistryPort`` (spec §16): nodes by id, added once, updated explicitly."""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import DeviceId, DeviceStatus
from ela.ports import AlreadyExistsError, DeviceRegistryPort, NotFoundError
from tests.domain.examples import DEVICE

OTHER_DEVICE = DEVICE.model_copy(
    update={"id": DeviceId(UUID("00000000-0000-4000-8000-000000000301")), "name": "Windows"}
)


async def test_register_then_get(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    assert await device_registry.get(DEVICE.id) == DEVICE


async def test_register_twice_is_rejected(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    with pytest.raises(AlreadyExistsError):
        await device_registry.register(DEVICE.model_copy(update={"name": "clone"}))
    assert await device_registry.get(DEVICE.id) == DEVICE


async def test_get_unknown_is_not_found(device_registry: DeviceRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.get(DEVICE.id)


async def test_update_replaces(device_registry: DeviceRegistryPort) -> None:
    await device_registry.register(DEVICE)
    idle = DEVICE.model_copy(update={"status": DeviceStatus.IDLE})
    await device_registry.update(idle)
    assert await device_registry.get(DEVICE.id) == idle


async def test_update_unknown_is_not_found(device_registry: DeviceRegistryPort) -> None:
    with pytest.raises(NotFoundError):
        await device_registry.update(DEVICE)


async def test_devices_in_registration_order_as_a_tuple(
    device_registry: DeviceRegistryPort,
) -> None:
    assert await device_registry.devices() == ()
    await device_registry.register(OTHER_DEVICE)
    await device_registry.register(DEVICE)
    devices = await device_registry.devices()
    assert isinstance(devices, tuple)
    assert devices == (OTHER_DEVICE, DEVICE)
