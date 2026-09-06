"""The step operations of the Task Engine (M3.2, ADR 0009): the graph, persisted in the trail.

Every case drives a real EXECUTING task with a real plan through the engine. Where the engine
refuses, the task, its trail and the audit trail are checked to be exactly as before (§33).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

from ela.domain import (
    AuditEventType,
    ExecutionStatus,
    StepId,
    StepState,
    TaskEvent,
    TaskEventId,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAuditLog,
    SqlTaskRepository,
    make_engine,
    verify_chain,
)
from ela.infrastructure.persistence.orm import Base
from ela.ports import NotFoundError
from ela.tasks.engine import STEP_OPERATIONS, SYSTEM_ACTOR, TaskEngine
from ela.tasks.errors import (
    ClockSkewError,
    CyclicDependencyError,
    IllegalStepTransitionError,
    InvalidGraphError,
    TaskEngineError,
    UnknownStepError,
)
from ela.tasks.graph import GraphState
from ela.testing.fakes import FakeClock, FakeIdGenerator
from tests.domain.examples import DEVICE_ID, ELA_ACTOR
from tests.tasks.graphs import chain, diamond, sid, step
from tests.tasks.support import (
    ERROR,
    HOUR,
    ORPHAN_AFTER,
    Harness,
    dag_plan_for,
    executing,
    executing_with,
    h,
    planning,
    result_for,
    step_result_for,
    task_in,
)

__all__ = ["h"]

S = TaskState
P = StepState


async def run(h: Harness, task_id: TaskId, *steps: StepId) -> GraphState:
    """Start and complete each step in turn (the caller passes them in a legal order)."""
    state = await h.engine.graph(task_id)
    for n, step_id in enumerate(steps):
        await h.engine.start_step(task_id, step_id)
        state = await h.engine.complete_step(
            task_id, step_id, step_result_for(task_id, step_id, tail=940 + n)
        )
    return state


def step_events(events: tuple[TaskEvent, ...]) -> list[TaskEvent]:
    return [e for e in events if e.event_type.name.startswith("STEP_")]


# --------------------------------------------------------------------------------------
# The legal case of every row
# --------------------------------------------------------------------------------------


async def test_start_step_records_a_trail_event_and_an_audit_event(h: Harness) -> None:
    task = await executing_with(h, diamond())
    state = await h.engine.start_step(task.id, sid(0), device_id=DEVICE_ID)
    assert state.states[sid(0)] is P.RUNNING
    assert state.ready() == ()
    assert (await h.repository.get(task.id)).state is S.EXECUTING
    event = (await h.repository.events(task.id))[-1]
    assert event.event_type is TaskEventType.STEP_STARTED
    assert event.step_id == sid(0)
    assert event.metadata == {"operation": "start_step"}
    assert event.message == f"on device {DEVICE_ID}"
    assert event.previous_state is None and event.new_state is None
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.STEP_STARTED
    assert audit.actor == ELA_ACTOR
    assert audit.task_id == task.id and audit.step_id == sid(0)
    assert audit.device_id == DEVICE_ID
    assert audit.payload == {
        "operation": "start_step",
        "step_id": str(sid(0)),
        "previous_step_state": "PENDING",
        "new_step_state": "RUNNING",
        "reason": f"on device {DEVICE_ID}",
    }
    assert audit.summary == f"start_step: step {sid(0)} PENDING -> RUNNING (on device {DEVICE_ID})"


async def test_complete_step_records_the_result_as_the_key(h: Harness) -> None:
    task = await executing_with(h, chain(2))
    await h.engine.start_step(task.id, sid(0))
    result = step_result_for(task.id, sid(0))
    state = await h.engine.complete_step(task.id, sid(0), result)
    assert state.states == {sid(0): P.COMPLETED, sid(1): P.PENDING}
    assert state.ready() == (sid(1),)
    event = (await h.repository.events(task.id))[-1]
    assert event.event_type is TaskEventType.STEP_COMPLETED
    assert event.metadata == {"operation": "complete_step", "result_id": str(result.id)}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.STEP_COMPLETED
    assert audit.step_id == sid(0) and audit.device_id == result.device_id
    assert audit.payload["result_id"] == str(result.id)
    assert audit.payload["capability_id"] == result.capability_id
    assert audit.payload["tool_name"] == result.tool_name
    assert audit.payload["new_step_state"] == "COMPLETED"


async def test_fail_step_cancels_every_pending_descendant_with_the_reason(h: Harness) -> None:
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    audits_before = len(await h.audit.read())
    state = await h.engine.fail_step(task.id, sid(0), ERROR)
    assert state.states == {
        sid(0): P.FAILED,
        sid(1): P.CANCELLED,
        sid(2): P.CANCELLED,
        sid(3): P.CANCELLED,
    }
    assert state.is_blocked and not state.is_complete and state.ready() == ()
    assert (await h.repository.get(task.id)).state is S.EXECUTING  # the task is not moved
    events = step_events(await h.repository.events(task.id))
    assert [(e.event_type, e.step_id) for e in events] == [
        (TaskEventType.STEP_STARTED, sid(0)),
        (TaskEventType.STEP_FAILED, sid(0)),
        (TaskEventType.STEP_CANCELLED, sid(1)),
        (TaskEventType.STEP_CANCELLED, sid(2)),
        (TaskEventType.STEP_CANCELLED, sid(3)),
    ]
    reason = f"dependency {sid(0)} failed: {ERROR.message}"
    assert events[1].message == ERROR.message
    assert events[1].metadata == {"operation": "fail_step"}
    for cancelled in events[2:]:
        assert cancelled.message == reason
        assert cancelled.metadata == {"operation": "cancel_step", "cause_step_id": str(sid(0))}
    audits = (await h.audit.read())[audits_before:]
    assert [a.event_type for a in audits] == [
        AuditEventType.STEP_FAILED,
        AuditEventType.STEP_CANCELLED,
        AuditEventType.STEP_CANCELLED,
        AuditEventType.STEP_CANCELLED,
    ]
    assert audits[0].actor == ELA_ACTOR and audits[0].error == ERROR
    assert audits[0].payload["code"] == ERROR.code and audits[0].payload["reason"] == ERROR.message
    for cancelled_audit, step_id in zip(audits[1:], (sid(1), sid(2), sid(3)), strict=True):
        assert cancelled_audit.actor == SYSTEM_ACTOR
        assert cancelled_audit.step_id == step_id
        assert cancelled_audit.error is None
        assert cancelled_audit.payload == {
            "operation": "cancel_step",
            "step_id": str(step_id),
            "previous_step_state": "PENDING",
            "new_step_state": "CANCELLED",
            "reason": reason,
            "cause_step_id": str(sid(0)),
        }


async def test_fail_step_leaves_independent_and_finished_steps_alone(h: Harness) -> None:
    forest = (step(0), step(1), step(2, sid(0)), step(3, sid(1)))
    task = await executing_with(h, forest)
    await run(h, task.id, sid(1), sid(3))
    await h.engine.start_step(task.id, sid(0))
    state = await h.engine.fail_step(task.id, sid(0), ERROR)
    assert state.states == {
        sid(0): P.FAILED,
        sid(1): P.COMPLETED,
        sid(2): P.CANCELLED,
        sid(3): P.COMPLETED,
    }


async def test_a_running_dependent_cannot_exist_so_only_pending_ones_are_cancelled(
    h: Harness,
) -> None:
    """Steps 1 and 2 both depend on 0; 2 is already RUNNING when 1 fails: nothing to cancel."""
    task = await executing_with(h, (step(0), step(1, sid(0)), step(2, sid(0)), step(3, sid(1))))
    await run(h, task.id, sid(0))
    await h.engine.start_step(task.id, sid(1))
    await h.engine.start_step(task.id, sid(2))
    state = await h.engine.fail_step(task.id, sid(1), ERROR)
    assert state.states[sid(2)] is P.RUNNING and state.states[sid(3)] is P.CANCELLED


async def test_the_whole_diamond_runs_to_completion(h: Harness) -> None:
    task = await executing_with(h, diamond())
    state = await run(h, task.id, sid(0), sid(1), sid(2), sid(3))
    assert state.is_complete and not state.is_blocked and state.ready() == ()
    completed = await h.engine.complete(task.id, result_for(task.id))
    assert completed.state is S.COMPLETED


# --------------------------------------------------------------------------------------
# Refusals: nothing written
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("state", [s for s in S if s is not S.EXECUTING], ids=str)
@pytest.mark.parametrize("operation", ["start_step", "complete_step", "fail_step"])
async def test_step_operations_need_an_executing_task(
    h: Harness, state: TaskState, operation: str
) -> None:
    task = await task_in(h, state)
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=f"{operation} needs an EXECUTING task"):
        await call(h, operation, task.id, sid(0))
    assert await h.snapshot(task.id) == before


async def call(h: Harness, operation: str, task_id: TaskId, step_id: StepId) -> GraphState:
    if operation == "start_step":
        return await h.engine.start_step(task_id, step_id)
    if operation == "complete_step":
        return await h.engine.complete_step(task_id, step_id, step_result_for(task_id, step_id))
    assert operation == "fail_step"
    return await h.engine.fail_step(task_id, step_id, ERROR)


@pytest.mark.parametrize("operation", ["start_step", "complete_step", "fail_step"])
async def test_an_unknown_step_is_refused(h: Harness, operation: str) -> None:
    task = await executing_with(h, diamond())
    before = await h.snapshot(task.id)
    with pytest.raises(UnknownStepError) as excinfo:
        await call(h, operation, task.id, sid(9))
    assert excinfo.value.step_id == sid(9)
    assert await h.snapshot(task.id) == before


async def test_start_step_needs_every_dependency_completed(h: Harness) -> None:
    task = await executing_with(h, diamond())
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=f"step {sid(3)} is not ready: waiting for"):
        await h.engine.start_step(task.id, sid(3))
    assert await h.snapshot(task.id) == before
    await h.engine.start_step(task.id, sid(0))  # RUNNING is not COMPLETED
    with pytest.raises(TaskEngineError, match=f"waiting for {sid(0)}"):
        await h.engine.start_step(task.id, sid(1))
    await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))
    assert (await h.engine.start_step(task.id, sid(1))).states[sid(1)] is P.RUNNING


@pytest.mark.parametrize(
    ("operation", "current", "requested"),
    [
        ("complete_step", "PENDING", "COMPLETED"),
        ("fail_step", "PENDING", "FAILED"),
    ],
)
async def test_a_pending_step_cannot_end(
    h: Harness, operation: str, current: str, requested: str
) -> None:
    task = await executing_with(h, chain(1))
    before = await h.snapshot(task.id)
    with pytest.raises(IllegalStepTransitionError) as excinfo:
        await call(h, operation, task.id, sid(0))
    assert (excinfo.value.current, excinfo.value.requested) == (current, requested)
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("operation", ["start_step", "complete_step", "fail_step"])
async def test_a_terminal_step_never_moves_again(h: Harness, operation: str) -> None:
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    await h.engine.fail_step(task.id, sid(0), ERROR)
    before = await h.snapshot(task.id)
    # Step 1 is CANCELLED: no row of the table starts there.
    with pytest.raises(IllegalStepTransitionError, match="CANCELLED"):
        await call(h, operation, task.id, sid(1))
    assert await h.snapshot(task.id) == before


async def test_complete_step_needs_a_succeeded_result_of_this_task_and_step(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="about task"):
        await h.engine.complete_step(task.id, sid(0), step_result_for(TaskId(UUID(int=9)), sid(0)))
    with pytest.raises(TaskEngineError, match="about step"):
        await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(1)))
    for status in ExecutionStatus:
        if status is not ExecutionStatus.SUCCEEDED:
            with pytest.raises(TaskEngineError, match="not SUCCEEDED"):
                await h.engine.complete_step(
                    task.id, sid(0), step_result_for(task.id, sid(0), status)
                )
    assert await h.snapshot(task.id) == before


async def test_a_clock_that_went_backwards_is_refused_for_steps_too(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    before = await h.snapshot(task.id)
    behind = TaskEngine(
        h.repository,
        h.audit,
        FakeClock(h.clock.now() - timedelta(seconds=1)),
        h.ids,
        approvals=h.approvals,
        actor=ELA_ACTOR,
        orphan_after=HOUR,
    )
    with pytest.raises(ClockSkewError):
        await behind.start_step(task.id, sid(0))
    assert await h.snapshot(task.id) == before


async def test_after_the_task_is_cancelled_the_steps_stay_as_they_were(h: Harness) -> None:
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    await h.engine.cancel(task.id, reason="changed my mind")
    state = await h.engine.graph(task.id)
    assert state.states[sid(0)] is P.RUNNING and state.states[sid(1)] is P.PENDING
    with pytest.raises(TaskEngineError, match="needs an EXECUTING task"):
        await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))


# --------------------------------------------------------------------------------------
# Idempotency and the crash window of the cascade (ADR 0009)
# --------------------------------------------------------------------------------------


async def test_start_step_twice_writes_once(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    first = await h.engine.start_step(task.id, sid(0))
    after = await h.snapshot(task.id)
    second = await h.engine.start_step(task.id, sid(0), device_id=DEVICE_ID)
    assert second.states == first.states
    assert await h.snapshot(task.id) == after


async def test_complete_step_twice_with_the_same_result_writes_once(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    result = step_result_for(task.id, sid(0))
    first = await h.engine.complete_step(task.id, sid(0), result)
    after = await h.snapshot(task.id)
    assert (await h.engine.complete_step(task.id, sid(0), result)).states == first.states
    assert await h.snapshot(task.id) == after


async def test_complete_step_with_another_result_is_refused(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))
    after = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=f"step {sid(0)} already COMPLETED with result_id"):
        await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0), tail=941))
    assert await h.snapshot(task.id) == after


async def test_a_keyed_step_no_op_reads_past_other_events_of_the_step(h: Harness) -> None:
    """The key lives on the last STEP_* event of the step, not on its last event of any type."""
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    result = step_result_for(task.id, sid(0))
    first = await h.engine.complete_step(task.id, sid(0), result)
    await h.repository.append_event(
        TaskEvent(
            id=TaskEventId(h.ids.new_uuid()),
            created_at=h.clock.now(),
            task_id=task.id,
            event_type=TaskEventType.NOTE,
            step_id=sid(0),
            message="a note about the step, after it completed",
        )
    )
    after = await h.snapshot(task.id)
    assert (await h.engine.complete_step(task.id, sid(0), result)).states == first.states
    assert await h.snapshot(task.id) == after


async def test_fail_step_twice_writes_once(h: Harness) -> None:
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    first = await h.engine.fail_step(task.id, sid(0), ERROR)
    after = await h.snapshot(task.id)
    assert (await h.engine.fail_step(task.id, sid(0), ERROR)).states == first.states
    assert await h.snapshot(task.id) == after


async def test_a_cascade_cut_short_by_a_crash_is_completed_by_the_retry(h: Harness) -> None:
    """The repository is written by hand, on purpose: STEP_FAILED stored, no cancellation."""
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    await h.repository.append_event(
        TaskEvent(
            id=TaskEventId(h.ids.new_uuid()),
            created_at=h.clock.now(),
            task_id=task.id,
            event_type=TaskEventType.STEP_FAILED,
            step_id=sid(0),
            metadata={"operation": "fail_step"},
        )
    )
    audits_before = len(await h.audit.read())
    state = await h.engine.fail_step(task.id, sid(0), ERROR)
    assert state.states == {
        sid(0): P.FAILED,
        sid(1): P.CANCELLED,
        sid(2): P.CANCELLED,
        sid(3): P.CANCELLED,
    }
    events = step_events(await h.repository.events(task.id))
    assert [e.event_type for e in events].count(TaskEventType.STEP_FAILED) == 1
    assert [e.event_type for e in events].count(TaskEventType.STEP_CANCELLED) == 3
    audits = (await h.audit.read())[audits_before:]
    assert [a.event_type for a in audits] == [AuditEventType.STEP_CANCELLED] * 3


async def test_a_partial_cascade_is_completed_without_repeating_what_is_done(h: Harness) -> None:
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    now = h.clock.now()
    for kind, step_id in (
        (TaskEventType.STEP_FAILED, sid(0)),
        (TaskEventType.STEP_CANCELLED, sid(1)),
    ):
        await h.repository.append_event(
            TaskEvent(
                id=TaskEventId(h.ids.new_uuid()),
                created_at=now,
                task_id=task.id,
                event_type=kind,
                step_id=step_id,
            )
        )
    await h.engine.fail_step(task.id, sid(0), ERROR)
    cancelled = [
        e.step_id
        for e in await h.repository.events(task.id)
        if e.event_type is TaskEventType.STEP_CANCELLED
    ]
    assert cancelled == [sid(1), sid(2), sid(3)]


# --------------------------------------------------------------------------------------
# The task and its graph: complete needs every step COMPLETED; plan validates the DAG
# --------------------------------------------------------------------------------------


async def test_complete_needs_every_step_completed(h: Harness) -> None:
    task = await executing_with(h, chain(2))
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=f"2 step\\(s\\) not COMPLETED: {sid(0)}, {sid(1)}"):
        await h.engine.complete(task.id, result_for(task.id))
    assert await h.snapshot(task.id) == before
    await run(h, task.id, sid(0))
    with pytest.raises(TaskEngineError, match="1 step\\(s\\) not COMPLETED"):
        await h.engine.complete(task.id, result_for(task.id))
    await run(h, task.id, sid(1))
    assert (await h.engine.complete(task.id, result_for(task.id))).state is S.COMPLETED


async def test_complete_is_refused_on_a_blocked_graph(h: Harness) -> None:
    task = await executing_with(h, chain(2))
    await h.engine.start_step(task.id, sid(0))
    await h.engine.fail_step(task.id, sid(0), ERROR)
    with pytest.raises(TaskEngineError, match="not COMPLETED"):
        await h.engine.complete(task.id, result_for(task.id))
    assert (await h.engine.fail(task.id, ERROR)).state is S.FAILED  # the caller's decision


async def test_complete_with_no_steps_needs_nothing(h: Harness) -> None:
    task = await executing(h)  # the default plan of the harness has no steps (P7)
    assert (await h.engine.complete(task.id, result_for(task.id))).state is S.COMPLETED


async def test_a_completed_task_with_the_same_result_is_still_a_no_op(h: Harness) -> None:
    """The idempotency check comes before the guard: a retry does not re-read the graph."""
    task = await executing_with(h, chain(1))
    await run(h, task.id, sid(0))
    result = result_for(task.id)
    first = await h.engine.complete(task.id, result)
    assert await h.engine.complete(task.id, result) == first


async def test_plan_refuses_a_cycle_and_writes_nothing(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    before = await h.snapshot(task.id)
    with pytest.raises(CyclicDependencyError):
        await h.engine.plan(task.id, dag_plan_for(task.id, (step(0, sid(1)), step(1, sid(0)))))
    assert await h.snapshot(task.id) == before
    with pytest.raises(NotFoundError):
        await h.repository.plan(task.id)


async def test_plan_refuses_an_unknown_dependency(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    with pytest.raises(InvalidGraphError, match="not in the plan"):
        await h.engine.plan(task.id, dag_plan_for(task.id, (step(0, sid(7)),)))
    assert (await h.repository.get(task.id)).plan_id is None


async def test_graph_reads_the_plan_and_the_trail(h: Harness) -> None:
    task = await executing_with(h, diamond())
    state = await h.engine.graph(task.id)
    assert isinstance(state, GraphState)
    assert state.graph.order == (sid(0), sid(1), sid(2), sid(3))
    assert set(state.states.values()) == {P.PENDING}
    assert state.ready() == (sid(0),)
    await run(h, task.id, sid(0))
    assert (await h.engine.graph(task.id)).ready() == (sid(1), sid(2))


async def test_graph_of_a_task_without_a_plan_or_unknown_is_not_found(h: Harness) -> None:
    task = await planning(h, with_plan=False)
    with pytest.raises(NotFoundError):
        await h.engine.graph(task.id)
    with pytest.raises(NotFoundError):
        await h.engine.graph(TaskId(UUID(int=99)))


def test_cancel_step_is_not_a_public_operation() -> None:
    assert "cancel_step" in STEP_OPERATIONS
    assert not hasattr(TaskEngine, "cancel_step")


# --------------------------------------------------------------------------------------
# §15 on SQLite on a file: the graph survives the process that was executing it
# --------------------------------------------------------------------------------------


async def test_the_graph_survives_a_restart_on_sqlite(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"
    clock = FakeClock()
    ids = FakeIdGenerator()

    engine = make_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    approvals = SqlApprovalStore(engine)
    mac = Harness(
        SqlTaskRepository(engine),  # type: ignore[arg-type]
        SqlAuditLog(engine),  # type: ignore[arg-type]
        clock,
        ids,
        approvals,  # type: ignore[arg-type]
        TaskEngine(
            SqlTaskRepository(engine),
            SqlAuditLog(engine),
            clock,
            ids,
            approvals=approvals,
            actor=ELA_ACTOR,
            orphan_after=ORPHAN_AFTER,
        ),
    )
    task = await executing_with(mac, diamond())
    await run(mac, task.id, sid(0))
    await mac.engine.start_step(task.id, sid(1), device_id=DEVICE_ID)
    on_mac = await mac.engine.graph(task.id)
    await engine.dispose()  # the node dies here

    clock.advance(timedelta(minutes=1))
    engine = make_engine(url)
    try:
        repository = SqlTaskRepository(engine)
        audit = SqlAuditLog(engine)
        windows = TaskEngine(
            repository,
            audit,
            clock,
            ids,
            approvals=SqlApprovalStore(engine),
            actor=ELA_ACTOR,
            orphan_after=ORPHAN_AFTER,
        )
        resumed = await windows.graph(task.id)
        assert resumed.states == on_mac.states
        assert resumed.ready() == on_mac.ready() == (sid(2),)
        assert resumed.graph.order == on_mac.graph.order
        # Step 1 is still RUNNING: the new node "starts" it again (a no-op) and finishes it.
        await windows.start_step(task.id, sid(1))
        await windows.complete_step(task.id, sid(1), step_result_for(task.id, sid(1), tail=951))
        await windows.start_step(task.id, sid(2))
        await windows.complete_step(task.id, sid(2), step_result_for(task.id, sid(2), tail=952))
        await windows.start_step(task.id, sid(3))
        final = await windows.complete_step(
            task.id, sid(3), step_result_for(task.id, sid(3), tail=953)
        )
        assert final.is_complete
        completed = await windows.complete(task.id, result_for(task.id))
        assert completed.state is S.COMPLETED
        trail = await audit.read(task_id=task.id)
        # The second start of step 1 was a no-op: one STEP_STARTED for it, written on the Mac.
        assert [a.event_type for a in trail][-7:] == [
            AuditEventType.STEP_STARTED,
            AuditEventType.STEP_COMPLETED,
            AuditEventType.STEP_STARTED,
            AuditEventType.STEP_COMPLETED,
            AuditEventType.STEP_STARTED,
            AuditEventType.STEP_COMPLETED,
            AuditEventType.TASK_COMPLETED,
        ]
        assert [a.event_type for a in trail].count(AuditEventType.STEP_STARTED) == 4
        assert (await verify_chain(engine)).length == len(trail)
    finally:
        await engine.dispose()
