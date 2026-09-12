"""A world for the executor: fakes for the ports, the real Guardian and engine, fake tools and
fake verifiers.

The catalogue is the wide one of the Guardian tests (``tests/permissions/support.py``): it holds
what production refuses — a HIGH capability, a guarded SAFE one — so the executor can be seen
handling every outcome. ``model.complete`` is in the catalogue and has neither tool nor
verifier, like production. Every fake verifier knows two conditions: :data:`OK` holds,
:data:`BAD` fails with :data:`BAD_FAILURE`, so a test chooses the verdict by choosing the
step's ``success_conditions``. Every task reaches EXECUTING and every step reaches RUNNING
through the engine, never by writing the repository.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ela.devices import DeviceOrchestrator, DeviceRegistry, PlacementDecision, score
from ela.devices.local import LOCAL_DEVICE_NAME
from ela.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    Device,
    DeviceId,
    DeviceStatus,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    IntentId,
    JsonMapping,
    NetworkKind,
    PerformanceClass,
    PlanId,
    PowerSource,
    PrivacyLevel,
    RiskLevel,
    StepId,
    StepState,
    Task,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive import Assignments, Execution, Executor, TaskRunner
from ela.permissions import PermissionGuardian
from ela.ports import (
    ApprovalStore,
    AssignmentStore,
    AuditLog,
    AuthorizationStore,
    ExecutionResultStore,
    TaskRepository,
    ToolPort,
    VerifierPort,
)
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAssignmentStore,
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeCapabilityRegistry,
    FakeClock,
    FakeDeviceRegistry,
    FakeExecutionResultStore,
    FakeIdGenerator,
    FakeTaskRepository,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from tests.devices.nodes import node
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.permissions.support import ARGUMENTS, CATALOGUE, COMPLETE
from tests.tasks.support import ORPHAN_AFTER

TOOLED: tuple[CapabilitySpec, ...] = tuple(spec for spec in CATALOGUE if spec is not COMPLETE)
"""Every capability of the test catalogue but ``model.complete``, which has no tool (M7.2)."""

OK = "fake.ok"
"""A condition every fake verifier of the world knows, and that holds."""
BAD = "fake.bad"
"""A condition every fake verifier of the world knows, and that fails with :data:`BAD_FAILURE`."""
BAD_FAILURE = ErrorMetadata(
    code="fake.mismatch",
    message="the world disagrees with the tool",
    retryable=True,
    details={"expected_bytes": 3, "actual_bytes": 0},
)


class SimulatedCrash(Exception):
    """The process died here: a write that never happened (ADR 0015 §8)."""


class Crashing:
    """A port whose named methods can be made to die instead of writing.

    ``arm(method, when)`` makes the next calls of ``method`` for which ``when(*args, **kwargs)``
    is true raise :class:`SimulatedCrash` **before** the inner port is touched; ``disarm()`` is
    the restart. Every other member is the inner port's. Works on a fake and on a SQL adapter
    alike, so the same crash can be simulated on both.

    ``after=True`` moves the death to the other side of the same write: the inner port is
    called, the write lands, and *then* the process is gone. Half the rows of ADR 0015 §8 are
    written that way — "il processo muore **dopo** ``PERMISSION_DECIDED``" — and for window 3
    there is no later write to arm instead, because what comes next depends on the decision that
    never came back. A crash before a write and a crash after it leave different worlds behind,
    and only one of the two was simulable until M9.4.
    """

    def __init__(self, inner: object, *methods: str) -> None:
        self._inner = inner
        self._methods = frozenset(methods)
        self.armed: dict[str, tuple[Callable[..., bool], bool]] = {}
        self.refused = 0

    def arm(
        self, method: str, when: Callable[..., bool] | None = None, *, after: bool = False
    ) -> None:
        assert method in self._methods, method
        self.armed[method] = ((lambda *args, **kwargs: True) if when is None else when, after)

    def disarm(self) -> None:
        self.armed = {}

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if name not in self._methods:
            return attribute

        async def guarded(*args: Any, **kwargs: Any) -> Any:
            armed = self.armed.get(name)
            if armed is None or not armed[0](*args, **kwargs):
                return await attribute(*args, **kwargs)
            if armed[1]:  # the write lands; what never happens is everything after it
                await attribute(*args, **kwargs)
            self.refused += 1
            raise SimulatedCrash(
                f"{type(self._inner).__name__}.{name} "
                + ("happened and then the process died" if armed[1] else "never happened")
            )

        return guarded


@dataclass
class World:
    repository: TaskRepository
    audit: AuditLog
    clock: FakeClock
    ids: FakeIdGenerator
    store: AuthorizationStore
    approvals: ApprovalStore
    results: ExecutionResultStore
    registry: FakeCapabilityRegistry
    guardian: PermissionGuardian
    tools: FakeToolRegistry
    verifiers: FakeVerifierRegistry
    engine: TaskEngine
    executor: Executor
    devices: DeviceRegistry
    device_port: FakeDeviceRegistry
    """The rows behind :attr:`devices`, so a test can add a node that is not this machine."""
    orchestrator: DeviceOrchestrator
    runner: TaskRunner
    assignments: Assignments
    node: Device
    """This machine, and deliberately so: its id **is** ``LOCAL_DEVICE_ID`` (M12.2, dec. A).

    Every plan of this world therefore runs in this process, as every plan of it always did: the
    remote branch is reached by an id that is not this one, and the tests that want it build their
    own node. A world whose node were any other id would hand all of its work out and run none.
    """
    fake_tools: dict[CapabilityId, FakeTool] = field(default_factory=dict)
    fake_verifiers: dict[CapabilityId, FakeVerifier] = field(default_factory=dict)

    @property
    def now(self) -> datetime:
        return self.clock.now()

    def intent(self) -> Any:
        """A fresh intent, so that every task of a test has its own id (ADR 0008 §8)."""
        return USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})

    def tool(self, capability_id: CapabilityId) -> FakeTool:
        return self.fake_tools[capability_id]

    def verifier(self, capability_id: CapabilityId) -> FakeVerifier:
        return self.fake_verifiers[capability_id]

    async def running(
        self,
        capability_id: CapabilityId,
        *,
        requires_authorization: bool = False,
        capabilities: tuple[CapabilityId, ...] | None = None,
        conditions: tuple[str, ...] = (OK,),
        goal: str = "run the capability",
        arguments: JsonMapping | None = None,
        start: bool = True,
        max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    ) -> tuple[Task, TaskStep]:
        """An EXECUTING task whose one-step plan declares ``capability_id``, the step RUNNING.

        ``arguments`` defaults to the ones the capability expects (``ARGUMENTS``): since ADR 0018
        they belong to the step, so a plan without them is a plan that cannot be executed.
        ``start=False`` stops before ``start_step``, leaving the step PENDING for the runner.
        """
        step = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.now,
            goal=goal,
            required_capabilities=(capability_id,) if capabilities is None else capabilities,
            arguments=ARGUMENTS.get(capability_id, {}) if arguments is None else arguments,
            risk=RiskLevel.LOW,
            expected_result="done",
            success_conditions=conditions,
            requires_authorization=requires_authorization,
        )
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})
        task = await self.engine.create(intent, max_privacy=max_privacy)
        await self.engine.start_planning(task.id)
        plan = TaskPlan(
            id=PlanId(self.ids.new_uuid()),
            created_at=self.now,
            task_id=task.id,
            goal=goal,
            steps=(step,),
        )
        await self.engine.plan(task.id, plan)
        await self.engine.queue(task.id)
        if not start:
            return await self.task(task.id), step
        task = await self.engine.start(task.id, device_id=self.node.id)
        await self.engine.start_step(task.id, step.id, device_id=self.node.id)
        return task, step

    async def running_pair(
        self, capability_id: CapabilityId, *, conditions: tuple[str, ...] = (OK,)
    ) -> tuple[Task, TaskStep, TaskStep]:
        """Two steps, the second depending on the first; the first RUNNING, the second PENDING."""
        first = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.now,
            goal="first",
            required_capabilities=(capability_id,),
            arguments=ARGUMENTS.get(capability_id, {}),
            risk=RiskLevel.LOW,
            expected_result="done",
            success_conditions=conditions,
            requires_authorization=False,
        )
        second = first.model_copy(
            update={
                "id": StepId(self.ids.new_uuid()),
                "goal": "second",
                "dependencies": (first.id,),
            }
        )
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})
        task = await self.engine.create(intent)
        await self.engine.start_planning(task.id)
        plan = TaskPlan(
            id=PlanId(self.ids.new_uuid()),
            created_at=self.now,
            task_id=task.id,
            goal="two steps",
            steps=(first, second),
        )
        await self.engine.plan(task.id, plan)
        await self.engine.queue(task.id)
        task = await self.engine.start(task.id, device_id=self.node.id)
        await self.engine.start_step(task.id, first.id, device_id=self.node.id)
        return task, first, second

    async def queued(
        self,
        *capabilities: CapabilityId,
        conditions: tuple[str, ...] = (OK,),
        chain: bool = True,
        goal: str = "walk the plan",
        deadline: datetime | None = None,
        max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    ) -> tuple[Task, tuple[TaskStep, ...]]:
        """A QUEUED task with one PENDING step per capability: what a runner is handed.

        ``chain`` makes each step depend on the one before it, so the topological order is the
        order given; without it the steps are independent and any of them may go first.

        ``max_privacy`` is declared here because since M12.2 that is the only place it can be
        declared: the level is the task's, written at creation and immutable (D20), and a test that
        wants its work to reach a node that is not this machine says so when it creates the task.
        """
        steps: list[TaskStep] = []
        for index, capability_id in enumerate(capabilities):
            steps.append(
                TaskStep(
                    id=StepId(self.ids.new_uuid()),
                    created_at=self.now,
                    goal=f"step {index}",
                    required_capabilities=(capability_id,),
                    arguments=ARGUMENTS.get(capability_id, {}),
                    risk=RiskLevel.LOW,
                    expected_result="done",
                    success_conditions=conditions,
                    dependencies=(steps[-1].id,) if chain and steps else (),
                    requires_authorization=False,
                )
            )
        task = await self.engine.create(self.intent(), deadline=deadline, max_privacy=max_privacy)
        await self.engine.start_planning(task.id)
        await self.engine.plan(
            task.id,
            TaskPlan(
                id=PlanId(self.ids.new_uuid()),
                created_at=self.now,
                task_id=task.id,
                goal=goal,
                steps=tuple(steps),
            ),
        )
        await self.engine.queue(task.id)
        return await self.task(task.id), tuple(steps)

    async def remote(
        self,
        name: str = "pc-windows",
        *,
        privacy: PrivacyLevel = PrivacyLevel.TRUSTED,
        tools: tuple[str, ...] | None = None,
    ) -> Device:
        """A node that is **not** this machine, registered and beating (M12.2, dec. A).

        Built to win on points — ``HIGH``, ``AC``, ``IDLE``, on the tailnet — so that a test which
        expects the work to go out does not also depend on a tie-break, and one which expects it to
        stay here is showing a filter and not a score. Its tools are this world's unless a test
        takes one away.
        """
        device = node(
            name,
            tools=tuple(tool.name for tool in self.tools.tools()) if tools is None else tools,
            privacy=privacy,
            status=DeviceStatus.IDLE,
            performance=PerformanceClass.HIGH,
            network=NetworkKind.REMOTE,
            power_source=PowerSource.AC,
            workload=0.0,
        ).model_copy(update={"last_seen_at": self.clock.now()})
        await self.device_port.register(device)
        return device

    async def alive(self) -> Device:
        """A sign of life from the one node (§16): the heartbeat a real node would send.

        Needed by every test that moves the clock past :data:`HEARTBEAT_TTL` and still expects a
        node to run on: availability is derived from the last heartbeat, not declared once.
        """
        return await self.devices.heartbeat(self.node.id)

    async def placement(
        self,
        task_id: TaskId,
        step_id: StepId,
        *,
        device_id: DeviceId | None = None,
        max_privacy: PrivacyLevel = PrivacyLevel.LOCAL_ONLY,
    ) -> PlacementDecision:
        """The decision ``executor.execute`` wants, built the way the orchestrator builds it.

        Not ``orchestrator.place``: that writes a ``DEVICE_SELECTED`` event, and most tests here
        assert the exact sequence of audit events an execution produces. So this reuses the two
        real pieces — ``requirements`` (which resolves capabilities into tool names) and the node
        as the **registry derives it**, availability included — and skips only the audit. A
        decision built on ``self.node`` as it was registered would carry ``UNKNOWN``
        availability and be refused by its own placement, which is exactly right and exactly not
        what these tests are about.
        """
        graph = await self.engine.graph(task_id)
        step = graph.graph.step(step_id)
        wanted = self.node.id if device_id is None else device_id
        found = [node for node in await self.devices.devices() if node.id == wanted]
        requirements = self.orchestrator.requirements(step, max_privacy=max_privacy)
        device = found[0] if found else None
        return PlacementDecision(
            created_at=self.clock.now(),
            task_id=task_id,
            step_id=step_id,
            requirements=requirements,
            device=device,
            scores=() if device is None else (score(device, requirements),),
            reason=f"placed on {wanted} by the test world",
        )

    async def execute(
        self,
        task_id: TaskId,
        step_id: StepId,
        *,
        device_id: DeviceId | None = None,
        placement: PlacementDecision | None = None,
    ) -> Execution:
        """``executor.execute`` on the world's one node unless the test names another.

        ``placement`` lets a test hand in a decision of its own — a forged one, one of another
        step — which is how the refusals of ``ensure_placed`` are tested (ADR 0026 §3).
        """
        if placement is None:
            placement = await self.placement(task_id, step_id, device_id=device_id)
        return await self.executor.execute(task_id, step_id, placement=placement)

    async def events(self, task_id: TaskId | None = None) -> tuple[AuditEvent, ...]:
        return await self.audit.read(task_id=task_id)

    async def event_types(self, task_id: TaskId | None = None) -> list[AuditEventType]:
        return [event.event_type for event in await self.events(task_id)]

    async def step_state(self, task_id: TaskId, step_id: StepId) -> StepState:
        return (await self.engine.graph(task_id)).states[step_id]

    async def task(self, task_id: TaskId) -> Task:
        return await self.repository.get(task_id)

    async def answered(
        self,
        approval: Approval,
        *,
        status: ApprovalStatus = ApprovalStatus.GRANTED,
        by: str = "tommaso",
    ) -> Approval:
        """The user's answer to a request the executor made, through the store (ADR 0015 §6)."""
        return await self.approvals.respond(
            approval.id, status=status, responded_by=by, now=self.now
        )


