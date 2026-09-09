"""End to end on the fakes (spec §27, §63): intent → task → plan → Guardian → tool → verifier →
audit.

The production catalogue (``catalogue_v01``), the production tools and verifiers (``tools_v01``
and ``verifiers_v01`` on a temporary workspace), the real Guardian and the real engine; only the
ports are fake, plus one registered node so the Device Orchestrator of M6.2 has somewhere to
place a step. Since M6.3 the walk itself is production code: :class:`~ela.executive.TaskRunner`
starts the step, calls the executor and closes the task, and the test only says what the plan is.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

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
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    IntentId,
    JsonMapping,
    PlanId,
    ProviderStatus,
    RiskLevel,
    StepId,
    StepState,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive import (
    EXECUTION_INTERRUPTED,
    VERIFICATION_FAILED,
    Execution,
    Executor,
    ExecutorError,
    RunOutcome,
    TaskRunner,
)
from ela.permissions import (
    CORE_ECHO,
    MODEL_COMPLETE,
    WORKSPACE_WRITE_NOTE,
    CapabilityNotFound,
    PermissionGuardian,
    catalogue_v01,
)
from ela.ports import ROUTING_UNKNOWN_TASK_TYPE
from ela.tasks.engine import TaskEngine
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuditLog,
    FakeAuthorizationStore,
    FakeClock,
    FakeDeviceRegistry,
    FakeExecutionResultStore,
    FakeIdGenerator,
    FakeModelProvider,
    FakeTaskRepository,
)
from ela.tools import (
    ECHO_MESSAGE_MATCHES,
    MODEL_ANSWERED,
    MODEL_ROUTED_AS_ASKED,
    NOTE_CONTENT_MATCHES,
    NOTE_CONTENT_MISMATCH,
    NOTE_EXISTS,
    NOTES_TOOL_NAME,
    NOTES_VERIFIER_NAME,
    PATH_MISSING,
    Outcome,
    ToolRegistry,
    WriteNoteTool,
    tools_v01,
    verifiers_v01,
)
from tests.domain.examples import USER_INTENT
from tests.executive.support import HEARTBEAT_TTL
from tests.routing.support import routing_for
from tests.tasks.support import ORPHAN_AFTER, result_for

E = AuditEventType
ELA = Actor(kind=ActorKind.ELA, id="ela")
NOTE_PATH = "workspace/notes/briefing.md"
BODY = "# Briefing\n\nSECRET-BODY\n"
CONDITIONS: dict[CapabilityId, tuple[str, ...]] = {
    CORE_ECHO: (ECHO_MESSAGE_MATCHES,),
    WORKSPACE_WRITE_NOTE: (NOTE_EXISTS, NOTE_CONTENT_MATCHES),
    MODEL_COMPLETE: (MODEL_ANSWERED, MODEL_ROUTED_AS_ASKED),
}
"""What a plan of v0.1 asks of each capability: the whole vocabulary of its verifier."""
ARGUMENTS: dict[CapabilityId, JsonMapping] = {
    CORE_ECHO: {"message": "hello, ELA"},
    WORKSPACE_WRITE_NOTE: {"path": NOTE_PATH, "body": BODY},
    MODEL_COMPLETE: {"input": "Riassumi le email della riunione."},
}
"""What each capability is called with. Since ADR 0018 this belongs to the step: a plan that does
not say it is a plan that cannot be executed."""


class _LyingNoteTool(WriteNoteTool):
    """A tool that writes something else and reports success: the case §63 exists for."""

    def __init__(self, *args: Any, body: str | None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lie = body

    async def _run(self, arguments: JsonMapping) -> Outcome:
        if self._lie is None:  # writes nothing at all, claims it did
            return Outcome({"path": arguments["path"], "bytes": 0})
        return await super()._run({**arguments, "body": self._lie})


class Pipeline:
    """Everything of §27 wired on the fakes, plus the moves the orchestrator will make."""

    def __init__(
        self,
        workspace: Path,
        *,
        tools: ToolRegistry | None = None,
        model_providers: tuple[FakeModelProvider, ...] | None = None,
    ) -> None:
        self.clock, self.ids, self.audit = FakeClock(), FakeIdGenerator(), FakeAuditLog()
        self.repository, self.store = FakeTaskRepository(), FakeAuthorizationStore()
        self.approvals, self.results = FakeApprovalStore(), FakeExecutionResultStore()
        self.registry = catalogue_v01()
        self.guardian = PermissionGuardian(self.registry, self.clock, self.ids, self.audit)
        chain = model_providers or (FakeModelProvider(self.clock, self.ids),)
        self.provider = next(p for p in chain if p.status is ProviderStatus.AVAILABLE)
        """The provider that will answer: the first of the route that is usable (ADR 0022 §7)."""
        self.router, self.providers = routing_for(*chain)
        self.tools = (
            tools_v01(
                root=workspace,
                clock=self.clock,
                ids=self.ids,
                router=self.router,
                providers=self.providers,
            )
            if tools is None
            else tools
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
        self.orchestrator = DeviceOrchestrator(
            self.devices, self.tools, self.audit, self.ids, self.clock
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
        )
        self.runner = TaskRunner(
            engine=self.engine,
            orchestrator=self.orchestrator,
            executor=self.executor,
            repository=self.repository,
            results=self.results,
            audit=self.audit,
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
        """``executor.execute`` on the one node of this pipeline.

        The decision is built the way the orchestrator builds it — the real ``requirements`` and
        the node as the registry derives it — but without ``place``'s audit event, which these
        tests count (ADR 0026 §3, as ``tests/executive/support.py``).
        """
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

    async def planned_and_running(
        self,
        capability_id: CapabilityId,
        *,
        requires_authorization: bool = False,
        conditions: tuple[str, ...] | None = None,
        arguments: JsonMapping | None = None,
        start: bool = True,
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
            arguments=ARGUMENTS.get(capability_id, {}) if arguments is None else arguments,
            success_conditions=CONDITIONS.get(capability_id, ("x.unknown",))
            if conditions is None
            else conditions,
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

    async def grant(self, task_id: TaskId, step_id: StepId) -> None:
        """The approval a MEDIUM capability needs: ask, answer, resume (§27, ADR 0012)."""
        asked = await self.execute(task_id, step_id)
        assert asked.approval is not None
        approval = await self.approvals.respond(
            asked.approval.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=self.clock.now(),
        )
        await self.engine.approve(task_id, approval)
        await self.engine.start(task_id)

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
    execution = await p.execute(task_id, step.id)
    assert execution.result is not None
    assert execution.result.output == {"message": "hello, ELA"}
    assert execution.graph.states[step.id] is StepState.COMPLETED
    task = await p.engine.complete(task_id, result_for(task_id))
    assert task.state is TaskState.COMPLETED
    assert await p.types(task_id) == [
        *LIFE_CYCLE,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    ]
    events = await p.audit.read(task_id=task_id)
    decided, executed, verified = events[6], events[7], events[8]
    assert decided.decision_id == executed.decision_id == execution.decision.id
    assert verified.decision_id == execution.decision.id
    assert executed.tool_name == "core-echo"
    assert verified.payload["verifier"] == "core-echo-verifier"
    assert verified.payload["passed"] is True
    assert execution.verification is not None and execution.verification.passed
    assert "hello, ELA" not in json.dumps([e.model_dump(mode="json") for e in events])


async def test_write_note_end_to_end_writes_inside_the_workspace(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE)
    execution = await p.execute(task_id, step.id)
    assert execution.result is not None
    assert execution.result.output == {"path": NOTE_PATH, "bytes": len(BODY.encode())}
    assert (workspace / NOTE_PATH).read_text(encoding="utf-8") == BODY
    executed, verified, completed = (await p.audit.read(task_id=task_id))[-3:]
    assert executed.event_type is E.TOOL_EXECUTED
    assert executed.payload["targets"] == (NOTE_PATH,)
    assert verified.event_type is E.EXECUTION_VERIFIED
    assert verified.payload["conditions"] == (NOTE_EXISTS, NOTE_CONTENT_MATCHES)
    assert verified.payload["failed"] == ()
    assert completed.event_type is E.STEP_COMPLETED
    assert execution.graph.states[step.id] is StepState.COMPLETED
    task = await p.engine.complete(task_id, result_for(task_id))
    assert task.state is TaskState.COMPLETED
    serialized = json.dumps([e.model_dump(mode="json") for e in await p.audit.read()])
    assert "SECRET-BODY" not in serialized


@pytest.mark.parametrize("lie", ["something else entirely\n", None], ids=["altered", "unwritten"])
async def test_a_tool_that_lies_about_a_note_fails_the_task_with_the_reason(
    workspace: Path, lie: str | None
) -> None:
    """The tool says SUCCEEDED, the disk says otherwise: verification fails, the task stops."""
    clock, ids = FakeClock(), FakeIdGenerator()
    liar = _LyingNoteTool(workspace, clock, ids, body=lie)
    p = Pipeline(workspace, tools=ToolRegistry((liar,)))
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE)
    execution = await p.execute(task_id, step.id)
    assert execution.result is not None
    assert execution.result.status.value == "SUCCEEDED"
    assert execution.verification is not None
    assert not execution.verification.passed
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.FAILED
    assert await p.types(task_id) == [
        *LIFE_CYCLE,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_FAILED,
        E.TASK_FAILED,
    ]
    failed = (await p.audit.read(task_id=task_id))[-1]
    assert failed.error is not None
    assert failed.error.code == VERIFICATION_FAILED
    assert failed.error.tool_name == NOTES_TOOL_NAME
    assert failed.error.details["verifier"] == NOTES_VERIFIER_NAME
    expected_code = NOTE_CONTENT_MISMATCH if lie is not None else PATH_MISSING
    assert expected_code in failed.error.message
    assert [f["code"] for f in failed.error.details["failures"]] == (
        [NOTE_CONTENT_MISMATCH] if lie is not None else [PATH_MISSING, PATH_MISSING]
    )
    assert failed.error.retryable is True
    serialized = json.dumps([e.model_dump(mode="json") for e in await p.audit.read()])
    assert "SECRET-BODY" not in serialized
    assert lie is None or lie.strip() not in serialized
    assert NOTE_PATH in serialized  # the target, yes


async def test_a_step_without_success_conditions_is_not_executed(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE, conditions=())
    with pytest.raises(ExecutorError, match="declares no success condition"):
        await p.execute(task_id, step.id)
    assert await p.types(task_id) == LIFE_CYCLE
    assert not (workspace / NOTE_PATH).exists()


async def test_a_condition_the_verifier_cannot_check_is_not_executed(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(
        WORKSPACE_WRITE_NOTE, conditions=(NOTE_EXISTS, "la nota contiene i partecipanti")
    )
    with pytest.raises(ExecutorError, match="la nota contiene i partecipanti"):
        await p.execute(task_id, step.id)
    assert await p.types(task_id) == LIFE_CYCLE
    assert not (workspace / NOTE_PATH).exists()


async def test_write_note_outside_the_scope_denies_the_task_and_writes_nothing(
    p: Pipeline, workspace: Path
) -> None:
    outside = {"path": "workspace/other/x.md", "body": BODY}
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE, arguments=outside)
    execution = await p.execute(task_id, step.id)
    assert execution.task.state is TaskState.DENIED
    assert execution.result is None
    assert await p.types(task_id) == [*LIFE_CYCLE, E.PERMISSION_DECIDED, E.TASK_DENIED]
    assert not (workspace / "workspace" / "other").exists()


async def test_a_step_that_requires_authorization_is_approved_granted_and_run_once(
    p: Pipeline, workspace: Path
) -> None:
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE, requires_authorization=True)
    asked = await p.execute(task_id, step.id)
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.approval is not None
    assert asked.approval.targets == (NOTE_PATH,)
    assert not (workspace / NOTE_PATH).exists()

    p.clock.advance(timedelta(minutes=2))
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
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]
    verified = (await p.audit.read(task_id=task_id))[-2]
    assert verified.authorization_id == execution.authorization.id

    # the same grant cannot serve a second step of the same kind: it is bound and spent
    other_step, other_task = await p.planned_and_running(
        WORKSPACE_WRITE_NOTE, requires_authorization=True
    )
    again = await p.execute(other_task, other_step.id)
    assert again.task.state is TaskState.WAITING_APPROVAL
    assert again.authorization is None  # bound to the first task and step: not even a candidate


async def test_model_complete_goes_out_through_the_guardian_and_comes_back_accounted_for(
    p: Pipeline,
) -> None:
    """The claim of M7.2, end to end (§27, §29, §32).

    ``model.complete`` is MEDIUM and always needs an authorization, so the first call asks; the
    second, with the grant, calls the provider **once**, writes a STARTED record before the call
    and its outcome after, and puts what the call consumed in the ``TOOL_EXECUTED``. The text of
    the answer is in the result and in no audit event (§57).
    """
    step, task_id = await p.planned_and_running(MODEL_COMPLETE)
    asked = await p.execute(task_id, step.id)
    assert asked.task.state is TaskState.WAITING_APPROVAL
    assert asked.approval is not None
    assert p.provider.requests == ()  # nothing left the machine before the answer

    approval = await p.approvals.respond(
        asked.approval.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=p.clock.now()
    )
    await p.engine.approve(task_id, approval)
    await p.engine.start(task_id)
    execution = await p.execute(task_id, step.id)

    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert len(p.provider.requests) == 1
    assert p.provider.requests[0].input == ARGUMENTS[MODEL_COMPLETE]["input"]
    assert execution.result is not None
    assert execution.result.output["output"] == "ok"
    assert execution.result.usage is not None

    stored = await p.results.for_step(task_id, step.id)
    started, outcome = stored
    assert started.status is ExecutionStatus.STARTED
    assert started.created_at <= outcome.created_at
    assert outcome.metadata["started_id"] == str(started.id)

    executed = next(
        e for e in await p.audit.read(task_id=task_id) if e.event_type is E.TOOL_EXECUTED
    )
    assert executed.usage == execution.result.usage
    assert "Riassumi" not in json.dumps([e.model_dump(mode="json") for e in await p.audit.read()])


async def test_a_routed_model_call_goes_where_the_table_says(p: Pipeline) -> None:
    """The claim of M7.3, end to end (§25): the plan says *what kind of task* it is, and the
    profile that reaches the provider is the table's — nobody typed it."""
    step, task_id = await p.planned_and_running(
        MODEL_COMPLETE, arguments={**ARGUMENTS[MODEL_COMPLETE], "task_type": "coding"}
    )
    await p.grant(task_id, step.id)
    execution = await p.execute(task_id, step.id)

    assert execution.graph.states[step.id] is StepState.COMPLETED  # both conditions held
    assert p.provider.requests[0].model_hint == "quality"
    assert execution.result is not None
    assert execution.result.output["profile"] == "quality"
    assert execution.result.output["skipped"] == ()


