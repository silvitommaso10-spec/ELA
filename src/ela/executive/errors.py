"""Errors of the executor (spec §27, §33).

Raised *before* anything is written: a precondition of the pipeline that does not hold — the
task is not EXECUTING, the step is not RUNNING, the step declares a number of capabilities other
than one — is refused without a decision, a grant or a tool call (ADR 0013 §2). The other
refusals the executor lets through are already named elsewhere: ``CapabilityNotFound``,
``ToolNotFound``, ``UnknownStepError``, ``ApprovalMismatchError``.
"""

from __future__ import annotations

from uuid import UUID

__all__ = ["ExecutorError"]


class ExecutorError(Exception):
    """A precondition of the executor did not hold; nothing was written."""

    def __init__(self, task_id: UUID, reason: str) -> None:
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"task {task_id}: {reason}")
