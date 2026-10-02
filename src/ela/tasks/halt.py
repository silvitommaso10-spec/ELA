"""What the step in progress had done when its task was stopped (§65; M6.3c, ADR 0054 §7).

A projection and never a stored value: the trail says which step was RUNNING at the instant the
task became CANCELLED and how that step closed afterwards, and the audit carries what the trail
does not — the code a ``STEP_FAILED`` was written with (``_write_step`` puts only the operation and
its key on the trail's event). Whether a node's claim on a step still open has lapsed is the third
fact, and it is not in either: the caller reads it from the assignments and passes the answer.

Pure, with no port: the engine has the two logs and the executor the assignments, and the one who
has all three composes them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

from ela.domain import (
    AuditEvent,
    AuditEventType,
    Halt,
    StepId,
    StepState,
    TaskEvent,
    TaskEventType,
    TaskState,
)
from ela.tasks.graph import STEP_EVENTS, TERMINAL_STEP_STATES

__all__ = ["halt_of", "in_progress_at_stop"]

_CLOSED: Final[Mapping[StepState, Halt]] = MappingProxyType(
    {StepState.CANCELLED: Halt.NOT_ACTED, StepState.COMPLETED: Halt.ACTED_VERIFIED}
)
"""A step closed after the stop: CANCELLED by ``stop_step`` did not act (ADR 0054 §4), COMPLETED
acted and its verification passed. FAILED needs the audit, and is read by :func:`_of_failure`."""


def _stop_index(trail: Sequence[TaskEvent]) -> int | None:
    for index, event in enumerate(trail):
        if (
            event.event_type is TaskEventType.STATE_CHANGED
            and event.new_state is TaskState.CANCELLED
        ):
            return index
    return None


def in_progress_at_stop(trail: Sequence[TaskEvent]) -> StepId | None:
    """The step that was RUNNING when the task became CANCELLED; ``None`` if none, or no stop.

    The runner is sequential, so there is at most one; were there two, the later started is the
    one the stop found working.
    """
    stop = _stop_index(trail)
    if stop is None:
        return None
    states: dict[StepId, StepState] = {}
    for event in trail[:stop]:
        target = STEP_EVENTS.get(event.event_type)
        if target is not None and event.step_id is not None:
            states.pop(event.step_id, None)
            states[event.step_id] = target
    running = [step for step, state in states.items() if state is StepState.RUNNING]
    return running[-1] if running else None


def halt_of(
    trail: Sequence[TaskEvent],
    audit: Sequence[AuditEvent],
    *,
    interrupted: str,
    lapsed: bool = False,
) -> Halt | None:
    """What the step in progress had done when the task was stopped; ``None`` when no step was in
    progress, or the task was never stopped.

    ``interrupted`` is the code of a step closed without knowing whether its tool acted
    (``execution.interrupted``, the executor's). ``lapsed`` says that a node's claim on the step,
    still open, has expired: nobody is executing it, and the answer is :attr:`Halt.UNKNOWN`, never
    :attr:`Halt.FINISHING` (decision 15 of the review).
    """
    step = in_progress_at_stop(trail)
    if step is None:
        return None
    stop = _stop_index(trail)
    assert stop is not None
    closed = [
        STEP_EVENTS[event.event_type]
        for event in trail[stop + 1 :]
        if event.step_id == step and STEP_EVENTS.get(event.event_type) in TERMINAL_STEP_STATES
    ]
    if not closed:
        return Halt.UNKNOWN if lapsed else Halt.FINISHING
    if closed[0] is StepState.FAILED:
        return _of_failure(audit, step, interrupted)
    return _CLOSED[closed[0]]


def _of_failure(audit: Sequence[AuditEvent], step: StepId, interrupted: str) -> Halt:
    """A failure after the point is ``ACTED``; one whose tool may not have acted is ``UNKNOWN``,
    and so is one whose audit row is missing — a doubt is not an «it acted» (§33)."""
    failures = [
        event
        for event in audit
        if event.event_type is AuditEventType.STEP_FAILED and event.step_id == step
    ]
    if not failures or failures[-1].error is None:
        return Halt.UNKNOWN
    return Halt.UNKNOWN if failures[-1].error.code == interrupted else Halt.ACTED
