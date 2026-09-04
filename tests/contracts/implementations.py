"""Every implementation of every port that the contract tests must run on.

The fakes are registered here today; a real adapter (SQLite repository, Claude provider, the
Guardian of M2) is registered here the day it exists, and from then on it passes the same contract
tests as the fake or ``make check`` fails. ``tests/contracts/test_protocols.py`` also checks that
every port has at least one implementation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Implementation:
    name: str
    make: Callable[[], object]

    def __str__(self) -> str:
        return self.name


def _guardian() -> FakePermissionGuardian:
    return FakePermissionGuardian(FakeClock(), FakeIdGenerator())


def _tool() -> FakeTool:
    return FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator())


def _provider() -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator())


IMPLEMENTATIONS: dict[type, tuple[Implementation, ...]] = {
    Clock: (Implementation("FakeClock", FakeClock),),
    IdGenerator: (Implementation("FakeIdGenerator", FakeIdGenerator),),
    TaskRepository: (Implementation("FakeTaskRepository", FakeTaskRepository),),
    AuditLog: (Implementation("FakeAuditLog", FakeAuditLog),),
    DeviceRegistryPort: (Implementation("FakeDeviceRegistry", FakeDeviceRegistry),),
    CapabilityRegistryPort: (Implementation("FakeCapabilityRegistry", FakeCapabilityRegistry),),
    AuthorizationStore: (Implementation("FakeAuthorizationStore", FakeAuthorizationStore),),
    PermissionGuardianPort: (Implementation("FakePermissionGuardian", _guardian),),
    ToolPort: (Implementation("FakeTool", _tool),),
    ModelProvider: (Implementation("FakeModelProvider", _provider),),
    ProviderRegistry: (Implementation("FakeProviderRegistry", FakeProviderRegistry),),
}


def implementations_of(port: type) -> list[Implementation]:
    return list(IMPLEMENTATIONS.get(port, ()))
