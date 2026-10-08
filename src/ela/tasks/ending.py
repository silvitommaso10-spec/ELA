"""Why a task ended, read back from the words of the transition that ended it (M13.1e, ADR 0059).

ADR 0055 made the reason of every end but ``COMPLETED`` the summary of the audit event of the
transition that put the task in its state — chosen by ``payload.new_state`` and not by type,
because the no is an ``APPROVAL_RESOLVED`` —, and without that row the message of the trail's
``STATE_CHANGED`` with the name of its operation (ADR 0054 §7). Until M13.1e only the runner read
it, for ``run``; since then every route that carries the state of a task carries it too, and
**this is the one reading** of it (decision A): the runner, the Planner and the routes call
:meth:`~ela.tasks.engine.TaskEngine.ending`, and architecture rule 64 keeps a second copy out.

The same event says the rest, and nothing is composed: the operation — who ended the task —, the
code the payload carries wherever it carries one (decision 1 of the review: a failure's, the
orphan's, the cap's ``spending.*``, never a list of operations), and who said no, for a no. A task
denied by its planning names its planning task, and whoever reads with the ports follows it there.

Pure, with no port, like :mod:`ela.tasks.halt`: the engine has the two logs, and composes them.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final, NamedTuple
from uuid import UUID

from pydantic import JsonValue

from ela.domain import AuditEvent, Task, TaskEvent, TaskEventType, TaskId, TaskState
from ela.tasks.state_machine import TERMINAL_STATES

__all__ = ["REASONED", "Ending", "of_the_audit", "of_the_trail"]

REASONED: Final[frozenset[TaskState]] = frozenset(TERMINAL_STATES - {TaskState.COMPLETED})
"""The ends that say why: every one but ``COMPLETED``, which explains itself (M13.1c, ADR 0055).
The runner, the routes and the tests read it from here (decision B of M13.1e)."""

PLANNING_KEY: Final = "planning_task_id"
"""The key with which ``deny_by_planning`` names the planning task that was denied (ADR 0058)."""


class Ending(NamedTuple):
    """Why a task ended: its reason and what the same event says beside it."""

    reason: str
    """The summary of the transition — the reason ``run`` has given since M13.1c, unchanged."""
    operation: str | None
    """The operation that ended the task: who ended it (ADR 0055 §1)."""
    code: str | None
    """The code the payload carries, wherever it carries one."""
    responded_by: str | None
    """The identity that said no, as the approval recorded it — for a task denied by its planning,
    filled by the reader from the planning task."""
    planning_task_id: TaskId | None
    """The planning task a task denied by its planning names (ADR 0058)."""


def _text(value: JsonValue | None) -> str | None:
    """A value of the engine's JSON a surface can say: a string with something in it."""
    return value if isinstance(value, str) and value else None


def _task(value: JsonValue | None) -> TaskId | None:
    return None if (said := _text(value)) is None else TaskId(UUID(said))


def of_the_audit(task: Task, audit: Sequence[AuditEvent]) -> Ending | None:
    """The end of ``task`` from the audit event that wrote its state; ``None`` without that row —
    the window of a crash between the trail and the audit — or for an end without a reason."""
    if task.state not in REASONED:
        return None
    for event in reversed(audit):
        payload = event.payload
        if payload.get("new_state") == task.state.value:
            return Ending(
                event.summary,
                _text(payload.get("operation")),
                _text(payload.get("code")),
                _text(payload.get("responded_by")),
                _task(payload.get(PLANNING_KEY)),
            )
    return None


def of_the_trail(task: Task, trail: Sequence[TaskEvent]) -> Ending:
    """The end of ``task`` from the trail, when the audit has no row: the message of the
    ``STATE_CHANGED`` with its operation; and with no such change, the state itself. Never empty
    (ADR 0054 §7). No code and nobody who answered: only the audit carries them."""
    for change in reversed(trail):
        if change.event_type is TaskEventType.STATE_CHANGED and change.new_state is task.state:
            operation = str(change.metadata.get("operation", ""))
            reason = f"{operation}: {change.message}" if change.message else operation
            return Ending(
                reason, operation or None, None, None, _task(change.metadata.get(PLANNING_KEY))
            )
    return Ending(task.state.value, None, None, None, None)
