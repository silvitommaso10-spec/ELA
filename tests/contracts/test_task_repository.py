"""Contract of ``TaskRepository`` (spec §14, §15): tasks and their event trail, stored as given."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from ela.domain import PlanId, TaskEventId, TaskId, TaskState
from ela.ports import AlreadyExistsError, NotFoundError, TaskRepository
from tests.domain.examples import TASK, TASK_EVENT, TASK_PLAN

OTHER_ID = TaskId(UUID("00000000-0000-4000-8000-000000000101"))
OTHER_TASK = TASK.model_copy(update={"id": OTHER_ID, "state": TaskState.QUEUED})
OTHER_EVENT = TASK_EVENT.model_copy(
    update={"id": TaskEventId(UUID("00000000-0000-4000-8000-000000000102"))}
)
CHILD = OTHER_TASK.model_copy(update={"parent_id": TASK.id})


async def test_add_then_get(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    assert await task_repository.get(TASK.id) == TASK


async def test_add_twice_is_rejected_and_the_first_stays(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    with pytest.raises(AlreadyExistsError):
        await task_repository.add(TASK.model_copy(update={"goal": "other"}))
    assert await task_repository.get(TASK.id) == TASK


async def test_get_unknown_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError):
        await task_repository.get(TASK.id)


async def test_save_replaces(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    changed = TASK.model_copy(update={"goal": "changed"})
    await task_repository.save(changed)
    assert await task_repository.get(TASK.id) == changed


async def test_save_unknown_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError):
        await task_repository.save(TASK)


async def test_child_after_parent_is_accepted(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add(CHILD)
    assert await task_repository.get(CHILD.id) == CHILD


async def test_add_with_unknown_parent_is_not_found(task_repository: TaskRepository) -> None:
    """The parent must be stored first (§15): the miss names the parent, and nothing is written."""
    with pytest.raises(NotFoundError) as excinfo:
        await task_repository.add(CHILD)
    assert excinfo.value.key == TASK.id
    with pytest.raises(NotFoundError):
        await task_repository.get(CHILD.id)


async def test_save_with_unknown_parent_is_not_found(task_repository: TaskRepository) -> None:
    await task_repository.add(OTHER_TASK)
    with pytest.raises(NotFoundError) as excinfo:
        await task_repository.save(CHILD)
    assert excinfo.value.key == TASK.id
    assert await task_repository.get(OTHER_TASK.id) == OTHER_TASK


async def test_tasks_in_insertion_order_as_a_tuple(task_repository: TaskRepository) -> None:
    await task_repository.add(OTHER_TASK)
    await task_repository.add(TASK)
    tasks = await task_repository.tasks()
    assert isinstance(tasks, tuple)
    assert tasks == (OTHER_TASK, TASK)


async def test_tasks_filtered_by_states(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add(OTHER_TASK)
    assert await task_repository.tasks(states=frozenset({TaskState.QUEUED})) == (OTHER_TASK,)
    assert await task_repository.tasks(states=frozenset({TaskState.COMPLETED})) == ()
    assert await task_repository.tasks(states=frozenset()) == ()
    both = frozenset({TaskState.PLANNING, TaskState.QUEUED})
    assert await task_repository.tasks(states=both) == (TASK, OTHER_TASK)


async def test_tasks_limit_keeps_the_first_in_insertion_order(
    task_repository: TaskRepository,
) -> None:
    await task_repository.add(OTHER_TASK)
    await task_repository.add(TASK)
    assert await task_repository.tasks(limit=1) == (OTHER_TASK,)
    assert await task_repository.tasks(limit=10) == (OTHER_TASK, TASK)


@pytest.mark.parametrize("limit", [0, -1])
async def test_a_non_positive_limit_is_a_callers_bug(
    task_repository: TaskRepository, limit: int
) -> None:
    """``limit`` is ``None`` or >= 1 (review M2.1): never an empty answer to a wrong question."""
    await task_repository.add(TASK)
    with pytest.raises(ValueError):
        await task_repository.tasks(limit=limit)


async def test_tasks_limit_applies_after_the_filter(task_repository: TaskRepository) -> None:
    await task_repository.add(OTHER_TASK)
    await task_repository.add(TASK)
    queued = frozenset({TaskState.PLANNING})
    assert await task_repository.tasks(states=queued, limit=1) == (TASK,)


async def test_count_is_by_state_and_never_zero(task_repository: TaskRepository) -> None:
    """One entry per state that has at least one task, never one at zero (ADR 0025 §2)."""
    await task_repository.add(TASK)  # PLANNING
    await task_repository.add(OTHER_TASK)  # QUEUED

    counted = await task_repository.count()

    assert counted == {TaskState.PLANNING: 1, TaskState.QUEUED: 1}
    assert TaskState.COMPLETED not in counted


async def test_count_of_an_empty_repository_is_an_empty_mapping(
    task_repository: TaskRepository,
) -> None:
    assert await task_repository.count() == {}


async def test_count_counts_and_does_not_sample(task_repository: TaskRepository) -> None:
    """Three tasks in one state come back as a three, not as three rows."""
    for index in range(3):
        await task_repository.add(
            TASK.model_copy(
                update={
                    "id": TaskId(UUID(f"00000000-0000-4000-8000-00000000011{index}")),
                    "state": TaskState.QUEUED,
                }
            )
        )

    assert await task_repository.count() == {TaskState.QUEUED: 3}


async def test_count_filtered_by_states(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add(OTHER_TASK)

    assert await task_repository.count(states=frozenset({TaskState.QUEUED})) == {
        TaskState.QUEUED: 1
    }
    assert await task_repository.count(states=frozenset({TaskState.COMPLETED})) == {}
    both = frozenset({TaskState.PLANNING, TaskState.QUEUED})
    assert await task_repository.count(states=both) == {
        TaskState.PLANNING: 1,
        TaskState.QUEUED: 1,
    }


async def test_count_of_no_state_is_the_one_case_that_differs_from_none(
    task_repository: TaskRepository,
) -> None:
    """A question about no state answers with nothing; ``None`` asks about all of them."""
    await task_repository.add(TASK)

    assert await task_repository.count(states=frozenset()) == {}
    assert await task_repository.count(states=None) == {TaskState.PLANNING: 1}


async def test_count_agrees_with_tasks(task_repository: TaskRepository) -> None:
    """The cheap answer and the expensive one say the same thing, which is the whole point."""
    await task_repository.add(TASK)
    await task_repository.add(OTHER_TASK)

    counted = await task_repository.count()
    loaded: dict[TaskState, int] = {}
    for task in await task_repository.tasks():
        loaded[task.state] = loaded.get(task.state, 0) + 1

    assert counted == loaded


async def test_new_task_has_no_events(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    assert await task_repository.events(TASK.id) == ()


async def test_events_in_append_order(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.append_event(OTHER_EVENT)
    await task_repository.append_event(TASK_EVENT)
    events = await task_repository.events(TASK.id)
    assert isinstance(events, tuple)
    assert events == (OTHER_EVENT, TASK_EVENT)


async def test_event_for_unknown_task_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError):
        await task_repository.append_event(TASK_EVENT)


async def test_duplicate_event_is_rejected(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.append_event(TASK_EVENT)
    with pytest.raises(AlreadyExistsError):
        await task_repository.append_event(TASK_EVENT)
    assert await task_repository.events(TASK.id) == (TASK_EVENT,)


async def test_events_of_unknown_task_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError):
        await task_repository.events(TASK.id)


# --------------------------------------------------------------------------------------
# Plans (M3.1, ADR 0008): one per task, stored once, read back with its steps
# --------------------------------------------------------------------------------------

OTHER_PLAN = TASK_PLAN.model_copy(
    update={"id": PlanId(UUID("00000000-0000-4000-8000-000000000103")), "task_id": OTHER_ID}
)


async def test_add_plan_then_plan(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add_plan(TASK_PLAN)
    assert await task_repository.plan(TASK.id) == TASK_PLAN


async def test_add_plan_for_unknown_task_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError) as excinfo:
        await task_repository.add_plan(TASK_PLAN)
    assert excinfo.value.key == TASK.id


async def test_second_plan_for_the_same_task_is_rejected(task_repository: TaskRepository) -> None:
    """One plan per task: replanning is not a thing in v0.1 (ADR 0004)."""
    await task_repository.add(TASK)
    await task_repository.add_plan(TASK_PLAN)
    another = OTHER_PLAN.model_copy(update={"task_id": TASK.id})
    with pytest.raises(AlreadyExistsError):
        await task_repository.add_plan(another)
    assert await task_repository.plan(TASK.id) == TASK_PLAN


async def test_same_plan_id_on_another_task_is_rejected(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add(OTHER_TASK)
    await task_repository.add_plan(TASK_PLAN)
    with pytest.raises(AlreadyExistsError):
        await task_repository.add_plan(TASK_PLAN.model_copy(update={"task_id": OTHER_ID}))
    with pytest.raises(NotFoundError):
        await task_repository.plan(OTHER_ID)


async def test_plan_of_a_task_without_one_is_not_found(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    with pytest.raises(NotFoundError) as excinfo:
        await task_repository.plan(TASK.id)
    assert excinfo.value.key == TASK.id


async def test_plan_of_unknown_task_is_not_found(task_repository: TaskRepository) -> None:
    with pytest.raises(NotFoundError):
        await task_repository.plan(TASK.id)


async def test_plans_belong_to_their_task(task_repository: TaskRepository) -> None:
    await task_repository.add(TASK)
    await task_repository.add(OTHER_TASK)
    await task_repository.add_plan(TASK_PLAN)
    await task_repository.add_plan(OTHER_PLAN)
    assert await task_repository.plan(TASK.id) == TASK_PLAN
    assert await task_repository.plan(OTHER_ID) == OTHER_PLAN


# ----------------------------------------------------------------------------------------
# ``due`` and ``due_count`` (M10.4, ADR 0032 §9): the question ``tasks`` cannot answer
# ----------------------------------------------------------------------------------------

LATER = TASK.model_copy(
    update={
        "id": TaskId(UUID("00000000-0000-4000-8000-000000000201")),
        "state": TaskState.QUEUED,
        "deadline": datetime(2026, 9, 10, 9, 0, tzinfo=UTC),
    }
)
SOONER = TASK.model_copy(
    update={
        "id": TaskId(UUID("00000000-0000-4000-8000-000000000202")),
        "state": TaskState.QUEUED,
        "deadline": datetime(2026, 9, 9, 9, 0, tzinfo=UTC),
    }
)
UNDATED = TASK.model_copy(
    update={"id": TaskId(UUID("00000000-0000-4000-8000-000000000203")), "deadline": None}
)


async def test_due_orders_by_deadline_and_not_by_insertion(
    task_repository: TaskRepository,
) -> None:
    """The one order that is not insertion order, which is why it is a member of its own."""
    await task_repository.add(LATER)
    await task_repository.add(SOONER)

    assert [task.id for task in await task_repository.due()] == [SOONER.id, LATER.id]
    assert [task.id for task in await task_repository.tasks()] == [LATER.id, SOONER.id]


async def test_due_leaves_out_a_task_with_no_deadline(task_repository: TaskRepository) -> None:
    """Not sorted to the end: a task with no deadline is not a late one (ADR 0032 §9)."""
    await task_repository.add(SOONER)
    await task_repository.add(UNDATED)

    assert [task.id for task in await task_repository.due()] == [SOONER.id]
    assert await task_repository.due_count() == 1


async def test_due_ties_fall_back_to_insertion_order(task_repository: TaskRepository) -> None:
    """Two tasks due at the same instant come back stably, never in whatever order the rows are."""
    first = LATER.model_copy(update={"deadline": SOONER.deadline})
    await task_repository.add(first)
    await task_repository.add(SOONER)

    assert [task.id for task in await task_repository.due()] == [first.id, SOONER.id]


async def test_due_filters_by_state_and_limits_after_filtering(
    task_repository: TaskRepository,
) -> None:
    await task_repository.add(SOONER)
    await task_repository.add(LATER.model_copy(update={"state": TaskState.COMPLETED}))

    live = frozenset({TaskState.QUEUED})
    assert [task.id for task in await task_repository.due(states=live)] == [SOONER.id]
    assert await task_repository.due_count(states=live) == 1
    assert len(await task_repository.due(limit=1)) == 1


async def test_due_of_an_empty_frozenset_asks_about_no_state_at_all(
    task_repository: TaskRepository,
) -> None:
    """The one case where ``frozenset()`` and ``None`` differ, as for ``tasks`` and ``count``."""
    await task_repository.add(SOONER)

    assert await task_repository.due(states=frozenset()) == ()
    assert await task_repository.due_count(states=frozenset()) == 0
    assert await task_repository.due(states=None) != ()


async def test_due_rejects_a_non_positive_limit(task_repository: TaskRepository) -> None:
    with pytest.raises(ValueError):
        await task_repository.due(limit=0)
    with pytest.raises(ValueError):
        await task_repository.due(limit=-1)


async def test_due_count_counts_without_the_limit_that_due_applies(
    task_repository: TaskRepository,
) -> None:
    """The whole reason ``due_count`` exists: twenty of a hundred must be able to say a hundred."""
    await task_repository.add(SOONER)
    await task_repository.add(LATER)

    assert len(await task_repository.due(limit=1)) == 1
    assert await task_repository.due_count() == 2


async def test_due_count_of_an_empty_repository_is_zero(task_repository: TaskRepository) -> None:
    assert await task_repository.due_count() == 0
