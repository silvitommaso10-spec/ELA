"""Property tests: random walks over the state machine never violate the table.

The pair-by-pair tests in ``test_state_machine.py`` check every single move; these check that
*sequences* of moves behave, that a terminal state absorbs everything that follows, and that the
event trace of a legal path tells the whole story.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from hypothesis import given, settings
from hypothesis import strategies as st

from ela.domain import Task, TaskEvent, TaskEventId, TaskEventType, TaskState
from ela.tasks.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    IllegalTransitionError,
    allowed_transitions,
    is_terminal,
    transition,
)
from tests.domain.strategies import json_mappings, tasks, texts, utc_datetimes, uuids

states = st.sampled_from(TaskState)
moves = st.lists(st.tuples(states, uuids, utc_datetimes), max_size=12)
terminal_tasks = tasks.filter(lambda task: is_terminal(task.state))


@given(task=tasks, sequence=moves)
@settings(max_examples=200, deadline=None)
def test_random_sequences_never_violate_the_table(
    task: Task, sequence: list[tuple[TaskState, UUID, datetime]]
) -> None:
    current = task
    for new_state, event_id, now in sequence:
        legal = new_state in TRANSITIONS[current.state]
        try:
            result = transition(current, new_state, event_id=TaskEventId(event_id), now=now)
        except IllegalTransitionError as error:
            assert not legal
            assert error.current is current.state
            assert error.requested is new_state
            # The task is untouched: the walk continues from where it was.
        else:
            assert legal
            assert result.task.state is new_state
            assert result.event.previous_state is current.state
            assert result.event.new_state is new_state
            current = result.task


@given(task=terminal_tasks, new_state=states, event_id=uuids, now=utc_datetimes)
@settings(max_examples=100, deadline=None)
def test_terminal_absorbs_everything(
    task: Task, new_state: TaskState, event_id: UUID, now: datetime
) -> None:
    try:
        transition(task, new_state, event_id=TaskEventId(event_id), now=now)
    except IllegalTransitionError as error:
        assert is_terminal(error.current)
        assert "is terminal" in str(error)
    else:
        raise AssertionError(f"{task.state} -> {new_state} was accepted")


@given(task=tasks, data=st.data())
@settings(max_examples=200, deadline=None)
def test_event_trace_reconstructs_the_path(task: Task, data: st.DataObject) -> None:
    """Following only legal moves until a terminal state, the events retell the states walked."""
    path = [task.state]
    events: list[TaskEvent] = []
    current = task
    while not is_terminal(current.state) and len(path) <= 10:
        new_state = data.draw(st.sampled_from(sorted(allowed_transitions(current.state))))
        event_id = TaskEventId(data.draw(uuids))
        now = data.draw(utc_datetimes)
        result = transition(current, new_state, event_id=event_id, now=now)
        path.append(new_state)
        events.append(result.event)
        current = result.task

    assert [e.previous_state for e in events] == path[:-1]
    assert [e.new_state for e in events] == path[1:]
    assert all(e.event_type is TaskEventType.STATE_CHANGED for e in events)
    assert all(e.task_id == task.id for e in events)
    assert current.state is path[-1]
    assert current.model_dump(exclude={"state"}) == task.model_dump(exclude={"state"})
    # Every walk that ran out of moves ended in one of the five terminal states.
    if is_terminal(current.state):
        assert current.state in TERMINAL_STATES


@given(
    task=tasks,
    new_state=states,
    event_id=uuids,
    now=utc_datetimes,
    message=texts,
    metadata=json_mappings,
)
@settings(max_examples=100, deadline=None)
def test_transition_is_pure(
    task: Task,
    new_state: TaskState,
    event_id: UUID,
    now: datetime,
    message: str,
    metadata: dict[str, object],
) -> None:
    """Same inputs, same outputs, and the input task never changes."""
    snapshot = task.model_dump()

    def run() -> object:
        try:
            return transition(
                task,
                new_state,
                event_id=TaskEventId(event_id),
                now=now,
                message=message,
                metadata=metadata,  # type: ignore[arg-type]
            )
        except IllegalTransitionError as error:
            return (type(error), error.current, error.requested)

    assert run() == run()
    assert task.model_dump() == snapshot
