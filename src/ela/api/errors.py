"""What the API refuses on its own (ADR 0023 §9, §10).

Two failures belong to the API and to nobody else: two runs of the same task at once, and a
database that does not answer. Everything else it reports is somebody else's exception —
the engine's, the executor's, a port's — translated into a status code and never re-worded.
"""

from __future__ import annotations

from ela.domain import TaskId

__all__ = [
    "ApiError",
    "DatabaseUnavailableError",
    "PlanNotReadyError",
    "RevisionRequiredError",
    "TaskAlreadyRunningError",
]


class ApiError(Exception):
    """Base class of what the API itself raises."""


class TaskAlreadyRunningError(ApiError):
    """A second ``run`` arrived while the first is still walking the plan (ADR 0023 §9).

    The answer is a refusal and not a queue: the executor has no lock of its own (ADR 0008 §11),
    and two runners on one task is a caller's bug rather than something to wait out.
    """

    def __init__(self, task_id: TaskId) -> None:
        super().__init__(f"task {task_id} is already running")
        self.task_id = task_id


class DatabaseUnavailableError(ApiError):
    """The health check could not read from the database."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"the database did not answer: {reason}")


class RevisionRequiredError(ApiError):
    """An announcement without the revision it is conditional on: ``If-Match`` is missing.

    Not a default: a write that assumed a revision would be the unconditional update this protocol
    exists to refuse (ADR 0037 §9). ``428 Precondition Required`` is the status HTTP has for it.
    """

    def __init__(self) -> None:
        super().__init__(
            'PUT /nodes/me is conditional: send the revision you last saw as If-Match: "<revision>"'
        )


class PlanNotReadyError(ApiError, ValueError):
    """A plan written by hand with a step the executor would refuse (M14.2, ADR 0058; decision 8).

    A ``ValueError``, so the table answers it as every malformed plan — ``422`` ``invalid`` —: the
    caller has to change *what* they sent. Until M14.2 such a plan came in, and left its task
    ``EXECUTING`` at the first run, answering ``409`` to every run after it.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"the plan has a step the executor would refuse: {reason}")
