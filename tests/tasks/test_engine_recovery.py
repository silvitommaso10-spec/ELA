"""Recovery of orphaned tasks (§14 "recuperare attività", ADR 0008 §6).

On the fakes: the closed bound, heartbeats that reset the count, other states untouched, an empty
trail. On SQLite on a file: a simulated restart, with the audit chain still verifying afterwards.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from ela.domain import ActorKind, AuditEventType, Task, TaskEventType, TaskId, TaskState
from ela.infrastructure.persistence import SqlAuditLog, SqlTaskRepository, make_engine, verify_chain
from ela.infrastructure.persistence.orm import Base
from ela.tasks.engine import ORPHANED, SYSTEM_ACTOR, TaskEngine
from ela.testing.fakes import FakeClock, FakeIdGenerator
from tests.domain.examples import ELA_ACTOR, USER_INTENT
from tests.tasks.support import ORPHAN_AFTER, Harness, executing, h, plan_for, planning, task_in

__all__ = ["h"]

S = TaskState
ONE_SECOND = timedelta(seconds=1)


async def test_a_silent_executing_task_is_failed_as_orphaned(h: Harness) -> None:
    task = await executing(h)
    started_at = h.clock.now()
    h.clock.advance(ORPHAN_AFTER)  # exactly the threshold: closed bound
    marked = await h.engine.recover()
    assert [t.id for t in marked] == [task.id]
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
    assert await h.engine.recover() == ()
    assert (await h.repository.get(task.id)).state is S.EXECUTING


async def test_a_heartbeat_resets_the_count(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    await h.engine.heartbeat(task.id)
    h.clock.advance(ORPHAN_AFTER - ONE_SECOND)
    assert await h.engine.recover() == ()
    h.clock.advance(ONE_SECOND)
    assert [t.id for t in await h.engine.recover()] == [task.id]


async def test_other_states_are_left_alone(h: Harness) -> None:
    others = [await task_in(h, state) for state in S if state is not S.EXECUTING]
    h.clock.advance(ORPHAN_AFTER * 10)
    assert await h.engine.recover() == ()
    for task in others:
        assert (await h.repository.get(task.id)).state is task.state


async def test_recovery_is_idempotent(h: Harness) -> None:
    await executing(h)
    h.clock.advance(ORPHAN_AFTER)
    assert len(await h.engine.recover()) == 1
    audits = len(await h.audit.read())
    assert await h.engine.recover() == ()
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
    assert await h.engine.recover() == ()
    h.clock.advance(ONE_SECOND)
    (marked,) = await h.engine.recover()
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
    assert [t.id for t in await h.engine.recover()] == [first.id, second.id]


async def test_a_recovered_task_can_be_failed_again_as_a_no_op(h: Harness) -> None:
    task = await executing(h)
    h.clock.advance(ORPHAN_AFTER)
    (marked,) = await h.engine.recover()
    from tests.tasks.support import ERROR

    assert await h.engine.fail(task.id, ERROR) == marked


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
            repository, audit, clock, ids, actor=ELA_ACTOR, orphan_after=ORPHAN_AFTER
        )
        (marked,) = await after.recover()
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
        assert await after.recover() == ()
    finally:
        await engine.dispose()


async def test_the_whole_life_cycle_on_sqlite_keeps_the_chain_valid(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'ela.db').as_posix()}"
    engine = make_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        h = Harness(
            SqlTaskRepository(engine),  # type: ignore[arg-type]
            SqlAuditLog(engine),  # type: ignore[arg-type]
            FakeClock(),
            FakeIdGenerator(),
            TaskEngine(
                SqlTaskRepository(engine),
                SqlAuditLog(engine),
                FakeClock(),
                FakeIdGenerator(),
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
