"""Errors of the Task Engine (spec §14).

One base class so that a caller can catch "anything the task machinery refused" in one clause.
The state machine raises :class:`ela.tasks.state_machine.IllegalTransitionError`; the Task Engine
(M3.1) adds its own exceptions here. No project-wide error hierarchy yet: nothing needs it.
"""

from __future__ import annotations

__all__ = ["TaskError"]


class TaskError(Exception):
    """Base class of every error raised by ``ela.tasks``."""
