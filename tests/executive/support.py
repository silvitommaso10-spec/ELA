"""A world for the executor: fakes for the ports, the real Guardian and engine, fake tools.

The catalogue is the wide one of the Guardian tests (``tests/permissions/support.py``): it holds
what production refuses — a HIGH capability, a guarded SAFE one — so the executor can be seen
handling every outcome. ``model.complete`` is in the catalogue and has no tool, like production.
Every task reaches EXECUTING and every step reaches RUNNING through the engine, never by writing
the repository.
"""

from __future__ import annotations

from collections.abc import Iterable
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
    IntentId,
    PlanId,
    RiskLevel,
    StepId,
    StepState,
    Task,
    TaskId,
    TaskPlan,
    TaskStep,
)
from ela.executive import Executor
from ela.permissions import PermissionGuardian
from ela.ports import AuthorizationStore, ToolPort
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeCapabilityRegistry,
    FakeClock,
    FakeIdGenerator,
    FakeTaskRepository,
    FakeTool,
    FakeToolRegistry,
)
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.permissions.support import CATALOGUE, COMPLETE
from tests.tasks.support import ORPHAN_AFTER

TOOLED: tuple[CapabilitySpec, ...] = tuple(spec for spec in CATALOGUE if spec is not COMPLETE)
"""Every capability of the test catalogue but ``model.complete``, which has no tool (M7.2)."""


@dataclass
class World:
    repository: FakeTaskRepository
    audit: FakeAuditLog
    clock: FakeClock
    ids: FakeIdGenerator
    store: AuthorizationStore
    registry: FakeCapabilityRegistry
    guardian: PermissionGuardian
    tools: FakeToolRegistry
    engine: TaskEngine
    executor: Executor
    fake_tools: dict[CapabilityId, FakeTool] = field(default_factory=dict)

    @property
    def now(self) -> datetime:
        return self.clock.now()

    def tool(self, capability_id: CapabilityId) -> FakeTool:
        return self.fake_tools[capability_id]

    async def running(
        self,
        capability_id: CapabilityId,
        *,
        requires_authorization: bool = False,
        capabilities: tuple[CapabilityId, ...] | None = None,
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

    async def running_pair(self, capability_id: CapabilityId) -> tuple[Task, TaskStep, TaskStep]:
        """Two steps, the second depending on the first; the first RUNNING, the second PENDING."""
        first = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.now,
            goal="first",
            required_capabilities=(capability_id,),
            risk=RiskLevel.LOW,
            expected_result="done",
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


def fake_tools(clock: FakeClock, ids: FakeIdGenerator) -> dict[CapabilityId, FakeTool]:
    return {
        spec.id: FakeTool(spec.id, clock, ids, name=f"fake-{spec.id}", output={"ok": True})
        for spec in TOOLED
    }


def world(
    *,
    tools: Iterable[ToolPort] | None = None,
    store: AuthorizationStore | None = None,
    **executor_options: Any,
) -> World:
    clock, ids, audit = FakeClock(), FakeIdGenerator(), FakeAuditLog()
    repository = FakeTaskRepository()
    authorizations = FakeAuthorizationStore() if store is None else store
    registry = FakeCapabilityRegistry(CATALOGUE)
    guardian = PermissionGuardian(registry, clock, ids, audit)
    fakes = fake_tools(clock, ids)
    tool_registry = FakeToolRegistry(fakes.values() if tools is None else tools)
    engine = TaskEngine(repository, audit, clock, ids, actor=ELA_ACTOR, orphan_after=ORPHAN_AFTER)
    executor = Executor(
        registry=registry,
        tools=tool_registry,
        guardian=guardian,
        engine=engine,
        repository=repository,
        authorizations=authorizations,
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
        registry,
        guardian,
        tool_registry,
        engine,
        executor,
        fakes,
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
    """The user's yes to a request the executor made."""
    return approval.model_copy(
        update={"status": ApprovalStatus.GRANTED, "responded_by": by, "responded_at": at}
    )
