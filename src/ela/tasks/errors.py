"""Errors of the Task Engine and the Task Graph (spec §14, §15, §33).

One base class so that a caller can catch "anything the task machinery refused" in one clause.
The state machine raises :class:`ela.tasks.state_machine.IllegalTransitionError` (M1.2); the
engine raises :class:`TaskEngineError` for what the table allows but the engine refuses — an
inconsistent input, a wrong key, the wrong operation for a legal move — and
:class:`ClockSkewError` when the clock went backwards (M3.1, ADR 0008). The Task Graph (M3.2,
ADR 0009) raises :class:`GraphError` and its subclasses: a plan that is not a DAG, a trail that
moves a step illegally, a step the plan does not know. Every refusal happens before anything is
written.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

__all__ = [
    "ClockSkewError",
    "CyclicDependencyError",
    "GraphError",
    "IllegalStepTransitionError",
    "InvalidGraphError",
    "TaskEngineError",
    "TaskError",
    "UnknownStepError",
]


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


class GraphError(TaskError):
    """Base class of what the Task Graph refuses (ADR 0009): the plan or the trail is unsound."""


class InvalidGraphError(GraphError):
    """The steps of a plan do not form a graph: a duplicate id, a dependency on an unknown step
    or a dependency listed twice."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid task graph: {reason}")


class CyclicDependencyError(GraphError):
    """The dependencies of a plan contain a cycle; ``cycle`` lists it, each step depending on
    the next and the last on the first. A self-dependency is a cycle of length one."""

    def __init__(self, cycle: tuple[UUID, ...]) -> None:
        self.cycle = cycle
        chain = " -> ".join(str(step) for step in (*cycle, cycle[0]))
        super().__init__(f"cyclic dependency between steps: {chain}")


class UnknownStepError(GraphError):
    """A step id the plan does not contain: on a trail event, or as an operation's argument."""

    def __init__(self, step_id: UUID | None) -> None:
        self.step_id = step_id
        what = "an event without step_id" if step_id is None else f"step {step_id}"
        super().__init__(f"{what} is not part of the plan")


class IllegalStepTransitionError(GraphError):
    """A step move the table does not allow, found in the trail or requested of the engine."""

    def __init__(self, step_id: UUID, current: str, requested: str) -> None:
        self.step_id = step_id
        self.current = current
        self.requested = requested
        super().__init__(f"step {step_id} cannot go from {current} to {requested}")
