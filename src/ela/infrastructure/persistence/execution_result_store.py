"""``ExecutionResultStore`` on SQLAlchemy (port in :mod:`ela.ports`, spec §63; ADR 0006, 0015).

Insert-only: a result is a fact the tool produced. ``AlreadyExistsError`` comes from a UNIQUE
constraint — on ``id``, or on the partial index that allows one ``STARTED`` record per step
(ADR 0021 §1-bis) — and ``NotFoundError`` from an empty read (ADR 0006 §8). The ``output``
column holds the user's content (§57) and stays in this private database; the audit trail only
names the result's id.

Which of the two constraints an ``IntegrityError`` came from is read from the row, not from the
database's message: a message is a string a driver may reword, and the caller is owed the reason
its insert was refused.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import ExecutionId, ExecutionResult, ExecutionStatus, StepId, TaskId
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import result_to_row, row_to_result
from ela.infrastructure.persistence.orm import ExecutionResultRow
from ela.ports import AlreadyExistsError, NotFoundError

__all__ = ["SqlExecutionResultStore"]

EXECUTION_RESULT = "execution result"
STARTED_FOR_STEP = "started record for step"


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
                raise self._refusal(result) from None

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

    async def for_step(self, task_id: TaskId, step_id: StepId) -> tuple[ExecutionResult, ...]:
        query = (
            select(ExecutionResultRow)
            .where(ExecutionResultRow.task_id == task_id, ExecutionResultRow.step_id == step_id)
            .order_by(ExecutionResultRow.seq)
        )
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_result(row) for row in rows)
