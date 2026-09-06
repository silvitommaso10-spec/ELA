"""End to end on SQLite (spec §27, §32): the same pipeline, the audit chain verified.

Repository, authorization store and audit log are the SQL adapters on one in-memory engine;
Guardian, engine, catalogue and tools are the production ones. ``verify_chain`` proves the trail
of a whole run links from the genesis; a row altered behind the adapter's back breaks it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.audit.chain import AuditChainError
from ela.domain import (
    Actor,
    ActorKind,
    AuditEventType,
    CapabilityId,
    IntentId,
    PlanId,
    StepId,
    StepState,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive import Executor
from ela.infrastructure.persistence import (
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlTaskRepository,
    make_engine,
    verify_chain,
)
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS
from ela.permissions import CORE_ECHO, WORKSPACE_WRITE_NOTE, PermissionGuardian, catalogue_v01
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import FakeClock, FakeIdGenerator
from ela.tools import tools_v01
from tests.contracts.implementations import MEMORY_URL
from tests.domain.examples import USER_INTENT
from tests.executive.support import granted
from tests.infrastructure.persistence.conftest import create_schema
from tests.tasks.support import ORPHAN_AFTER, result_for

E = AuditEventType
ELA = Actor(kind=ActorKind.ELA, id="ela")
NOTE_PATH = "workspace/notes/briefing.md"


class SqlPipeline:
    def __init__(self, engine: AsyncEngine, workspace: Path) -> None:
        self.engine_db = engine
        self.clock, self.ids = FakeClock(), FakeIdGenerator()
        self.audit = SqlAuditLog(engine)
        self.repository = SqlTaskRepository(engine)
        self.store = SqlAuthorizationStore(engine)
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

    async def running(
        self, capability_id: CapabilityId, *, requires_authorization: bool = False
    ) -> tuple[TaskStep, TaskId]:
        intent = USER_INTENT.model_copy(update={"id": IntentId(self.ids.new_uuid())})
        task = await self.engine.create(intent)
        await self.engine.start_planning(task.id)
        spec = self.registry.get(capability_id)
        step = TaskStep(
            id=StepId(self.ids.new_uuid()),
            created_at=self.clock.now(),
            goal=f"run {capability_id}",
            required_capabilities=(spec.id,),
            risk=spec.risk,
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
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = make_engine(MEMORY_URL)
    await create_schema(engine)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def p(engine: AsyncEngine, tmp_path: Path) -> SqlPipeline:
    return SqlPipeline(engine, tmp_path / "workspace")


async def test_echo_leaves_a_verified_chain(p: SqlPipeline, engine: AsyncEngine) -> None:
    step, task_id = await p.running(CORE_ECHO)
    execution = await p.executor.execute(task_id, step.id, {"message": "hello"})
    assert execution.result is not None and execution.result.output == {"message": "hello"}
    await p.engine.complete(task_id, result_for(task_id))
    types = await p.types(task_id)
    assert types[-4:] == [
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    ]
    assert (await verify_chain(engine)).length == len(types) == 10


async def test_write_note_leaves_the_file_and_a_verified_chain(
    p: SqlPipeline, engine: AsyncEngine, tmp_path: Path
) -> None:
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE)
    execution = await p.executor.execute(task_id, step.id, {"path": NOTE_PATH, "body": "hi"})
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert (tmp_path / "workspace" / NOTE_PATH).read_text(encoding="utf-8") == "hi"
    assert (await verify_chain(engine)).length == 9


async def test_the_approval_flow_on_sqlite_consumes_the_grant_atomically_and_verifies(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    arguments = {"path": NOTE_PATH, "body": "hi"}
    asked = await p.executor.execute(task_id, step.id, arguments)
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.approval is not None
    p.clock.advance(timedelta(minutes=1))
    approval = granted(asked.approval, at=p.clock.now())
    await p.engine.approve(task_id, approval)
    await p.engine.start(task_id)
    execution = await p.executor.execute(task_id, step.id, arguments, approval=approval)
    assert execution.authorization is not None
    assert await p.store.uses(execution.authorization.id) == 1
    assert execution.graph.states[step.id] is StepState.COMPLETED
    types = await p.types(task_id)
    assert types[-4:] == [
        E.AUTHORIZATION_GRANTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.STEP_COMPLETED,
    ]
    summary = await verify_chain(engine)
    assert summary.length == len(types)


async def test_a_row_altered_behind_the_adapter_breaks_the_chain(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await p.running(CORE_ECHO)
    await p.executor.execute(task_id, step.id, {"message": "hello"})
    async with engine.begin() as connection:
        for name in APPEND_ONLY_TRIGGERS:
            await connection.execute(text(f"DROP TRIGGER {name}"))
        await connection.execute(
            text(
                "UPDATE audit_events SET summary = 'nothing happened' "
                "WHERE event_type = 'TOOL_EXECUTED'"
            )
        )
    with pytest.raises(AuditChainError):
        await verify_chain(engine)
