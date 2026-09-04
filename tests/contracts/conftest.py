"""One fixture per port, parametrised over every registered implementation.

A contract test asks for ``audit_log`` and runs once per implementation of ``AuditLog``; the
fake today, a real adapter tomorrow, with no change to the test.
"""

from __future__ import annotations

import pytest

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
from tests.contracts.implementations import implementations_of


@pytest.fixture(params=implementations_of(Clock), ids=str)
def clock(request: pytest.FixtureRequest) -> Clock:
    instance: Clock = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(IdGenerator), ids=str)
def ids(request: pytest.FixtureRequest) -> IdGenerator:
    instance: IdGenerator = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(TaskRepository), ids=str)
def task_repository(request: pytest.FixtureRequest) -> TaskRepository:
    instance: TaskRepository = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(AuditLog), ids=str)
def audit_log(request: pytest.FixtureRequest) -> AuditLog:
    instance: AuditLog = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(DeviceRegistryPort), ids=str)
def device_registry(request: pytest.FixtureRequest) -> DeviceRegistryPort:
    instance: DeviceRegistryPort = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(CapabilityRegistryPort), ids=str)
def capability_registry(request: pytest.FixtureRequest) -> CapabilityRegistryPort:
    instance: CapabilityRegistryPort = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(AuthorizationStore), ids=str)
def authorization_store(request: pytest.FixtureRequest) -> AuthorizationStore:
    instance: AuthorizationStore = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(PermissionGuardianPort), ids=str)
def guardian(request: pytest.FixtureRequest) -> PermissionGuardianPort:
    instance: PermissionGuardianPort = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(ToolPort), ids=str)
def tool(request: pytest.FixtureRequest) -> ToolPort:
    instance: ToolPort = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(ModelProvider), ids=str)
def provider(request: pytest.FixtureRequest) -> ModelProvider:
    instance: ModelProvider = request.param.make()
    return instance


@pytest.fixture(params=implementations_of(ProviderRegistry), ids=str)
def provider_registry(request: pytest.FixtureRequest) -> ProviderRegistry:
    instance: ProviderRegistry = request.param.make()
    return instance