@dataclass
class Crashes:
    audit: Crashing
    repository: Crashing
    results: Crashing
    approvals: Crashing
    authorizations: Crashing
    """The grant store joined the others in M9.4: window 6 dies between ``consume`` and the tool,
    and ``consume`` is a write of this store and of no other."""

    def disarm(self) -> None:
        for port in (
            self.audit,
            self.repository,
            self.results,
            self.approvals,
            self.authorizations,
        ):
            port.disarm()


def crashing_world(
    *, grants: AuthorizationStore | None = None, **options: Any
) -> tuple[World, Crashes]:
    """A world whose writes can be made to die one at a time.

    ``grants`` replaces the store the grants live in — the way window 10 gets one whose grant is
    gone by the time it is consumed. It is a separate parameter and not ``store`` of
    :func:`world` because that one is already taken: this world always wraps the grant store.
    """
    crashes = Crashes(
        Crashing(FakeAuditLog(), "append"),
        Crashing(FakeTaskRepository(), "save", "append_event"),
        Crashing(FakeExecutionResultStore(), "add"),
        Crashing(FakeApprovalStore(), "add"),
        Crashing(FakeAuthorizationStore() if grants is None else grants, "grant", "consume"),
    )
    w = world(
        audit=crashes.audit,  # type: ignore[arg-type]
        repository=crashes.repository,  # type: ignore[arg-type]
        results=crashes.results,  # type: ignore[arg-type]
        approvals=crashes.approvals,  # type: ignore[arg-type]
        store=crashes.authorizations,  # type: ignore[arg-type]
        **options,
    )
    return w, crashes


