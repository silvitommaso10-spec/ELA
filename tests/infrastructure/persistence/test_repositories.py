"""What the SQL adapters do beyond the contract (ADR 0006 §4, §6, §8).

The contract tests in ``tests/contracts/`` already run on these adapters. Here: where the errors
come from, that the file really persists, that ``uses`` survives concurrency, that the foreign
keys hold, and that trivial reads cost no query.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import TaskId, TaskState
from ela.infrastructure.persistence import (
    SqlAuthorizationStore,
    SqlTaskRepository,
    make_engine,
)
from ela.ports import AlreadyExistsError, NotFoundError
from tests.contracts.test_task_repository import CHILD, OTHER_TASK
from tests.domain.examples import POLICY_AUTHORIZATION, SINGLE_USE_AUTHORIZATION, TASK, TASK_EVENT
from tests.infrastructure.persistence.conftest import Recorder, create_schema

Attach = Callable[[AsyncEngine], Recorder]


def _inserts(recorded: list[str], table: str) -> list[str]:
    return [s for s in recorded if s.startswith(f"INSERT INTO {table}")]


def _selects(recorded: list[str], table: str) -> list[str]:
    return [s for s in recorded if s.startswith("SELECT") and f"FROM {table}" in s]


# ----------------------------------------------------------------------------------------
# Where the errors come from
# ----------------------------------------------------------------------------------------


async def test_duplicate_task_is_caught_by_the_unique_constraint(
    engine: AsyncEngine, statements: Attach
) -> None:
    repository = SqlTaskRepository(engine)
    await repository.add(TASK)
    recorded = statements(engine)
    with pytest.raises(AlreadyExistsError):
        await repository.add(TASK)
    seen = recorded()
    assert _selects(seen, "tasks") == []  # no check before the insert
    assert len(_inserts(seen, "tasks")) == 1


async def test_duplicate_grant_is_caught_by_the_unique_constraint(
    engine: AsyncEngine, statements: Attach
) -> None:
    store = SqlAuthorizationStore(engine)
    await store.grant(POLICY_AUTHORIZATION)
    recorded = statements(engine)
    with pytest.raises(AlreadyExistsError):
        await store.grant(POLICY_AUTHORIZATION)
    assert _selects(recorded(), "authorizations") == []


async def test_save_of_an_unknown_task_writes_nothing(engine: AsyncEngine) -> None:
    repository = SqlTaskRepository(engine)
    with pytest.raises(NotFoundError):
        await repository.save(TASK)
    assert await repository.tasks() == ()


async def test_events_of_unknown_task_and_unknown_grant_are_not_found(
    engine: AsyncEngine,
) -> None:
    with pytest.raises(NotFoundError):
        await SqlTaskRepository(engine).events(TASK.id)
    with pytest.raises(NotFoundError):
        await SqlAuthorizationStore(engine).uses(POLICY_AUTHORIZATION.id)


# ----------------------------------------------------------------------------------------
# Foreign keys (decision 5 of the review: parent_id and task_id are real references)
# ----------------------------------------------------------------------------------------


async def test_unknown_parent_is_refused_and_nothing_is_written(engine: AsyncEngine) -> None:
    repository = SqlTaskRepository(engine)
    with pytest.raises(NotFoundError) as excinfo:
        await repository.add(CHILD)
    assert (excinfo.value.kind, excinfo.value.key) == ("task", TASK.id)
    assert await repository.tasks() == ()


async def test_a_task_cannot_be_its_own_parent(engine: AsyncEngine) -> None:
    repository = SqlTaskRepository(engine)
    with pytest.raises(NotFoundError):
        await repository.add(TASK.model_copy(update={"parent_id": TASK.id}))


async def test_the_database_itself_refuses_an_unknown_parent(engine: AsyncEngine) -> None:
    """Defence in depth: even a direct INSERT past the repository hits the foreign key."""
    async with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="FOREIGN KEY"):
            await connection.execute(
                text(
                    "INSERT INTO tasks (id, created_at, goal, state, parent_id, metadata)"
                    " VALUES ('t1', '2026-01-01', 'g', 'CREATED', 'nobody', '{}')"
                )
            )


# ----------------------------------------------------------------------------------------
# Real persistence
# ----------------------------------------------------------------------------------------


async def test_data_survives_a_new_engine_on_the_same_file(file_url: str) -> None:
    first = make_engine(file_url)
    await create_schema(first)
    precise = TASK.model_copy(
        update={"created_at": datetime(2026, 9, 4, 10, 30, 15, 123456, tzinfo=UTC)}
    )
    await SqlTaskRepository(first).add(precise)
    await SqlTaskRepository(first).append_event(TASK_EVENT)
    await SqlAuthorizationStore(first).grant(SINGLE_USE_AUTHORIZATION)
    await SqlAuthorizationStore(first).record_use(SINGLE_USE_AUTHORIZATION.id)
    await first.dispose()

    second = make_engine(file_url)
    try:
        repository = SqlTaskRepository(second)
        store = SqlAuthorizationStore(second)
        assert await repository.get(TASK.id) == precise
        assert await repository.events(TASK.id) == (TASK_EVENT,)
        assert await store.get(SINGLE_USE_AUTHORIZATION.id) == SINGLE_USE_AUTHORIZATION
        assert await store.uses(SINGLE_USE_AUTHORIZATION.id) == 1
    finally:
        await second.dispose()


async def test_record_use_counts_every_concurrent_call(file_url: str) -> None:
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        store = SqlAuthorizationStore(engine)
        await store.grant(POLICY_AUTHORIZATION)
        totals = await asyncio.gather(
            *(store.record_use(POLICY_AUTHORIZATION.id) for _ in range(20))
        )
        assert sorted(totals) == list(range(1, 21))
        assert await store.uses(POLICY_AUTHORIZATION.id) == 20
    finally:
        await engine.dispose()


async def test_record_use_increments_in_sql(engine: AsyncEngine, statements: Attach) -> None:
    store = SqlAuthorizationStore(engine)
    await store.grant(POLICY_AUTHORIZATION)
    recorded = statements(engine)
    assert await store.record_use(POLICY_AUTHORIZATION.id) == 1
    updates = [s for s in recorded() if s.startswith("UPDATE authorizations")]
    assert len(updates) == 1
    assert "uses=(authorizations.uses + ?)" in updates[0]


# ----------------------------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------------------------


async def test_trivial_reads_run_no_query(engine: AsyncEngine, statements: Attach) -> None:
    repository = SqlTaskRepository(engine)
    await repository.add(TASK)
    recorded = statements(engine)
    assert await repository.tasks(states=frozenset()) == ()
    assert await repository.tasks(limit=0) == ()
    assert await repository.tasks(limit=-1) == ()
    assert recorded() == []


async def test_reads_are_ordered_by_sequence_not_by_time(engine: AsyncEngine) -> None:
    repository = SqlTaskRepository(engine)
    later = OTHER_TASK.model_copy(update={"created_at": datetime(2030, 1, 1, tzinfo=UTC)})
    await repository.add(later)
    await repository.add(TASK)
    assert await repository.tasks() == (later, TASK)
    assert await repository.tasks(states=frozenset({TaskState.QUEUED}), limit=5) == (later,)


async def test_the_engine_is_exposed(engine: AsyncEngine) -> None:
    assert SqlTaskRepository(engine).engine is engine
    assert SqlAuthorizationStore(engine).engine is engine


async def test_unknown_id_in_every_task_read(engine: AsyncEngine) -> None:
    unknown = TaskId(UUID(int=999))
    repository = SqlTaskRepository(engine)
    for call in (repository.get(unknown), repository.events(unknown)):
        with pytest.raises(NotFoundError):
            await call
