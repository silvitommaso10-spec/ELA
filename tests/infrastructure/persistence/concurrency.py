"""Two real connections on one file, each held at the same statement until the other reaches it.

The shape of M12.1's criteria 3, 11 and 12 (ADR 0037 §9): what they assert is the ``rowcount`` of
two conditional ``UPDATE`` statements that both got past every check a reader could make — one and
zero — and not the row that is left, which the loser of a race by order of arrival would also
leave behind.

Held with :func:`~sqlalchemy.util.await_only` on an :class:`asyncio.Barrier`, for the reason
``test_audit_log.py`` gives: a statement listener runs in the greenlet on the event loop's thread,
so a ``threading`` wait would block the loop, and the other connection with it. Before the
statement and not after: neither transaction has asked for the write lock yet, so both
connections are at the door at once and the database, not the test, decides who goes first.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.util import await_only

DEADLOCK_GUARD = 30.0
"""Seconds before a wait gives up. Not a margin: it turns a regression that would hang the suite
into a test that fails (``test_audit_log.py``)."""


class Meeting:
    """Where two connections wait for each other, and the ``rowcount`` each came away with."""

    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.barrier = asyncio.Barrier(2)
        self.rowcounts: list[int] = []

    def attend(self, engine: AsyncEngine) -> None:
        """Hold the first statement ``engine`` runs that starts with the prefix until the other
        engine has reached its own; record the ``rowcount`` of every such statement."""
        held = False

        @event.listens_for(engine.sync_engine, "before_cursor_execute")
        def _wait(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            nonlocal held
            if statement.startswith(self.prefix) and not held:
                held = True
                await_only(asyncio.wait_for(self.barrier.wait(), DEADLOCK_GUARD))

        @event.listens_for(engine.sync_engine, "after_cursor_execute")
        def _count(conn: Any, cursor: Any, statement: str, *args: Any) -> None:
            if statement.startswith(self.prefix):
                self.rowcounts.append(cursor.rowcount)