def audit_of(event_type: AuditEventType) -> Any:
    return lambda event: event.event_type is event_type


def trail_of(event_type: TaskEventType) -> Any:
    return lambda event: event.event_type is event_type


def saved_as(state: TaskState) -> Any:
    return lambda task: task.state is state


def moved_to(state: TaskState) -> Any:
    """The trail event of *one* transition: ``STATE_CHANGED`` says which, ``trail_of`` does not."""
    return lambda event: event.new_state is state


async def count(w: World, task_id: Any, event_type: AuditEventType) -> int:
    return (await w.event_types(task_id)).count(event_type)


async def only_result(w: World, task_id: Any, step_id: Any) -> ExecutionResult:
    (stored,) = await w.results.for_step(task_id, step_id)
    return stored


def fake_tools(
    clock: FakeClock, ids: FakeIdGenerator, failing: frozenset[CapabilityId] = frozenset()
) -> dict[CapabilityId, FakeTool]:
    """One tool per capability of the catalogue; those in ``failing`` report their own failure.

    A tool that says FAILED is not an exception: it is the outcome ADR 0014 §4 keeps distinct
    from a failed verification, and the one whose task the runner has to close.
    """
    return {
        spec.id: FakeTool(
            spec.id,
            clock,
            ids,
            name=f"fake-{spec.id}",
            output={"ok": True},
            status=ExecutionStatus.FAILED if spec.id in failing else ExecutionStatus.SUCCEEDED,
        )
        for spec in TOOLED
    }


