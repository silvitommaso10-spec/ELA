"""The step in progress when its task ends, and who closes it (M6.3c, ADR 0054 §3–§9).

* **The test of decision 1**: the reachable pairs «operation that ends the task × phase of the step»
  are a table **written by hand** — the product does not exist, and the SPEC says so (B-R18) —,
  closed on the operations: one that ends a task and has no row fails it. After each road, no task
  that has ended has a RUNNING step, **except three, and nothing else** (decisions 13 and 15): the
  step of a tool on the Core past its point that has not returned, the one of a node with a live
  claim, and the one of a lapsed claim until the first start-up or the first ``run`` of its task.
* ``close_open_step``, branch by branch; the executor that listens before the grant and spends no
  yes; the closing rule for ``_fail``, the refusal and the failure before the point; ``_close``,
  which does not fail a task that has ended; ``halt`` composed with the claim.
* The runner: the reason of a stop, never empty, even without its audit row; ``answer`` for the
  ``run`` that finds the lock taken; and the four empty reasons of M13.1c, still empty.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Final

import pytest

from ela.domain import (
    ApprovalStatus,
    Assignment,
    AssignmentState,
    AuditEventType,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    Halt,
    JsonMapping,
    PermissionDecision,
    PrivacyLevel,
    StepId,
    StepState,
    TaskEvent,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.executive import (
    EXECUTION_INTERRUPTED,
    EXECUTION_STOPPED,
    NOT_ACTED_REASON,
    NOT_REACHED,
    PASSED,
    POINT,
    Closing,
    ExecutorError,
    RunOutcome,
    Standing,
)
from ela.ports import AssignmentStateError, NotFoundError, StopPoint, TaskStop
from ela.tasks.engine import OPERATIONS, TERMINAL_STATES
from ela.tasks.errors import ClockSkewError
from ela.testing.fakes import FakeAssignmentStore, FakeAuthorizationStore, FakeClock, FakeTool
from tests.domain.examples import APPROVAL_ID
from tests.executive.support import (
    BAD,
    SimulatedCrash,
    World,
    audit_of,
    crashing_world,
    fake_tools,
    grant_for,
    saved_as,
    world,
)
from tests.executive.test_executor_remote import answered
from tests.executive.test_spending_gate import a_world
from tests.permissions.support import CRITICAL, ECHO, GUARDED_ECHO, NOTE
from tests.tasks.support import Harness, planning_denied

E = AuditEventType
POINT_NAME: Final = "the point"
INSTANT = timedelta(microseconds=1)


class Hooked(FakeTool):
    """The echo of the world with a point, and with what a test needs around the call: a wait
    before the point — the probe, the hash, the start of a browser —, a wait after it — the tool
    at work —, or a failure of its own before it."""

    def __init__(self, w: World, **options: Any) -> None:
        super().__init__(
            ECHO.id,
            w.clock,
            w.ids,
            name=f"fake-{ECHO.id}",
            output={"ok": True},
            stop_point=StopPoint(here=POINT_NAME, on_a_node=None),
            **options,
        )
        self.before: Callable[[], Awaitable[object]] | None = None
        self.during: Callable[[], Awaitable[object]] | None = None
        self.fails_before_the_point = False

    async def execute(
        self, decision: PermissionDecision, arguments: JsonMapping, stop: TaskStop
    ) -> ExecutionResult:
        if self.before is not None:
            await self.before()
        if self.fails_before_the_point:
            return _failed(await self._plain().execute(decision, arguments, _Unheard()))
        stop.listen(POINT_NAME)
        if self.during is not None:
            await self.during()
        return await self._plain().execute(decision, arguments, stop)

    def _plain(self) -> FakeTool:
        return FakeTool(ECHO.id, self._clock, self._ids, name=self.name, output=self.output)


def _failed(result: ExecutionResult) -> ExecutionResult:
    """A tool that failed before its point, and says why (§64; M13.1c, ADR 0055)."""
    error = ErrorMetadata(code="probe.before_the_point", message="the tool failed before its point")
    return result.model_copy(update={"status": ExecutionStatus.FAILED, "error": error})


class _Unheard:
    """A stop nobody listens to: what the plain fake inside :class:`Hooked` is handed."""

    def listen(self, where: str) -> None:
        raise AssertionError(f"the plain fake listened at {where}")

    def is_set(self) -> bool:
        return False

    def stopped(self) -> Awaitable[object]:
        return asyncio.Event().wait()


def hooked_world(**options: Any) -> tuple[World, Hooked]:
    built = world()
    tool = Hooked(built)
    tools = fake_tools(built.clock, built.ids)
    tools[ECHO.id] = tool
    fresh = world(tools=tools.values(), **options)
    return fresh, tool


async def handed(w: World) -> tuple[TaskId, StepId, Assignment]:
    """A step of an EXECUTING task offered to a node that is not this machine."""
    await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)
    run = await w.runner.run(task.id)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    return task.id, step.id, stand.assignment


async def running(w: World, task_id: TaskId) -> list[StepId]:
    if (await w.repository.get(task_id)).plan_id is None:
        return []  # a task that ended while planning (M14.2): no plan, so no step at all
    graph = await w.engine.graph(task_id)
    return [step for step, state in graph.states.items() if state is StepState.RUNNING]


async def stop(w: World, task_id: TaskId) -> None:
    await w.engine.cancel(task_id, reason="ferma")


# ----------------------------------------------------------------------------------------
# The test of decision 1: a table written by hand, closed on the operations
# ----------------------------------------------------------------------------------------

LIVE_TOOL: Final = "a tool on the Core past its point that has not returned"
LIVE_CLAIM: Final = "a node with a live claim"
LAPSED_CLAIM: Final = "a lapsed claim, until the first start-up or the first run of its task"
EXCEPTIONS: Final = frozenset({LIVE_TOOL, LIVE_CLAIM, LAPSED_CLAIM})
"""The three of criterion 2, and nothing else."""


@dataclass(frozen=True)
class Road:
    """One way a task ends with a step in some phase, and how production closes that step."""

    operation: str
    phase: str
    closed: StepState | None
    """The state of the step in progress once its closer has run; ``None`` when no step was in
    progress at the end."""
    exception: str | None
    scenario: Callable[[], Awaitable[Ended]]


@dataclass(frozen=True)
class Ended:
    w: World
    task_id: TaskId
    step_id: StepId | None
    running_at_the_end: list[StepId]
    """The RUNNING steps right after the operation and before any closer: what the exceptions
    leave."""


async def _closed_by_the_route(w: World, task_id: TaskId) -> None:
    """The route of the «ferma» and of the no, with the lock free: the open step closed."""
    await w.executor.close_open_step(task_id)


async def cancel_asking() -> Ended:
    w = world()
    task, (step,) = await w.queued(GUARDED_ECHO.id)
    assert (await w.runner.run(task.id)).outcome is RunOutcome.WAITING_APPROVAL
    await stop(w, task.id)
    at_the_end = await running(w, task.id)
    await _closed_by_the_route(w, task.id)
    return Ended(w, task.id, step.id, at_the_end)


async def no_while_asking() -> Ended:
    w = world()
    task, (step,) = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)
    (request,) = await w.approvals.for_task(task.id)
    await w.engine.deny(task.id, approval=await w.answered(request, status=ApprovalStatus.REJECTED))
    at_the_end = await running(w, task.id)
    await _closed_by_the_route(w, task.id)
    return Ended(w, task.id, step.id, at_the_end)


async def question_expired() -> Ended:
    w = world(approval_ttl=timedelta(minutes=5))
    task, (step,) = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)
    w.clock.advance(timedelta(minutes=5))
    summary = await w.engine.recover()
    assert [t.id for t in summary.expired] == [task.id]
    at_the_end = await running(w, task.id)
    await w.executor.close_every_open_step()
    return Ended(w, task.id, step.id, at_the_end)


async def _nothing(w: World) -> tuple[TaskId, StepId]:
    task, step = await w.running(ECHO.id)
    return task.id, step.id


async def cancel_nothing() -> Ended:
    w = world()
    task_id, step_id = await _nothing(w)
    await stop(w, task_id)
    at_the_end = await running(w, task_id)
    await _closed_by_the_route(w, task_id)
    return Ended(w, task_id, step_id, at_the_end)


async def orphan_nothing() -> Ended:
    w = world()
    task_id, step_id = await _nothing(w)
    w.clock.advance(timedelta(minutes=5))
    await w.engine.recover()
    at_the_end = await running(w, task_id)
    await w.executor.close_every_open_step()
    return Ended(w, task_id, step_id, at_the_end)


async def _started(w: World) -> tuple[TaskId, StepId]:
    """A STARTED record and nothing after it: the tool cannot be repeated, and the process died
    between its call and the insert of its outcome."""
    task, step = await w.running(ECHO.id)
    w.tool(ECHO.id).idempotent = False
    stores: Any = w.results
    adding = stores.add

    async def dying(result: ExecutionResult) -> None:
        if result.status is not ExecutionStatus.STARTED:
            raise SimulatedCrash("the outcome was never stored")
        await adding(result)

    stores.add = dying
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    stores.add = adding
    return task.id, step.id


async def cancel_started() -> Ended:
    w = world()
    task_id, step_id = await _started(w)
    await stop(w, task_id)
    at_the_end = await running(w, task_id)
    await _closed_by_the_route(w, task_id)
    return Ended(w, task_id, step_id, at_the_end)


async def orphan_started() -> Ended:
    w = world()
    task_id, step_id = await _started(w)
    w.clock.advance(timedelta(minutes=5))
    await w.engine.recover()
    at_the_end = await running(w, task_id)
    await w.executor.close_every_open_step()
    return Ended(w, task_id, step_id, at_the_end)


async def _settled(*, before_the_point: bool = False) -> tuple[World, TaskId, StepId]:
    """An outcome stored and never recorded: the process died before ``TOOL_EXECUTED``."""
    built = world()
    tool = Hooked(built)
    tool.fails_before_the_point = before_the_point
    tools = fake_tools(built.clock, built.ids)
    tools[ECHO.id] = tool
    w, crashes = crashing_world(tools=tools.values())
    task, step = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TOOL_EXECUTED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()
    (stored,) = await w.results.for_step(task.id, step.id)
    assert stored.metadata[POINT] == (NOT_REACHED if before_the_point else PASSED)
    return w, task.id, step.id


async def cancel_settled() -> Ended:
    w, task_id, step_id = await _settled()
    await stop(w, task_id)
    at_the_end = await running(w, task_id)
    await _closed_by_the_route(w, task_id)
    return Ended(w, task_id, step_id, at_the_end)


async def cancel_settled_before_the_point() -> Ended:
    w, task_id, step_id = await _settled(before_the_point=True)
    await stop(w, task_id)
    at_the_end = await running(w, task_id)
    await _closed_by_the_route(w, task_id)
    return Ended(w, task_id, step_id, at_the_end)


async def orphan_settled() -> Ended:
    w, task_id, step_id = await _settled()
    w.clock.advance(timedelta(minutes=5))
    await w.engine.recover()
    at_the_end = await running(w, task_id)
    await w.executor.close_every_open_step()
    return Ended(w, task_id, step_id, at_the_end)


async def cancel_offered() -> Ended:
    w = world()
    task_id, step_id, _ = await handed(w)
    await stop(w, task_id)
    at_the_end = await running(w, task_id)
    await _closed_by_the_route(w, task_id)
    return Ended(w, task_id, step_id, at_the_end)


async def cancel_claimed() -> Ended:
    """The node took the work: its claim is live, and its delivery closes the step."""
    w = world()
    task_id, step_id, offer = await handed(w)
    await w.executor.begin(offer.id, offer.device_id)
    await stop(w, task_id)
    await _closed_by_the_route(w, task_id)
    at_the_end = await running(w, task_id)
    await w.executor.deliver(offer.id, offer.device_id, answered())
    return Ended(w, task_id, step_id, at_the_end)


async def cancel_lapsed() -> Ended:
    """The claim ran out after the stop: the step stays RUNNING until the first start-up — here —
    or the first run of its task, and then closes from what the store holds."""
    w = world()
    task_id, step_id, offer = await handed(w)
    claimed = await w.executor.begin(offer.id, offer.device_id)
    await stop(w, task_id)
    await _closed_by_the_route(w, task_id)
    w.clock.advance(claimed.assignment.expires_at - w.clock.now() + INSTANT)
    at_the_end = await running(w, task_id)
    assert await w.executor.halt(task_id) is Halt.UNKNOWN
    await w.executor.close_every_open_step()
    return Ended(w, task_id, step_id, at_the_end)


async def cancel_tool_at_work() -> Ended:
    """A tool past its point, at work when the stop lands: the step stays RUNNING until the tool
    returns, and then closes as a normal one."""
    w, tool = hooked_world()
    task, step = await w.running(ECHO.id)
    reached, released = asyncio.Event(), asyncio.Event()

    async def working() -> None:
        reached.set()
        await released.wait()

    tool.during = working
    executing = asyncio.create_task(w.execute(task.id, step.id))
    await reached.wait()
    await stop(w, task.id)
    # The route of the «ferma» sees the lock of the run taken, and leaves the closing to it.
    at_the_end = await running(w, task.id)
    released.set()
    await executing
    return Ended(w, task.id, step.id, at_the_end)


async def guardian_says_no() -> Ended:
    w = world()
    task, (step,) = await w.queued(CRITICAL.id)
    run = await w.runner.run(task.id)
    assert run.outcome is RunOutcome.DENIED
    return Ended(w, task.id, step.id, [])


async def cap_says_no_here() -> Ended:
    """No cap on the Core (M14.1, ADR 0057): the Guardian allowed, and the call that spends is
    denied before its STARTED record, by the same run that would have made it."""
    w = a_world(cap=None)
    task, step = await w.running(ECHO.id)
    assert (await w.execute(task.id, step.id)).task.state is TaskState.DENIED
    return Ended(w, task.id, step.id, [])


async def cap_says_no_at_the_claim() -> Ended:
    """The cap at a node's claim: the offer is withdrawn and the node is sent nothing."""
    w = a_world(cap=None)
    task_id, step_id, offer = await handed(w)
    with pytest.raises(AssignmentStateError):
        await w.executor.begin(offer.id, offer.device_id)
    return Ended(w, task_id, step_id, [])


