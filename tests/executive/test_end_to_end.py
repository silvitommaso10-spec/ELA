"""End to end on the fakes (spec §27): intent → task → plan → Guardian → tool → audit.

The production catalogue (``catalogue_v01``), the production tools (``tools_v01`` on a temporary
workspace), the real Guardian and the real engine; only the ports are fake. The orchestrator of
M6.2 is played by the test: it starts the step, calls the executor, completes the task.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import (
    Actor,
    ActorKind,
    AuditEventType,
    CapabilityId,
    IntentId,
    PlanId,
    RiskLevel,
    StepId,
    StepState,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive import Executor
from ela.permissions import (
    CORE_ECHO,
    MODEL_COMPLETE,
    WORKSPACE_WRITE_NOTE,
    CapabilityNotFound,
    PermissionGuardian,
    catalogue_v01,
)
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeClock,
    FakeIdGenerator,
    FakeTaskRepository,
)
from ela.tools import ToolNotFound, tools_v01
from tests.domain.examples import USER_INTENT
from tests.executive.support import granted
from tests.tasks.support import ORPHAN_AFTER, result_for

E = AuditEventType
ELA = Actor(kind=ActorKind.ELA, id="ela")
NOTE_PATH = "workspace/notes/briefing.md"
BODY = "# Briefing\n\nSECRET-BODY\n"


class Pipeline:
    """Everything of §27 wired on the fakes, plus the moves the orchestrator will make."""

    def __init__(self, workspace: Path) -> None:
        self.clock, self.ids, self.audit = FakeClock(), FakeIdGenerator(), FakeAuditLog()
        self.repository, self.store = FakeTaskRepository(), FakeAuthorizationStore()
        self.registry = catalogue_v01()
        self.guardian = PermissionGuardian(self.registry, self.clock, self.ids, self.audit)
        self.tools = tools_v01(root=workspace, clock=self.clock, ids=self.ids)
        self.engine = TaskEngine(
            self.repository, self.audit, self.clock, self.ids, actor=ELA, orphan_after=ORPHAN_AFTER
        )
        self.executor = Executor(
            registry=self.registry,
            tools=self.tools,
            guardian=self.guardian,
            engine=self.engine,
            repository=self.repository,
            authorizations=self.store,
            audit=self.audit,
            clock=self.clock,
            ids=self.ids,
            actor=ELA,
        )

    async def planned_and_running(
        self, capability_id: CapabilityId, *, requires_authorization: bool = False
    ) -> tuple[TaskStep, TaskId]:
        """Intent → task → plan → queue → start → step RUNNING, all through the engine."""
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})
        task = await self.engine.create(intent)
        await self.engine.start_planning(task.id)
        step = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.clock.now(),
            goal=f"run {capability_id}",
            required_capabilities=(capability_id,),
            risk=self.registry.get(capability_id).risk
            if capability_id in {s.id for s in self.registry.specs()}
            else RiskLevel.LOW,
            expected_result="done",
            requires_authorization=requires_authorization,
        )
        plan = TaskPlan(
            id=PlanId(self.ids.new_uuid()),
            created_at=self.clock.now(),
            task_id=task.id,
            goal=intent.text,
            steps=(step,),
        )
        await self.engine.plan(task.id, plan)
        await self.engine.queue(task.id)
        await self.engine.start(task.id)
        await self.engine.start_step(task.id, step.id)
        return step, task.id

    async def types(self, task_id: TaskId) -> list[AuditEventType]:
        return [e.event_type for e in await self.audit.read(task_id=task_id)]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def p(workspace: Path) -> Pipeline:
    return Pipeline(workspace)


LIFE_CYCLE = [
    E.TASK_CREATED,
    E.TASK_PLANNING_STARTED,
    E.PLAN_CREATED,
    E.TASK_QUEUED,
    E.TASK_STARTED,
    E.STEP_STARTED,
]


async def test_echo_end_to_end(p: Pipeline) -> None:
    step, task_id = await p.planned_and_running(CORE_ECHO)
    execution = await p.executor.execute(task_id, step.id, {"message": "hello, ELA"})
    assert execution.result is not None
    assert execution.result.output == {"message": "hello, ELA"}
    assert execution.graph.states[step.id] is StepState.COMPLETED
    task = await p.engine.complete(task_id, result_for(task_id))
    assert task.state is TaskState.COMPLETED
    assert await p.types(task_id) == [
        *LIFE_CYCLE,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    ]
    events = await p.audit.read(task_id=task_id)
    decided, executed = events[6], events[7]
    assert decided.decision_id == executed.decision_id == execution.decision.id
    assert executed.tool_name == "core-echo"
    assert "hello, ELA" not in json.dumps([e.model_dump(mode="json") for e in events])


async def test_write_note_end_to_end_writes_inside_the_workspace(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE)
    execution = await p.executor.execute(task_id, step.id, {"path": NOTE_PATH, "body": BODY})
    assert execution.result is not None
    assert execution.result.output == {"path": NOTE_PATH, "bytes": len(BODY.encode())}
    assert (workspace / NOTE_PATH).read_text(encoding="utf-8") == BODY
    executed = (await p.audit.read(task_id=task_id))[-2]
    assert executed.event_type is E.TOOL_EXECUTED
    assert executed.payload["targets"] == (NOTE_PATH,)
    serialized = json.dumps([e.model_dump(mode="json") for e in await p.audit.read()])
    assert "SECRET-BODY" not in serialized


async def test_write_note_outside_the_scope_denies_the_task_and_writes_nothing(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE)
    outside = {"path": "workspace/other/x.md", "body": BODY}
    execution = await p.executor.execute(task_id, step.id, outside)
    assert execution.task.state is TaskState.DENIED
    assert execution.result is None
    assert await p.types(task_id) == [*LIFE_CYCLE, E.PERMISSION_DECIDED, E.TASK_DENIED]
    assert not (workspace / "workspace" / "other").exists()


async def test_a_step_that_requires_authorization_is_approved_granted_and_run_once(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    arguments = {"path": NOTE_PATH, "body": BODY}
    asked = await p.executor.execute(task_id, step.id, arguments)
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.approval is not None
    assert asked.approval.targets == (NOTE_PATH,)
    assert not (workspace / NOTE_PATH).exists()

    p.clock.advance(timedelta(minutes=2))
    approval = granted(asked.approval, at=p.clock.now())
    await p.engine.approve(task_id, approval)
    await p.engine.start(task_id)
    execution = await p.executor.execute(task_id, step.id, arguments, approval=approval)
    assert execution.authorization is not None
    assert await p.store.uses(execution.authorization.id) == 1
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert (workspace / NOTE_PATH).read_text(encoding="utf-8") == BODY
    assert await p.types(task_id) == [
        *LIFE_CYCLE,
        E.PERMISSION_DECIDED,
        E.APPROVAL_REQUESTED,
        E.APPROVAL_RESOLVED,
        E.TASK_STARTED,
        E.AUTHORIZATION_GRANTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.STEP_COMPLETED,
    ]

    # the same grant cannot serve a second step of the same kind: it is bound and spent
    other_step, other_task = await p.planned_and_running(
        WORKSPACE_WRITE_NOTE, requires_authorization=True
    )
    again = await p.executor.execute(other_task, other_step.id, arguments)
    assert again.task.state is TaskState.WAITING_APPROVAL
    assert again.authorization is None  # bound to the first task and step: not even a candidate


async def test_model_complete_has_no_tool_yet(p: Pipeline) -> None:
    step, task_id = await p.planned_and_running(MODEL_COMPLETE)
    with pytest.raises(ToolNotFound):
        await p.executor.execute(task_id, step.id, {"input": "Riassumi."})
    assert await p.types(task_id) == LIFE_CYCLE


async def test_a_capability_outside_the_catalogue_is_refused_by_name(p: Pipeline) -> None:
    step, task_id = await p.planned_and_running(CapabilityId("nobody.knows_this"))
    with pytest.raises(CapabilityNotFound):
        await p.executor.execute(task_id, step.id, {})
    assert await p.types(task_id) == LIFE_CYCLE
