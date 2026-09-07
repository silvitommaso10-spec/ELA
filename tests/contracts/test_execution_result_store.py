"""Contract of ``ExecutionResultStore`` (spec §63; ADR 0015): what a tool produced, stored once,
read back whole, found by step."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from ela.domain import ExecutionId, ExecutionStatus, StepId, TaskId
from ela.executive import STARTED_ID
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


async def test_a_started_record_and_its_outcome_are_the_two_rows_of_one_step(
    execution_result_store: ExecutionResultStore,
) -> None:
    """The contract the STARTED protocol rests on (ADR 0021 §1, §1-bis), on every store.

    A step run by a tool that cannot be repeated holds **at most one STARTED record**, **at most
    one outcome**, and — when both are there — the outcome names the record it settles in
    ``metadata["started_id"]``. That last link is what makes the two rows one run instead of two,
    and it is why this is a contract test and not a sentence in a docstring: the executor reads
    these rows to decide whether to call a tool that charges money, and it must read the same
    thing from the fake and from SQLite.
    """
    outcome = RESULT.model_copy(update={"metadata": {STARTED_ID: str(STARTED.id)}})
    await execution_result_store.add(STARTED)
    await execution_result_store.add(outcome)
    assert STARTED.task_id is not None and STARTED.step_id is not None

    stored = await execution_result_store.for_step(STARTED.task_id, STARTED.step_id)

    assert stored == (STARTED, outcome)  # insertion order: the record, then what settled it
    records = [r for r in stored if r.status is ExecutionStatus.STARTED]
    outcomes = [r for r in stored if r.status is not ExecutionStatus.STARTED]
    assert len(records) == 1
    assert len(outcomes) == 1
    assert outcomes[0].metadata[STARTED_ID] == str(records[0].id)


async def test_a_second_started_record_for_one_step_is_refused(
    execution_result_store: ExecutionResultStore,
) -> None:
    """The negative case (ADR 0021 §1-bis): two STARTED records for one step would mean a tool
    that cannot be run twice was about to run twice, written down as if it were normal.

    Refused by the **store**, not only by the executor: a check that lives in the caller protects
    nothing against a second caller, which is the reason ``id`` is UNIQUE rather than looked up.
    """
    second = STARTED.model_copy(
        update={"id": ExecutionId(UUID("00000000-0000-4000-8000-000000000608"))}
    )
    await execution_result_store.add(STARTED)

    with pytest.raises(AlreadyExistsError):
        await execution_result_store.add(second)

    assert STARTED.task_id is not None and STARTED.step_id is not None
    assert await execution_result_store.for_step(STARTED.task_id, STARTED.step_id) == (STARTED,)


async def test_a_started_record_for_another_step_is_not_refused(
    execution_result_store: ExecutionResultStore,
) -> None:
    """The constraint is per step, and proving it is not vacuous: the same tool, started for a
    different step of the same task, is a different run."""
    elsewhere = STARTED.model_copy(
        update={
            "id": ExecutionId(UUID("00000000-0000-4000-8000-000000000609")),
            "step_id": StepId(UUID("00000000-0000-4000-8000-000000000610")),
        }
    )
    await execution_result_store.add(STARTED)
    await execution_result_store.add(elsewhere)

    assert elsewhere.task_id is not None and elsewhere.step_id is not None
    assert await execution_result_store.for_step(elsewhere.task_id, elsewhere.step_id) == (
        elsewhere,
    )


async def test_an_outcome_next_to_a_started_record_is_not_refused(
    execution_result_store: ExecutionResultStore,
) -> None:
    """The asymmetry is on purpose: the store constrains the records, not the outcomes.

    A second *outcome* for one step is the executor's refusal (ADR 0013 §1), and a UNIQUE on
    ``(task_id, step_id)`` was deliberately deferred (ADR 0015, alternatives). Narrowing the
    constraint to ``STARTED`` is what lets this milestone add it without reversing that.
    """
    await execution_result_store.add(STARTED)
    await execution_result_store.add(RESULT)
    await execution_result_store.add(OTHER)

    assert RESULT.task_id is not None and RESULT.step_id is not None
    stored = await execution_result_store.for_step(RESULT.task_id, RESULT.step_id)
    assert [r.status for r in stored] == [
        ExecutionStatus.STARTED,
        RESULT.status,
        OTHER.status,
    ]
    assert len([r for r in stored if r.status is not ExecutionStatus.STARTED]) == 2


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
