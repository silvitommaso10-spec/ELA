"""Every implementation of every port that the contract tests must run on.

The fakes are registered here today; a real adapter (SQLite repository, the capability catalogue,
the Guardian, a Claude provider) is registered here the day it exists, and from then on it passes
the same contract tests as the fake or ``make check`` fails. ``tests/contracts/test_protocols.py``
also checks that every port has at least one implementation.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from weakref import WeakKeyDictionary

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.composition import SystemClock, UuidGenerator
from ela.domain import CapabilityId, RiskLevel
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlDeviceRegistry,
    SqlExecutionResultStore,
    SqlTaskRepository,
    make_engine,
)
from ela.infrastructure.persistence.orm import Base
from ela.permissions import CapabilityRegistry, PermissionGuardian
from ela.ports import (
    ApprovalStore,
    AuditLog,
    AuthorizationStore,
    AuthorizingGuardianPort,
    CapabilityRegistryPort,
    Clock,
    DeviceRegistryPort,
    ExecutionResultStore,
    IdGenerator,
    ModelProvider,
    ModelRouterPort,
    PermissionGuardianPort,
    ProviderRegistryPort,
    TaskRepository,
    ToolPort,
    ToolRegistryPort,
    VerifierPort,
    VerifierRegistryPort,
)
from ela.providers import ProviderRegistry
from ela.providers.anthropic import AnthropicProvider, AnthropicSettings, anthropic_provider
from ela.routing import ModelRouter
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeExecutionResultStore,
    FakeIdGenerator,
    FakeModelProvider,
    FakeModelRouter,
    FakePermissionGuardian,
    FakeProviderRegistry,
    FakeTaskRepository,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from ela.tools import (
    EchoTool,
    EchoVerifier,
    ToolRegistry,
    VerifierRegistry,
    tools_v01,
    verifiers_v01,
)
from tests.domain.examples import CAPABILITY_SPEC, MODEL_COMPLETE, WRITE_NOTE
from tests.providers.support import FakeAnthropic, answer, settings
from tests.routing.support import policy_for, routing_for

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


def _sql_device_registry() -> SqlDeviceRegistry:
    return SqlDeviceRegistry(make_engine(MEMORY_URL))


def _sql_approval_store() -> SqlApprovalStore:
    return SqlApprovalStore(make_engine(MEMORY_URL))


def _sql_execution_result_store() -> SqlExecutionResultStore:
    return SqlExecutionResultStore(make_engine(MEMORY_URL))


SQL_STORES = (
    SqlTaskRepository,
    SqlAuthorizationStore,
    SqlApprovalStore,
    SqlExecutionResultStore,
    SqlDeviceRegistry,
)
"""The adapters that expose their engine, so the schema can be created and the engine disposed."""


async def _create_all(engine: AsyncEngine) -> None:
    """``create_all`` on the in-memory engine; ``test_migrations.py`` proves it equals ``head``."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _create_schema(instance: object) -> None:
    assert isinstance(instance, SQL_STORES)
    await _create_all(instance.engine)


async def _dispose(instance: object) -> None:
    assert isinstance(instance, SQL_STORES)
    await instance.engine.dispose()


class SqlAuditLogHarness:
    """Builds ``SqlAuditLog`` instances and keeps their engines on their behalf.

    The log exposes exactly ``append`` and ``read`` — no ``engine`` property, by contract — so
    the harness remembers which engine each log was built on, to create the schema before the
    test and dispose it after.
    """

    def __init__(self) -> None:
        self._engines: WeakKeyDictionary[SqlAuditLog, AsyncEngine] = WeakKeyDictionary()

    def make(self) -> SqlAuditLog:
        engine = make_engine(MEMORY_URL)
        log = SqlAuditLog(engine)
        self._engines[log] = engine
        return log

    async def setup(self, instance: object) -> None:
        assert isinstance(instance, SqlAuditLog)
        await _create_all(self._engines[instance])

    async def teardown(self, instance: object) -> None:
        assert isinstance(instance, SqlAuditLog)
        await self._engines.pop(instance).dispose()


_audit_logs = SqlAuditLogHarness()


REGISTRY_CATALOGUE = (
    CAPABILITY_SPEC,
    CAPABILITY_SPEC.model_copy(update={"id": MODEL_COMPLETE, "risk": RiskLevel.MEDIUM}),
)
"""What every ``CapabilityRegistryPort`` implementation under contract is built with (ADR 0010)."""


def _fake_registry() -> FakeCapabilityRegistry:
    return FakeCapabilityRegistry(REGISTRY_CATALOGUE)


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(REGISTRY_CATALOGUE)


def _fake_guardian() -> FakePermissionGuardian:
    return FakePermissionGuardian(FakeClock(), FakeIdGenerator())


