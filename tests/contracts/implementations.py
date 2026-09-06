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
from weakref import WeakKeyDictionary

from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import RiskLevel
from ela.infrastructure.persistence import (
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlTaskRepository,
    make_engine,
)
from ela.infrastructure.persistence.orm import Base
from ela.permissions import CapabilityRegistry, PermissionGuardian
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
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from ela.tools import (
    EchoTool,
    EchoVerifier,
    ToolRegistry,
    VerifierRegistry,
    WriteNoteTool,
    WriteNoteVerifier,
)
from tests.domain.examples import CAPABILITY_SPEC, MODEL_COMPLETE, WRITE_NOTE

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


async def _create_all(engine: AsyncEngine) -> None:
    """``create_all`` on the in-memory engine; ``test_migrations.py`` proves it equals ``head``."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def _create_schema(instance: object) -> None:
    assert isinstance(instance, SqlTaskRepository | SqlAuthorizationStore)
    await _create_all(instance.engine)


async def _dispose(instance: object) -> None:
    assert isinstance(instance, SqlTaskRepository | SqlAuthorizationStore)
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


class WriteNoteToolHarness:
    """Builds ``WriteNoteTool`` instances on temporary workspaces and removes them afterwards."""

    def __init__(self) -> None:
        self._roots: WeakKeyDictionary[WriteNoteTool, Path] = WeakKeyDictionary()

    def make(self) -> WriteNoteTool:
        root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
        tool = WriteNoteTool(root, FakeClock(), FakeIdGenerator())
        self._roots[tool] = root
        return tool

    async def teardown(self, instance: object) -> None:
        assert isinstance(instance, WriteNoteTool)
        shutil.rmtree(self._roots.pop(instance), ignore_errors=True)


_note_tools = WriteNoteToolHarness()

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


class WriteNoteVerifierHarness:
    """Builds ``WriteNoteVerifier`` instances on temporary workspaces, removed afterwards.

    The verifier never creates its root (ADR 0014 §2), so the harness does, as the tool would.
    """

    def __init__(self) -> None:
        self._roots: WeakKeyDictionary[WriteNoteVerifier, Path] = WeakKeyDictionary()

    def make(self) -> WriteNoteVerifier:
        root = Path(tempfile.mkdtemp(prefix="ela-workspace-"))
        verifier = WriteNoteVerifier(root)
        self._roots[verifier] = root
        return verifier

    async def teardown(self, instance: object) -> None:
        assert isinstance(instance, WriteNoteVerifier)
        shutil.rmtree(self._roots.pop(instance), ignore_errors=True)


_note_verifiers = WriteNoteVerifierHarness()

REGISTRY_VERIFIERS = (FakeVerifier(WRITE_NOTE), _echo_verifier())
"""What every ``VerifierRegistryPort`` implementation under contract is built with (ADR 0014)."""


def _fake_verifier_registry() -> FakeVerifierRegistry:
    return FakeVerifierRegistry(REGISTRY_VERIFIERS)


def _verifier_registry() -> VerifierRegistry:
    return VerifierRegistry(REGISTRY_VERIFIERS)


def _provider() -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator())


IMPLEMENTATIONS: dict[type, tuple[Implementation, ...]] = {
    Clock: (Implementation("FakeClock", FakeClock),),
    IdGenerator: (Implementation("FakeIdGenerator", FakeIdGenerator),),
    TaskRepository: (
        Implementation("FakeTaskRepository", FakeTaskRepository),
        Implementation("SqlTaskRepository", _sql_task_repository, _create_schema, _dispose),
    ),
    AuditLog: (
        Implementation("FakeAuditLog", FakeAuditLog),
        Implementation("SqlAuditLog", _audit_logs.make, _audit_logs.setup, _audit_logs.teardown),
    ),
    DeviceRegistryPort: (Implementation("FakeDeviceRegistry", FakeDeviceRegistry),),
    CapabilityRegistryPort: (
        Implementation("FakeCapabilityRegistry", _fake_registry),
        Implementation("CapabilityRegistry", _registry),
    ),
    AuthorizationStore: (
        Implementation("FakeAuthorizationStore", FakeAuthorizationStore),
        Implementation("SqlAuthorizationStore", _sql_authorization_store, _create_schema, _dispose),
    ),
    PermissionGuardianPort: (
        Implementation("FakePermissionGuardian", _fake_guardian),
        Implementation("PermissionGuardian", _guardian),
    ),
    AuthorizingGuardianPort: (Implementation("PermissionGuardian", _guardian),),
    ToolPort: (
        Implementation("FakeTool", _tool),
        Implementation("EchoTool", _echo_tool),
        Implementation("WriteNoteTool", _note_tools.make, None, _note_tools.teardown),
    ),
    ToolRegistryPort: (
        Implementation("FakeToolRegistry", _fake_tool_registry),
        Implementation("ToolRegistry", _tool_registry),
    ),
    VerifierPort: (
        Implementation("FakeVerifier", _fake_verifier),
        Implementation("EchoVerifier", _echo_verifier),
        Implementation("WriteNoteVerifier", _note_verifiers.make, None, _note_verifiers.teardown),
    ),
    VerifierRegistryPort: (
        Implementation("FakeVerifierRegistry", _fake_verifier_registry),
        Implementation("VerifierRegistry", _verifier_registry),
    ),
    ModelProvider: (Implementation("FakeModelProvider", _provider),),
    ProviderRegistry: (Implementation("FakeProviderRegistry", FakeProviderRegistry),),
}


def implementations_of(port: type) -> list[Implementation]:
    return list(IMPLEMENTATIONS.get(port, ()))
