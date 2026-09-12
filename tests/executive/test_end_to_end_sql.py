"""End to end on SQLite (spec §27, §32, §63): the same pipeline, the audit chain verified.

Repository, authorization store and audit log are the SQL adapters on one in-memory engine;
Guardian, engine, catalogue, tools and verifiers are the production ones. ``verify_chain`` proves
the trail of a whole run links from the genesis; a row altered behind the adapter's back breaks
it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.audit.chain import AuditChainError
from ela.devices import (
    DeviceOrchestrator,
    DeviceRegistry,
    PlacementDecision,
    local_device,
    score,
)
from ela.domain import (
    Actor,
    ActorKind,
    ApprovalStatus,
    AuditEventType,
    CapabilityId,
    IntentId,
    JsonMapping,
    PlanId,
    StepId,
    StepState,
    TaskEventType,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive import (
    VERIFICATION_FAILED,
    Assignments,
    Execution,
    Executor,
    ExecutorError,
    RunOutcome,
    TaskRunner,
)
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAssignmentStore,
    SqlAuditLog,
    SqlAuthorizationStore,
    SqlExecutionResultStore,
    SqlTaskRepository,
    make_engine,
    verify_chain,
)
from ela.infrastructure.persistence.orm import APPEND_ONLY_TRIGGERS
from ela.permissions import CORE_ECHO, WORKSPACE_WRITE_NOTE, PermissionGuardian, catalogue_v01
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeClock,
    FakeDeviceRegistry,
    FakeIdGenerator,
    FakeModelProvider,
)
from ela.tools import (
    ECHO_MESSAGE_MATCHES,
    NOTE_CONTENT_MATCHES,
    NOTE_EXISTS,
    tools_v01,
    verifiers_v01,
)
from tests.contracts.implementations import MEMORY_URL
from tests.domain.examples import USER_INTENT
from tests.executive.support import (
    HEARTBEAT_TTL,
    Crashes,
    Crashing,
    SimulatedCrash,
    audit_of,
    saved_as,
    trail_of,
)
from tests.infrastructure.persistence.conftest import create_schema
from tests.routing.support import routing_for
from tests.tasks.support import ORPHAN_AFTER, result_for

E = AuditEventType
ELA = Actor(kind=ActorKind.ELA, id="ela")
NOTE_PATH = "workspace/notes/briefing.md"
CONDITIONS: dict[CapabilityId, tuple[str, ...]] = {
    CORE_ECHO: (ECHO_MESSAGE_MATCHES,),
    WORKSPACE_WRITE_NOTE: (NOTE_EXISTS, NOTE_CONTENT_MATCHES),
}
ARGUMENTS: dict[CapabilityId, JsonMapping] = {
    CORE_ECHO: {"message": "hello"},
    WORKSPACE_WRITE_NOTE: {"path": NOTE_PATH, "body": "hi"},
}
"""What each capability is called with; on the step since ADR 0018."""


class SqlPipeline:
    def __init__(self, engine: AsyncEngine, workspace: Path) -> None:
        self.engine_db = engine
        self.workspace = workspace
        self.clock, self.ids = FakeClock(), FakeIdGenerator()
        self.audit = SqlAuditLog(engine)
        self.repository = SqlTaskRepository(engine)
        self.store = SqlAuthorizationStore(engine)
        self.approvals = SqlApprovalStore(engine)
        self.results = SqlExecutionResultStore(engine)
        self.registry = catalogue_v01()
        self.guardian = PermissionGuardian(self.registry, self.clock, self.ids, self.audit)
        self.provider = FakeModelProvider(self.clock, self.ids)
        self.router, self.providers = routing_for(self.provider)
        self.tools = tools_v01(
            root=workspace,
            clock=self.clock,
            ids=self.ids,
            router=self.router,
            providers=self.providers,
        )
        self.verifiers = verifiers_v01(root=workspace, router=self.router)
        self.device = local_device(created_at=self.clock.now()).model_copy(
            update={
                "last_seen_at": self.clock.now(),
                "available_tools": tuple(tool.name for tool in self.tools.tools()),
            }
        )
        self.devices = DeviceRegistry(
            FakeDeviceRegistry((self.device,)),
            self.clock,
            self.audit,
            self.ids,
            heartbeat_ttl=HEARTBEAT_TTL,
        )
        self.engine = TaskEngine(
            self.repository,
            self.audit,
            self.clock,
            self.ids,
            approvals=self.approvals,
            actor=ELA,
            orphan_after=ORPHAN_AFTER,
        )
        self.assignments = Assignments(
            SqlAssignmentStore(self.engine_db),
            engine=self.engine,
            repository=self.repository,
            results=self.results,
            devices=self.devices,
            audit=self.audit,
            clock=self.clock,
            ids=self.ids,
        )
        self.executor = Executor(
            registry=self.registry,
            tools=self.tools,
            verifiers=self.verifiers,
            guardian=self.guardian,
            engine=self.engine,
            repository=self.repository,
            authorizations=self.store,
            approvals=self.approvals,
            results=self.results,
            audit=self.audit,
            clock=self.clock,
            ids=self.ids,
            actor=ELA,
            assignments=self.assignments,
        )
        self._wire_the_walk()

    def _wire_the_walk(self) -> None:
        """The orchestrator and the runner over whatever audit this pipeline ended up with.

        Called again by :class:`CrashingSqlPipeline`, which swaps the ports underneath: an
        orchestrator holding the audit log of before the swap would write outside the crash.
        """
        self.orchestrator = DeviceOrchestrator(
            self.devices, self.tools, self.audit, self.ids, self.clock, verifiers=self.verifiers
        )
        self.runner = TaskRunner(
            engine=self.engine,
            orchestrator=self.orchestrator,
            executor=self.executor,
            repository=self.repository,
            results=self.results,
            audit=self.audit,
            assignments=self.assignments,
        )

    async def alive(self) -> None:
        """A sign of life from the one node, as a running ELA sends before every walk.

        ``POST /tasks/{id}/run`` reports the local node alive before it starts (ADR 0023 §5-bis).
        A test that lets the clock run past the heartbeat TTL — because the user takes their time
        over an approval — must do the same, or the placement the executor checks would name a
        node nobody would place on today (ADR 0026 §3).
        """
        await self.devices.heartbeat(self.device.id)

    async def execute(self, task_id: TaskId, step_id: StepId) -> Execution:
        """The decision the executor wants, built as ``tests/executive/support.py`` builds it:
        the real ``requirements`` and the node as the registry derives it, without ``place``'s
        audit event, which these tests count (ADR 0026 §3)."""
        graph = await self.engine.graph(task_id)
        step = graph.graph.step(step_id)
        requirements = self.orchestrator.requirements(step)
        found = [n for n in await self.devices.devices() if n.id == self.device.id]
        device = found[0] if found else None
        return await self.executor.execute(
            task_id,
            step_id,
            placement=PlacementDecision(
                created_at=self.clock.now(),
                task_id=task_id,
                step_id=step_id,
                requirements=requirements,
                device=device,
                scores=() if device is None else (score(device, requirements),),
                reason=f"placed on {self.device.id} by the test pipeline",
            ),
        )

    async def running(
        self,
        capability_id: CapabilityId,
        *,
        requires_authorization: bool = False,
        arguments: JsonMapping | None = None,
        start: bool = True,
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
            arguments=ARGUMENTS[capability_id] if arguments is None else arguments,
            risk=spec.risk,
            expected_result="done",
            success_conditions=CONDITIONS[capability_id],
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
        if start:
            await self.engine.start(task.id, device_id=self.device.id)
            await self.engine.start_step(task.id, step.id, device_id=self.device.id)
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
    execution = await p.execute(task_id, step.id)
    assert execution.result is not None and execution.result.output == {"message": "hello"}
    await p.engine.complete(task_id, result_for(task_id))
    types = await p.types(task_id)
    assert types[-5:] == [
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    ]
    assert (await verify_chain(engine)).length == len(types) == 11


async def test_write_note_leaves_the_file_and_a_verified_chain(
    p: SqlPipeline, engine: AsyncEngine, tmp_path: Path
) -> None:
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE)
    execution = await p.execute(task_id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert (tmp_path / "workspace" / NOTE_PATH).read_text(encoding="utf-8") == "hi"
    assert (await verify_chain(engine)).length == 10


class _ForgetfulNoteTool:
    """Claims the note of ``inner`` but removes it before answering (§63 on SQLite)."""

    idempotent = True
    """As the tool it wraps: removing the note twice leaves the same absence (ADR 0015 §8)."""

    def __init__(self, inner: object, root: Path) -> None:
        self._inner = inner
        self._root = root

    @property
    def capability_id(self) -> object:
        return self._inner.capability_id  # type: ignore[attr-defined]

    @property
    def name(self) -> str:
        return str(self._inner.name)  # type: ignore[attr-defined]

    async def execute(self, decision: object, arguments: object) -> object:
        result = await self._inner.execute(decision, arguments)  # type: ignore[attr-defined]
        (self._root / str(arguments["path"])).unlink()  # type: ignore[index]
        return result


async def test_a_failed_verification_fails_the_task_and_the_chain_still_verifies(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    forgetful = _ForgetfulNoteTool(p.tools.get(WORKSPACE_WRITE_NOTE), p.workspace)
    from ela.tools import ToolRegistry

    p.executor = Executor(
        registry=p.registry,
        tools=ToolRegistry((forgetful,)),  # type: ignore[arg-type]
        verifiers=p.verifiers,
        guardian=p.guardian,
        engine=p.engine,
        repository=p.repository,
        authorizations=p.store,
        approvals=p.approvals,
        results=p.results,
        audit=p.audit,
        clock=p.clock,
        ids=p.ids,
        actor=ELA,
        assignments=p.assignments,
    )
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE)
    execution = await p.execute(task_id, step.id)
    assert execution.task.state is TaskState.FAILED
    assert execution.graph.states[step.id] is StepState.FAILED
    types = await p.types(task_id)
    assert types[-4:] == [E.TOOL_EXECUTED, E.EXECUTION_VERIFIED, E.STEP_FAILED, E.TASK_FAILED]
    failed = (await p.audit.read(task_id=task_id))[-1]
    assert failed.error is not None and failed.error.code == VERIFICATION_FAILED
    assert (await p.repository.get(task_id)).state is TaskState.FAILED
    assert (await verify_chain(engine)).length == len(types)


async def test_the_approval_flow_on_sqlite_consumes_the_grant_atomically_and_verifies(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    asked = await p.execute(task_id, step.id)
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.approval is not None
    p.clock.advance(timedelta(minutes=1))
    # The user took their time; the node kept reporting itself meanwhile (see `alive`).
    await p.alive()
    approval = await p.approvals.respond(
        asked.approval.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=p.clock.now()
    )
    await p.engine.approve(task_id, approval)
    await p.engine.start(task_id)
    execution = await p.execute(task_id, step.id)
    assert execution.authorization is not None
    assert await p.store.uses(execution.authorization.id) == 1
    assert execution.graph.states[step.id] is StepState.COMPLETED
    types = await p.types(task_id)
    assert types[-5:] == [
        E.AUTHORIZATION_GRANTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    summary = await verify_chain(engine)
    assert summary.length == len(types)


async def test_a_row_altered_behind_the_adapter_breaks_the_chain(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await p.running(CORE_ECHO)
    await p.execute(task_id, step.id)
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


async def test_a_verification_row_altered_behind_the_adapter_breaks_the_chain(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await p.running(CORE_ECHO)
    await p.execute(task_id, step.id)
    async with engine.begin() as connection:
        for name in APPEND_ONLY_TRIGGERS:
            await connection.execute(text(f"DROP TRIGGER {name}"))
        await connection.execute(
            text(
                "UPDATE audit_events SET summary = 'verify: passed anyway' "
                "WHERE event_type = 'EXECUTION_VERIFIED'"
            )
        )
    with pytest.raises(AuditChainError):
        await verify_chain(engine)


# --------------------------------------------------------------------------------------
# Crashes between writes, on SQLite, with the chain verified after every retry (ADR 0015 §8)
# --------------------------------------------------------------------------------------


class CrashingSqlPipeline(SqlPipeline):
    """The SQL pipeline with every port that writes wrapped so that one write can die."""

    def __init__(self, engine: AsyncEngine, workspace: Path) -> None:
        super().__init__(engine, workspace)
        self.crashes = Crashes(
            Crashing(self.audit, "append"),
            Crashing(self.repository, "save", "append_event"),
            Crashing(self.results, "add"),
            Crashing(self.approvals, "add"),
            Crashing(self.store, "grant", "consume"),
        )
        self.audit = self.crashes.audit  # type: ignore[assignment]
        self.repository = self.crashes.repository  # type: ignore[assignment]
        self.results = self.crashes.results  # type: ignore[assignment]
        self.approvals = self.crashes.approvals  # type: ignore[assignment]
        self.store = self.crashes.authorizations  # type: ignore[assignment]
        self.guardian = PermissionGuardian(self.registry, self.clock, self.ids, self.audit)
        self.engine = TaskEngine(
            self.repository,
            self.audit,
            self.clock,
            self.ids,
            approvals=self.approvals,
            actor=ELA,
            orphan_after=ORPHAN_AFTER,
        )
        self.assignments = Assignments(
            SqlAssignmentStore(self.engine_db),
            engine=self.engine,
            repository=self.repository,
            results=self.results,
            devices=self.devices,
            audit=self.audit,
            clock=self.clock,
            ids=self.ids,
        )
        self.executor = Executor(
            registry=self.registry,
            tools=self.tools,
            verifiers=self.verifiers,
            guardian=self.guardian,
            engine=self.engine,
            repository=self.repository,
            authorizations=self.store,
            approvals=self.approvals,
            results=self.results,
            audit=self.audit,
            clock=self.clock,
            ids=self.ids,
            actor=ELA,
            assignments=self.assignments,
        )
        self._wire_the_walk()


@pytest.fixture
def cp(engine: AsyncEngine, tmp_path: Path) -> CrashingSqlPipeline:
    return CrashingSqlPipeline(engine, tmp_path / "workspace")


async def approved(cp: CrashingSqlPipeline) -> tuple[Any, Any]:
    """Ask, answer, resume: an EXECUTING task whose RUNNING step has a GRANTED request."""
    step, task_id = await cp.running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    asked = await cp.execute(task_id, step.id)
    assert asked.approval is not None
    cp.clock.advance(timedelta(minutes=1))
    # The user took their time; the node kept reporting itself meanwhile (see `alive`).
    await cp.alive()
    answer = await cp.approvals.respond(
        asked.approval.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=cp.clock.now()
    )
    await cp.engine.approve(task_id, answer)
    await cp.engine.start(task_id)
    return step, task_id


REPAIRED_ON_THE_WAY_TO_COMPLETED = {
    "1: AUTHORIZATION_GRANTED": lambda c: c.audit.arm("append", audit_of(E.AUTHORIZATION_GRANTED)),
    "7b: TOOL_EXECUTED": lambda c: c.audit.arm("append", audit_of(E.TOOL_EXECUTED)),
    "8a: EXECUTION_VERIFIED": lambda c: c.audit.arm("append", audit_of(E.EXECUTION_VERIFIED)),
    "8b: STEP_COMPLETED": lambda c: c.repository.arm(
        "append_event", trail_of(TaskEventType.STEP_COMPLETED)
    ),
}


@pytest.mark.parametrize("window", sorted(REPAIRED_ON_THE_WAY_TO_COMPLETED))
async def test_a_crash_on_the_way_to_completed_is_repaired_by_the_retry_on_sqlite(
    cp: CrashingSqlPipeline, engine: AsyncEngine, window: str
) -> None:
    step, task_id = await approved(cp)
    REPAIRED_ON_THE_WAY_TO_COMPLETED[window](cp.crashes)
    with pytest.raises(SimulatedCrash):
        await cp.execute(task_id, step.id)
    assert (await verify_chain(engine)).length == len(await cp.types(task_id))
    cp.crashes.disarm()
    execution = await cp.execute(task_id, step.id)
    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert (cp.workspace / NOTE_PATH).read_text(encoding="utf-8") == "hi"
    types = await cp.types(task_id)
    for event_type in (
        E.AUTHORIZATION_GRANTED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ):
        assert types.count(event_type) == 1, event_type
    assert types[-4:] == [
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    assert types.count(E.PERMISSION_DECIDED) == 2  # the request, then the run: never a third
    (stored,) = await cp.results.for_step(task_id, step.id)
    executed = next(
        e for e in await cp.audit.read(task_id=task_id) if e.event_type is E.TOOL_EXECUTED
    )
    assert executed.payload["result_id"] == str(stored.id)
    assert executed.authorization_id == stored.authorization_id is not None
    assert (await verify_chain(engine)).length == len(types)
    await cp.engine.complete(task_id, result_for(task_id))
    assert (await verify_chain(engine)).length == len(types) + 1


async def test_window_5_on_sqlite_the_stored_request_is_asked_once(
    cp: CrashingSqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await cp.running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    cp.crashes.repository.arm("save", saved_as(TaskState.WAITING_APPROVAL))
    with pytest.raises(SimulatedCrash):
        await cp.execute(task_id, step.id)
    (stored,) = await cp.approvals.for_task(task_id)
    cp.crashes.disarm()
    execution = await cp.execute(task_id, step.id)
    assert execution.decision is None and execution.approval == stored
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert await cp.approvals.pending() == (stored,)
    types = await cp.types(task_id)
    assert types.count(E.PERMISSION_DECIDED) == 1 and types[-1] is E.APPROVAL_REQUESTED
    assert (await verify_chain(engine)).length == len(types)


async def test_window_7a_on_sqlite_the_note_is_written_and_the_spent_grant_asks_again(
    cp: CrashingSqlPipeline, engine: AsyncEngine
) -> None:
    """Declared: the effect is on disk, nothing is stored, the single-use grant was spent."""
    step, task_id = await approved(cp)
    cp.crashes.results.arm("add")
    with pytest.raises(SimulatedCrash):
        await cp.execute(task_id, step.id)
    assert (cp.workspace / NOTE_PATH).read_text(encoding="utf-8") == "hi"
    assert await cp.results.for_step(task_id, step.id) == ()
    cp.crashes.disarm()
    execution = await cp.execute(task_id, step.id)
    assert execution.task.state is TaskState.WAITING_APPROVAL
    assert execution.approval is not None and "used 1 of 1 times" in execution.approval.prompt
    assert len(await cp.approvals.for_task(task_id)) == 2
    assert (await verify_chain(engine)).length == len(await cp.types(task_id))


async def test_window_9_on_sqlite_is_the_engines_hole_and_the_chain_still_verifies(
    cp: CrashingSqlPipeline, engine: AsyncEngine
) -> None:
    step, task_id = await approved(cp)
    cp.crashes.audit.arm("append", audit_of(E.STEP_COMPLETED))
    with pytest.raises(SimulatedCrash):
        await cp.execute(task_id, step.id)
    cp.crashes.disarm()
    with pytest.raises(ExecutorError, match="is COMPLETED, not RUNNING"):
        await cp.execute(task_id, step.id)
    types = await cp.types(task_id)
    assert E.STEP_COMPLETED not in types and types[-1] is E.EXECUTION_VERIFIED
    assert (await verify_chain(engine)).length == len(types)


async def test_the_runner_walks_a_real_plan_and_the_node_reaches_the_row(
    p: SqlPipeline, engine: AsyncEngine
) -> None:
    """The whole stack on SQLite: the runner closes the task, and the node the orchestrator chose
    is on the persisted result, not only in memory. The chain still verifies."""
    step, task_id = await p.running(WORKSPACE_WRITE_NOTE, start=False)

    run = await p.runner.run(task_id)

    assert run.outcome is RunOutcome.COMPLETED
    assert (p.workspace / NOTE_PATH).read_text(encoding="utf-8") == "hi"
    (stored,) = await p.results.for_step(task_id, step.id)
    assert stored.device_id == p.device.id  # read back through the adapter, not from memory
    executed = [e for e in await p.audit.read(task_id=task_id) if e.event_type is E.TOOL_EXECUTED]
    assert [e.device_id for e in executed] == [p.device.id]
    await verify_chain(engine)