async def cap_says_no_before_asking() -> Ended:
    """The question a yes could not make pass is not asked (M14.1, review decision 7)."""
    w = a_world(cap=None)
    task, step = await w.running(NOTE.id, requires_authorization=True)
    execution = await w.execute(task.id, step.id)
    assert execution.task.state is TaskState.DENIED
    assert execution.approval is None
    return Ended(w, task.id, step.id, [])


async def fail_after_a_step_failed() -> Ended:
    w = world(failing=frozenset({ECHO.id}))
    task, (step,) = await w.queued(ECHO.id)
    assert (await w.runner.run(task.id)).outcome is RunOutcome.FAILED
    return Ended(w, task.id, None, await running(w, task.id))


async def complete() -> Ended:
    w = world()
    task, _ = await w.queued(ECHO.id)
    assert (await w.runner.run(task.id)).outcome is RunOutcome.COMPLETED
    return Ended(w, task.id, None, await running(w, task.id))


async def no_to_the_planning_call() -> Ended:
    """M14.2 (ADR 0058): a task whose planning call the user refused ends in PLANNING, where it has
    neither a plan nor a step — there is nothing to close."""
    w = world()
    parts = (w.repository, w.audit, w.clock, w.ids, w.approvals, w.engine)
    harness = Harness(*parts)  # type: ignore[arg-type]  # the world's fakes, typed as ports
    parent, child = await planning_denied(harness)
    await w.engine.deny_by_planning(parent.id, planning_task_id=child.id, reason="no")
    return Ended(w, parent.id, None, await running(w, parent.id))


