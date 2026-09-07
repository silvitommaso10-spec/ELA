"""Errors of the executor and of the runner (spec §27, §33).

Raised *before* anything is written: a precondition of the pipeline that does not hold — the
task is not EXECUTING, the step is not RUNNING, the step declares a number of capabilities other
than one — is refused without a decision, a grant or a tool call (ADR 0013 §2). The other
refusals the executor lets through are already named elsewhere: ``CapabilityNotFound``,
``ToolNotFound``, ``UnknownStepError``, ``ApprovalMismatchError``.

:class:`RunnerError` says the same thing one level up (M6.3, ADR 0019): a task that cannot be
walked — not QUEUED nor EXECUTING, a plan with no steps — is refused at the door, and a state the
loop cannot make sense of — two RUNNING steps, a RUNNING step whose node no ``STEP_STARTED``
names, a completed plan whose closing result is missing — stops it rather than being guessed
around (§33).
"""

from __future__ import annotations

from uuid import UUID

__all__ = ["ExecutorError", "RunnerError"]


class ExecutorError(Exception):
    """A precondition of the executor did not hold; nothing was written."""

    def __init__(self, task_id: UUID, reason: str) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"task {task_id}: {reason}")


class RunnerError(Exception):
    """The runner cannot walk this task, or cannot make sense of where it stands."""

    def __init__(self, task_id: UUID, reason: str) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"task {task_id}: {reason}")
