"""``SqlDeviceRegistry``: the nodes survive the process, and every field survives the round trip.

The behaviour of the port is under contract in ``tests/contracts/test_device_registry.py``, which
now runs against this adapter too. What is here is what only a real database can show: a file
closed and reopened, and a node with all eleven aspects of §16 filled in.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.infrastructure.persistence import SqlDeviceRegistry, make_engine
from ela.infrastructure.persistence.orm import Base
from ela.ports import AlreadyExistsError, NotFoundError
from tests.domain.examples import DEVICE

OTHER = DEVICE.model_copy(update={"name": "Windows"})


async def test_a_device_survives_a_reopen(file_url: str) -> None:
    """On a file, not in memory: a registry that forgets on restart is not a registry."""
    engine = make_engine(file_url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await SqlDeviceRegistry(engine).register(DEVICE)
    finally:
        await engine.dispose()

    reopened = make_engine(file_url)
    try:
        assert await SqlDeviceRegistry(reopened).get(DEVICE.id) == DEVICE
    finally:
        await reopened.dispose()


async def test_every_field_survives_a_round_trip(engine: AsyncEngine) -> None:
    """All eleven aspects of §16, including the traits and the tool names."""
    registry = SqlDeviceRegistry(engine)
    await registry.register(DEVICE)
    stored = await registry.get(DEVICE.id)
    assert stored == DEVICE
    assert stored.capabilities == DEVICE.capabilities
    assert stored.capabilities[0].attributes == {"vram_gb": 24, "families": ("ada", "hopper")}
    assert stored.available_tools == DEVICE.available_tools
    assert stored.current_workload == DEVICE.current_workload
    assert stored.metadata == DEVICE.metadata


async def test_a_second_registration_is_refused_by_the_database(engine: AsyncEngine) -> None:
    """The UNIQUE on ``id``, not a read-then-write check."""
    registry = SqlDeviceRegistry(engine)
    await registry.register(DEVICE)
    with pytest.raises(AlreadyExistsError):
        await registry.register(OTHER)
    assert (await registry.get(DEVICE.id)).name == DEVICE.name


async def test_update_of_an_unknown_device_writes_nothing(engine: AsyncEngine) -> None:
    registry = SqlDeviceRegistry(engine)
    with pytest.raises(NotFoundError):
        await registry.update(DEVICE)
    assert await registry.devices() == ()


def test_the_registry_exposes_its_engine(engine: AsyncEngine) -> None:
    registry = SqlDeviceRegistry(engine)
    assert registry.engine is engine