def fake_verifier(capability_id: CapabilityId) -> FakeVerifier:
    """A verifier for ``capability_id`` that knows :data:`OK` (holds) and :data:`BAD` (fails)."""
    return FakeVerifier(
        capability_id,
        name=f"fake-{capability_id}-verifier",
        conditions=(OK, BAD),
        failures={BAD: BAD_FAILURE},
    )


def fake_verifiers() -> dict[CapabilityId, FakeVerifier]:
    return {spec.id: fake_verifier(spec.id) for spec in TOOLED}


HEARTBEAT_TTL = timedelta(seconds=60)
"""The real default of ``ELA_DEVICE_HEARTBEAT_TTL_SECONDS`` (ADR 0016 §3), as ``tests/devices``.

Deliberately short (review of M6.3). A long TTL would make the node of this world immortal and
hide exactly the class of bug Fase 12 has to find: a node that goes quiet in the middle of a long
task. So a test that moves the clock past a minute and then expects the walk to go on has to say
so, with :meth:`World.alive` — because that is what would have to happen for real.
"""


def world(
    *,
    tools: Iterable[ToolPort] | None = None,
    verifiers: Iterable[VerifierPort] | None = None,
    store: AuthorizationStore | None = None,
    approvals: ApprovalStore | None = None,
    results: ExecutionResultStore | None = None,
    repository: TaskRepository | None = None,
    audit: AuditLog | None = None,
    assignment_store: AssignmentStore | None = None,
    ttl: timedelta | None = None,
    cap: timedelta | None = None,
    failing: frozenset[CapabilityId] = frozenset(),
    **executor_options: Any,
) -> World:
    clock, ids = FakeClock(), FakeIdGenerator()
    audit = FakeAuditLog() if audit is None else audit
    repository = FakeTaskRepository() if repository is None else repository
    authorizations = FakeAuthorizationStore() if store is None else store
    approval_store = FakeApprovalStore() if approvals is None else approvals
    result_store = FakeExecutionResultStore() if results is None else results
    registry = FakeCapabilityRegistry(CATALOGUE)
    guardian = PermissionGuardian(registry, clock, ids, audit)
    fakes = fake_tools(clock, ids, failing)
    tool_registry = FakeToolRegistry(fakes.values() if tools is None else tools)
    checkers = fake_verifiers()
    verifier_registry = FakeVerifierRegistry(checkers.values() if verifiers is None else verifiers)
    engine = TaskEngine(
        repository,
        audit,
        clock,
        ids,
        approvals=approval_store,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    device = node(
        LOCAL_DEVICE_NAME, tools=tuple(tool.name for tool in tool_registry.tools())
    ).model_copy(update={"last_seen_at": clock.now()})
    device_port = FakeDeviceRegistry((device,))
    devices = DeviceRegistry(device_port, clock, audit, ids, heartbeat_ttl=HEARTBEAT_TTL)
    orchestrator = DeviceOrchestrator(
        devices, tool_registry, audit, ids, clock, verifiers=verifier_registry
    )
    assignments = Assignments(
        FakeAssignmentStore() if assignment_store is None else assignment_store,
        engine=engine,
        repository=repository,
        results=result_store,
        devices=devices,
        audit=audit,
        clock=clock,
        ids=ids,
        **({} if ttl is None else {"ttl": ttl}),
        **({} if cap is None else {"cap": cap}),
    )
    executor = Executor(
        registry=registry,
        tools=tool_registry,
        verifiers=verifier_registry,
        guardian=guardian,
        engine=engine,
        repository=repository,
        authorizations=authorizations,
        approvals=approval_store,
        results=result_store,
        audit=audit,
        clock=clock,
        ids=ids,
        actor=ELA_ACTOR,
        assignments=assignments,
        **executor_options,
    )
    runner = TaskRunner(
        engine=engine,
        orchestrator=orchestrator,
        executor=executor,
        repository=repository,
        results=result_store,
        audit=audit,
        assignments=assignments,
    )
    return World(
        repository,
        audit,
        clock,
        ids,
        authorizations,
        approval_store,
        result_store,
        registry,
        guardian,
        tool_registry,
        verifier_registry,
        engine,
        executor,
        devices,
        device_port,
        orchestrator,
        runner,
        assignments,
        device,
        fakes,
        checkers,
    )


def grant_for(
    spec: CapabilitySpec,
    *,
    task: Task | None = None,
    step: TaskStep | None = None,
    tail: int = 700,
    created_at: datetime,
    **changes: Any,
) -> Authorization:
    """A grant for ``spec`` — bound to ``task`` and ``step`` if given — then ``changes`` applied.

    Built here, in the tests, where no architecture rule applies: production grants are born in
    ``ela.permissions`` only (rule 15).
    """
    base = Authorization(
        id=AuthorizationId(f"00000000-0000-4000-8000-{tail:012d}"),  # type: ignore[arg-type]
        created_at=created_at,
        capability_id=spec.id,
        scope=spec.scope,
        granted_by="tommaso",
        task_id=None if task is None else task.id,
        step_id=None if step is None else step.id,
    )
    return base.model_copy(update=changes)


def granted(approval: Approval, *, at: datetime, by: str = "tommaso") -> Approval:
    """The user's yes to a request, as a value: for the engine's checks, not for a store — a
    "yes" enters a store only through ``respond`` (ADR 0015 §1)."""
    return approval.model_copy(
        update={"status": ApprovalStatus.GRANTED, "responded_by": by, "responded_at": at}
    )
