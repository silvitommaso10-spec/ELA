"""The composition root: the one place that builds ELA (spec §46, §54; ADR 0023 §1, §5).

Every piece of §27 has existed for milestones — catalogue, Guardian, authorizations, executor,
tools, verifiers, device registry, orchestrator, runner, provider, router, the SQL adapters — and
nothing put them in a row: each test built its own world by hand, and outside the tests ELA did
not exist as a process. :func:`build` is that row, written once.

It is the only module in ``src/ela`` that names concrete implementations (architecture rule 27):
everybody else receives a port. That is what makes "provider abstraction" (§50) a property of the
code rather than a habit — there is exactly one file to read to know what ELA is wired to.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Protocol

from ela.audit.verifier import AuditVerifier
from ela.composition.errors import ConfigurationError
from ela.composition.settings import Settings
from ela.composition.system import SystemClock, UuidGenerator
from ela.devices import DeviceOrchestrator, DeviceRegistry
from ela.devices.local import LOCAL_DEVICE_ID
from ela.domain import Actor, ActorKind
from ela.executive import Executor, TaskRunner
from ela.infrastructure.perception import (
    DarwinProbe,
    ScreenCaptureCommand,
    UnsupportedProbe,
    UnsupportedScreenCapture,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlDeviceRegistry,
    SqlExecutionResultStore,
    SqlTaskRepository,
    make_engine,
    missing_tables,
)
from ela.perception import PerceptionCore
from ela.permissions import PermissionGuardian, production_catalogue
from ela.ports import (
    ApprovalStore,
    AuditLog,
    AuthorizationStore,
    CapabilityRegistryPort,
    Clock,
    ExecutionResultStore,
    IdGenerator,
    RoutingError,
    TaskRepository,
)
from ela.providers.anthropic import anthropic_provider
from ela.providers.registry import ProviderRegistry
from ela.routing import ModelRouter
from ela.tasks.engine import TaskEngine
from ela.tools import (
    CaptureStore,
    ToolRegistry,
    VerifierRegistry,
    production_tools,
    production_verifiers,
)

__all__ = ["ELA_ACTOR", "WORKSPACE_MODE", "Database", "Ela", "build"]

ELA_ACTOR = Actor(kind=ActorKind.ELA, id="ela")
"""Who ELA says it is in the audit trail when it acts on its own (§32)."""
WORKSPACE_MODE = 0o700
"""The workspace holds the user's notes (§57): nobody else on the machine reads them."""


class Database(Protocol):
    """The one thing the composition root does about the database engine: close it.

    A ``Protocol`` and not ``AsyncEngine`` because this package may not import SQLAlchemy
    (architecture rule 3): the engine arrives from :mod:`ela.infrastructure.persistence` already
    built, and what is left here is its lifetime.
    """

    async def dispose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class Ela:
    """ELA, built: every port bound to an implementation, ready to be used or served.

    Frozen, because the wiring of a running assistant is not something a request should be able
    to change. What holds state is behind the ports — the database, the workspace — not here.
    """

    settings: Settings
    clock: Clock
    ids: IdGenerator
    database: Database
    audit: AuditLog
    audit_verifier: AuditVerifier
    """The same log, asked a different question (ADR 0024 §4).

    A second name and not a second object: the adapter that appends is the only one that can say
    whether what was appended still hangs together. Kept apart from ``audit`` because the port a
    caller receives says what that caller may do, and whoever verifies must not gain an
    ``append``.
    """
    repository: TaskRepository
    authorizations: AuthorizationStore
    approvals: ApprovalStore
    results: ExecutionResultStore
    capabilities: CapabilityRegistryPort
    guardian: PermissionGuardian
    providers: ProviderRegistry
    router: ModelRouter
    tools: ToolRegistry
    verifiers: VerifierRegistry
    devices: DeviceRegistry
    engine: TaskEngine
    orchestrator: DeviceOrchestrator
    executor: Executor
    runner: TaskRunner
    captures: CaptureStore
    """Where screen captures are kept, and for how long (M10.2, ADR 0029 §1).

    Exposed on ``Ela`` because three places must agree about it and none of them is the tool: the
    start-up purge in the ``lifespan``, ``/diagnostics``, and the tool itself. A retention nobody
    outside the tool can see is a promise that cannot be checked (§57).
    """
    perception: PerceptionCore
    """What ELA believes about the machine it runs on (§10, §11; M10.1, ADR 0028).

    Built last and wired to nothing else: in v0.1 nobody consumes perception — no task reads it,
    no decision depends on it. That is the milestone's shape, not an omission, and it is why the
    continuous loop is off by default: an observer nobody reads should not be watching.
    """

    async def aclose(self) -> None:
        """Release the database connections. Idempotent, as ``dispose`` is."""
        await self.database.dispose()


