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
from datetime import datetime
from typing import Any

from ela.domain import (
    Approval,
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    Authorization,
    AuthorizationId,
    CapabilityId,
    CapabilitySpec,
    ErrorMetadata,
    ExecutionResult,
    IntentId,
    PlanId,
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
from ela.executive import Executor
from ela.permissions import PermissionGuardian
from ela.ports import (
    ApprovalStore,
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
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeCapabilityRegistry,
    FakeClock,
    FakeExecutionResultStore,
    FakeIdGenerator,
    FakeTaskRepository,
    FakeTool,
    FakeToolRegistry,
    FakeVerifier,
    FakeVerifierRegistry,
)
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.permissions.support import CATALOGUE, COMPLETE
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
    is true raise :class:`SimulatedCrash` before the inner port is touched; ``disarm()`` is the
    restart. Every other member is the inner port's. Works on a fake and on a SQL adapter
    alike, so the same crash can be simulated on both.
    """

    def __init__(self, inner: object, *methods: str) -> None:
        self._inner = inner
        self._methods = frozenset(methods)
        self.armed: dict[str, Callable[..., bool]] = {}
        self.refused = 0

    def arm(self, method: str, when: Callable[..., bool] | None = None) -> None:
        assert method in self._methods, method
        self.armed[method] = (lambda *args, **kwargs: True) if when is None else when

    def disarm(self) -> None:
        self.armed = {}

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._inner, name)
        if name not in self._methods:
            return attribute

        async def guarded(*args: Any, **kwargs: Any) -> Any:
            when = self.armed.get(name)
            if when is not None and when(*args, **kwargs):
                self.refused += 1
                raise SimulatedCrash(f"{type(self._inner).__name__}.{name} never happened")
            return await attribute(*args, **kwargs)

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
    fake_tools: dict[CapabilityId, FakeTool] = field(default_factory=dict)
    fake_verifiers: dict[CapabilityId, FakeVerifier] = field(default_factory=dict)

    @property
    def now(self) -> datetime:
        return self.clock.now()

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
    ) -> tuple[Task, TaskStep]:
        """An EXECUTING task whose one-step plan declares ``capability_id``, the step RUNNING."""
        step = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.now,
            goal=goal,
            required_capabilities=(capability_id,) if capabilities is None else capabilities,
            risk=RiskLevel.LOW,
            expected_result="done",
            success_conditions=conditions,
            requires_authorization=requires_authorization,
        )
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})
        task = await self.engine.create(intent)
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
        task = await self.engine.start(task.id)
        await self.engine.start_step(task.id, step.id)
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
        task = await self.engine.start(task.id)
        await self.engine.start_step(task.id, first.id)
        return task, first, second

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

    def disarm(self) -> None:
        for port in (self.audit, self.repository, self.results, self.approvals):
            port.disarm()


def crashing_world(**options: Any) -> tuple[World, Crashes]:
    """A world whose writes can be made to die one at a time."""
    crashes = Crashes(
        Crashing(FakeAuditLog(), "append"),
        Crashing(FakeTaskRepository(), "save", "append_event"),
        Crashing(FakeExecutionResultStore(), "add"),
        Crashing(FakeApprovalStore(), "add"),
    )
    w = world(
        audit=crashes.audit,  # type: ignore[arg-type]
        repository=crashes.repository,  # type: ignore[arg-type]
        results=crashes.results,  # type: ignore[arg-type]
        approvals=crashes.approvals,  # type: ignore[arg-type]
        **options,
    )
    return w, crashes


def audit_of(event_type: AuditEventType) -> Any:
    return lambda event: event.event_type is event_type


def trail_of(event_type: TaskEventType) -> Any:
    return lambda event: event.event_type is event_type


def saved_as(state: TaskState) -> Any:
    return lambda task: task.state is state


async def count(w: World, task_id: Any, event_type: AuditEventType) -> int:
    return (await w.event_types(task_id)).count(event_type)


async def only_result(w: World, task_id: Any, step_id: Any) -> ExecutionResult:
    (stored,) = await w.results.for_step(task_id, step_id)
    return stored


def fake_tools(clock: FakeClock, ids: FakeIdGenerator) -> dict[CapabilityId, FakeTool]:
    return {
        spec.id: FakeTool(spec.id, clock, ids, name=f"fake-{spec.id}", output={"ok": True})
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


def world(
    *,
    tools: Iterable[ToolPort] | None = None,
    verifiers: Iterable[VerifierPort] | None = None,
    store: AuthorizationStore | None = None,
    approvals: ApprovalStore | None = None,
    results: ExecutionResultStore | None = None,
    repository: TaskRepository | None = None,
    audit: AuditLog | None = None,
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
    fakes = fake_tools(clock, ids)
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
        **executor_options,
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
