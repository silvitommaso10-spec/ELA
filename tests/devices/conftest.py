"""A ``DeviceRegistry`` over every implementation of the port it stands on (ADR 0016 §1).

The service is the same code in both cases; running its tests on the fake *and* on SQLite is what
proves that the heartbeat deadline is the service's business and not an accident of storage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

import pytest

from ela.devices import DeviceRegistry
from ela.infrastructure.persistence import SqlDeviceRegistry, make_engine
from ela.infrastructure.persistence.orm import Base
from ela.ports import DeviceRegistryPort
from ela.testing.fakes import FakeAuditLog, FakeClock, FakeDeviceRegistry, FakeIdGenerator
from tests.contracts.implementations import MEMORY_URL
from tests.domain.examples import MUCH_LATER

TTL = timedelta(seconds=60)
"""The default of ``ELA_DEVICE_HEARTBEAT_TTL_SECONDS``, as a ``timedelta`` (ADR 0016 §3)."""


@pytest.fixture(params=["FakeDeviceRegistry", "SqlDeviceRegistry"])
async def port(request: pytest.FixtureRequest) -> AsyncIterator[DeviceRegistryPort]:
    if request.param == "FakeDeviceRegistry":
        yield FakeDeviceRegistry()
        return
    engine = make_engine(MEMORY_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield SqlDeviceRegistry(engine)
    finally:
        await engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    """Fixed at ``MUCH_LATER``, an hour after the ``last_seen_at`` of the example node."""
    return FakeClock(MUCH_LATER)


@pytest.fixture
def audit() -> FakeAuditLog:
    """The registry writes now (ADR 0035 §3), so every one of them is handed a log."""
    return FakeAuditLog()


@pytest.fixture
def registry(port: DeviceRegistryPort, clock: FakeClock, audit: FakeAuditLog) -> DeviceRegistry:
    return DeviceRegistry(port, clock, audit, FakeIdGenerator(), heartbeat_ttl=TTL)
