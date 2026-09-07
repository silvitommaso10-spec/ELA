"""``AuditLog`` on SQLAlchemy, with the hash chain of :mod:`ela.audit.chain` (spec §32; ADR 0007).

Three public members — ``append``, ``read`` and ``verify`` — and no way to change what was
written: no ``engine`` property, no update, no delete. The chain is maintained here on the way in
(``append`` reads the hash at the head of the log and links the new row to it) and checked by
:func:`verify_chain`.

``verify`` was added in M8.2 (ADR 0024 §4) so that the answer can be asked for through the
``AuditVerifier`` protocol, and therefore over the API: the function stays where it is and the
method is one line over it. It reads and reports; the port ``AuditLog`` keeps its two members, so
holding one still gives nobody a third way to write.

``append`` starts its transaction with ``BEGIN IMMEDIATE``: SQLite then holds the write lock from
the read of the head to the insert, so no other writer can slip a row in between (a second
``append`` waits, then reads the new head). Under that lock the only ``IntegrityError`` an insert
can raise is the UNIQUE on ``id``, which becomes :class:`~ela.ports.AlreadyExistsError` with no
check before the insert (ADR 0006 §8); ``UNIQUE(prev_hash)`` remains the backstop against any
writer that bypasses this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.audit.chain import (
    EMPTY_CHAIN,
    GENESIS_HASH,
    ChainSummary,
    Link,
    Record,
    link_hash,
    verify_links,
)
from ela.domain import AuditEvent, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import audit_event_to_row, row_to_audit_event
from ela.infrastructure.persistence.orm import HASHED_COLUMNS, AuditEventRow
from ela.ports import AlreadyExistsError, check_limit

__all__ = ["SqlAuditLog", "row_record", "verify_chain"]

AUDIT_EVENT: Final = "audit event"
DEFAULT_BATCH_SIZE: Final = 1000
BEGIN_IMMEDIATE: Final = text("BEGIN IMMEDIATE")
BEGIN_SNAPSHOT: Final = text("BEGIN")
"""The read transaction of ``verify_chain``: pysqlite opens none before a ``SELECT`` on its own,
and without one every window would be its own snapshot, missing a row appended midway."""


def _canonical(value: object) -> object:
    """A column value as the chain sees it: UUIDs and instants become fixed-form strings."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds")
    return value


def row_record(row: AuditEventRow) -> Record:
    """The :data:`~ela.infrastructure.persistence.orm.HASHED_COLUMNS` of a row as a record.

    The same function serves the row about to be inserted and the row read back, so the two
    canonical forms coincide: an aware instant in any offset and the UTC instant the database
    returns canonicalise to the same string.
    """
    return {name: _canonical(getattr(row, name)) for name in HASHED_COLUMNS}


def _link(row: AuditEventRow) -> Link:
    return Link(row.seq, row.prev_hash, row.row_hash, row_record(row))


class SqlAuditLog:
    """The append-only trail in ``audit_events`` (port ``AuditLog``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    async def append(self, event: AuditEvent) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(BEGIN_IMMEDIATE)
            head = await session.scalar(
                select(AuditEventRow.row_hash).order_by(AuditEventRow.seq.desc()).limit(1)
            )
            row = audit_event_to_row(event)
            row.prev_hash = GENESIS_HASH if head is None else head
            row.row_hash = link_hash(row.prev_hash, row_record(row))
            session.add(row)
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(AUDIT_EVENT, event.id) from None

    async def read(
        self,
        *,
        task_id: TaskId | None = None,
        since: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> tuple[AuditEvent, ...]:
        """Events in append order, or from the end when ``newest_first`` (M8.3, ADR 0025 §3).

        The direction is the ``ORDER BY``, so ``LIMIT`` takes its rows from the end the caller
        asked for and the database never reads the other end of the log. The tuple keeps the
        order it was read in: reversing it here would make ``limit`` and the order disagree.
        """
        check_limit(limit)
        order = AuditEventRow.seq.desc() if newest_first else AuditEventRow.seq
        query = select(AuditEventRow).order_by(order)
        if task_id is not None:
            query = query.where(AuditEventRow.task_id == task_id)
        if since is not None:
            query = query.where(AuditEventRow.created_at >= since)
        if limit is not None:
            query = query.limit(limit)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_audit_event(row) for row in rows)

    async def verify(self) -> ChainSummary:
        """The whole chain, verified (protocol :class:`~ela.audit.verifier.AuditVerifier`).

        :raises ~ela.audit.chain.AuditChainError: at the first entry that does not fit.
        """
        return await verify_chain(self._engine)


async def verify_chain(
    engine: AsyncEngine, *, batch_size: int = DEFAULT_BATCH_SIZE
) -> ChainSummary:
    """Verify the whole log, ``batch_size`` rows at a time, in one read transaction.

    Raises :class:`~ela.audit.chain.AuditChainError` with the ``seq`` of the first row that does
    not fit the chain. Never loads the whole log: rows are read in ``seq`` order with a keyset
    window, and a window shorter than ``batch_size`` is the last one. All windows see the same
    snapshot — the log as it was when the verification began — because the transaction is opened
    explicitly (:data:`BEGIN_SNAPSHOT`); with the WAL journal of the engine (ADR 0006 §12) that
    snapshot never blocks a concurrent ``append``.
    """
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, not {batch_size}")
    summary = EMPTY_CHAIN
    last_seq = 0
    async with make_session_factory(engine)() as session:
        await session.execute(BEGIN_SNAPSHOT)
        while True:
            window = select(AuditEventRow).where(AuditEventRow.seq > last_seq)
            rows = (
                await session.scalars(window.order_by(AuditEventRow.seq).limit(batch_size))
            ).all()
            summary = verify_links((_link(row) for row in rows), after=summary)
            if len(rows) < batch_size:
                return summary
            last_seq = rows[-1].seq
