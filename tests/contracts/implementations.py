"""Every implementation of every port that the contract tests must run on.

The fakes are registered here today; a real adapter (SQLite repository, Claude provider, the
Guardian of M2) is registered here the day it exists, and from then on it passes the same contract
tests as the fake or ``make check`` fails. ``tests/contracts/test_protocols.py`` also checks that
every port has at least one implementation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from ela.infrastructure.persistence import (
    SqlAuthorizationStore,
    SqlTaskRepository,
    make_engine,
)
from ela.infrastructure.persistence.orm import Base
from ela.ports import (
    AuditLog,
    AuthorizationStore,
    CapabilityRegistryPort,
    Clock,
    DeviceRegistryPort,
    IdGenerator,
    ModelProvider,
    PermissionGuardianPort,
    ProviderRegistry,
    TaskRepository,
    ToolPort,
)
from ela.testing.fakes import (
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeModelProvider,
    FakePermissionGuardian,
    FakeProviderRegistry,
    FakeTaskRepository,
    FakeTool,
)
from tests.domain.examples import WRITE_NOTE

Hook = Callable[[object], Awaitable[None]]


@dataclass(frozen=True)
class Implementation:
    """How to build one implementation, plus what to do around it inside the event loop.

    ``make`` is synchronous because ``test_protocols.py`` calls it outside any loop; an adapter
    that needs I/O before use (a schema) or after (closing an engine) gets ``setup``/``teardown``.
    """

    name: str
    make: Callable[[], object]
    setup: Hook | None = None
    teardown: Hook | None = None

    def __str__(self) -> str:
        return self.name


MEMORY_URL = "sqlite:///:memory:"


def _sql_task_repository() -> SqlTaskRepository:
    return SqlTaskRepository(make_engine(MEMORY_URL))


def _sql_authorization_store() -> SqlAuthorizationStore:
    return SqlAuthorizationStore(make_engine(MEMORY_URL))


async def _create_schema(instance: object) -> None:
    """``create_all`` on the in-memory engine; ``test_migrations.py`` proves it equals ``head``."""
    assert isinstance(instance, SqlTaskRepository | SqlAuthorizationStore)
    async with instance.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _dispose(instance: object) -> None:
    assert isinstance(instance, SqlTaskRepository | SqlAuthorizationStore)
    await instance.engine.dispose()


def _guardian() -> FakePermissionGuardian:
    return FakePermissionGuardian(FakeClock(), FakeIdGenerator())


def _tool() -> FakeTool:
    return FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator())


def _provider() -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator())


IMPLEMENTATIONS: dict[type, tuple[Implementation, ...]] = {
    Clock: (Implementation("FakeClock", FakeClock),),
    IdGenerator: (Implementation("FakeIdGenerator", FakeIdGenerator),),
    TaskRepository: (
        Implementation("FakeTaskRepository", FakeTaskRepository),
        Implementation("SqlTaskRepository", _sql_task_repository, _create_schema, _dispose),
    ),
    AuditLog: (Implementation("FakeAuditLog", FakeAuditLog),),
    DeviceRegistryPort: (Implementation("FakeDeviceRegistry", FakeDeviceRegistry),),
    CapabilityRegistryPort: (Implementation("FakeCapabilityRegistry", FakeCapabilityRegistry),),
    AuthorizationStore: (
        Implementation("FakeAuthorizationStore", FakeAuthorizationStore),
        Implementation("SqlAuthorizationStore", _sql_authorization_store, _create_schema, _dispose),
    ),
    PermissionGuardianPort: (Implementation("FakePermissionGuardian", _guardian),),
    ToolPort: (Implementation("FakeTool", _tool),),
    ModelProvider: (Implementation("FakeModelProvider", _provider),),
    ProviderRegistry: (Implementation("FakeProviderRegistry", FakeProviderRegistry),),
}


def implementations_of(port: type) -> list[Implementation]:
    return list(IMPLEMENTATIONS.get(port, ()))
