"""The stop of a task, in the engine (M6.3c, ADR 0054 §2, §4, §7).

Three things the engine owns, each driven through a real task on the fakes:

* **the stop signal**: one event per task, raised by every operation that ends the task, after the
  row, the trail and the audit, and by no other; not raised again by the idempotent branch;
* **``stop_step`` and the closings on an ended task**: RUNNING → CANCELLED only on a task that has
  ended; ``complete_step``, ``fail_step`` and ``stop_step`` close a RUNNING step of an ended task
  and nothing else; ``fail_step`` with ``stopped_if_ended`` is stopped instead, under the lock;
* **``halt_of``**: one case per row of the table of proposal 5 of the SPEC, read from the trail and
  the audit, and the failure whose audit row is missing, which says ``UNKNOWN``.

Where the engine refuses, the task, its trail and the audit are exactly as before (§33).
"""

from __future__ import annotations

from typing import Final

import pytest

from ela.domain import (
    ApprovalStatus,
    AuditEvent,
    AuditEventType,
    Halt,
    PermissionOutcome,
    StepState,
    Task,
    TaskEventType,
    TaskId,
    TaskState,
)
from ela.tasks.engine import (
    CLOSINGS,
    ENDED_ONLY,
    OPERATIONS,
    STEP_OPERATIONS,
    TERMINAL_STATES,
    TaskEngine,
)
from ela.tasks.errors import IllegalStepTransitionError, TaskEngineError
from ela.tasks.graph import STEP_TRANSITIONS
from ela.tasks.halt import halt_of, in_progress_at_stop
from ela.testing.fakes import FakeAuditLog
from tests.domain.examples import ELA_ACTOR
from tests.tasks.graphs import chain, diamond, sid
from tests.tasks.support import (
    ERROR,
    HOUR,
    ORPHAN_AFTER,
    Harness,
    approval_for,
    created,
    decision_for,
    executing_with,
    h,
    make_harness,
    planning,
    queued,
    result_for,
    step_result_for,
    waiting_approval,
)

__all__ = ["h"]

S = TaskState
P = StepState
INTERRUPTED: Final = "execution.interrupted"
"""The executor's code for a step closed without knowing whether its tool acted."""
NOT_ACTED: Final = "the task ended before the tool of this step acted"
AFTER_THE_POINT: Final = ERROR.model_copy(update={"code": "browser.not_verified"})


# --------------------------------------------------------------------------------------
# The table
# --------------------------------------------------------------------------------------


def test_a_running_step_can_be_stopped_and_only_a_running_one() -> None:
    op = STEP_OPERATIONS["stop_step"]
    assert (op.sources, op.target) == (frozenset({P.RUNNING}), P.CANCELLED)
    assert (op.event_type, op.audit_type) == (
        TaskEventType.STEP_CANCELLED,
        AuditEventType.STEP_CANCELLED,
    )
    assert op.key is None
    assert P.CANCELLED in STEP_TRANSITIONS[P.RUNNING]


def test_the_closings_on_an_ended_task_are_three_and_one_of_them_is_only_for_it() -> None:
    assert {"complete_step", "fail_step", "stop_step"} == CLOSINGS
    assert {"stop_step"} == ENDED_ONLY
    assert ENDED_ONLY <= CLOSINGS <= set(STEP_OPERATIONS)
    assert all(STEP_OPERATIONS[name].sources == {P.RUNNING} for name in CLOSINGS)


# --------------------------------------------------------------------------------------
# The stop signal
# --------------------------------------------------------------------------------------


class _Watching(FakeAuditLog):
    """An audit log that notes, at every append, whether the task's stop was already raised."""

    def __init__(self) -> None:
        super().__init__()
        self.engine: TaskEngine | None = None
        self.raised_at_append: list[tuple[AuditEventType, bool]] = []

    async def append(self, event: AuditEvent) -> None:
        assert self.engine is not None and event.task_id is not None
        raised = self.engine.stop_signal(event.task_id).is_set()
        self.raised_at_append.append((event.event_type, raised))
        await super().append(event)