async def test_a_provider_that_is_down_is_stepped_over_end_to_end(tmp_path: Path) -> None:
    """Decision 6a through the whole pipeline: ``down`` is in the route, is never called, and the
    step completes on ``up`` — with the jump readable in the stored result and in no audit event
    (§57, rule 23)."""
    clock, ids = FakeClock(), FakeIdGenerator()
    down = FakeModelProvider(clock, ids, name="down", status=ProviderStatus.UNAVAILABLE)
    up = FakeModelProvider(clock, ids, name="up")
    p = Pipeline(tmp_path / "workspace", model_providers=(down, up))

    step, task_id = await p.planned_and_running(MODEL_COMPLETE)
    await p.grant(task_id, step.id)
    execution = await p.execute(task_id, step.id)

    assert execution.graph.states[step.id] is StepState.COMPLETED
    assert down.requests == ()
    assert len(up.requests) == 1
    assert execution.result is not None
    assert execution.result.output["provider"] == "up"
    assert execution.result.output["skipped"] == ("down",)
    events = json.dumps([e.model_dump(mode="json") for e in await p.audit.read()])
    assert "skipped" not in events


async def test_an_unknown_task_type_fails_the_step_without_a_call(p: Pipeline) -> None:
    """Decision 7b end to end: the Guardian allows it — the schema says ``task_type`` is a
    string — and the *router* refuses it, before the network, with a code of its own."""
    step, task_id = await p.planned_and_running(
        MODEL_COMPLETE, arguments={**ARGUMENTS[MODEL_COMPLETE], "task_type": "telepathy"}
    )
    await p.grant(task_id, step.id)
    execution = await p.execute(task_id, step.id)

    assert execution.graph.states[step.id] is StepState.FAILED
    assert p.provider.requests == ()
    executed = next(
        e for e in await p.audit.read(task_id=task_id) if e.event_type is E.TOOL_EXECUTED
    )
    assert executed.error is not None
    assert executed.error.code == ROUTING_UNKNOWN_TASK_TYPE
    assert executed.error.retryable is False