ROADS: Final = (
    Road("cancel", "asking", StepState.CANCELLED, None, cancel_asking),
    Road("cancel", "nothing in the stores", StepState.CANCELLED, None, cancel_nothing),
    Road("cancel", "a STARTED record", StepState.FAILED, None, cancel_started),
    Road("cancel", "an outcome past the point", StepState.COMPLETED, None, cancel_settled),
    Road(
        "cancel",
        "an outcome before the point",
        StepState.CANCELLED,
        None,
        cancel_settled_before_the_point,
    ),
    Road("cancel", "offered to a node", StepState.CANCELLED, None, cancel_offered),
    Road("cancel", "claimed by a node", StepState.COMPLETED, LIVE_CLAIM, cancel_claimed),
    Road("cancel", "a lapsed claim", StepState.CANCELLED, LAPSED_CLAIM, cancel_lapsed),
    Road("cancel", "a tool at work", StepState.COMPLETED, LIVE_TOOL, cancel_tool_at_work),
    Road("deny_by_approval", "asking", StepState.CANCELLED, None, no_while_asking),
    Road("expire", "asking", StepState.CANCELLED, None, question_expired),
    Road("recover", "nothing in the stores", StepState.CANCELLED, None, orphan_nothing),
    Road("recover", "a STARTED record", StepState.FAILED, None, orphan_started),
    Road("recover", "an outcome past the point", StepState.COMPLETED, None, orphan_settled),
    Road("deny_by_decision", "being decided", StepState.CANCELLED, None, guardian_says_no),
    Road("deny_by_cap", "being gated here", StepState.CANCELLED, None, cap_says_no_here),
    Road("deny_by_cap", "being claimed", StepState.CANCELLED, None, cap_says_no_at_the_claim),
    Road("deny_by_cap", "about to ask", StepState.CANCELLED, None, cap_says_no_before_asking),
    Road("fail", "none: the step failed first", None, None, fail_after_a_step_failed),
    Road("complete", "none: every step completed", None, None, complete),
    Road("deny_by_planning", "none: a task still planning", None, None, no_to_the_planning_call),
)
OUTSIDE: Final = {
    "expire": "engine.expire from EXECUTING has no caller in src/ (B-R18): only the expiry of a "
    "question, from WAITING_APPROVAL, is a road"
}