def watched() -> tuple[Harness, _Watching]:
    h = make_harness()
    audit = _Watching()
    engine = TaskEngine(
        h.repository,
        audit,
        h.clock,
        h.ids,
        approvals=h.approvals,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    audit.engine = engine
    return Harness(h.repository, audit, h.clock, h.ids, h.approvals, engine), audit


async def _ended_by(h: Harness, operation: str) -> Task:
    """A task brought to the operation that ends it, which is the last thing applied."""
    if operation == "complete":
        task = await executing_with(h, ())
        return await h.engine.complete(task.id, result_for(task.id))
    if operation == "fail":
        task = await executing_with(h, ())
        return await h.engine.fail(task.id, ERROR)
    if operation == "cancel":
        task = await executing_with(h, ())
        return await h.engine.cancel(task.id, reason="ferma")
    if operation == "deny_by_decision":
        task = await executing_with(h, ())
        return await h.engine.deny(task.id, decision=decision_for(task.id))
    if operation == "deny_by_cap":
        task = await executing_with(h, ())
        allowed = decision_for(task.id, PermissionOutcome.ALLOWED)
        return await h.engine.deny_by_cap(task.id, decision=allowed, reason="cap", payload={})
    if operation == "deny_by_approval":
        task = await waiting_approval(h)
        return await h.engine.deny(task.id, approval=approval_for(task.id, ApprovalStatus.REJECTED))
    if operation == "expire":
        task = await created(h, deadline=h.clock.now() + HOUR)
        h.clock.advance(HOUR)
        return await h.engine.expire(task.id)
    assert operation == "recover"
    task = await executing_with(h, ())
    h.clock.advance(ORPHAN_AFTER)
    (failed,) = (await h.engine.recover()).failed
    return failed


ENDING: Final = sorted(name for name, op in OPERATIONS.items() if op.target in TERMINAL_STATES)


def test_the_operations_that_end_a_task_are_the_ones_the_tests_drive() -> None:
    assert ENDING == [
        "cancel",
        "complete",
        "deny_by_approval",
        "deny_by_cap",
        "deny_by_decision",
        "expire",
        "fail",
        "recover",
    ]


@pytest.mark.parametrize("operation", ENDING)
async def test_every_operation_that_ends_a_task_raises_its_stop_after_the_audit(
    operation: str,
) -> None:
    h, audit = watched()
    task = await _ended_by(h, operation)
    assert task.state in TERMINAL_STATES
    assert h.engine.stop_signal(task.id).is_set()
    # The transition's own audit row was written before the stop: it saw it lowered.
    *_, (kind, raised) = audit.raised_at_append
    assert kind is OPERATIONS[operation].audit_type
    assert raised is False


async def test_no_operation_that_keeps_a_task_alive_raises_its_stop() -> None:
    h, audit = watched()
    task = await planning(h)
    task = await h.engine.queue(task.id)
    task = await h.engine.start(task.id)
    task = await h.engine.request_approval(
        task.id, approval_for(task.id, ApprovalStatus.PENDING, responded_by=None)
    )
    task = await h.engine.approve(task.id, approval_for(task.id, ApprovalStatus.GRANTED))
    assert task.state is S.QUEUED
    assert not h.engine.stop_signal(task.id).is_set()
    assert all(raised is False for _, raised in audit.raised_at_append)


async def test_the_stop_of_one_task_is_not_the_stop_of_another(h: Harness) -> None:
    stopped = await queued(h)
    alive = await queued(h)
    await h.engine.cancel(stopped.id)
    assert h.engine.stop_signal(stopped.id).is_set()
    assert not h.engine.stop_signal(alive.id).is_set()
    assert h.engine.stop_signal(stopped.id) is h.engine.stop_signal(stopped.id)


async def test_the_idempotent_branch_does_not_raise_the_stop_again(h: Harness) -> None:
    """A second engine over the same logs is a process born again: the task it finds cancelled
    is a fact of the past, and repeating the cancel does not raise a stop nobody is waiting on."""
    task = await queued(h)
    await h.engine.cancel(task.id, reason="ferma")
    reborn = TaskEngine(
        h.repository,
        h.audit,
        h.clock,
        h.ids,
        approvals=h.approvals,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    before = await h.snapshot(task.id)
    again = await reborn.cancel(task.id, reason="ferma")
    assert again.state is S.CANCELLED
    assert await h.snapshot(task.id) == before
    assert not reborn.stop_signal(task.id).is_set()


async def test_a_refused_end_raises_no_stop(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    with pytest.raises(TaskEngineError):
        await h.engine.complete(task.id, result_for(task.id))  # step 0 is not COMPLETED
    assert not h.engine.stop_signal(task.id).is_set()


# --------------------------------------------------------------------------------------
# stop_step and the closings on an ended task
# --------------------------------------------------------------------------------------


async def running_then(h: Harness, end: str) -> Task:
    """A task of the diamond, step 0 RUNNING, then ended with ``end`` — every way a task with a
    running step can end: COMPLETED cannot, since it wants every step COMPLETED."""
    task = await executing_with(h, diamond(), deadline=h.clock.now() + HOUR)
    await h.engine.start_step(task.id, sid(0))
    if end == "cancel":
        return await h.engine.cancel(task.id, reason="ferma")
    if end == "fail":
        return await h.engine.fail(task.id, ERROR)
    if end == "deny":
        return await h.engine.deny(task.id, decision=decision_for(task.id))
    if end == "expire":
        h.clock.advance(HOUR)
        return await h.engine.expire(task.id)
    assert end == "recover"
    h.clock.advance(ORPHAN_AFTER)
    (failed,) = (await h.engine.recover()).failed
    return failed


ENDS: Final = ["cancel", "fail", "deny", "expire", "recover"]


@pytest.mark.parametrize("end", ENDS)
async def test_stop_step_closes_a_running_step_of_an_ended_task(h: Harness, end: str) -> None:
    task = await running_then(h, end)
    state = await h.engine.stop_step(task.id, sid(0), reason=NOT_ACTED)
    assert state.states[sid(0)] is P.CANCELLED
    assert state.states[sid(1)] is P.PENDING  # decision 11: the stop cancels no PENDING step
    assert (await h.repository.get(task.id)).state is task.state
    event = (await h.repository.events(task.id))[-1]
    assert event.event_type is TaskEventType.STEP_CANCELLED
    assert (event.step_id, event.message) == (sid(0), NOT_ACTED)
    assert event.metadata == {"operation": "stop_step"}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.STEP_CANCELLED
    assert audit.step_id == sid(0) and audit.error is None


async def test_stop_step_is_idempotent_by_state(h: Harness) -> None:
    task = await running_then(h, "cancel")
    await h.engine.stop_step(task.id, sid(0), reason=NOT_ACTED)
    before = await h.snapshot(task.id)
    again = await h.engine.stop_step(task.id, sid(0), reason="another reason")
    assert again.states[sid(0)] is P.CANCELLED
    assert await h.snapshot(task.id) == before


async def test_stop_step_on_a_live_task_is_refused(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match="stop_step needs a task that has ended"):
        await h.engine.stop_step(task.id, sid(0), reason=NOT_ACTED)
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("operation", sorted(CLOSINGS))
async def test_a_closing_never_moves_a_step_that_is_not_running(h: Harness, operation: str) -> None:
    """Step 1 is PENDING in the cancelled task: no closing starts from there."""
    task = await running_then(h, "cancel")
    before = await h.snapshot(task.id)
    with pytest.raises(IllegalStepTransitionError) as excinfo:
        await close(h, operation, task.id, 1)
    assert excinfo.value.current == "PENDING"
    assert await h.snapshot(task.id) == before


@pytest.mark.parametrize("operation", sorted(CLOSINGS))
async def test_a_closing_already_applied_writes_nothing(h: Harness, operation: str) -> None:
    task = await running_then(h, "cancel")
    await close(h, operation, task.id, 0)
    before = await h.snapshot(task.id)
    await close(h, operation, task.id, 0)
    assert await h.snapshot(task.id) == before


async def close(h: Harness, operation: str, task_id: TaskId, index: int) -> object:
    if operation == "complete_step":
        return await h.engine.complete_step(
            task_id, sid(index), step_result_for(task_id, sid(index))
        )
    if operation == "fail_step":
        return await h.engine.fail_step(task_id, sid(index), AFTER_THE_POINT)
    assert operation == "stop_step"
    return await h.engine.stop_step(task_id, sid(index), reason=NOT_ACTED)


@pytest.mark.parametrize("operation", ["start_step", "release_step"])
async def test_nothing_starts_or_goes_back_in_play_in_an_ended_task(
    h: Harness, operation: str
) -> None:
    task = await running_then(h, "cancel")
    before = await h.snapshot(task.id)
    with pytest.raises(TaskEngineError, match=f"{operation} needs an EXECUTING task"):
        if operation == "start_step":
            await h.engine.start_step(task.id, sid(1))
        else:
            await h.engine.release_step(task.id, sid(0), key=sid(7))
    assert await h.snapshot(task.id) == before


async def test_a_step_past_its_point_fails_on_an_ended_task_and_cascades(h: Harness) -> None:
    """The tool acted and its verification did not pass: the step fails as in a live task, and
    the cascade — the one road that cancels PENDING steps — runs."""
    task = await running_then(h, "cancel")
    state = await h.engine.fail_step(task.id, sid(0), AFTER_THE_POINT)
    assert [state.states[sid(i)] for i in range(4)] == [
        P.FAILED,
        P.CANCELLED,
        P.CANCELLED,
        P.CANCELLED,
    ]


# --------------------------------------------------------------------------------------
# fail_step(stopped_if_ended=…): decided under the lock
# --------------------------------------------------------------------------------------


async def test_a_failure_of_a_tool_that_did_not_act_fails_in_a_live_task(h: Harness) -> None:
    task = await executing_with(h, chain(2))
    await h.engine.start_step(task.id, sid(0))
    state = await h.engine.fail_step(task.id, sid(0), ERROR, stopped_if_ended=NOT_ACTED)
    assert (state.states[sid(0)], state.states[sid(1)]) == (P.FAILED, P.CANCELLED)


async def test_a_failure_of_a_tool_that_did_not_act_is_a_stop_in_an_ended_task(
    h: Harness,
) -> None:
    task = await running_then(h, "cancel")
    state = await h.engine.fail_step(task.id, sid(0), ERROR, stopped_if_ended=NOT_ACTED)
    assert state.states[sid(0)] is P.CANCELLED
    assert {state.states[sid(i)] for i in (1, 2, 3)} == {P.PENDING}
    event = (await h.repository.events(task.id))[-1]
    assert (event.event_type, event.message) == (TaskEventType.STEP_CANCELLED, NOT_ACTED)
    audit = (await h.audit.read())[-1]
    assert (audit.event_type, audit.error) == (AuditEventType.STEP_CANCELLED, None)


async def test_a_retried_failure_on_an_ended_task_finishes_its_cascade(h: Harness) -> None:
    """The step FAILED while the task was alive and the crash cut the cascade; the task ended
    after: the retry is a retry of the failure, never a stop of a step that is not RUNNING."""
    task = await executing_with(h, chain(3))
    await h.engine.start_step(task.id, sid(0))
    await h.engine.fail_step(task.id, sid(0), ERROR)
    await h.engine.cancel(task.id, reason="ferma")
    state = await h.engine.fail_step(task.id, sid(0), ERROR, stopped_if_ended=NOT_ACTED)
    assert state.states[sid(0)] is P.FAILED


# --------------------------------------------------------------------------------------
# halt_of: one case per row of the table of proposal 5
# --------------------------------------------------------------------------------------


async def halt(h: Harness, task_id: TaskId, *, lapsed: bool = False) -> Halt | None:
    trail = await h.repository.events(task_id)
    return halt_of(
        trail, await h.audit.read(task_id=task_id), interrupted=INTERRUPTED, lapsed=lapsed
    )


async def test_no_step_in_progress_has_no_halt(h: Harness) -> None:
    task = await executing_with(h, chain(2))
    await h.engine.start_step(task.id, sid(0))
    await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))
    await h.engine.cancel(task.id, reason="ferma")
    assert in_progress_at_stop(await h.repository.events(task.id)) is None
    assert await halt(h, task.id) is None


async def test_a_task_that_was_never_stopped_has_no_halt(h: Harness) -> None:
    """``halt`` is only for a CANCELLED task: the no, the denial, the expiry and the orphan have
    their own outcomes."""
    task = await running_then(h, "fail")
    assert in_progress_at_stop(await h.repository.events(task.id)) is None
    assert await halt(h, task.id) is None


async def test_a_released_step_was_not_in_progress(h: Harness) -> None:
    task = await executing_with(h, chain(1))
    await h.engine.start_step(task.id, sid(0))
    await h.engine.release_step(task.id, sid(0), key=sid(7))
    await h.engine.cancel(task.id)
    assert await halt(h, task.id) is None


async def test_a_step_stopped_before_its_point_had_not_acted(h: Harness) -> None:
    task = await running_then(h, "cancel")
    await h.engine.stop_step(task.id, sid(0), reason=NOT_ACTED)
    assert await halt(h, task.id) is Halt.NOT_ACTED


async def test_a_step_completed_after_the_stop_had_acted_and_was_verified(h: Harness) -> None:
    task = await running_then(h, "cancel")
    await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))
    assert await halt(h, task.id) is Halt.ACTED_VERIFIED


