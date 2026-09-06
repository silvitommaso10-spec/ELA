"""Recovery of orphaned tasks (§14 "recuperare attività", ADR 0008 §6).

On the fakes: the closed bound, heartbeats that reset the count, other states untouched, an empty
trail. On SQLite on a file: a simulated restart, with the audit chain still verifying afterwards.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from ela.domain import (
    ActorKind,
    Approval,
    ApprovalId,
    ApprovalStatus,
    AuditEventType,
    Task,
    TaskEvent,
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
from ela.tasks.engine import ORPHANED, SYSTEM_ACTOR, RecoverySummary, TaskEngine
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuditLog,
    FakeClock,
    FakeIdGenerator,
    FakeTaskRepository,
)
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.tasks.support import (
    ERROR,
    ORPHAN_AFTER,
    Harness,
    approval_for,
    executing,
    h,
    make_harness,
    plan_for,
    planning,
    result_for,
    task_in,
)

__all__ = ["h"]

S = TaskState
ONE_SECOND = timedelta(seconds=1)


async def test_a_silent_executing_task_is_failed_as_orphaned(h: Harness) -> None:
    task = await executing(h)
    started_at = h.clock.now()
    h.clock.advance(ORPHAN_AFTER)  # exactly the threshold: closed bound
    summary = await h.engine.recover()
    assert [t.id for t in summary.failed] == [task.id]
    assert summary.skipped == ()
    failed = await h.repository.get(task.id)
    assert failed.state is S.FAILED
    event = (await h.repository.events(task.id))[-1]
    assert (event.previous_state, event.new_state) == (S.EXECUTING, S.FAILED)
    assert event.metadata == {"operation": "recover"}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_FAILED
    assert audit.actor == SYSTEM_ACTOR and audit.actor.kind is ActorKind.SYSTEM
    assert audit.error is not None and audit.error.code == ORPHANED
    assert audit.error.retryable is True
    assert audit.error.details["last_seen_at"] == started_at.isoformat()
    assert audit.error.details["orphan_after_seconds"] == ORPHAN_AFTER.total_seconds()
    assert audit.payload["code"] == ORPHANED


async def test_one_second_short_of_the_threshold_is_not_orphaned(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    assert await h.engine.recover() == RecoverySummary((), ())
    assert (await h.repository.get(task.id)).state is S.EXECUTING


async def test_a_heartbeat_resets_the_count(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    await h.engine.heartbeat(task.id)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    assert await h.engine.recover() == RecoverySummary((), ())
    h.clock.advance(ONE_SECOND)
    assert [t.id for t in (await h.engine.recover()).failed] == [task.id]


async def test_other_states_are_left_alone(h: Harness) -> None:
    others = [await task_in(h, state) for state in S if state is not S.EXECUTING]
    h.clock.advance(ORPHAN_AFTER * 10)
    assert await h.engine.recover() == RecoverySummary((), ())
    for task in others:
        assert (await h.repository.get(task.id)).state is task.state


async def test_recovery_is_idempotent(h: Harness) -> None:
    await executing(h)
    h.clock.advance(ORPHAN_AFTER)
    assert len((await h.engine.recover()).failed) == 1
    audits = len(await h.audit.read())
    assert await h.engine.recover() == RecoverySummary((), ())
    assert len(await h.audit.read()) == audits


async def test_an_empty_trail_counts_from_creation(h: Harness) -> None:
    """A repository populated by hand: the task's birth is its last sign of life."""
    stranded = Task(
        id=TaskId(USER_INTENT.id.__class__(int=77)),
        created_at=h.clock.now(),
        goal="stranded",
        state=S.EXECUTING,
    )
    await h.repository.add(stranded)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    assert await h.engine.recover() == RecoverySummary((), ())
    h.clock.advance(ONE_SECOND)
    (marked,) = (await h.engine.recover()).failed
    assert marked.id == stranded.id and marked.state is S.FAILED


async def test_recovery_marks_every_orphan_in_insertion_order(h: Harness) -> None:
    first = await executing(h)
    second_intent = USER_INTENT.model_copy(update={"id": USER_INTENT.id.__class__(int=2)})
    second = await h.engine.create(second_intent)
    second = await h.engine.start_planning(second.id)
    await h.engine.plan(second.id, plan_for(second.id, tail=902))
    await h.engine.queue(second.id)
    await h.engine.start(second.id)
    h.clock.advance(ORPHAN_AFTER)
    assert [t.id for t in (await h.engine.recover()).failed] == [first.id, second.id]


async def test_a_recovered_task_can_be_failed_again_as_a_no_op(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER)
    (marked,) = (await h.engine.recover()).failed
    assert await h.engine.fail(task.id, ERROR) == marked


# --------------------------------------------------------------------------------------
# Candidates that change between the listing and the lock (review M3.1): skipped, not failed
# --------------------------------------------------------------------------------------