def test_the_table_has_a_road_for_every_operation_that_ends_a_task() -> None:
    ending = {name for name, op in OPERATIONS.items() if op.target in TERMINAL_STATES}
    assert {road.operation for road in ROADS} == ending
    assert set(OUTSIDE) <= ending


def test_the_exceptions_are_three_and_nothing_else() -> None:
    assert {road.exception for road in ROADS} - {None} == EXCEPTIONS


@pytest.mark.parametrize("road", ROADS, ids=lambda road: f"{road.operation}-{road.phase}")
async def test_no_task_that_has_ended_keeps_a_running_step_but_the_three(road: Road) -> None:
    ended = await road.scenario()
    task = await ended.w.task(ended.task_id)

    assert task.state in TERMINAL_STATES
    if road.exception is None:
        assert ended.running_at_the_end in ([], [ended.step_id]), road
        assert await running(ended.w, ended.task_id) == []
    else:
        assert ended.running_at_the_end == [ended.step_id], road.exception
    if road.closed is None:
        assert ended.step_id is None
        assert await running(ended.w, ended.task_id) == []
    else:
        assert ended.step_id is not None
        assert await ended.w.step_state(ended.task_id, ended.step_id) is road.closed
    assert await running(ended.w, ended.task_id) == []


# ----------------------------------------------------------------------------------------
# close_open_step: the branches the table does not reach
# ----------------------------------------------------------------------------------------


async def test_close_open_step_wants_a_task_that_has_ended() -> None:
    w = world()
    task_id, _ = await _nothing(w)
    with pytest.raises(ExecutorError, match="an open step is closed in a task that has ended"):
        await w.executor.close_open_step(task_id)


@pytest.mark.parametrize("planning", [False, True], ids=["created", "planning"])
async def test_close_open_step_of_a_task_stopped_before_its_plan_finds_nothing(
    planning: bool,
) -> None:
    """Found by M14.2: the graph of a task with no plan does not exist, and the route of the stop
    answered 404 for a stop already written. No plan, no step: nothing to close."""
    w = world()
    task = await w.engine.create(w.intent())
    if planning:
        await w.engine.start_planning(task.id)
    await w.engine.cancel(task.id)

    assert await w.executor.close_open_step(task.id) is None


