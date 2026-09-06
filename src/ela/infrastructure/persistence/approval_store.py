"""``ApprovalStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §30, §62; ADR 0006, 0015).

A request for consent is inserted PENDING and answered once. ``respond`` is a single conditional
``UPDATE`` — ``SET status, responded_by, responded_at WHERE id = :id AND status = 'PENDING' AND
(expires_at IS NULL OR expires_at > :now)`` — that SQLite runs under its write lock, so two
concurrent answers cannot both be recorded (the shape of ``consume``, ADR 0012 §5). If it touches
no row, one read names the error. Nothing but the answer is ever rewritten.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import Approval, ApprovalId, ApprovalStatus, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import approval_to_row, row_to_approval
from ela.infrastructure.persistence.orm import ApprovalRow
from ela.ports import (
    AlreadyExistsError,
    ApprovalAlreadyAnsweredError,
    ApprovalExpiredError,
    NotFoundError,
    check_answer,
    check_limit,
)

__all__ = ["SqlApprovalStore"]

APPROVAL = "approval"


class SqlApprovalStore:
    """Requests for consent and their answers in ``approvals`` (port ``ApprovalStore``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this store is bound to."""
        return self._engine

    async def add(self, approval: Approval) -> None:
        if approval.status is not ApprovalStatus.PENDING:
            raise ValueError(f"a request is added PENDING, not {approval.status.value}")
        async with self._sessions() as session, session.begin():
            session.add(approval_to_row(approval))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(APPROVAL, approval.id) from None

    async def get(self, approval_id: ApprovalId) -> Approval:
        async with self._sessions() as session:
            row = await session.scalar(select(ApprovalRow).where(ApprovalRow.id == approval_id))
            if row is None:
                raise NotFoundError(APPROVAL, approval_id)
            return row_to_approval(row)

    async def for_task(self, task_id: TaskId) -> tuple[Approval, ...]:
        query = select(ApprovalRow).where(ApprovalRow.task_id == task_id).order_by(ApprovalRow.seq)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_approval(row) for row in rows)

    async def pending(
        self, *, now: datetime | None = None, limit: int | None = None
    ) -> tuple[Approval, ...]:
        check_limit(limit)
        query = (
            select(ApprovalRow)
            .where(ApprovalRow.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRow.seq)
        )
        if now is not None:  # the same closed bound ``respond`` applies
            query = query.where(or_(ApprovalRow.expires_at.is_(None), ApprovalRow.expires_at > now))
        if limit is not None:
            query = query.limit(limit)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_approval(row) for row in rows)

    async def respond(
        self,
        approval_id: ApprovalId,
        *,
        status: ApprovalStatus,
        responded_by: str,
        now: datetime,
    ) -> Approval:
        """One conditional ``UPDATE``; if it touches no row, one read names the error."""
        check_answer(status)
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(ApprovalRow)
                .where(
                    ApprovalRow.id == approval_id,
                    ApprovalRow.status == ApprovalStatus.PENDING.value,
                    or_(ApprovalRow.expires_at.is_(None), ApprovalRow.expires_at > now),
                )
                .values(status=status.value, responded_by=responded_by, responded_at=now)
            )
            row = await session.scalar(select(ApprovalRow).where(ApprovalRow.id == approval_id))
            if cast(CursorResult[Any], result).rowcount == 0:
                raise _why_not_answered(approval_id, row, now)
            assert row is not None
            return row_to_approval(row)


def _why_not_answered(approval_id: ApprovalId, row: ApprovalRow | None, now: datetime) -> Exception:
    """The error for an ``UPDATE`` that matched nothing: unknown, answered, else expired.

    The safety is in the ``UPDATE``; this read only names the reason (already answered before
    expired: a request answered in time and then expired is answered).
    """
    if row is None:
        return NotFoundError(APPROVAL, approval_id)
    if row.status != ApprovalStatus.PENDING.value:
        return ApprovalAlreadyAnsweredError(approval_id, ApprovalStatus(row.status))
    assert row.expires_at is not None and row.expires_at <= now
    return ApprovalExpiredError(approval_id, row.expires_at)