class RacingRepository(FakeTaskRepository):
    """A fake that runs a coroutine right after the pre-lock read of one task's trail.

    That is the window between "this task looks orphaned" and the lock that re-checks it: what
    the hook does there (complete the task, send a heartbeat) must be seen under the lock.
    """

    def __init__(self) -> None:
        super().__init__()
        self.race_on: TaskId | None = None
        self.hook: Callable[[], Awaitable[None]] | None = None

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        trail = await super().events(task_id)
        if task_id == self.race_on and self.hook is not None:
            hook, self.hook = self.hook, None
            await hook()
        return trail


def _racing_harness() -> tuple[Harness, RacingRepository]:
    h = make_harness()
    repository = RacingRepository()
    h.repository = repository
    h.engine = TaskEngine(
        repository,
        h.audit,
        h.clock,
        h.ids,
        approvals=h.approvals,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    return h, repository


async def test_a_candidate_that_changed_state_is_skipped_and_the_others_proceed() -> None:
    h, repository = _racing_harness()
    first = await executing(h)
    second = await executing(h)
    third = await executing(h)
    h.clock.advance(ORPHAN_AFTER)

    async def complete_second() -> None:
        await h.engine.complete(second.id, result_for(second.id))

    repository.race_on, repository.hook = second.id, complete_second
    summary = await h.engine.recover()
    assert [t.id for t in summary.failed] == [first.id, third.id]
    assert [(t.id, t.state) for t in summary.skipped] == [(second.id, S.COMPLETED)]
    assert (await repository.get(second.id)).state is S.COMPLETED
    audits = await h.audit.read(task_id=second.id)
    assert [a.event_type for a in audits][-1] is AuditEventType.TASK_COMPLETED


async def test_a_candidate_alive_again_is_skipped() -> None:
    h, repository = _racing_harness()
    first = await executing(h)
    second = await executing(h)
    h.clock.advance(ORPHAN_AFTER)

    async def heartbeat_first() -> None:
        await h.engine.heartbeat(first.id)

    repository.race_on, repository.hook = first.id, heartbeat_first
    summary = await h.engine.recover()
    assert [t.id for t in summary.failed] == [second.id]
    assert [(t.id, t.state) for t in summary.skipped] == [(first.id, S.EXECUTING)]
    assert (await repository.get(first.id)).state is S.EXECUTING


# --------------------------------------------------------------------------------------
# A restart on SQLite on a file
# --------------------------------------------------------------------------------------


async def test_recovery_after_a_restart_on_sqlite(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"
    clock = FakeClock()
    ids = FakeIdGenerator()

    engine = make_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    before = TaskEngine(
        SqlTaskRepository(engine),
        SqlAuditLog(engine),
        clock,
        ids,
        approvals=SqlApprovalStore(engine),
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    task = await before.create(USER_INTENT)
    task = await before.start_planning(task.id)
    task = await before.plan(task.id, plan_for(task.id))
    task = await before.queue(task.id)
    task = await before.start(task.id)
    clock.advance(timedelta(minutes=1))
    await before.heartbeat(task.id)
    await engine.dispose()  # the process dies here

    clock.advance(ORPHAN_AFTER)
    engine = make_engine(url)
    try:
        repository = SqlTaskRepository(engine)
        audit = SqlAuditLog(engine)
        after = TaskEngine(
            repository,
            audit,
            clock,
            ids,
            approvals=SqlApprovalStore(engine),
            actor=ELA_ACTOR,
            orphan_after=ORPHAN_AFTER,
        )
        (marked,) = (await after.recover()).failed
        assert marked.id == task.id and marked.state is S.FAILED
        assert (await repository.get(task.id)).state is S.FAILED
        events = await repository.events(task.id)
        assert [e.event_type for e in events][-3:] == [
            TaskEventType.STATE_CHANGED,
            TaskEventType.HEARTBEAT,
            TaskEventType.STATE_CHANGED,
        ]
        assert (await repository.plan(task.id)).task_id == task.id
        trail = await audit.read(task_id=task.id)
        assert [a.event_type for a in trail] == [
            AuditEventType.TASK_CREATED,
            AuditEventType.TASK_PLANNING_STARTED,
            AuditEventType.PLAN_CREATED,
            AuditEventType.TASK_QUEUED,
            AuditEventType.TASK_STARTED,
            AuditEventType.TASK_FAILED,
        ]
        assert trail[-1].error is not None and trail[-1].error.code == ORPHANED
        assert (await verify_chain(engine)).length == 6
        assert await after.recover() == RecoverySummary((), ())
    finally:
        await engine.dispose()


async def test_the_whole_life_cycle_on_sqlite_keeps_the_chain_valid(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"
    engine = make_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        approvals = SqlApprovalStore(engine)
        h = Harness(
            SqlTaskRepository(engine),  # type: ignore[arg-type]
            SqlAuditLog(engine),  # type: ignore[arg-type]
            FakeClock(),
            FakeIdGenerator(),
            approvals,  # type: ignore[arg-type]
            TaskEngine(
                SqlTaskRepository(engine),
                SqlAuditLog(engine),
                FakeClock(),
                FakeIdGenerator(),
                approvals=approvals,
                actor=ELA_ACTOR,
                orphan_after=ORPHAN_AFTER,
            ),
        )
        task = await planning(h)
        task = await h.engine.queue(task.id)
        assert (await h.engine.queue(task.id)) == task  # idempotent on SQLite too
        assert (await verify_chain(engine)).length == 4
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------------------
# A request for approval that expired unanswered (ADR 0015 §6)
# --------------------------------------------------------------------------------------


async def waiting_on(h: Harness, *, ttl: timedelta | None = ONE_SECOND * 60) -> tuple[Task, Any]:
    """A task WAITING_APPROVAL on a PENDING request stored in the approval store."""
    task = await planning(h)
    request = approval_for(task.id, ApprovalStatus.PENDING, responded_by=None).model_copy(
        update={
            "id": ApprovalId(h.ids.new_uuid()),
            "responded_at": None,
            "expires_at": None if ttl is None else h.clock.now() + ttl,
        }
    )
    await h.approvals.add(request)
    return await h.engine.request_approval(task.id, request), request


async def test_a_task_waiting_on_an_expired_request_is_expired(h: Harness) -> None:
    task, request = await waiting_on(h)
    h.clock.advance(ONE_SECOND * 60)  # the exact instant: closed bound
    summary = await h.engine.recover()
    assert [t.id for t in summary.expired] == [task.id]
    assert summary.failed == () and summary.skipped == ()
    expired = await h.repository.get(task.id)
    assert expired.state is S.EXPIRED
    event = (await h.repository.events(task.id))[-1]
    assert (event.previous_state, event.new_state) == (S.WAITING_APPROVAL, S.EXPIRED)
    assert event.metadata == {"operation": "expire"}
    audit = (await h.audit.read())[-1]
    assert audit.event_type is AuditEventType.TASK_EXPIRED
    assert audit.actor == SYSTEM_ACTOR and audit.actor.kind is ActorKind.SYSTEM
    assert audit.payload["approval_id"] == str(request.id)
    assert audit.payload["expires_at"] == request.expires_at.isoformat()
    assert str(request.id) in audit.summary and "expired" in audit.summary
    # the request itself is left as it was asked: the store writes no EXPIRED
    assert await h.approvals.get(request.id) == request
    assert (await h.approvals.get(request.id)).status is ApprovalStatus.PENDING


async def test_one_second_before_the_request_expires_the_task_waits_on(h: Harness) -> None:
    task, _ = await waiting_on(h)
    h.clock.advance(ONE_SECOND * 59)
    summary = await h.engine.recover()
    assert summary.expired == ()
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL


async def test_a_request_without_expiry_never_expires_the_task(h: Harness) -> None:
    task, _ = await waiting_on(h, ttl=None)
    h.clock.advance(ONE_SECOND * 3600 * 24 * 30)
    assert (await h.engine.recover()).expired == ()
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL


async def test_a_waiting_task_whose_request_was_answered_is_left_to_its_caller(
    h: Harness,
) -> None:
    """Window 5c of ADR 0015 §8: the answer is in the store, the engine never saw it — not
    recovery's to move, whatever the expiry says now."""
    task, request = await waiting_on(h)
    await h.approvals.respond(
        request.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=h.clock.now()
    )
    h.clock.advance(ONE_SECOND * 3600)
    summary = await h.engine.recover()
    assert summary.expired == () and summary.skipped == ()
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL


async def test_a_waiting_task_without_any_request_in_the_store_is_left_alone(h: Harness) -> None:
    """Window 5b: the task waits, the store has nothing (an engine driven by hand, or a store
    lost): nothing to read, nothing to expire."""
    task = await task_in(h, S.WAITING_APPROVAL)  # the harness never stored its request
    h.clock.advance(ONE_SECOND * 3600 * 24 * 30)
    assert (await h.engine.recover()).expired == ()
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL


async def test_the_last_pending_request_is_the_one_the_task_waits_on(h: Harness) -> None:
    task, first = await waiting_on(h, ttl=ONE_SECOND * 10)
    second = first.model_copy(
        update={"id": ApprovalId(h.ids.new_uuid()), "expires_at": h.clock.now() + ONE_SECOND * 60}
    )
    await h.approvals.add(second)
    h.clock.advance(ONE_SECOND * 30)  # the first expired, the second did not
    assert (await h.engine.recover()).expired == ()
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL
    h.clock.advance(ONE_SECOND * 30)
    (expired,) = (await h.engine.recover()).expired
    assert expired.id == task.id
    assert (await h.audit.read())[-1].payload["approval_id"] == str(second.id)


async def test_expiring_a_request_is_idempotent_and_orders_by_insertion(h: Harness) -> None:
    first, _ = await waiting_on(h)
    second, _ = await waiting_on(h)
    h.clock.advance(ONE_SECOND * 60)
    summary = await h.engine.recover()
    assert [t.id for t in summary.expired] == [first.id, second.id]
    assert await h.engine.recover() == RecoverySummary((), (), ())


class RacingApprovalStore(FakeApprovalStore):
    """A store that runs a coroutine right after the pre-lock read of one task's requests: the
    window between "this request looks expired" and the lock that re-checks it."""

    def __init__(self) -> None:
        super().__init__()
        self.race_on: TaskId | None = None
        self.hook: Callable[[], Awaitable[None]] | None = None

    async def for_task(self, task_id: TaskId) -> tuple[Approval, ...]:
        requests = await super().for_task(task_id)
        if task_id == self.race_on and self.hook is not None:
            hook, self.hook = self.hook, None
            await hook()
        return requests


async def test_a_candidate_answered_under_the_lock_is_skipped() -> None:
    h = make_harness()
    approvals = RacingApprovalStore()
    h.approvals = approvals
    h.engine = TaskEngine(
        h.repository,
        h.audit,
        h.clock,
        h.ids,
        approvals=approvals,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    task, request = await waiting_on(h)
    other, _ = await waiting_on(h)
    h.clock.advance(ONE_SECOND * 60)

    async def answer() -> None:  # just in time: the answer's ``now`` is the caller's fact
        await approvals.respond(
            request.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=request.expires_at - ONE_SECOND,
        )

    approvals.race_on, approvals.hook = task.id, answer
    summary = await h.engine.recover()
    assert [t.id for t in summary.expired] == [other.id]
    assert [(t.id, t.state) for t in summary.skipped] == [(task.id, S.WAITING_APPROVAL)]
    assert (await h.repository.get(task.id)).state is S.WAITING_APPROVAL


async def test_orphans_and_expired_requests_are_recovered_in_one_call(h: Harness) -> None:
    orphan = await executing(h)
    waiting, _ = await waiting_on(h)
    h.clock.advance(ORPHAN_AFTER)
    summary = await h.engine.recover()
    assert [t.id for t in summary.failed] == [orphan.id]
    assert [t.id for t in summary.expired] == [waiting.id]


def test_the_engine_needs_the_approval_store() -> None:
    with pytest.raises(TypeError):
        TaskEngine(  # type: ignore[call-arg]
            FakeTaskRepository(),
            FakeAuditLog(),
            FakeClock(),
            FakeIdGenerator(),
            actor=ELA_ACTOR,
            orphan_after=ORPHAN_AFTER,
        )


async def test_an_expired_request_is_recovered_after_a_restart_on_sqlite(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"
    clock, ids = FakeClock(), FakeIdGenerator()
    engine = make_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    approvals = SqlApprovalStore(engine)
    before = TaskEngine(
        SqlTaskRepository(engine),
        SqlAuditLog(engine),
        clock,
        ids,
        approvals=approvals,
        actor=ELA_ACTOR,
        orphan_after=ORPHAN_AFTER,
    )
    task = await before.create(USER_INTENT)
    await before.start_planning(task.id)
    await before.plan(task.id, plan_for(task.id))
    request = approval_for(task.id, ApprovalStatus.PENDING, responded_by=None).model_copy(
        update={"responded_at": None, "expires_at": clock.now() + ONE_SECOND * 60}
    )
    await approvals.add(request)
    await before.request_approval(task.id, request)
    await engine.dispose()  # the process dies here

    clock.advance(ONE_SECOND * 60)
    engine = make_engine(url)
    try:
        repository, audit = SqlTaskRepository(engine), SqlAuditLog(engine)
        after = TaskEngine(
            repository,
            audit,
            clock,
            ids,
            approvals=SqlApprovalStore(engine),
            actor=ELA_ACTOR,
            orphan_after=ORPHAN_AFTER,
        )
        (expired,) = (await after.recover()).expired
        assert expired.id == task.id and expired.state is S.EXPIRED
        trail = await audit.read(task_id=task.id)
        assert [a.event_type for a in trail][-2:] == [
            AuditEventType.APPROVAL_REQUESTED,
            AuditEventType.TASK_EXPIRED,
        ]
        assert (await SqlApprovalStore(engine).get(request.id)).status is ApprovalStatus.PENDING
        assert (await verify_chain(engine)).length == len(trail)
        assert await after.recover() == RecoverySummary((), (), ())
    finally:
        await engine.dispose()