async def test_close_open_step_finds_nothing_to_close_twice() -> None:
    w = world()
    task_id, step_id = await _nothing(w)
    await stop(w, task_id)

    closed = await w.executor.close_open_step(task_id)

    assert closed is not None and closed.step_id == step_id
    assert await w.executor.close_open_step(task_id) is None


class _ClaimedFirst(FakeAssignmentStore):
    """A store where a node's claim lands between the read of the offer and its withdrawal."""

    claim_with: tuple[Any, Any] | None = None

    async def withdraw(self, assignment_id: Any, *, now: Any) -> Assignment:
        assert self.claim_with is not None
        device_id, expires_at = self.claim_with
        await self.claim(assignment_id, device_id=device_id, now=now, expires_at=expires_at)
        return await super().withdraw(assignment_id, now=now)


async def test_an_offer_claimed_before_its_withdrawal_is_left_to_its_node() -> None:
    store = _ClaimedFirst()
    w = world(assignment_store=store)
    task_id, step_id, offer = await handed(w)
    store.claim_with = (offer.device_id, offer.expires_at)
    await stop(w, task_id)

    assert await w.executor.close_open_step(task_id) is None

    (held,) = await store.for_step(task_id, step_id)
    assert held.state is AssignmentState.CLAIMED
    assert await w.step_state(task_id, step_id) is StepState.RUNNING
    assert await w.executor.halt(task_id) is Halt.FINISHING


async def test_a_lapsed_claim_with_a_started_record_closes_interrupted() -> None:
    """A tool that cannot be repeated leaves its STARTED record at the claim: when the claim
    lapses after the stop, whether the node acted is unknown, and the step says so."""
    w = world()
    w.tool(ECHO.id).idempotent = False
    task_id, step_id, offer = await handed(w)
    claimed = await w.executor.begin(offer.id, offer.device_id)
    await stop(w, task_id)
    w.clock.advance(claimed.assignment.expires_at - w.clock.now() + INSTANT)

    closed = await w.executor.close_open_step(task_id)

    assert closed is not None
    assert await w.step_state(task_id, step_id) is StepState.FAILED
    (expired,) = await w.assignments._store.for_step(task_id, step_id)  # noqa: SLF001
    assert expired.state is AssignmentState.EXPIRED
    failed = [e for e in await w.events(task_id) if e.event_type is E.STEP_FAILED]
    assert failed[-1].error is not None and failed[-1].error.code == EXECUTION_INTERRUPTED
    assert await w.executor.halt(task_id) is Halt.UNKNOWN


async def test_the_start_up_reads_every_task_that_ended_with_a_plan_and_counts_what_it_closed() -> (
    None
):
    w = world()
    done, _ = await w.queued(ECHO.id)
    await w.runner.run(done.id)
    open_id, _ = await _nothing(w)
    await stop(w, open_id)
    planless = await w.engine.create(w.intent())
    await w.engine.cancel(planless.id)

    assert await w.executor.close_every_open_step() == Closing(read=2, closed=1)
    assert await w.executor.close_every_open_step() == Closing(read=2, closed=0)


# ----------------------------------------------------------------------------------------
# The executor's own listening, and the closing rule
# ----------------------------------------------------------------------------------------


async def test_a_task_stopped_before_the_grant_spends_no_yes_and_calls_no_tool() -> None:
    """The stop lands while the Guardian decides — after the decision, before the grant is
    consumed: no use of the grant, no STARTED record, no tool, and the step CANCELLED."""
    w = world()
    task, step = await w.running(GUARDED_ECHO.id)
    w.tool(GUARDED_ECHO.id).idempotent = False
    granted = grant_for(
        GUARDED_ECHO, task=task, step=step, created_at=w.now, approval_id=APPROVAL_ID, max_uses=1
    )
    await w.store.grant(granted)
    log: Any = w.audit
    appending = log.append

    async def stopping_at_the_decision(event: Any) -> None:
        await appending(event)
        if event.event_type is E.PERMISSION_DECIDED:
            await stop(w, task.id)

    log.append = stopping_at_the_decision
    execution = await w.execute(task.id, step.id)

    assert execution.result is None
    assert await w.store.uses(granted.id) == 0
    assert await w.results.for_step(task.id, step.id) == ()
    assert w.tool(GUARDED_ECHO.id).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.CANCELLED
    assert await w.executor.halt(task.id) is Halt.NOT_ACTED


async def test_a_task_that_ended_before_the_call_is_closed_on_arrival() -> None:
    w = world()
    task_id, step_id = await _nothing(w)
    await stop(w, task_id)

    execution = await w.execute(task_id, step_id)

    assert execution.decision is None and execution.result is None
    assert execution.graph.states[step_id] is StepState.CANCELLED
    assert w.tool(ECHO.id).calls == ()
    again = await w.execute(task_id, step_id)
    assert again.result is None and again.task.state is TaskState.CANCELLED


