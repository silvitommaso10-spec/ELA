"""Contract of ``TaskRepository`` (spec §14, §15): tasks and their event trail, stored as given."""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.domain import TaskEventId, TaskId, TaskState
from ela.ports import AlreadyExistsError, NotFoundError, TaskRepository
from tests.domain.examples import TASK, TASK_EVENT

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
    assert await task_repository.tasks(limit=0) == ()
    assert await task_repository.tasks(limit=10) == (OTHER_TASK, TASK)


async def test_tasks_limit_applies_after_the_filter(task_repository: TaskRepository) -> None:
    await task_repository.add(OTHER_TASK)
    await task_repository.add(TASK)
    queued = frozenset({TaskState.PLANNING})
    assert await task_repository.tasks(states=queued, limit=1) == (TASK,)


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
