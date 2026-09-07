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
from ela.permissions import PermissionGuardian, catalogue_v01
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
from ela.tools import ToolRegistry, VerifierRegistry, tools_v01, verifiers_v01

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

        capabilities = catalogue_v01()
        guardian = PermissionGuardian(capabilities, clock, ids, audit)

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
        tools = tools_v01(root=root, clock=clock, ids=ids, router=router, providers=providers)
        verifiers = verifiers_v01(root=root, router=router)

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
    )
