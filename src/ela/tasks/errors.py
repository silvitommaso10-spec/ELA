"""Errors of the Task Engine (spec §14, §33).

One base class so that a caller can catch "anything the task machinery refused" in one clause.
The state machine raises :class:`ela.tasks.state_machine.IllegalTransitionError` (M1.2); the
engine raises :class:`TaskEngineError` for what the table allows but the engine refuses — an
inconsistent input, a wrong key, the wrong operation for a legal move — and
:class:`ClockSkewError` when the clock went backwards (M3.1, ADR 0008). Every refusal happens
before anything is written.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

__all__ = ["ClockSkewError", "TaskEngineError", "TaskError"]


class TaskError(Exception):
    """Base class of every error raised by ``ela.tasks``."""


class TaskEngineError(TaskError):
    """The engine refused an operation that the transition table alone would not forbid.

    The reason names what was wrong: the input is inconsistent with the task, the operation
    was already applied with another key, or the move needs a different operation (§33: when in
    doubt, refuse). Nothing was written.
    """

    def __init__(self, task_id: UUID, reason: str) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"task {task_id}: {reason}")


class ClockSkewError(TaskEngineError):
    """The clock reads earlier than the last instant recorded for the task (ADR 0008 §7).

    A clock that went backwards is a fault, not a value to record: the operation is refused and
    the trail keeps its order.
    """

    def __init__(self, task_id: UUID, now: datetime, last_seen: datetime) -> None:
        self.now = now
        self.last_seen = last_seen
        super().__init__(
            task_id,
            f"the clock reads {now.isoformat()} but the task was last seen at "
            f"{last_seen.isoformat()}: refusing to write out of order",
        )