async def test_a_tool_stopped_at_its_point_leaves_a_cancelled_result_and_did_not_act() -> None:
    """The stop lands after the executor's own look and before the tool's point — in the wait a
    tool has before it —, so the tool is the one that hears it: a ``CANCELLED`` result, with
    ``execution.stopped``, ``ExecutionStatus.CANCELLED``'s first producer (decision 10)."""
    w, tool = hooked_world()
    task, step = await w.running(ECHO.id)

    async def stopped_before_the_point() -> None:
        await stop(w, task.id)

    tool.before = stopped_before_the_point
    execution = await w.execute(task.id, step.id)

    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.CANCELLED
    assert execution.result.error is not None
    assert execution.result.error.code == EXECUTION_STOPPED
    assert execution.result.metadata[POINT] == NOT_REACHED
    assert tool.calls == ()
    assert await w.step_state(task.id, step.id) is StepState.CANCELLED
    assert await w.executor.halt(task.id) is Halt.NOT_ACTED


async def test_a_tool_past_its_point_says_so_in_its_result() -> None:
    w, _ = hooked_world()
    task, step = await w.running(ECHO.id)

    execution = await w.execute(task.id, step.id)

    assert execution.result is not None
    assert execution.result.metadata[POINT] == PASSED
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED


async def test_a_tool_whose_point_is_the_call_says_nothing_and_closes_from_its_result() -> None:
    """Decision 1 of the review: ``core.echo`` called and returned has acted; a stop after the
    call does not change it — the step closes COMPLETED, and the halt says it acted."""
    w = world()
    task, step = await w.running(ECHO.id)
    stores: Any = w.results
    adding = stores.add

    async def stopped_after_the_call(result: ExecutionResult) -> None:
        await adding(result)
        await stop(w, task.id)

    stores.add = stopped_after_the_call
    execution = await w.execute(task.id, step.id)

    assert execution.result is not None and POINT not in execution.result.metadata
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED
    assert (await w.task(task.id)).state is TaskState.CANCELLED
    assert await w.executor.halt(task.id) is Halt.ACTED_VERIFIED


async def test_a_tool_that_failed_before_its_point_did_not_act_if_its_task_ended() -> None:
    w, tool = hooked_world()
    tool.fails_before_the_point = True
    task, step = await w.running(ECHO.id)

    async def stopped_while_it_ran() -> None:
        await stop(w, task.id)

    tool.before = stopped_while_it_ran
    execution = await w.execute(task.id, step.id)

    assert execution.result is not None
    assert execution.result.status is ExecutionStatus.FAILED
    assert execution.result.metadata[POINT] == NOT_REACHED
    assert await w.step_state(task.id, step.id) is StepState.CANCELLED


async def test_a_tool_that_failed_before_its_point_fails_its_step_in_a_live_task() -> None:
    w, tool = hooked_world()
    tool.fails_before_the_point = True
    task, step = await w.running(ECHO.id)

    await w.execute(task.id, step.id)

    assert await w.step_state(task.id, step.id) is StepState.FAILED


async def test_a_verification_that_fails_after_the_stop_fails_the_step_and_not_the_task() -> None:
    """``_close`` on a task stopped while its tool ran: the step says how it went — the tool acted,
    its verification did not pass —, and the task stays CANCELLED."""
    w, tool = hooked_world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))

    async def stopped_while_it_ran() -> None:
        await stop(w, task.id)

    tool.during = stopped_while_it_ran
    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.CANCELLED
    assert await w.step_state(task.id, step.id) is StepState.FAILED
    assert (await w.event_types(task.id)).count(E.TASK_FAILED) == 0
    assert await w.executor.halt(task.id) is Halt.ACTED


async def test_a_refusal_of_a_task_still_alive_is_what_it_was() -> None:
    """The negative case of ``_close``: a refusal of the engine on a task that has not ended is
    not taken for a stop — here a clock that went backwards between the step and the task."""
    w = world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    engine_fail = w.engine.fail

    async def behind(task_id: TaskId, error: Any) -> Any:
        w.engine._clock = FakeClock(w.now - timedelta(seconds=1))  # noqa: SLF001
        return await engine_fail(task_id, error)

    w.engine.fail = behind  # type: ignore[method-assign]

    with pytest.raises(ClockSkewError):
        await w.execute(task.id, step.id)
    assert (await w.task(task.id)).state is TaskState.EXECUTING


class _VanishingWhileStopped(FakeAuthorizationStore):
    """A grant gone by the time it is consumed — and the task stopped in that same instant."""

    stopping: Callable[[], Awaitable[None]] | None = None

    async def consume(self, authorization_id: Any, *, now: Any) -> int:
        assert self.stopping is not None
        await self.stopping()
        raise NotFoundError("authorization", authorization_id)


async def test_a_vanished_grant_on_a_task_that_ended_closes_the_step_cancelled() -> None:
    """``_fail``: nothing ran — the grant vanished between the decision and the consume — and the
    task was stopped meanwhile. The step did not act, and closes CANCELLED, never FAILED."""
    grants = _VanishingWhileStopped()
    w = world(store=grants)
    task, step = await w.running(NOTE.id, requires_authorization=True)
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    async def stopping() -> None:
        await stop(w, task.id)

    grants.stopping = stopping
    execution = await w.execute(task.id, step.id)

    assert execution.result is None
    stopped = [e for e in await w.events(task.id) if e.event_type is AuditEventType.STEP_CANCELLED]
    assert stopped, "the step closes CANCELLED: the grant vanished and the task had ended"
    assert w.tool(NOTE.id).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.CANCELLED


