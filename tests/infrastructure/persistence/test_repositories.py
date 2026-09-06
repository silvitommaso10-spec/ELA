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

from ela.domain import ApprovalStatus, TaskId, TaskState
from ela.infrastructure.persistence import (
    SqlApprovalStore,
    SqlAuthorizationStore,
    SqlExecutionResultStore,
    SqlTaskRepository,
    make_engine,
)
from ela.ports import (
    AlreadyExistsError,
    ApprovalAlreadyAnsweredError,
    AuthorizationExhaustedError,
    NotFoundError,
)
from tests.contracts.test_approval_store import PENDING as PENDING_APPROVAL
from tests.contracts.test_task_repository import CHILD, OTHER_TASK
from tests.domain.examples import (
    APPROVAL,
    EXECUTION_RESULT,
    LATER,
    NOW,
    POLICY_AUTHORIZATION,
    SINGLE_USE_AUTHORIZATION,
    TASK,
    TASK_EVENT,
)
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
    await SqlAuthorizationStore(first).consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
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


async def test_concurrent_consumes_of_a_single_use_grant_let_exactly_one_through(
    file_url: str,
) -> None:
    """ADR 0012 §5: the check and the count are one ``UPDATE`` under SQLite's write lock."""
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        store = SqlAuthorizationStore(engine)
        await store.grant(SINGLE_USE_AUTHORIZATION)
        outcomes = await asyncio.gather(
            *(store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW) for _ in range(20)),
            return_exceptions=True,
        )
        assert [o for o in outcomes if not isinstance(o, BaseException)] == [1]
        refused = [o for o in outcomes if isinstance(o, BaseException)]
        assert len(refused) == 19
        assert all(isinstance(o, AuthorizationExhaustedError) for o in refused)
        assert await store.uses(SINGLE_USE_AUTHORIZATION.id) == 1
    finally:
        await engine.dispose()


async def test_concurrent_consumes_of_a_limited_grant_count_exactly_max_uses(
    file_url: str,
) -> None:
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        store = SqlAuthorizationStore(engine)
        five = POLICY_AUTHORIZATION.model_copy(update={"max_uses": 5})
        await store.grant(five)
        outcomes = await asyncio.gather(
            *(store.consume(five.id, now=NOW) for _ in range(20)), return_exceptions=True
        )
        assert sorted(o for o in outcomes if isinstance(o, int)) == [1, 2, 3, 4, 5]
        assert sum(isinstance(o, AuthorizationExhaustedError) for o in outcomes) == 15
        assert await store.uses(five.id) == 5
    finally:
        await engine.dispose()


async def test_consume_is_one_conditional_update_in_sql(
    engine: AsyncEngine, statements: Attach
) -> None:
    store = SqlAuthorizationStore(engine)
    await store.grant(SINGLE_USE_AUTHORIZATION)
    recorded = statements(engine)
    assert await store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW) == 1
    updates = [s for s in recorded() if s.startswith("UPDATE authorizations")]
    assert len(updates) == 1
    (statement,) = updates
    assert "uses=(authorizations.uses + ?)" in statement
    assert "authorizations.uses < authorizations.max_uses" in statement
    assert "authorizations.expires_at > ?" in statement
    assert "authorizations.max_uses IS NULL" in statement
    assert "authorizations.expires_at IS NULL" in statement


async def test_a_refused_consume_updates_nothing_and_reads_once_to_name_the_error(
    engine: AsyncEngine, statements: Attach
) -> None:
    """The safety is in the ``UPDATE`` that matches no row; the ``SELECT`` only names the error."""
    store = SqlAuthorizationStore(engine)
    await store.grant(SINGLE_USE_AUTHORIZATION)
    await store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    recorded = statements(engine)
    with pytest.raises(AuthorizationExhaustedError):
        await store.consume(SINGLE_USE_AUTHORIZATION.id, now=NOW)
    seen = recorded()
    assert len([s for s in seen if s.startswith("UPDATE authorizations")]) == 1
    assert len(_selects(seen, "authorizations")) == 1
    assert await store.uses(SINGLE_USE_AUTHORIZATION.id) == 1
    assert LATER > NOW  # the grant expires LATER: the refusal above was exhaustion, not expiry


# ----------------------------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------------------------


async def test_an_empty_state_filter_runs_no_query(engine: AsyncEngine, statements: Attach) -> None:
    repository = SqlTaskRepository(engine)
    await repository.add(TASK)
    recorded = statements(engine)
    assert await repository.tasks(states=frozenset()) == ()
    assert recorded() == []