async def test_an_interrupted_model_call_is_never_made_twice(p: Pipeline) -> None:
    """The reason the STARTED record exists (ADR 0021 §2): a crash before the outcome leaves a
    record, and the retry fails the step instead of calling — and charging — again."""
    step, task_id = await p.planned_and_running(MODEL_COMPLETE)
    asked = await p.execute(task_id, step.id)
    assert asked.approval is not None
    approval = await p.approvals.respond(
        asked.approval.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=p.clock.now()
    )
    await p.engine.approve(task_id, approval)
    await p.engine.start(task_id)

    # the crash: the STARTED record is written, the outcome never is
    stopped = _StoppingStore(p.results)
    p.executor._results = stopped  # noqa: SLF001
    with pytest.raises(_Crash):
        await p.execute(task_id, step.id)
    assert len(p.provider.requests) == 1
    p.executor._results = p.results  # noqa: SLF001

    execution = await p.execute(task_id, step.id)
    assert len(p.provider.requests) == 1  # the model is not asked again
    assert execution.graph.states[step.id] is StepState.FAILED
    assert execution.task.state is TaskState.EXECUTING
    executed = next(
        e for e in await p.audit.read(task_id=task_id) if e.event_type is E.TOOL_EXECUTED
    )
    assert executed.error is not None
    assert executed.error.code == EXECUTION_INTERRUPTED
    assert executed.error.retryable is True
    assert executed.payload["status"] == ExecutionStatus.STARTED.value


