"""``SqlAuditLog`` and ``verify_chain`` beyond the contract (ADR 0007).

The contract tests already run on the adapter. Here: the four levels of append-only, each with
its negative case; the chain on real rows — intact, altered, cut, forged; the write lock; the
errors; the file.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError, OperationalError, StatementError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.util import await_only

from ela.audit.chain import GENESIS_HASH, AuditChainError, ChainFault, ChainSummary, link_hash
from ela.audit.verifier import AuditVerifier
from ela.domain import AuditEventId, TaskId
from ela.infrastructure.persistence import (
    SqlAuditLog,
    SqlTaskRepository,
    make_engine,
    make_session_factory,
    verify_chain,
)
from ela.infrastructure.persistence.audit_log import row_record
from ela.infrastructure.persistence.engine import async_url
from ela.infrastructure.persistence.mappers import audit_event_to_row
from ela.infrastructure.persistence.orm import (
    APPEND_ONLY_TRIGGERS,
    HASHED_COLUMNS,
    AppendOnlyViolation,
    AuditEventRow,
    TaskRow,
)
from ela.ports import AlreadyExistsError
from tests.domain.examples import AUDIT_EVENT, TASK
from tests.infrastructure.persistence.conftest import Recorder, create_schema

Attach = Callable[[AsyncEngine], Recorder]

TAMPERING = [
    "UPDATE audit_events SET summary = 'rewritten'",
    "DELETE FROM audit_events",
    "INSERT OR REPLACE INTO audit_events (id, created_at, event_type, actor_kind, actor_id,"
    " summary, payload, prev_hash, row_hash) VALUES (:id, '2026-01-01', 'NOTE', 'ELA', 'ela',"
    " 'rewritten', '{}', 'p', 'r')",
    "REPLACE INTO audit_events (id, created_at, event_type, actor_kind, actor_id, summary,"
    " payload, prev_hash, row_hash) VALUES (:id, '2026-01-01', 'NOTE', 'ELA', 'ela',"
    " 'rewritten', '{}', 'p', 'r')",
    "UPDATE OR REPLACE audit_events SET summary = 'rewritten'",
]
TAMPERING_IDS = ["update", "delete", "insert-or-replace", "replace-into", "update-or-replace"]


def event_number(n: int) -> AuditEventId:
    return AuditEventId(UUID(f"00000000-0000-4000-8000-0000000003{n:02d}"))


def events(count: int) -> list[AuditEventId]:
    return [event_number(n) for n in range(count)]


async def append_many(log: SqlAuditLog, count: int) -> None:
    for n in range(count):
        await log.append(AUDIT_EVENT.model_copy(update={"id": event_number(n), "summary": f"#{n}"}))


async def rows_of(engine: AsyncEngine) -> list[AuditEventRow]:
    async with make_session_factory(engine)() as session:
        return list(await session.scalars(select(AuditEventRow).order_by(AuditEventRow.seq)))


async def raw(engine: AsyncEngine, statement: str, **params: object) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement), params)


async def drop_triggers(engine: AsyncEngine) -> None:
    """Simulate an attacker with file access: the database no longer refuses changes."""
    for name in APPEND_ONLY_TRIGGERS:
        await raw(engine, f"DROP TRIGGER {name}")


# ----------------------------------------------------------------------------------------
# Level 1: the adapter
# ----------------------------------------------------------------------------------------


def test_the_log_exposes_exactly_append_read_and_verify(engine: AsyncEngine) -> None:
    """The first level of append-only is the surface itself: nothing here changes a row.

    ``verify`` joined the two in M8.2 (ADR 0024 §4) and reads like ``read`` does; the port
    ``AuditLog`` still declares two members, so receiving the log still gives nobody a third way
    to write, and there is still no ``update``, no ``delete`` and no ``engine`` to go around them.
    """
    log = SqlAuditLog(engine)
    assert [name for name in dir(log) if not name.startswith("_")] == ["append", "read", "verify"]


# ----------------------------------------------------------------------------------------
# Level 2: the ORM
# ----------------------------------------------------------------------------------------


async def test_the_orm_refuses_to_update_an_audit_row(
    engine: AsyncEngine, statements: Attach
) -> None:
    log = SqlAuditLog(engine)
    await log.append(AUDIT_EVENT)
    recorded = statements(engine)
    async with make_session_factory(engine)() as session:
        row = await session.scalar(select(AuditEventRow))
        assert row is not None
        row.summary = "rewritten"
        with pytest.raises(AppendOnlyViolation, match="append-only"):
            await session.flush()
    assert not any(s.startswith("UPDATE") for s in recorded())
    assert await log.read() == (AUDIT_EVENT,)


async def test_the_orm_refuses_to_delete_an_audit_row(
    engine: AsyncEngine, statements: Attach
) -> None:
    log = SqlAuditLog(engine)
    await log.append(AUDIT_EVENT)
    recorded = statements(engine)
    async with make_session_factory(engine)() as session:
        row = await session.scalar(select(AuditEventRow))
        assert row is not None
        await session.delete(row)
        with pytest.raises(AppendOnlyViolation):
            await session.flush()
    assert not any(s.startswith("DELETE") for s in recorded())
    assert await log.read() == (AUDIT_EVENT,)


async def test_the_orm_guard_leaves_other_tables_alone(engine: AsyncEngine) -> None:
    """Decision 4 of the review: only ``audit_events`` is refused; a task changes as before."""
    await SqlTaskRepository(engine).add(TASK)
    async with make_session_factory(engine)() as session, session.begin():
        row = await session.scalar(select(TaskRow))
        assert row is not None
        row.goal = "changed"
        await session.flush()
    assert (await SqlTaskRepository(engine).get(TASK.id)).goal == "changed"


# ----------------------------------------------------------------------------------------
# Level 3: the database
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("statement", TAMPERING, ids=TAMPERING_IDS)
async def test_raw_sql_cannot_change_or_remove_a_row(engine: AsyncEngine, statement: str) -> None:
    log = SqlAuditLog(engine)
    await log.append(AUDIT_EVENT)
    with pytest.raises(IntegrityError, match="append-only"):
        await raw(engine, statement, id=AUDIT_EVENT.id.hex)
    assert await log.read() == (AUDIT_EVENT,)
    assert (await verify_chain(engine)).length == 1


async def test_without_the_triggers_raw_sql_would_change_a_row(engine: AsyncEngine) -> None:
    """Negative case: the refusal is the triggers' doing, not SQLite's."""
    log = SqlAuditLog(engine)
    await log.append(AUDIT_EVENT)
    await drop_triggers(engine)
    await raw(engine, TAMPERING[0])
    assert (await log.read())[0].summary == "rewritten"


async def test_a_bare_engine_lets_replace_walk_around_the_delete_trigger(file_url: str) -> None:
    """Negative case for ``PRAGMA recursive_triggers``: without it, REPLACE bypasses the trigger."""
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        await SqlAuditLog(engine).append(AUDIT_EVENT)
    finally:
        await engine.dispose()
    bare = create_async_engine(async_url(file_url))
    try:
        await raw(bare, TAMPERING[2], id=AUDIT_EVENT.id.hex)
        rows = await rows_of(bare)
        assert [row.summary for row in rows] == ["rewritten"]
    finally:
        await bare.dispose()


# ----------------------------------------------------------------------------------------
# The chain
# ----------------------------------------------------------------------------------------


async def test_rows_are_linked_from_the_genesis(engine: AsyncEngine) -> None:
    log = SqlAuditLog(engine)
    await append_many(log, 3)
    rows = await rows_of(engine)
    assert rows[0].prev_hash == GENESIS_HASH
    for previous, row in zip(rows, rows[1:], strict=False):
        assert row.prev_hash == previous.row_hash
    for row in rows:
        assert row.row_hash == link_hash(row.prev_hash, row_record(row))
    assert await verify_chain(engine) == ChainSummary(length=3, head_hash=rows[-1].row_hash)


async def test_an_empty_log_verifies_to_the_genesis(engine: AsyncEngine) -> None:
    assert await verify_chain(engine) == ChainSummary(length=0, head_hash=GENESIS_HASH)


async def test_the_record_is_the_same_before_and_after_the_database(engine: AsyncEngine) -> None:
    """The canonical form of the row about to be written equals that of the row read back."""
    await SqlAuditLog(engine).append(AUDIT_EVENT)
    (stored,) = await rows_of(engine)
    assert row_record(audit_event_to_row(AUDIT_EVENT)) == row_record(stored)
    assert set(row_record(stored)) == set(HASHED_COLUMNS)


async def test_an_altered_row_is_detected(engine: AsyncEngine) -> None:
    log = SqlAuditLog(engine)
    await append_many(log, 3)
    await drop_triggers(engine)
    await raw(engine, "UPDATE audit_events SET summary = 'rewritten' WHERE seq = 2")
    with pytest.raises(AuditChainError) as excinfo:
        await verify_chain(engine)
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.ALTERED_ROW)


@pytest.mark.parametrize("column", [name for name in HASHED_COLUMNS if name != "summary"])
async def test_every_hashed_column_is_covered(engine: AsyncEngine, column: str) -> None:
    await append_many(SqlAuditLog(engine), 1)
    await drop_triggers(engine)
    value = f"'{'f' * 32}'" if column == "id" or column.endswith("_id") else "'x'"
    if column == "created_at":
        value = "'2001-01-01 00:00:00'"
    elif column in ("usage", "error", "payload"):
        value = "'{\"altered\": true}'"
    await raw(engine, f"UPDATE audit_events SET {column} = {value} WHERE seq = 1")
    with pytest.raises(AuditChainError) as excinfo:
        await verify_chain(engine)
    assert excinfo.value.fault is ChainFault.ALTERED_ROW


async def test_a_row_removed_from_the_middle_is_detected(engine: AsyncEngine) -> None:
    await append_many(SqlAuditLog(engine), 3)
    await drop_triggers(engine)
    await raw(engine, "DELETE FROM audit_events WHERE seq = 2")
    with pytest.raises(AuditChainError) as excinfo:
        await verify_chain(engine)
    assert (excinfo.value.position, excinfo.value.fault) == (3, ChainFault.BROKEN_LINK)


async def test_a_forged_previous_hash_is_detected(engine: AsyncEngine) -> None:
    await append_many(SqlAuditLog(engine), 2)
    await drop_triggers(engine)
    await raw(engine, f"UPDATE audit_events SET prev_hash = '{'f' * 64}' WHERE seq = 2")
    with pytest.raises(AuditChainError) as excinfo:
        await verify_chain(engine)
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.BROKEN_LINK)


async def test_a_first_row_off_the_genesis_is_detected(engine: AsyncEngine) -> None:
    await append_many(SqlAuditLog(engine), 2)
    await drop_triggers(engine)
    await raw(engine, "DELETE FROM audit_events WHERE seq = 1")
    with pytest.raises(AuditChainError) as excinfo:
        await verify_chain(engine)
    assert (excinfo.value.position, excinfo.value.fault) == (2, ChainFault.BROKEN_LINK)


async def test_a_truncated_tail_is_not_detected(engine: AsyncEngine) -> None:
    """Documented limit (ADR 0007 §8): the summary is what to anchor elsewhere."""
    await append_many(SqlAuditLog(engine), 3)
    before = await verify_chain(engine)
    await drop_triggers(engine)
    await raw(engine, "DELETE FROM audit_events WHERE seq = 3")
    after = await verify_chain(engine)
    assert after.length == 2 and after != before


async def test_a_fork_cannot_be_written_even_without_the_adapter(engine: AsyncEngine) -> None:
    """``UNIQUE(prev_hash)``: a second row claiming the same predecessor is refused."""
    await append_many(SqlAuditLog(engine), 2)
    (first, _) = await rows_of(engine)
    with pytest.raises(IntegrityError, match="UNIQUE"):
        await raw(
            engine,
            "INSERT INTO audit_events (id, created_at, event_type, actor_kind, actor_id, summary,"
            " payload, prev_hash, row_hash) VALUES (:id, '2026-01-01', 'NOTE', 'ELA', 'ela',"
            " 'fork', '{}', :prev, 'r')",
            id=event_number(9).hex,
            prev=first.row_hash,
        )
    with pytest.raises(IntegrityError, match="UNIQUE"):
        await raw(
            engine,
            "INSERT INTO audit_events (id, created_at, event_type, actor_kind, actor_id, summary,"
            " payload, prev_hash, row_hash) VALUES (:id, '2026-01-01', 'NOTE', 'ELA', 'ela',"
            " 'second genesis', '{}', :prev, 'r')",
            id=event_number(9).hex,
            prev=GENESIS_HASH,
        )


async def test_verification_reads_in_windows(engine: AsyncEngine, statements: Attach) -> None:
    await append_many(SqlAuditLog(engine), 5)
    recorded = statements(engine)
    windowed = await verify_chain(engine, batch_size=2)
    selects = [s for s in recorded() if s.startswith("SELECT")]
    assert len(selects) == 3
    assert all("LIMIT" in s and "audit_events.seq >" in s for s in selects)
    assert windowed == await verify_chain(engine)


async def test_a_log_that_fills_its_windows_exactly_is_verified(engine: AsyncEngine) -> None:
    await append_many(SqlAuditLog(engine), 4)
    assert (await verify_chain(engine, batch_size=2)).length == 4


@pytest.mark.parametrize("batch_size", [0, -1])
async def test_a_non_positive_batch_size_is_a_callers_bug(
    engine: AsyncEngine, batch_size: int
) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        await verify_chain(engine, batch_size=batch_size)


# ----------------------------------------------------------------------------------------
# The write lock and the errors
# ----------------------------------------------------------------------------------------


async def test_append_takes_the_write_lock_before_reading_the_head(
    engine: AsyncEngine, statements: Attach
) -> None:
    recorded = statements(engine)
    await SqlAuditLog(engine).append(AUDIT_EVENT)
    seen = recorded()
    assert seen[0] == "BEGIN IMMEDIATE"
    assert seen[1].startswith("SELECT audit_events.row_hash")
    assert seen[2].startswith("INSERT INTO audit_events")
    assert not any("WHERE audit_events.id" in s for s in seen)  # no check before the insert


async def test_a_duplicate_is_caught_by_the_unique_constraint(engine: AsyncEngine) -> None:
    log = SqlAuditLog(engine)
    await log.append(AUDIT_EVENT)
    with pytest.raises(AlreadyExistsError):
        await log.append(AUDIT_EVENT.model_copy(update={"summary": "rewritten history"}))
    assert (await verify_chain(engine)).length == 1


async def test_concurrent_appends_queue_on_the_lock_and_chain_up(file_url: str) -> None:
    """Two writers on two connections: the second waits, then links to the first (decision 5)."""
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        log = SqlAuditLog(engine)
        first, second = (AUDIT_EVENT.model_copy(update={"id": event_number(n)}) for n in (1, 2))
        await asyncio.gather(log.append(first), log.append(second))
        assert (await verify_chain(engine)).length == 2
        assert {event.id for event in await log.read()} == {first.id, second.id}
    finally:
        await engine.dispose()


WINDOW = "audit_events.seq >"
"""What a window of ``verify_chain`` looks like from a statement listener."""

DEADLOCK_GUARD = 30.0
"""Seconds before a wait gives up. Not a margin: nothing that works waits anywhere near this
long, and nothing that works fails because a machine was slow. It is what turns a regression
that would hang the suite into a test that fails."""


class _ParkedWindow:
    """A verification stopped inside its own snapshot, and the switch that lets it go on."""

    def __init__(self) -> None:
        self.parked = asyncio.Event()
        """Set by the verification once it is holding its snapshot."""
        self.released = asyncio.Event()
        """Set by the test once it has finished looking."""


def _park_the_first_window(engine: AsyncEngine) -> _ParkedWindow:
    """Hold ``verify_chain`` after its first window until the test releases it.

    ``after_cursor_execute`` and not ``before``: SQLite takes the snapshot at the first read of
    the transaction, so a listener firing before it would park a reader still holding nothing and
    the append would have nothing to prove. Only the first window is held; the rest run at
    whatever speed the machine has, because by then nothing depends on it.

    The wait goes through :func:`~sqlalchemy.util.await_only` and not through a
    ``threading.Event``. A statement listener does not run on the connection's thread: it runs in
    the greenlet on the event loop's, so blocking it blocks the loop — and an append that cannot
    reach the loop is an append this test would be timing rather than watching. ``await_only``
    suspends the verification the way SQLAlchemy suspends it itself, and leaves the loop free.
    """
    window = _ParkedWindow()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _hold(conn: object, cursor: object, statement: str, *args: object) -> None:
        if WINDOW in statement and not window.parked.is_set():
            window.parked.set()
            await_only(window.released.wait())

    return window


def _refuse_to_wait_for_a_lock(engine: AsyncEngine) -> None:
    """``PRAGMA busy_timeout=0``: a connection that cannot take the lock says so at once.

    SQLite otherwise retries for five seconds, and a test watching for a lock would be back to
    measuring a wait — which is the thing this file no longer does.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _no_waiting(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA busy_timeout=0")
        cursor.close()


async def _append_while_the_verification_is_parked(
    engine: AsyncEngine, rows: int
) -> tuple[bool, ChainSummary]:
    """Append one row with the verification held open inside its snapshot; whether it was still
    running when the append returned, and what it saw.

    The verification is not made *slow*, it is made to *wait*: it stops on an event and goes on
    when the test says so, so "still running" is true by construction and not by arithmetic on a
    budget. What remains to be found out is the only thing worth asserting — whether the append
    can get through while a reader holds a snapshot open. Under WAL it returns; under a rollback
    journal it would sit on the lock until SQLite gave up, and that is a failure, not a hang.
    """
    log = SqlAuditLog(engine)
    await append_many(log, rows)
    window = _park_the_first_window(engine)
    verification = asyncio.create_task(verify_chain(engine, batch_size=1))
    try:
        async with asyncio.timeout(DEADLOCK_GUARD):
            await window.parked.wait()
        await log.append(AUDIT_EVENT.model_copy(update={"id": event_number(99)}))
        still_running = not verification.done()
    finally:
        window.released.set()
    return still_running, await verification


async def test_a_long_verification_does_not_block_an_append(file_url: str) -> None:
    """Review M2.2: with WAL a reader never blocks a writer; the append returns while the
    verification is still running, and the verification sees its snapshot, not the new row.

    The verification is held open by an event and not by a sleep (the CI fix): what this asserts
    is decided by SQLite's journal mode, never by how fast the machine got through 500ms.
    """
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        still_running, summary = await _append_while_the_verification_is_parked(engine, rows=8)
        assert still_running
        assert summary.length == 8
        assert (await verify_chain(engine)).length == 9
    finally:
        await engine.dispose()


async def test_without_wal_the_append_is_refused_while_the_verification_reads(
    file_url: str,
) -> None:
    """Negative case: on a rollback journal the reader's snapshot holds the writer's commit.

    What is asserted changed with the M9.1 CI fix, and it is worth saying why (ADR 0006 §13).
    This test used to say "the append had not returned yet" and read that off a clock: it waited,
    then concluded from nothing having happened. A negative established by a stopwatch is a
    negative that a slow machine can turn into a positive, which is exactly how the sibling test
    broke CI. With ``busy_timeout=0`` the wait becomes a refusal, and the refusal is a fact the
    test can see: SQLite says ``database is locked`` because the reader is holding the
    transaction, and the row is not in the log afterwards. Same promise, observed instead of
    inferred.
    """
    engine = create_async_engine(async_url(file_url))
    _refuse_to_wait_for_a_lock(engine)
    try:
        await create_schema(engine)
        log = SqlAuditLog(engine)
        await append_many(log, 8)
        window = _park_the_first_window(engine)
        verification = asyncio.create_task(verify_chain(engine, batch_size=1))
        try:
            async with asyncio.timeout(DEADLOCK_GUARD):
                await window.parked.wait()
            with pytest.raises(OperationalError, match="database is locked"):
                await log.append(AUDIT_EVENT.model_copy(update={"id": event_number(99)}))
        finally:
            window.released.set()
        assert (await verification).length == 8
        assert (await verify_chain(engine)).length == 8  # the refused row never landed
    finally:
        await engine.dispose()


async def test_verification_opens_its_snapshot_before_the_first_window(
    engine: AsyncEngine, statements: Attach
) -> None:
    await append_many(SqlAuditLog(engine), 2)
    recorded = statements(engine)
    await verify_chain(engine)
    assert recorded()[0] == "BEGIN"


async def test_a_naive_since_is_refused(engine: AsyncEngine) -> None:
    with pytest.raises(StatementError, match="timezone-aware"):
        await SqlAuditLog(engine).read(since=datetime(2026, 9, 4))


async def test_the_log_survives_reopening_the_file(file_url: str) -> None:
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        await append_many(SqlAuditLog(engine), 3)
    finally:
        await engine.dispose()
    reopened = make_engine(file_url)
    try:
        assert (
            len(
                await SqlAuditLog(reopened).read(task_id=TaskId(AUDIT_EVENT.task_id or UUID(int=0)))
            )
            == 3
        )
        assert (await verify_chain(reopened)).length == 3
    finally:
        await reopened.dispose()


# ----------------------------------------------------------------------------------------
# ``verify``: the same answer, asked through the protocol (M8.2, ADR 0024 §4)
# ----------------------------------------------------------------------------------------


async def test_the_adapter_is_the_verifier_the_core_asks(engine: AsyncEngine) -> None:
    """One line over ``verify_chain``, and the only class that can answer it: the summary is made
    of ``seq``, ``prev_hash`` and ``row_hash``, which an ``AuditEvent`` does not carry."""
    log = SqlAuditLog(engine)
    await append_many(log, 3)

    assert isinstance(log, AuditVerifier)
    assert await log.verify() == await verify_chain(engine)


async def test_verify_raises_where_the_chain_breaks(engine: AsyncEngine) -> None:
    """Raised, never returned as a ``False`` somebody can forget to look at (§33)."""
    log = SqlAuditLog(engine)
    await append_many(log, 3)
    await drop_triggers(engine)
    await raw(engine, "UPDATE audit_events SET summary = 'rewritten' WHERE seq = 2")

    with pytest.raises(AuditChainError) as raised:
        await log.verify()

    assert (raised.value.position, raised.value.fault) == (2, ChainFault.ALTERED_ROW)