async def test_a_bad_limit_is_refused_before_any_query(
    engine: AsyncEngine, statements: Attach
) -> None:
    """``LIMIT -1`` would mean "no limit" to SQLite: the check happens before SQL is built."""
    repository = SqlTaskRepository(engine)
    recorded = statements(engine)
    with pytest.raises(ValueError):
        await repository.tasks(limit=-1)
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


# ----------------------------------------------------------------------------------------
# respond: one conditional UPDATE, as consume (ADR 0015 §3)
# ----------------------------------------------------------------------------------------


async def test_concurrent_answers_to_one_request_let_exactly_one_through(file_url: str) -> None:
    engine = make_engine(file_url)
    try:
        await create_schema(engine)
        store = SqlApprovalStore(engine)
        await store.add(PENDING_APPROVAL)
        outcomes = await asyncio.gather(
            *(
                store.respond(
                    PENDING_APPROVAL.id,
                    status=ApprovalStatus.GRANTED if i % 2 else ApprovalStatus.REJECTED,
                    responded_by=f"user-{i}",
                    now=NOW,
                )
                for i in range(20)
            ),
            return_exceptions=True,
        )
        answered = [o for o in outcomes if not isinstance(o, BaseException)]
        assert len(answered) == 1
        refused = [o for o in outcomes if isinstance(o, BaseException)]
        assert len(refused) == 19
        assert all(isinstance(o, ApprovalAlreadyAnsweredError) for o in refused)
        assert await store.get(PENDING_APPROVAL.id) == answered[0]
    finally:
        await engine.dispose()


async def test_respond_is_one_conditional_update_in_sql(
    engine: AsyncEngine, statements: Attach
) -> None:
    store = SqlApprovalStore(engine)
    await store.add(PENDING_APPROVAL)
    recorded = statements(engine)
    answered = await store.respond(
        PENDING_APPROVAL.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=NOW
    )
    assert answered.status is ApprovalStatus.GRANTED
    updates = [s for s in recorded() if s.startswith("UPDATE approvals")]
    assert len(updates) == 1
    (statement,) = updates
    assert "SET status=?, responded_at=?, responded_by=?" in statement
    assert "approvals.status = ?" in statement
    assert "approvals.expires_at > ?" in statement
    assert "approvals.expires_at IS NULL" in statement


async def test_a_refused_answer_updates_nothing_and_reads_once_to_name_the_error(
    engine: AsyncEngine, statements: Attach
) -> None:
    store = SqlApprovalStore(engine)
    await store.add(PENDING_APPROVAL)
    await store.respond(
        PENDING_APPROVAL.id, status=ApprovalStatus.REJECTED, responded_by="tommaso", now=NOW
    )
    recorded = statements(engine)
    with pytest.raises(ApprovalAlreadyAnsweredError):
        await store.respond(
            PENDING_APPROVAL.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=NOW
        )
    seen = recorded()
    assert len([s for s in seen if s.startswith("UPDATE approvals")]) == 1
    assert len(_selects(seen, "approvals")) == 1
    assert (await store.get(PENDING_APPROVAL.id)).status is ApprovalStatus.REJECTED


async def test_duplicate_request_and_result_are_caught_by_the_unique_constraint(
    engine: AsyncEngine, statements: Attach
) -> None:
    approvals, results = SqlApprovalStore(engine), SqlExecutionResultStore(engine)
    await approvals.add(PENDING_APPROVAL)
    await results.add(EXECUTION_RESULT)
    recorded = statements(engine)
    with pytest.raises(AlreadyExistsError):
        await approvals.add(PENDING_APPROVAL)
    with pytest.raises(AlreadyExistsError):
        await results.add(EXECUTION_RESULT)
    seen = recorded()
    assert len(_inserts(seen, "approvals")) == 1 and len(_inserts(seen, "execution_results")) == 1
    assert _selects(seen, "approvals") == [] and _selects(seen, "execution_results") == []


async def test_a_request_that_is_not_pending_is_refused_before_any_query(
    engine: AsyncEngine, statements: Attach
) -> None:
    store = SqlApprovalStore(engine)
    recorded = statements(engine)
    with pytest.raises(ValueError, match="PENDING"):
        await store.add(APPROVAL)
    with pytest.raises(ValueError, match="GRANTED or REJECTED"):
        await store.respond(
            APPROVAL.id, status=ApprovalStatus.EXPIRED, responded_by="tommaso", now=NOW
        )
    assert recorded() == []


async def test_the_two_stores_expose_their_engine(engine: AsyncEngine) -> None:
    assert SqlApprovalStore(engine).engine is engine
    assert SqlExecutionResultStore(engine).engine is engine