async def test_a_step_failed_after_its_point_had_acted(h: Harness) -> None:
    task = await running_then(h, "cancel")
    await h.engine.fail_step(task.id, sid(0), AFTER_THE_POINT)
    assert await halt(h, task.id) is Halt.ACTED


async def test_a_step_closed_without_knowing_is_unknown(h: Harness) -> None:
    task = await running_then(h, "cancel")
    await h.engine.fail_step(task.id, sid(0), ERROR.model_copy(update={"code": INTERRUPTED}))
    assert await halt(h, task.id) is Halt.UNKNOWN


async def test_a_failure_whose_audit_row_is_missing_is_unknown(h: Harness) -> None:
    """A crash between the trail's event and the audit: a doubt is not an «it acted» (§33)."""
    task = await running_then(h, "cancel")
    await h.engine.fail_step(task.id, sid(0), AFTER_THE_POINT)
    trail = await h.repository.events(task.id)
    audit = [
        event
        for event in await h.audit.read(task_id=task.id)
        if event.event_type is not AuditEventType.STEP_FAILED
    ]
    assert halt_of(trail, audit, interrupted=INTERRUPTED) is Halt.UNKNOWN
    without_error = [
        event.model_copy(update={"error": None})
        if event.event_type is AuditEventType.STEP_FAILED
        else event
        for event in await h.audit.read(task_id=task.id)
    ]
    assert halt_of(trail, without_error, interrupted=INTERRUPTED) is Halt.UNKNOWN


