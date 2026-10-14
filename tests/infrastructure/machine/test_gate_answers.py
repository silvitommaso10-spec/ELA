"""An answer of the gate that cannot be written leaves nothing behind (found by ``make check`` of
M13.10, 2026-10-14).

When the driver of a browser dies while the gate is answering a paused request — the browser closed
at a step's end, at a task's end, at ELA's stop —, Playwright raises a plain ``Exception``
(«Connection closed while reading from the driver»), not a ``PlaywrightError``. The gate's own task
let it out, and the loop printed «Task exception was never retrieved» in the middle of the suite.

**Not answering is safe**: a request the gate does not let go stays paused, and a paused request
never leaves (ADR 0064 §2). So whatever the driver says to the answer, the task of the answer ends
quietly.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ela.infrastructure.machine.browser import _Gate


class GoneDriver:
    """The session of a browser whose driver has died: every command fails as Playwright fails."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.sent: list[str] = []

    async def send(self, method: str, params: Any = None) -> Any:
        self.sent.append(method)
        raise self.error


def a_gate(session: GoneDriver, *, leaves: bool) -> Any:
    gate: Any = object.__new__(_Gate)
    gate._session = session
    gate._stopping = asyncio.Event()
    gate.broken = False

    async def judged(event: Any) -> bool:
        return leaves

    gate._leaves = judged
    return gate


@pytest.mark.parametrize("leaves", [True, False], ids=["let-go", "refused"])
async def test_an_answer_the_dead_driver_cannot_take_ends_quietly(leaves: bool) -> None:
    session = GoneDriver(
        Exception("CDPSession.send: Connection closed while reading from the driver")
    )
    gate = a_gate(session, leaves=leaves)

    await gate._answered({"requestId": "1", "request": {"url": "https://sito.example/"}})

    assert session.sent == ["Fetch.continueRequest" if leaves else "Fetch.failRequest"]


async def test_a_cancelled_answer_is_still_a_cancellation() -> None:
    """Quiet, but not deaf: the cancellation of the task of an answer is not swallowed."""
    session = GoneDriver(asyncio.CancelledError())  # type: ignore[arg-type]
    gate = a_gate(session, leaves=True)

    with pytest.raises(asyncio.CancelledError):
        await gate._answered({"requestId": "1", "request": {"url": "https://sito.example/"}})
