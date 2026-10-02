"""The stop of a task as one call of a tool sees it (§65; M6.3c, ADR 0054 §2–§3).

The engine raises one ``asyncio.Event`` per task when the task ends (``TaskEngine.stop_signal``);
the executor hands a tool this view of it, built **per call**: :meth:`StopOfTask.listen` raises
:class:`~ela.ports.ToolStopped` once the task is stopped, and records that the tool passed its
point when the place it listens at is the point it declared. What the executor reads afterwards —
whether the tool acted — is :attr:`StopOfTask.passed`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from ela.ports import ToolStopped

__all__ = ["StopOfTask"]


class StopOfTask:
    """Implements :class:`~ela.ports.TaskStop` for one call of one tool.

    ``here`` is the tool's own point (``StopPoint.here``). ``None`` means the point is the call
    itself: a tool with no wait before its effect is past it once called, and ``passed`` says so.
    """

    __slots__ = ("_event", "_here", "_passed")

    def __init__(self, event: asyncio.Event, here: str | None) -> None:
        self._event = event
        self._here = here
        self._passed = False

    def listen(self, where: str) -> None:
        if self._event.is_set():
            raise ToolStopped(where)
        if where == self._here:
            self._passed = True

    def is_set(self) -> bool:
        return self._event.is_set()

    def stopped(self) -> Awaitable[object]:
        return self._event.wait()

    @property
    def passed(self) -> bool:
        """Whether the tool passed its point of no return in this call: it acted."""
        return self._here is None or self._passed
