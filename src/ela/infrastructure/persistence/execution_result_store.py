"""``ExecutionResultStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §63; ADR 0006, 0015).

Insert-only: a result is a fact the tool produced. ``AlreadyExistsError`` comes from the UNIQUE
constraint on ``id``, ``NotFoundError`` from an empty read (ADR 0006 §8). The ``output`` column
holds the user's content (§57) and stays in this private database; the audit trail only names
the result's id.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import ExecutionId, ExecutionResult, StepId, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import result_to_row, row_to_result
from ela.infrastructure.persistence.orm import ExecutionResultRow
from ela.ports import AlreadyExistsError, NotFoundError

__all__ = ["SqlExecutionResultStore"]

EXECUTION_RESULT = "execution result"


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
        async with self._sessions() as session, session.begin():
            session.add(result_to_row(result))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(EXECUTION_RESULT, result.id) from None

    async def get(self, result_id: ExecutionId) -> ExecutionResult:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ExecutionResultRow).where(ExecutionResultRow.id == result_id)
            )
            if row is None:
                raise NotFoundError(EXECUTION_RESULT, result_id)
            return row_to_result(row)

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        query = (
            select(ExecutionResultRow)
            .where(ExecutionResultRow.task_id == task_id, ExecutionResultRow.step_id == step_id)
            .order_by(ExecutionResultRow.seq)
        )
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_result(row) for row in rows)
