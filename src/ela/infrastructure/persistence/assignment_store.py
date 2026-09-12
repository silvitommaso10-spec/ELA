"""``AssignmentStore`` on SQLAlchemy (port in :mod:`ela.ports`; M12.2, ADR 0038).

Every move is one conditional ``UPDATE`` — the shape of ``SqlAuthorizationStore.consume`` and
``SqlApprovalStore.respond`` (ADR 0012 §5) — and when it touches no row, one read in the same
transaction names the reason. The claim carries the one condition an index cannot hold, "the node
holds no claim that has not expired", as a ``NOT EXISTS`` in the same statement (M12.1, D16):
SQLite runs the statement under its write lock, so two claims of one node cannot both see "no
live claim". That atomicity is the single writer's, and it is declared (ADR 0038): on an engine
with concurrent writers the ``NOT EXISTS`` would not be enough, and a lock on the node would.

One assignment per step that is not ``EXPIRED`` is a partial unique index, which does not need to
know the time: between an expiry and the next assignment of the same step there is always the
write of ``EXPIRED``, by whoever acted on it.

The statements carry ``synchronize_session=False``: nothing of these rows is loaded in the session
when they run, and the ORM must not issue a read of its own before the ``UPDATE`` — the check and
the write are one statement, and a read in front of it is the race this module exists to close.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, cast

from sqlalchemy import CursorResult, Update, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import Assignment, AssignmentId, AssignmentState, DeviceId, StepId, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import assignment_to_row, row_to_assignment
from ela.infrastructure.persistence.orm import AssignmentRow
from ela.ports import (
    AlreadyExistsError,
    AssignmentExpiredError,
    AssignmentHeldElsewhereError,
    AssignmentNodeBusyError,
    AssignmentStateError,
    AssignmentStillLiveError,
    NotFoundError,
)

__all__ = ["SqlAssignmentStore"]

ASSIGNMENT: Final = "assignment"
OPEN_FOR_STEP: Final = "open assignment for step"
LIVE_STATES: Final = (AssignmentState.OFFERED.value, AssignmentState.CLAIMED.value)
"""The states an expiry can still act on: an offer nobody took, and work in hand."""


class SqlAssignmentStore:
    """The work handed to remote nodes, in ``assignments`` (port ``AssignmentStore``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this store is bound to."""
        return self._engine

    async def add(self, assignment: Assignment) -> None:
        try:
            async with self._sessions() as session, session.begin():
                session.add(assignment_to_row(assignment))
                await session.flush()
        except IntegrityError:
            raise await self._why_not_added(assignment) from None

    async def get(self, assignment_id: AssignmentId) -> Assignment:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AssignmentRow).where(AssignmentRow.id == assignment_id)
            )
            if row is None:
                raise NotFoundError(ASSIGNMENT, assignment_id)
            return row_to_assignment(row)

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[Assignment, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(AssignmentRow)
                .where(AssignmentRow.task_id == task_id, AssignmentRow.step_id == step_id)
                .order_by(AssignmentRow.seq)
            )
            return tuple(row_to_assignment(row) for row in rows)

    async def offered_to(self, device_id: DeviceId) -> tuple[Assignment, ...]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(AssignmentRow)
                .where(
                    AssignmentRow.device_id == device_id,
                    AssignmentRow.state == AssignmentState.OFFERED.value,
                )
                .order_by(AssignmentRow.seq)
            )
            return tuple(row_to_assignment(row) for row in rows)

    async def claim(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        """One statement: the offer is the node's and alive, and the node holds nothing alive.

        The inner read is on an alias of the table, from SQLAlchemy's core: this module never
        imports ``sqlalchemy.orm``, which would put the ORM and the domain in one module (rule 8).
        """
        held = AssignmentRow.__table__.alias("held")
        busy = exists().where(
            held.c.device_id == device_id,
            held.c.state == AssignmentState.CLAIMED.value,
            held.c.expires_at > now,
        )
        statement = (
            update(AssignmentRow)
            .where(
                AssignmentRow.id == assignment_id,
                AssignmentRow.device_id == device_id,
                AssignmentRow.state == AssignmentState.OFFERED.value,
                AssignmentRow.expires_at > now,
                ~busy,
            )
            .values(state=AssignmentState.CLAIMED.value, claimed_at=now, expires_at=expires_at)
        )
        return await self._move(statement, assignment_id, device_id, AssignmentState.OFFERED, now)

    async def deliver(
        self, assignment_id: AssignmentId, *, device_id: DeviceId, now: datetime, digest: str
    ) -> Assignment:
        statement = (
            update(AssignmentRow)
            .where(*_claimed_by(assignment_id, device_id, now))
            .values(state=AssignmentState.DELIVERED.value, delivered_at=now, delivery_digest=digest)
        )
        return await self._move(statement, assignment_id, device_id, AssignmentState.CLAIMED, now)

    async def renew(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        statement = (
            update(AssignmentRow)
            .where(*_claimed_by(assignment_id, device_id, now))
            .values(expires_at=expires_at)
        )
        return await self._move(statement, assignment_id, device_id, AssignmentState.CLAIMED, now)

    async def expire(self, assignment_id: AssignmentId, *, now: datetime) -> Assignment:
        """``EXPIRED`` only where time has already decided; an expiry written twice is one."""
        statement = (
            update(AssignmentRow)
            .where(
                AssignmentRow.id == assignment_id,
                AssignmentRow.state.in_(LIVE_STATES),
                AssignmentRow.expires_at <= now,
            )
            .values(state=AssignmentState.EXPIRED.value)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            row = await session.scalar(
                select(AssignmentRow).where(AssignmentRow.id == assignment_id)
            )
            if row is None:
                raise NotFoundError(ASSIGNMENT, assignment_id)
            if cast(CursorResult[Any], result).rowcount == 0:
                if row.state == AssignmentState.DELIVERED.value:
                    raise AssignmentStateError(assignment_id, AssignmentState.DELIVERED)
                if row.state != AssignmentState.EXPIRED.value:
                    raise AssignmentStillLiveError(assignment_id, row.expires_at)
            return row_to_assignment(row)

    async def cut_short(self, device_id: DeviceId, *, now: datetime) -> int:
        statement = (
            update(AssignmentRow)
            .where(
                AssignmentRow.device_id == device_id,
                AssignmentRow.state.in_(LIVE_STATES),
                AssignmentRow.expires_at > now,
            )
            .values(expires_at=now)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement)
            return cast(CursorResult[Any], result).rowcount

    async def _move(
        self,
        statement: Update,
        assignment_id: AssignmentId,
        device_id: DeviceId,
        state: AssignmentState,
        now: datetime,
    ) -> Assignment:
        """The ``UPDATE``, then one read that returns the row or names why it did not move."""
        async with self._sessions() as session, session.begin():
            result = await session.execute(statement.execution_options(synchronize_session=False))
            row = await session.scalar(
                select(AssignmentRow).where(AssignmentRow.id == assignment_id)
            )
            if cast(CursorResult[Any], result).rowcount == 0 or row is None:
                raise _why_not_moved(assignment_id, row, device_id, state, now)
            return row_to_assignment(row)

    async def _why_not_added(self, assignment: Assignment) -> AlreadyExistsError:
        """Which of the two constraints refused the row — its id, else its step — read from the
        table and never parsed out of the database's message."""
        async with self._sessions() as session:
            taken = await session.scalar(
                select(AssignmentRow.seq).where(AssignmentRow.id == assignment.id)
            )
        if taken is not None:
            return AlreadyExistsError(ASSIGNMENT, assignment.id)
        return AlreadyExistsError(OPEN_FOR_STEP, assignment.step_id)


def _claimed_by(assignment_id: AssignmentId, device_id: DeviceId, now: datetime) -> tuple[Any, ...]:
    """The predicate of every move of work in hand: this node's, ``CLAIMED``, alive at ``now``."""
    return (
        AssignmentRow.id == assignment_id,
        AssignmentRow.device_id == device_id,
        AssignmentRow.state == AssignmentState.CLAIMED.value,
        AssignmentRow.expires_at > now,
    )


def _why_not_moved(
    assignment_id: AssignmentId,
    row: AssignmentRow | None,
    device_id: DeviceId,
    state: AssignmentState,
    now: datetime,
) -> Exception:
    """Unknown, another node's, not in the state the move starts from, expired — the port's order.

    What is left when the row passes all four is the one condition beyond the row itself, and only
    a claim has one: the node holds work that has not expired.
    """
    if row is None:
        return NotFoundError(ASSIGNMENT, assignment_id)
    if row.device_id != device_id:
        return AssignmentHeldElsewhereError(assignment_id, DeviceId(row.device_id))
    if row.state != state.value:
        return AssignmentStateError(assignment_id, AssignmentState(row.state))
    if row.expires_at <= now:
        return AssignmentExpiredError(assignment_id, row.expires_at)
    assert state is AssignmentState.OFFERED, "only a claim has a condition beyond its own row"
    return AssignmentNodeBusyError(assignment_id, device_id)
