"""``ExecutionResultStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §63; ADR 0006, 0015).

Insert-only: a result is a fact the tool produced. ``AlreadyExistsError`` comes from a UNIQUE
constraint — on ``id``, or on the partial index that allows one ``STARTED`` record per step
(ADR 0021 §1-bis) — and ``NotFoundError`` from an empty read (ADR 0006 §8). The ``output``
column holds the user's content (§57) and stays in this private database; the audit trail only
names the result's id.

Which of the two constraints an ``IntegrityError`` came from is read from the row, not from the
database's message: a message is a string a driver may reword, and the caller is owed the reason
its insert was refused.

**The reservation of the spending cap** (M14.1, ADR 0057) is the one write that reads first:
``reserve`` holds SQLite's write lock from the read of the month's rows to the insert, with the
``BEGIN IMMEDIATE`` the audit log uses for its head, so two calls cannot both be written on the
same margin. The sum is not the store's: it reads the rows and asks the caller.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Final

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ela.domain import ExecutionId, ExecutionResult, ExecutionStatus, StepId, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import result_to_row, row_to_result
from ela.infrastructure.persistence.orm import ExecutionResultRow
from ela.ports import STARTED_ID, AlreadyExistsError, NotFoundError

__all__ = ["SqlExecutionResultStore"]

EXECUTION_RESULT = "execution result"
STARTED_FOR_STEP = "started record for step"
BEGIN_IMMEDIATE: Final = text("BEGIN IMMEDIATE")


class SqlExecutionResultStore:
    """What tools produced, in ``execution_results`` (port ``ExecutionResultStore``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this store is bound to."""
        return self._engine

    async def add(self, result: ExecutionResult) -> None:
        """Insert-only; and **what the domain refuses never becomes a row** (M13.1c, ADR 0055): a
        copy (``model_copy``) skips the validators, and this is the one door every result passes
        before anybody reads it — a row the mapper could not read back would hide every result of
        its task.
        """
        checked = ExecutionResult.model_validate(result.model_dump())
        async with self._sessions() as session, session.begin():
            await self._insert(session, checked, result)

    async def _insert(
        self, session: AsyncSession, checked: ExecutionResult, result: ExecutionResult
    ) -> None:
        session.add(result_to_row(checked))
        try:
            await session.flush()
        except IntegrityError:
            raise self._refusal(result) from None

    async def spending(self, since: datetime, until: datetime) -> tuple[ExecutionResult, ...]:
        async with self._sessions() as session:
            return await self._spending(session, since, until)

    async def reserve(
        self,
        record: ExecutionResult,
        since: datetime,
        until: datetime,
        admits: Callable[[tuple[ExecutionResult, ...]], bool],
    ) -> bool:
        checked = ExecutionResult.model_validate(record.model_dump())
        async with self._sessions() as session, session.begin():
            await session.execute(BEGIN_IMMEDIATE)
            if not admits(await self._spending(session, since, until)):
                return False
            await self._insert(session, checked, record)
            return True

    @staticmethod
    async def _spending(
        session: AsyncSession, since: datetime, until: datetime
    ) -> tuple[ExecutionResult, ...]:
        """The period's reservations, then what closes them: the results of the same steps that
        name one of them. Filtered here and not in SQL — a JSON ``NULL`` and a SQL ``NULL`` are
        two things, and the rows of a month are few."""
        started = (
            select(ExecutionResultRow)
            .where(
                ExecutionResultRow.status == ExecutionStatus.STARTED.value,
                ExecutionResultRow.created_at >= since,
                ExecutionResultRow.created_at < until,
            )
            .order_by(ExecutionResultRow.seq)
        )
        reservations = [
            result
            for result in (row_to_result(row) for row in await session.scalars(started))
            if result.worst_case is not None
        ]
        ids = {str(result.id) for result in reservations}
        tasks = {result.task_id for result in reservations if result.task_id is not None}
        if not tasks:
            return tuple(reservations)
        others = (
            select(ExecutionResultRow)
            .where(
                ExecutionResultRow.task_id.in_(tasks),
                ExecutionResultRow.status != ExecutionStatus.STARTED.value,
            )
            .order_by(ExecutionResultRow.seq)
        )
        closing = [
            result
            for result in (row_to_result(row) for row in await session.scalars(others))
            if result.metadata.get(STARTED_ID) in ids
        ]
        return (*reservations, *closing)

    @staticmethod
    def _refusal(result: ExecutionResult) -> AlreadyExistsError:
        """Which UNIQUE turned the insert down, named from what was being written.

        A ``STARTED`` row whose id is *also* taken satisfies both constraints, and is reported as
        the step conflict: that is the one that matters, and the exception type — which is what
        the port promises — is the same either way.
        """
        if result.status is ExecutionStatus.STARTED:
            return AlreadyExistsError(STARTED_FOR_STEP, result.step_id)
        return AlreadyExistsError(EXECUTION_RESULT, result.id)

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ExecutionResultRow).where(ExecutionResultRow.id == result_id)
            )
            if row is None:
                raise NotFoundError(EXECUTION_RESULT, result_id)
            return row_to_result(row)

    async def for_task(self, task_id: TaskId) -> tuple[ExecutionResult, ...]:
        query = (
            select(ExecutionResultRow)
            .where(ExecutionResultRow.task_id == task_id)
            .order_by(ExecutionResultRow.seq)
        )
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_result(row) for row in rows)

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        query = (
            select(ExecutionResultRow)
            .where(ExecutionResultRow.task_id == task_id, ExecutionResultRow.step_id == step_id)
            .order_by(ExecutionResultRow.seq)
        )
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_result(row) for row in rows)