# ----------------------------------------------------------------------------------------
# The node: a claim of an offer whose task ended, and the renewal of a claim of one
# ----------------------------------------------------------------------------------------


async def test_a_claim_of_an_offer_whose_task_ended_finds_nothing_to_take() -> None:
    w = world()
    task_id, step_id, offer = await handed(w)
    await stop(w, task_id)

    with pytest.raises(AssignmentStateError) as refused:
        await w.executor.begin(offer.id, offer.device_id)

    assert refused.value.state is AssignmentState.WITHDRAWN
    (held,) = await w.assignments._store.for_step(task_id, step_id)  # noqa: SLF001
    assert held.state is AssignmentState.WITHDRAWN
    assert await w.step_state(task_id, step_id) is StepState.CANCELLED
    assert (await w.assignments.standing(task_id, step_id)).standing is Standing.NONE


async def test_the_renewal_of_a_claim_whose_task_ended_signs_no_life_and_lives_on() -> None:
    w = world()
    task_id, _, offer = await handed(w)
    claimed = await w.executor.begin(offer.id, offer.device_id)
    await stop(w, task_id)
    trail = len(await w.repository.events(task_id))
    w.clock.advance(timedelta(seconds=10))

    renewed = await w.assignments.renew(offer.id, offer.device_id)

    assert renewed.expires_at > claimed.assignment.expires_at
    events: tuple[TaskEvent, ...] = await w.repository.events(task_id)
    assert len(events) == trail
    assert TaskEventType.HEARTBEAT not in [e.event_type for e in events[trail:]]


async def test_the_halt_of_a_live_claim_is_finishing_and_of_a_task_not_stopped_is_none() -> None:
    w = world()
    task_id, _, offer = await handed(w)
    await w.executor.begin(offer.id, offer.device_id)
    assert await w.executor.halt(task_id) is None
    await stop(w, task_id)
    assert await w.executor.halt(task_id) is Halt.FINISHING


# ----------------------------------------------------------------------------------------
# The runner: the reason of a stop, the answer at a taken lock, and M13.1c's four
# ----------------------------------------------------------------------------------------


async def test_the_reason_of_a_stop_is_the_summary_of_its_audit_event() -> None:
    w = world()
    task_id, _ = await _nothing(w)
    await stop(w, task_id)

    run = await w.runner.run(task_id)

    assert run.outcome is RunOutcome.CANCELLED
    assert run.reason == "cancel: EXECUTING -> CANCELLED (ferma)"
    assert run.halt is Halt.NOT_ACTED


async def test_without_its_audit_row_the_reason_is_the_trail_s_with_its_operation() -> None:
    """A crash between the row of the task and its audit: the reason is still never empty."""
    w, crashes = crashing_world()
    task, _ = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TASK_CANCELLED))
    with pytest.raises(SimulatedCrash):
        await w.engine.cancel(task.id, reason="ferma")
    crashes.disarm()

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.CANCELLED
    assert run.reason == "cancel: ferma"


async def test_a_stop_without_words_is_still_named_by_its_operation() -> None:
    w, crashes = crashing_world()
    task, _ = await w.running(ECHO.id)
    crashes.audit.arm("append", audit_of(E.TASK_CANCELLED))
    with pytest.raises(SimulatedCrash):
        await w.engine.cancel(task.id)
    crashes.disarm()

    run = await w.runner.run(task.id)

    assert run.reason == "cancel"


async def test_a_state_no_transition_wrote_is_named_by_the_state() -> None:
    """The last answer of the reason, for a state neither the audit nor the trail has a
    transition to — which the engine never leaves: asked of a task value, not written in a store.
    Never empty. Since M13.1e the runner reads it from the engine's one reading (ADR 0059)."""
    w = world()
    task = await w.engine.create(w.intent())
    claimed = task.model_copy(update={"state": TaskState.CANCELLED})

    assert await w.runner._reason(claimed) == "CANCELLED"  # noqa: SLF001


async def test_answer_says_the_outcome_at_the_door_and_closes_nothing() -> None:
    """For the ``run`` that finds the lock held by another (decision 16): never a 409 for a task
    that was stopped, and nothing written — whoever holds the lock closes."""
    w = world()
    task_id, step_id = await _nothing(w)
    await stop(w, task_id)
    before = len(await w.events(task_id))

    run = await w.runner.answer(task_id)

    assert run.outcome is RunOutcome.CANCELLED
    assert run.reason == "cancel: EXECUTING -> CANCELLED (ferma)"
    assert run.halt is Halt.FINISHING
    assert run.steps == ()
    assert len(await w.events(task_id)) == before
    assert await w.step_state(task_id, step_id) is StepState.RUNNING


async def test_a_task_failed_by_somebody_else_under_the_run_is_said_with_that_end() -> None:
    """The walk finds its task ended by another writer — the orphan's recovery, here, while the
    tool worked: the outcome is the end that was written, with its words."""
    w, tool = hooked_world()
    task, (step,) = await w.queued(ECHO.id)

    async def orphaned_meanwhile() -> None:
        w.clock.advance(timedelta(minutes=10))
        await w.engine.recover()

    tool.during = orphaned_meanwhile
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.reason is not None and run.reason.startswith("recover: EXECUTING -> FAILED")
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED


