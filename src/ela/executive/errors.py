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

from datetime import datetime
from uuid import UUID

__all__ = ["AssignmentAtCapError", "AssignmentRefusedError", "ExecutorError", "RunnerError"]


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


class AssignmentRefusedError(Exception):
    """Work was not handed to a node, and nothing was written (ADR 0038 §6).

    The decision is not ``ALLOWED``, has expired, or is about no step; or the node is ``local``,
    which runs in this process and is never assigned. A placement that allows no node is the
    orchestrator's own refusal, :class:`~ela.devices.errors.NotPlacedError`.
    """

    def __init__(self, decision_id: UUID, reason: str) -> None:
        self.decision_id = decision_id
        self.reason = reason
        super().__init__(f"decision {decision_id}: {reason}")


class AssignmentAtCapError(Exception):
    """A renewal that cannot move the expiry any further: the work is at its cap (ADR 0038 §13).

    Nothing is written; the work expires when it says, and a node stuck renewing for ever does
    not hold a step for ever.
    """

    def __init__(self, assignment_id: UUID, expires_at: datetime) -> None:
        self.assignment_id = assignment_id
        self.expires_at = expires_at
        super().__init__(
            f"assignment {assignment_id} is at its cap: it expires at {expires_at.isoformat()}"
        )