def _guardian() -> PermissionGuardian:
    """The real Guardian on the real catalogue class, with fakes for what it does not own."""
    return PermissionGuardian(_registry(), FakeClock(), FakeIdGenerator(), FakeAuditLog())


def _tool() -> FakeTool:
    return FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator())


def _echo_tool() -> EchoTool:
    return EchoTool(FakeClock(), FakeIdGenerator())


REGISTRY_TOOLS = (FakeTool(WRITE_NOTE, FakeClock(), FakeIdGenerator()), _echo_tool())
"""What every ``ToolRegistryPort`` implementation under contract is built with (ADR 0013)."""


def _fake_tool_registry() -> FakeToolRegistry:
    return FakeToolRegistry(REGISTRY_TOOLS)


def _tool_registry() -> ToolRegistry:
    return ToolRegistry(REGISTRY_TOOLS)


def _fake_verifier() -> FakeVerifier:
    return FakeVerifier(WRITE_NOTE)


def _echo_verifier() -> EchoVerifier:
    return EchoVerifier()


REGISTRY_VERIFIERS = (FakeVerifier(WRITE_NOTE), _echo_verifier())
"""What every ``VerifierRegistryPort`` implementation under contract is built with (ADR 0014)."""


def _fake_verifier_registry() -> FakeVerifierRegistry:
    return FakeVerifierRegistry(REGISTRY_VERIFIERS)


def _verifier_registry() -> VerifierRegistry:
    return VerifierRegistry(REGISTRY_VERIFIERS)


def _provider() -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator())


def _fake_router() -> FakeModelRouter:
    return FakeModelRouter(provider="fake")


def _router() -> ModelRouter:
    """The real router over a registry that has the provider its table names (ADR 0022 §7)."""
    provider = _provider()
    return ModelRouter(policy_for(provider.name), ProviderRegistry((provider,)))


def _unconfigured_anthropic() -> AnthropicProvider:
    """The real adapter with no credentials: UNAVAILABLE, and still under the same contract."""
    return anthropic_provider(
        FakeClock(),
        FakeIdGenerator(),
        settings=AnthropicSettings(_env_file=None, anthropic_api_key=None),
    )


def _anthropic_on_a_double() -> AnthropicProvider:
    """The real adapter on a client double: the contract holds on the answering path too.

    No network: ``tests/conftest.py`` makes the HTTP transports unusable for the whole suite.
    """
    return AnthropicProvider(
        cast(AsyncAnthropic, FakeAnthropic(answer(), repeat=True)),
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        settings=settings(),
    )


class ToolsV01Harness:
    """One implementation per tool of ``tools_v01``, derived instead of listed (ADR 0026 §8).

    Until M9.1 this table named ``EchoTool`` and ``WriteNoteTool`` by hand, and
    ``ModelCompleteTool`` — the tool that carries the user's content off this machine (§57) — was
    simply missing: the one tool whose "no execution without an ``ALLOWED`` decision" had never
    been checked. Listing it too would have fixed today and left the fourth tool to be forgotten
    the same way, so the list is now read from ``tools_v01``.

    Each instance gets its own temporary workspace, as the hand-written harness did: the registry
    builds all three tools at once, so a fresh registry per instance is the cheapest way to hand
    out one tool that owns its root.
    """

    def __init__(self) -> None:
        self._roots: WeakKeyDictionary[object, Path] = WeakKeyDictionary()

    def _registry(self, root: Path) -> ToolRegistry:
        router, providers = routing_for(_provider())
        return tools_v01(
            root=root,
            clock=FakeClock(),
            ids=FakeIdGenerator(),
            router=router,
            providers=providers,
        )

    def capabilities(self) -> tuple[CapabilityId, ...]:
        root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
        try:
            return tuple(tool.capability_id for tool in self._registry(root).tools())
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def maker(self, capability_id: CapabilityId) -> Callable[[], object]:
        def make() -> object:
            root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
            tool = self._registry(root).get(capability_id)
            self._roots[tool] = root
            return tool

        return make

    async def teardown(self, instance: object) -> None:
        shutil.rmtree(self._roots.pop(instance, Path(tempfile.gettempdir())), ignore_errors=True)


