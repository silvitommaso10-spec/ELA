"""The loop of ``local``'s heartbeat lives and dies with the application (M13.3, ADR 0048 §2).

The lifespan is run for real — the ``ASGITransport`` of the other tests does not run it —, and what
is asserted is the fact, not a duration: while the application is up there is a task running the
Core's heartbeat loop, and when it stops there is none.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI

from ela.composition import Ela


def loops_of(ela: Ela) -> list[asyncio.Task[None]]:
    """The tasks of this event loop that are running ``ela``'s heartbeat loop."""
    return [
        task
        for task in asyncio.all_tasks()
        if not task.done()
        and task.get_coro().cr_frame is not None  # type: ignore[union-attr]
        and task.get_coro().cr_code is ela.heartbeat.run.__code__  # type: ignore[union-attr]
    ]


async def test_the_heartbeat_loop_starts_with_the_application_and_stops_with_it(
    app: FastAPI, ela: Ela
) -> None:
    async with app.router.lifespan_context(app):
        running = loops_of(ela)
        assert len(running) == 1

    assert running[0].cancelled()
    assert loops_of(ela) == []