async def build(settings: Settings) -> Ela:
    """Build ELA from ``settings``, in one function and in the order of ADR 0023 §5.

    :raises ConfigurationError: for anything that makes this configuration unusable — a schema
        nobody migrated, a routing table naming a provider that is not registered, an empty one.
        The message names what to change, and the database engine is released before it is raised.

    A provider with **no key** is not one of those: it registers ``UNAVAILABLE``, the router skips
    it, and a call fails with ``provider.unavailable`` without touching the network (ADR 0020 §2).
    ELA starts on a machine where nobody has configured a key — it just cannot call a model.

    One function rather than several: the value of a composition root is that the whole wiring is
    readable in one place, and a reader who has to jump between helpers to know what ELA is bound
    to has lost exactly what this module exists to give.
    """
    clock, ids = SystemClock(), UuidGenerator()
    database = make_engine(settings.persistence.db_url)
    try:
        absent = await missing_tables(database)
        if absent:
            raise ConfigurationError(
                f"the database at {settings.persistence.db_url} is missing the tables "
                f"{', '.join(absent)}. ELA does not migrate on start-up (ADR 0006): run "
                "`uv run alembic upgrade head` first."
            )

        audit = SqlAuditLog(database)
        repository = SqlTaskRepository(database)
        authorizations = SqlAuthorizationStore(database)
        approvals = SqlApprovalStore(database)
        results = SqlExecutionResultStore(database)
        devices = DeviceRegistry(
            SqlDeviceRegistry(database), clock, heartbeat_ttl=settings.devices.heartbeat_ttl
        )

        # The scope of ``workspace.write_note`` and the life of a decision are configuration
        # since M8.3 (ADR 0025 §5, §6): the catalogue and the Guardian have always accepted them,
        # and until now this line was the reason they were constants.
        capabilities = production_catalogue(notes_scope=settings.core.notes_scope)
        guardian = PermissionGuardian(
            capabilities, clock, ids, audit, decision_ttl=settings.core.decision_ttl
        )

        # The order of ADR 0022 §7: a provider, a registry that holds it, a router over the two.
        provider = anthropic_provider(clock, ids, settings=settings.anthropic)
        providers = ProviderRegistry((provider,))
        try:
            router = ModelRouter(settings.routing.policy(), providers)
        except RoutingError as wrong:
            raise ConfigurationError(
                f"ELA_MODEL_ROUTES cannot be used ({wrong.code}): {wrong}. Unset it to fall back "
                "to the routing table of spec §25."
            ) from wrong

        # The same router object for both (ADR 0022 §10): the verifier of ``model.routed_as_asked``
        # recomputes the route, and a second policy would fail every verification.
        root = settings.workspace.workspace_dir
        root.mkdir(mode=WORKSPACE_MODE, parents=True, exist_ok=True)

        # The one place that knows which operating system this is (architecture rule 27), for the
        # capture as for the probe: on anything but macOS ELA photographs nothing, and that is a
        # named object with a test rather than a branch buried in an adapter (ADR 0028, ADR 0029).
        darwin = platform.system() == "Darwin"
        probe = (
            DarwinProbe(timeout=settings.perception.probe_timeout) if darwin else UnsupportedProbe()
        )
        # Beside the database and never inside the workspace, and that is a permanent constraint
        # rather than this milestone's convenience (ADR 0029 §1): the workspace is what §23 calls
        # synchronised, and content in a folder something may one day sync leaves the machine
        # without anybody having decided it.
        captures = CaptureStore(settings.captures)
        screen = (
            ScreenCaptureCommand(timeout=settings.captures.capture_timeout)
            if darwin
            else UnsupportedScreenCapture()
        )
        # Its own timeout, measured against its own work: unlike the capture, recognition runs in
        # ELA's process and does degrade under load (2,7x measured), so it does not inherit the
        # capture's number or the ratio that produced it (ADR 0030 §14).
        recognition = (
            VisionTextRecognition(timeout=settings.captures.ocr_timeout)
            if darwin
            else UnsupportedTextRecognition()
        )
        tools = production_tools(
            root=root,
            clock=clock,
            ids=ids,
            router=router,
            providers=providers,
            captures=captures,
            screen=screen,
            probe=probe,
            recognition=recognition,
            languages=settings.captures.ocr_languages,
        )
        verifiers = production_verifiers(root=root, router=router, captures=captures)

        # Which tools this machine has is not something the registry can know (ADR 0016 §4), and
        # without the names no node is ever eligible and every task waits.
        await devices.ensure_local(available_tools=tuple(tool.name for tool in tools.tools()))
        # And it is alive: the local node *is* this process, so ELA can say so about itself
        # without claiming anything it does not know (§16). A node registered and never heard
        # from is UNAVAILABLE, and no step would ever be placed on it (ADR 0016 §3). Keeping it
        # alive over time is another matter: every run says so again (ADR 0023 §9), and the
        # periodic heartbeat of a node that reports itself is M8.3.
        await devices.heartbeat(LOCAL_DEVICE_ID)

        engine = TaskEngine(
            repository,
            audit,
            clock,
            ids,
            approvals=approvals,
            actor=ELA_ACTOR,
            orphan_after=settings.core.orphan_after,
        )
        orchestrator = DeviceOrchestrator(devices, tools, audit, ids, clock)
        executor = Executor(
            registry=capabilities,
            tools=tools,
            verifiers=verifiers,
            guardian=guardian,
            engine=engine,
            repository=repository,
            authorizations=authorizations,
            approvals=approvals,
            results=results,
            audit=audit,
            clock=clock,
            ids=ids,
            actor=ELA_ACTOR,
            authorization_ttl=settings.core.authorization_ttl,
            approval_ttl=settings.core.approval_ttl,
        )
        runner = TaskRunner(
            engine=engine,
            orchestrator=orchestrator,
            executor=executor,
            repository=repository,
            results=results,
            audit=audit,
        )

        # The same probe object the capture tool preflights with: one reader of this machine, so
        # "what ELA believes" and "what ELA checks before acting" cannot come from two places
        # that disagree. They are still two *reads* — a periodic belief never decides an action
        # (ADR 0029 §7).
        perception = PerceptionCore(probe, clock, settings.perception)
    except BaseException:
        await database.dispose()
        raise

    return Ela(
        settings=settings,
        clock=clock,
        ids=ids,
        database=database,
        audit=audit,
        audit_verifier=audit,
        repository=repository,
        authorizations=authorizations,
        approvals=approvals,
        results=results,
        capabilities=capabilities,
        guardian=guardian,
        providers=providers,
        router=router,
        tools=tools,
        verifiers=verifiers,
        devices=devices,
        engine=engine,
        orchestrator=orchestrator,
        executor=executor,
        runner=runner,
        captures=captures,
        perception=perception,
    )
