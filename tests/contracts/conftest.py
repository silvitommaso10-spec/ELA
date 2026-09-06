"""One fixture per port, parametrised over every registered implementation.

A contract test asks for ``audit_log`` and runs once per implementation of ``AuditLog``; the
fake today, a real adapter tomorrow, with no change to the test. The fixtures are async so that
an adapter's ``setup``/``teardown`` (a schema to create, an engine to close) run in the same
event loop as the test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast

import pytest

from ela.ports import (
    AuditLog,
    AuthorizationStore,
    AuthorizingGuardianPort,
    CapabilityRegistryPort,
    Clock,
    DeviceRegistryPort,
    IdGenerator,
    ModelProvider,
    PermissionGuardianPort,
    ProviderRegistry,
    TaskRepository,
    ToolPort,
    ToolRegistryPort,
    VerifierPort,
    VerifierRegistryPort,
)
from tests.contracts.implementations import Implementation, implementations_of


async def _instance(implementation: Implementation) -> AsyncIterator[object]:
    instance = implementation.make()
    if implementation.setup is not None:
        await implementation.setup(instance)
    try:
        yield instance
    finally:
        if implementation.teardown is not None:
            await implementation.teardown(instance)


@pytest.fixture(params=implementations_of(Clock), ids=str)
async def clock(request: pytest.FixtureRequest) -> AsyncIterator[Clock]:
    async for instance in _instance(request.param):
        yield cast(Clock, instance)


@pytest.fixture(params=implementations_of(IdGenerator), ids=str)
async def ids(request: pytest.FixtureRequest) -> AsyncIterator[IdGenerator]:
    async for instance in _instance(request.param):
        yield cast(IdGenerator, instance)


@pytest.fixture(params=implementations_of(TaskRepository), ids=str)
async def task_repository(request: pytest.FixtureRequest) -> AsyncIterator[TaskRepository]:
    async for instance in _instance(request.param):
        yield cast(TaskRepository, instance)


@pytest.fixture(params=implementations_of(AuditLog), ids=str)
async def audit_log(request: pytest.FixtureRequest) -> AsyncIterator[AuditLog]:
    async for instance in _instance(request.param):
        yield cast(AuditLog, instance)


@pytest.fixture(params=implementations_of(DeviceRegistryPort), ids=str)
async def device_registry(request: pytest.FixtureRequest) -> AsyncIterator[DeviceRegistryPort]:
    async for instance in _instance(request.param):
        yield cast(DeviceRegistryPort, instance)


@pytest.fixture(params=implementations_of(CapabilityRegistryPort), ids=str)
async def capability_registry(
    request: pytest.FixtureRequest,
) -> AsyncIterator[CapabilityRegistryPort]:
    async for instance in _instance(request.param):
        yield cast(CapabilityRegistryPort, instance)


@pytest.fixture(params=implementations_of(AuthorizationStore), ids=str)
async def authorization_store(request: pytest.FixtureRequest) -> AsyncIterator[AuthorizationStore]:
    async for instance in _instance(request.param):
        yield cast(AuthorizationStore, instance)


@pytest.fixture(params=implementations_of(PermissionGuardianPort), ids=str)
async def guardian(request: pytest.FixtureRequest) -> AsyncIterator[PermissionGuardianPort]:
    async for instance in _instance(request.param):
        yield cast(PermissionGuardianPort, instance)


@pytest.fixture(params=implementations_of(AuthorizingGuardianPort), ids=str)
async def authorizing_guardian(
    request: pytest.FixtureRequest,
) -> AsyncIterator[AuthorizingGuardianPort]:
    async for instance in _instance(request.param):
        yield cast(AuthorizingGuardianPort, instance)


@pytest.fixture(params=implementations_of(ToolRegistryPort), ids=str)
async def tool_registry(request: pytest.FixtureRequest) -> AsyncIterator[ToolRegistryPort]:
    async for instance in _instance(request.param):
        yield cast(ToolRegistryPort, instance)


@pytest.fixture(params=implementations_of(ToolPort), ids=str)
async def tool(request: pytest.FixtureRequest) -> AsyncIterator[ToolPort]:
    async for instance in _instance(request.param):
        yield cast(ToolPort, instance)


@pytest.fixture(params=implementations_of(VerifierRegistryPort), ids=str)
async def verifier_registry(
    request: pytest.FixtureRequest,
) -> AsyncIterator[VerifierRegistryPort]:
    async for instance in _instance(request.param):
        yield cast(VerifierRegistryPort, instance)


@pytest.fixture(params=implementations_of(VerifierPort), ids=str)
async def verifier(request: pytest.FixtureRequest) -> AsyncIterator[VerifierPort]:
    async for instance in _instance(request.param):
        yield cast(VerifierPort, instance)


@pytest.fixture(params=implementations_of(ModelProvider), ids=str)
async def provider(request: pytest.FixtureRequest) -> AsyncIterator[ModelProvider]:
    async for instance in _instance(request.param):
        yield cast(ModelProvider, instance)


@pytest.fixture(params=implementations_of(ProviderRegistry), ids=str)
async def provider_registry(request: pytest.FixtureRequest) -> AsyncIterator[ProviderRegistry]:
    async for instance in _instance(request.param):
        yield cast(ProviderRegistry, instance)