class VerifiersV01Harness:
    """The mirror of :class:`ToolsV01Harness` for ``verifiers_v01`` (ADR 0026 §8).

    A verifier never creates its root (ADR 0014 §2), so the harness does, as the tool would.
    """

    def __init__(self) -> None:
        self._roots: WeakKeyDictionary[object, Path] = WeakKeyDictionary()

    def capabilities(self) -> tuple[CapabilityId, ...]:
        root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
        try:
            router, _ = routing_for(_provider())
            return tuple(
                v.capability_id for v in verifiers_v01(root=root, router=router).verifiers()
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def maker(self, capability_id: CapabilityId) -> Callable[[], object]:
        def make() -> object:
            root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
            router, _ = routing_for(_provider())
            verifier = verifiers_v01(root=root, router=router).get(capability_id)
            self._roots[verifier] = root
            return verifier

        return make

    async def teardown(self, instance: object) -> None:
        shutil.rmtree(self._roots.pop(instance, Path(tempfile.gettempdir())), ignore_errors=True)


_v01_tools = ToolsV01Harness()
_v01_verifiers = VerifiersV01Harness()


def _derived(harness: ToolsV01Harness | VerifiersV01Harness) -> tuple[Implementation, ...]:
    """One :class:`Implementation` per member of the real v0.1 registry, named by its class."""
    built: list[Implementation] = []
    for capability_id in harness.capabilities():
        make = harness.maker(capability_id)
        probe = make()
        built.append(Implementation(type(probe).__name__, make, None, harness.teardown))
    return tuple(built)


TOOLS_V01 = _derived(_v01_tools)
"""Every tool of ``tools_v01`` under the ``ToolPort`` contract, derived from the registry."""
VERIFIERS_V01 = _derived(_v01_verifiers)
"""Every verifier of ``verifiers_v01`` under the ``VerifierPort`` contract."""


IMPLEMENTATIONS: dict[type, tuple[Implementation, ...]] = {
    Clock: (
        Implementation("FakeClock", FakeClock),
        Implementation("SystemClock", SystemClock),
    ),
    IdGenerator: (
        Implementation("FakeIdGenerator", FakeIdGenerator),
        Implementation("UuidGenerator", UuidGenerator),
    ),
    TaskRepository: (
        Implementation("FakeTaskRepository", FakeTaskRepository),
        Implementation("SqlTaskRepository", _sql_task_repository, _create_schema, _dispose),
    ),
    AuditLog: (
        Implementation("FakeAuditLog", FakeAuditLog),
        Implementation("SqlAuditLog", _audit_logs.make, _audit_logs.setup, _audit_logs.teardown),
    ),
    DeviceRegistryPort: (
        Implementation("FakeDeviceRegistry", FakeDeviceRegistry),
        Implementation("SqlDeviceRegistry", _sql_device_registry, _create_schema, _dispose),
    ),
    CapabilityRegistryPort: (
        Implementation("FakeCapabilityRegistry", _fake_registry),
        Implementation("CapabilityRegistry", _registry),
    ),
    AuthorizationStore: (
        Implementation("FakeAuthorizationStore", FakeAuthorizationStore),
        Implementation("SqlAuthorizationStore", _sql_authorization_store, _create_schema, _dispose),
    ),
    ApprovalStore: (
        Implementation("FakeApprovalStore", FakeApprovalStore),
        Implementation("SqlApprovalStore", _sql_approval_store, _create_schema, _dispose),
    ),
    ExecutionResultStore: (
        Implementation("FakeExecutionResultStore", FakeExecutionResultStore),
        Implementation(
            "SqlExecutionResultStore", _sql_execution_result_store, _create_schema, _dispose
        ),
    ),
    PermissionGuardianPort: (
        Implementation("FakePermissionGuardian", _fake_guardian),
        Implementation("PermissionGuardian", _guardian),
    ),
    AuthorizingGuardianPort: (Implementation("PermissionGuardian", _guardian),),
    ToolPort: (Implementation("FakeTool", _tool), *TOOLS_V01),
    ToolRegistryPort: (
        Implementation("FakeToolRegistry", _fake_tool_registry),
        Implementation("ToolRegistry", _tool_registry),
    ),
    VerifierPort: (Implementation("FakeVerifier", _fake_verifier), *VERIFIERS_V01),
    VerifierRegistryPort: (
        Implementation("FakeVerifierRegistry", _fake_verifier_registry),
        Implementation("VerifierRegistry", _verifier_registry),
    ),
    ModelProvider: (
        Implementation("FakeModelProvider", _provider),
        Implementation("AnthropicProvider(no key)", _unconfigured_anthropic),
        Implementation("AnthropicProvider", _anthropic_on_a_double),
    ),
    ProviderRegistryPort: (
        Implementation("FakeProviderRegistry", FakeProviderRegistry),
        Implementation("ProviderRegistry", ProviderRegistry),
    ),
    ModelRouterPort: (
        Implementation("FakeModelRouter", _fake_router),
        Implementation("ModelRouter", _router),
    ),
}


def implementations_of(port: type) -> list[Implementation]:
    return list(IMPLEMENTATIONS.get(port, ()))
