"""Task state machine (spec §14): the only place where a :class:`Task` changes state.

§14 fixes ten states and asks that illegal transitions be impossible. This module makes that a
fact: the legal transitions are an explicit, immutable table (:data:`TRANSITIONS`), and
:func:`transition` is a pure function that either returns the task in its new state together
with the :class:`TaskEvent` recording the change, or raises :class:`IllegalTransitionError`.

The module applies the table and nothing else. Whether a task *should* expire, whether an
approval *was* granted, whether the Guardian *did* allow a step are questions for the Task Engine
and the Guardian; here the only question is whether the move is legal. When in doubt the answer
is no (§33).

The table, the principles behind it and the shape of :func:`transition` are argued in
``docs/adr/0004-task-transitions.md``. The Mermaid diagram there is checked against
:data:`TRANSITIONS` by ``tests/docs/test_adr_transitions.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Final, NamedTuple

from pydantic import JsonValue

from ela.domain import StepId, Task, TaskEvent, TaskEventId, TaskEventType, TaskId, TaskState

__all__ = [
    "TERMINAL_STATES",
    "TRANSITIONS",
    "IllegalTransitionError",
    "Transition",
    "allowed_transitions",
    "can_transition",
    "is_terminal",
    "transition",
]

_S = TaskState

TERMINAL_STATES: Final[frozenset[TaskState]] = frozenset(
    {_S.COMPLETED, _S.FAILED, _S.CANCELLED, _S.DENIED, _S.EXPIRED}
)
"""States a task never leaves (ADR 0004, P1)."""

TRANSITIONS: Final[Mapping[TaskState, frozenset[TaskState]]] = MappingProxyType(
    {
        _S.CREATED: frozenset({_S.PLANNING, _S.CANCELLED, _S.EXPIRED}),
        _S.PLANNING: frozenset(
            {_S.WAITING_APPROVAL, _S.QUEUED, _S.FAILED, _S.DENIED, _S.CANCELLED, _S.EXPIRED}
        ),
        _S.WAITING_APPROVAL: frozenset({_S.QUEUED, _S.DENIED, _S.CANCELLED, _S.EXPIRED}),
        _S.QUEUED: frozenset({_S.EXECUTING, _S.CANCELLED, _S.EXPIRED}),
        _S.EXECUTING: frozenset(
            {
                _S.COMPLETED,
                _S.FAILED,
                _S.WAITING_APPROVAL,
                _S.QUEUED,
                _S.DENIED,
                _S.CANCELLED,
                _S.EXPIRED,
            }
        ),
        _S.COMPLETED: frozenset(),
        _S.FAILED: frozenset(),
        _S.CANCELLED: frozenset(),
        _S.DENIED: frozenset(),
        _S.EXPIRED: frozenset(),
    }
)
"""The legal transitions of §14, one row per state, as decided in ADR 0004.

Total by construction: every :class:`TaskState` is a key, and a terminal state maps to the empty
set. Anything not listed here is illegal.
"""


class IllegalTransitionError(Exception):
    """A transition the table does not allow. The task is left untouched."""

    def __init__(self, task_id: TaskId, current: TaskState, requested: TaskState) -> None:
        self.task_id = task_id
        self.current = current
        self.requested = requested
        if is_terminal(current):
            why = f"{current.value} is terminal"
        elif current is requested:
            why = "a task cannot re-enter the state it is already in"
        else:
            why = "the transition is not in the table"
        super().__init__(
            f"task {task_id} cannot go from {current.value} to {requested.value}: {why}"
        )


class Transition(NamedTuple):
    """What :func:`transition` returns: the task in its new state and the event that says so."""

    task: Task
    event: TaskEvent


def is_terminal(state: TaskState) -> bool:
    """Whether ``state`` is one of the five states a task never leaves."""
    return state in TERMINAL_STATES


def allowed_transitions(state: TaskState) -> frozenset[TaskState]:
    """The states a task in ``state`` may move to; empty for a terminal state."""
    return TRANSITIONS[state]


def can_transition(current: TaskState, new_state: TaskState) -> bool:
    """Whether the table allows ``current -> new_state``."""
    return new_state in TRANSITIONS[current]


def transition(
    task: Task,
    new_state: TaskState,
    *,
    event_id: TaskEventId,
    now: datetime,
    message: str = "",
    step_id: StepId | None = None,
    metadata: Mapping[str, JsonValue] | None = None,
) -> Transition:
    """Move ``task`` to ``new_state`` or raise :class:`IllegalTransitionError`.

    Pure and deterministic: the caller provides ``event_id`` and ``now`` because the domain
    neither generates ids nor reads the clock (ADR 0003). The returned task is a copy of ``task``
    that differs only in ``state``; the returned event is a ``STATE_CHANGED`` event whose
    ``previous_state`` and ``new_state`` describe exactly this move, so a transition without its
    event cannot exist (ADR 0004 §3). ``message``, ``step_id`` and ``metadata`` are passed to the
    event unchanged.

    ``new_state`` must be a :class:`TaskState` member. A plain string is rejected with
    ``TypeError`` even when it spells a valid state: ``"QUEUED" == TaskState.QUEUED`` holds for a
    ``StrEnum`` and ``model_copy`` does not validate, so without this check a string would end up
    inside the task.
    """
    if not isinstance(new_state, TaskState):
        raise TypeError(f"new_state must be a TaskState, got {type(new_state).__name__}")
    if not can_transition(task.state, new_state):
        raise IllegalTransitionError(task.id, task.state, new_state)
    event = TaskEvent(
        id=event_id,
        created_at=now,
        task_id=task.id,
        event_type=TaskEventType.STATE_CHANGED,
        step_id=step_id,
        previous_state=task.state,
        new_state=new_state,
        message=message,
        metadata={} if metadata is None else metadata,
    )
    return Transition(task.model_copy(update={"state": new_state}), event)
