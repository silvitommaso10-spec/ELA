"""Contract of ``ExecutionResultStore`` (spec §63; ADR 0015): what a tool produced, stored once,
read back whole, found by step."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from ela.domain import ExecutionId, ExecutionStatus, StepId, TaskId
from ela.ports import AlreadyExistsError, ExecutionResultStore, NotFoundError
from tests.domain.examples import EXECUTION_RESULT

RESULT = EXECUTION_RESULT
OTHER = RESULT.model_copy(
    update={
        "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000601")),
        "status": ExecutionStatus.SUCCEEDED,
        "error": None,
    }
)
OTHER_STEP = RESULT.model_copy(
    update={
        "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000602")),
        "step_id": StepId(UUID("00000000-0000-4000-8000-000000000603")),
    }
)
OTHER_TASK = RESULT.model_copy(
    update={
        "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000604")),
        "task_id": TaskId(UUID("00000000-0000-4000-8000-000000000605")),
    }
)
BARE = RESULT.model_copy(
    update={
        "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000606")),
        "task_id": None,
        "step_id": None,
        "tool_name": None,
        "device_id": None,
        "decision_id": None,
        "authorization_id": None,
        "output": {},
        "error": None,
        "usage": None,
        "duration_ms": None,
        "metadata": {},
    }
)
STARTED = RESULT.model_copy(
    update={
        "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000607")),
        "status": ExecutionStatus.STARTED,
        "output": {},
        "error": None,
        "usage": None,
        "duration_ms": None,
        "metadata": {},
    }
)
"""The record a non-idempotent tool leaves before it acts (ADR 0021 §1): a status, a decision,
a node, and nothing about an outcome."""


async def test_add_then_get(execution_result_store: ExecutionResultStore) -> None:
    await execution_result_store.add(RESULT)
    assert await execution_result_store.get(RESULT.id) == RESULT


async def test_add_twice_is_rejected_and_the_first_stays(
    execution_result_store: ExecutionResultStore,
) -> None:
    await execution_result_store.add(RESULT)
    with pytest.raises(AlreadyExistsError):
        await execution_result_store.add(RESULT.model_copy(update={"output": {"other": 1}}))
    assert await execution_result_store.get(RESULT.id) == RESULT


async def test_get_unknown_is_not_found(execution_result_store: ExecutionResultStore) -> None:
    with pytest.raises(NotFoundError):
        await execution_result_store.get(RESULT.id)


async def test_every_field_survives_the_round_trip(
    execution_result_store: ExecutionResultStore,
) -> None:
    """Output, error, usage, decision, grant, duration, metadata: the mapper forgets nothing.

    ``usage`` holds a ``Decimal`` (ADR 0021 §3), which is the field most likely to come back as
    something else: a cost that went through a float would stop adding up.
    """
    assert RESULT.error is not None and RESULT.decision_id is not None
    assert RESULT.authorization_id is not None and RESULT.duration_ms is not None
    assert RESULT.usage is not None and RESULT.usage.cost is not None
    await execution_result_store.add(RESULT)
    await execution_result_store.add(BARE)
    stored = await execution_result_store.get(RESULT.id)
    assert stored == RESULT
    assert stored.usage is not None
    assert stored.usage.cost == RESULT.usage.cost
    assert isinstance(stored.usage.cost, Decimal)
    assert await execution_result_store.get(BARE.id) == BARE


async def test_a_started_record_and_its_outcome_are_two_rows_of_one_step(
    execution_result_store: ExecutionResultStore,
) -> None:
    """ADR 0021 §1: the store stays insert-only and a step keeps at most two rows — the record
    written before a non-idempotent tool acted, and the outcome that settles it."""
    outcome = RESULT.model_copy(update={"metadata": {"started_id": str(STARTED.id)}})
    await execution_result_store.add(STARTED)
    await execution_result_store.add(outcome)
    assert STARTED.task_id is not None and STARTED.step_id is not None

    stored = await execution_result_store.for_step(STARTED.task_id, STARTED.step_id)

    assert stored == (STARTED, outcome)
    assert stored[0].status is ExecutionStatus.STARTED
    assert stored[1].metadata["started_id"] == str(STARTED.id)


async def test_for_step_filters_by_task_and_step_in_insertion_order(
    execution_result_store: ExecutionResultStore,
) -> None:
    await execution_result_store.add(OTHER_STEP)
    await execution_result_store.add(OTHER)
    await execution_result_store.add(OTHER_TASK)
    await execution_result_store.add(RESULT)
    assert RESULT.task_id is not None and RESULT.step_id is not None
    assert await execution_result_store.for_step(RESULT.task_id, RESULT.step_id) == (
        OTHER,
        RESULT,
    )
    assert OTHER_STEP.step_id is not None
    assert await execution_result_store.for_step(RESULT.task_id, OTHER_STEP.step_id) == (
        OTHER_STEP,
    )
    assert OTHER_TASK.task_id is not None
    assert await execution_result_store.for_step(OTHER_TASK.task_id, RESULT.step_id) == (
        OTHER_TASK,
    )
    assert await execution_result_store.for_step(TaskId(UUID(int=7)), RESULT.step_id) == ()