async def transition_summary(w: World, task_id: TaskId) -> str:
    """The summary of the audit event that put the task in its state (ADR 0054 §7, ADR 0055)."""
    state = (await w.task(task_id)).state
    return next(
        event.summary
        for event in reversed(await w.events(task_id))
        if event.payload.get("new_state") == state.value
    )


async def test_an_interrupted_step_fails_the_task_with_the_words_of_its_transition() -> None:
    """M13.1c turned this case (decision D of its session): the run that closes the task and the run
    after it say the same reason, the transition's, with the code beside the message."""
    w = world()
    task_id, _ = await _started(w)

    run = await w.runner.run(task_id)
    again = await w.runner.run(task_id)

    assert run.outcome is RunOutcome.FAILED
    assert run.reason == again.reason == await transition_summary(w, task_id)
    assert (
        run.reason is not None
        and "fail: EXECUTING -> FAILED (execution.interrupted: " in run.reason
    )


async def test_a_plan_blocked_at_the_resume_fails_the_task_with_the_words_of_its_transition() -> (
    None
):
    """Window R6, the other way to the row of a failure a node delivered: the call that fails the
    task has no execution of its own, and still says why."""
    w, crashes = crashing_world(failing=frozenset({ECHO.id}))
    task, _ = await w.queued(ECHO.id, NOTE.id)
    crashes.repository.arm("save", saved_as(TaskState.FAILED))
    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)
    crashes.disarm()

    run = await w.runner.run(task.id)
    again = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.reason == again.reason == await transition_summary(w, task.id)
    assert run.reason is not None and run.reason.startswith("fail: EXECUTING -> FAILED (")


async def test_execute_called_on_a_step_whose_verification_failed_fails_the_task_it_left_open() -> (
    None
):
    """The contract of ``execute`` (and ``finish``) called directly on a step a verification failed,
    whose task a crash left open (ADR 0015 §7): the task is failed, and nothing else is in the
    answer. **Not a branch of ``run``** (decision 3 of the review of M13.1c, ADR 0055): the runner
    sees the blocked plan first and fails the task itself — the row of a blocked plan, with its
    reason."""
    w, crashes = crashing_world()
    task, step = await w.running(ECHO.id, conditions=(BAD,))
    crashes.repository.arm("save", saved_as(TaskState.FAILED))
    with pytest.raises(SimulatedCrash):
        await w.execute(task.id, step.id)
    crashes.disarm()

    closed = await w.execute(task.id, step.id)

    assert closed.task.state is TaskState.FAILED
    assert (closed.result, closed.verification) == (None, None)


async def test_a_task_failed_by_another_between_the_two_reads_is_said_with_that_end() -> None:
    """Row 13 of the table of M13.1c, theoretical in production — ``recover()`` runs only at
    start-up —: the end is written after the runner read the task and before the executor does. The
    executor answers with the task already FAILED, the states the runner compares are equal, and
    until M13.1c the reason was the executor's word about a call that ran nothing: none."""
    w = world()
    task, _ = await w.queued(ECHO.id)
    executing = w.executor.execute

    async def ended_before(task_id: TaskId, step_id: StepId, **kwargs: Any) -> Any:
        await w.engine.fail(task_id, ErrorMetadata(code="probe.ended", message="by another"))
        return await executing(task_id, step_id, **kwargs)

    w.executor.execute = ended_before  # type: ignore[method-assign]
    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert run.reason == "fail: EXECUTING -> FAILED (probe.ended: by another)"


def test_the_reason_a_step_did_not_act_is_one_sentence() -> None:
    assert NOT_ACTED_REASON == "the task ended before the tool of this step acted"


async def test_finishing_a_step_of_a_task_still_waiting_is_refused() -> None:
    """``finish`` on a task that has not ended and is not EXECUTING: nothing to finish, and
    nothing to close — the refusal it always gave."""
    w = world()
    task, _ = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)
    (step,) = await running(w, task.id)

    with pytest.raises(ExecutorError, match="finishing a step needs an EXECUTING task"):
        await w.executor.finish(task.id, step)


async def test_a_refusal_of_the_engine_in_a_live_walk_is_what_it_was() -> None:
    """The negative case of the runner's reading after a ``TaskError``: the task did not end, so
    the error is not a stop — here a clock behind the task's trail, in the middle of the walk."""
    w, tool = hooked_world()
    task, _ = await w.queued(ECHO.id)

    async def behind() -> None:
        w.engine._clock = FakeClock(w.now - timedelta(seconds=1))  # noqa: SLF001

    tool.during = behind

    with pytest.raises(ClockSkewError):
        await w.runner.run(task.id)
    assert (await w.task(task.id)).state is TaskState.EXECUTING


async def test_a_task_waiting_for_its_yes_is_answered_at_the_door_without_a_halt() -> None:
    w = world()
    task, (step,) = await w.queued(GUARDED_ECHO.id)
    await w.runner.run(task.id)

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.WAITING_APPROVAL
    assert (again.steps, again.reason, again.halt) == ((), None, None)
    assert await w.step_state(task.id, step.id) is StepState.RUNNING