class _Crash(Exception):
    """The process dying between the tool's call and the insert of its outcome."""


class _StoppingStore:
    """The result store that accepts the STARTED record and dies on the outcome."""

    def __init__(self, inner: FakeExecutionResultStore) -> None:
        self._inner = inner

    async def add(self, result: ExecutionResult) -> None:
        if result.status is not ExecutionStatus.STARTED:
            raise _Crash
        await self._inner.add(result)

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        return await self._inner.get(result_id)

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        return await self._inner.for_step(task_id, step_id)


async def test_a_capability_outside_the_catalogue_is_refused_by_name(p: Pipeline) -> None:
    step, task_id = await p.planned_and_running(CapabilityId("nobody.knows_this"))
    with pytest.raises(CapabilityNotFound):
        await p.execute(task_id, step.id)
    assert await p.types(task_id) == LIFE_CYCLE


async def test_the_runner_walks_a_real_plan_end_to_end(p: Pipeline, workspace: Path) -> None:
    """The whole stack in one call: the production catalogue, the production tool and verifier,
    the orchestrator and the runner. Nobody starts the step or closes the task by hand."""
    step, task_id = await p.planned_and_running(WORKSPACE_WRITE_NOTE, start=False)

    run = await p.runner.run(task_id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)
    assert (workspace / NOTE_PATH).read_text(encoding="utf-8") == BODY
    assert await p.types(task_id) == [
        *LIFE_CYCLE[:4],
        E.DEVICE_SELECTED,
        E.TASK_STARTED,
        E.STEP_STARTED,
        E.PERMISSION_DECIDED,
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
        E.TASK_COMPLETED,
    ]


async def test_a_node_gone_quiet_leaves_a_real_plan_queued(p: Pipeline) -> None:
    """The Fase 12 case, on the production stack: the node stops answering and the task waits."""
    _, task_id = await p.planned_and_running(CORE_ECHO, start=False)
    p.clock.advance(HEARTBEAT_TTL * 2)

    run = await p.runner.run(task_id)

    assert run.outcome is RunOutcome.WAITING_DEVICE
    assert run.task.state is TaskState.QUEUED
    assert E.TASK_FAILED not in await p.types(task_id)

    await p.devices.heartbeat(p.device.id)
    assert (await p.runner.run(task_id)).outcome is RunOutcome.COMPLETED
