"""``TaskRepository`` on SQLAlchemy (port in :mod:`ela.ports`, spec §14, §15; ADR 0006).

One transaction per call. Port errors come from the database, not from a check-then-act:
``AlreadyExistsError`` from the UNIQUE constraint on ``id``, ``NotFoundError`` from an empty
read or a zero row count. The two places with two possible errors — a parent in ``add``/``save``
and the task of ``append_event`` — check the referenced task first, inside the same transaction,
so that a foreign-key failure is never mistaken for a duplicate.
"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ela.domain import Task, TaskEvent, TaskId, TaskState
from ela.infrastructure.persistence.engine import make_session_factory
from ela.infrastructure.persistence.mappers import (
    event_to_row,
    row_to_event,
    row_to_task,
    task_to_row,
    task_values,
)
from ela.infrastructure.persistence.orm import TaskEventRow, TaskRow
from ela.ports import AlreadyExistsError, NotFoundError

__all__ = ["SqlTaskRepository"]

TASK = "task"
TASK_EVENT = "task event"


async def _exists(session: AsyncSession, task_id: TaskId) -> bool:
    return await session.scalar(select(TaskRow.seq).where(TaskRow.id == task_id)) is not None


async def _require_task(session: AsyncSession, task_id: TaskId) -> None:
    if not await _exists(session, task_id):
        raise NotFoundError(TASK, task_id)


async def _require_parent(session: AsyncSession, task: Task) -> None:
    if task.parent_id is not None:
        await _require_task(session, task.parent_id)


class SqlTaskRepository:
    """Tasks and their events in ``tasks`` and ``task_events`` (port ``TaskRepository``)."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine
        self._sessions = make_session_factory(engine)

    @property
    def engine(self) -> AsyncEngine:
        """The engine this repository is bound to."""
        return self._engine

    async def add(self, task: Task) -> None:
        async with self._sessions() as session, session.begin():
            await _require_parent(session, task)
            session.add(task_to_row(task))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(TASK, task.id) from None

    async def save(self, task: Task) -> None:
        async with self._sessions() as session, session.begin():
            await _require_parent(session, task)
            values: dict[str, Any] = task_values(task)
            result = await session.execute(
                update(TaskRow).where(TaskRow.id == task.id).values(**values)
            )
            if cast(CursorResult[Any], result).rowcount == 0:
                raise NotFoundError(TASK, task.id)

    async def get(self, task_id: TaskId) -> Task:
        async with self._sessions() as session:
            row = await session.scalar(select(TaskRow).where(TaskRow.id == task_id))
            if row is None:
                raise NotFoundError(TASK, task_id)
            return row_to_task(row)

    async def tasks(
        self, *, states: frozenset[TaskState] | None = None, limit: int | None = None
    ) -> tuple[Task, ...]:
        if (states is not None and not states) or (limit is not None and limit <= 0):
            return ()
        query = select(TaskRow).order_by(TaskRow.seq)
        if states is not None:
            query = query.where(TaskRow.state.in_([state.value for state in states]))
        if limit is not None:
            query = query.limit(limit)
        async with self._sessions() as session:
            rows = await session.scalars(query)
            return tuple(row_to_task(row) for row in rows)

    async def append_event(self, event: TaskEvent) -> None:
        async with self._sessions() as session, session.begin():
            await _require_task(session, event.task_id)
            session.add(event_to_row(event))
            try:
                await session.flush()
            except IntegrityError:
                raise AlreadyExistsError(TASK_EVENT, event.id) from None

    async def events(self, task_id: TaskId) -> tuple[TaskEvent, ...]:
        async with self._sessions() as session:
            await _require_task(session, task_id)
            query = (
                select(TaskEventRow)
                .where(TaskEventRow.task_id == task_id)
                .order_by(TaskEventRow.seq)
            )
            rows = await session.scalars(query)
            return tuple(row_to_event(row) for row in rows)