async def test_a_step_not_yet_closed_is_finishing_unless_its_claim_has_lapsed(
    h: Harness,
) -> None:
    task = await running_then(h, "cancel")
    assert await halt(h, task.id) is Halt.FINISHING
    assert await halt(h, task.id, lapsed=True) is Halt.UNKNOWN


async def test_the_step_in_progress_is_the_one_started_last(h: Harness) -> None:
    """The runner is sequential, so two running steps do not happen; were there two, the stop
    found working the later started, and the earlier closing does not answer for it."""
    task = await executing_with(h, diamond())
    await h.engine.start_step(task.id, sid(0))
    await h.engine.complete_step(task.id, sid(0), step_result_for(task.id, sid(0)))
    await h.engine.start_step(task.id, sid(1))
    await h.engine.start_step(task.id, sid(2))
    await h.engine.cancel(task.id)
    assert in_progress_at_stop(await h.repository.events(task.id)) == sid(2)
    await h.engine.complete_step(task.id, sid(1), step_result_for(task.id, sid(1)))
    assert await halt(h, task.id) is Halt.FINISHING
    await h.engine.stop_step(task.id, sid(2), reason=NOT_ACTED)
    assert await halt(h, task.id) is Halt.NOT_ACTED


def test_the_values_of_halt_are_the_rows_of_the_table() -> None:
    assert [value.value for value in Halt] == [
        "NOT_ACTED",
        "ACTED_VERIFIED",
        "ACTED",
        "UNKNOWN",
        "FINISHING",
    ]
