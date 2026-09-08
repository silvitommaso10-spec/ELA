"""``spawn``: start a command, wait, and kill it if it overstays.

Plain ``asyncio`` that knows nothing about macOS, so it runs on every runner — which is the whole
reason it was pulled out of the helper: the part that can be exercised anywhere should be, and
what is left unexercisable shrinks to one file.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

from ela.infrastructure.perception import TIMED_OUT, spawn


async def test_a_command_that_answers_gives_its_code_and_its_output() -> None:
    code, output = await spawn([sys.executable, "-c", "print('{}')"], 10)

    assert (code, output.strip()) == (0, "{}")


async def test_a_command_that_fails_gives_a_non_zero_code() -> None:
    code, _ = await spawn([sys.executable, "-c", "raise SystemExit(3)"], 10)

    assert code == 3


async def test_a_command_that_overstays_is_killed_and_reported_as_timed_out() -> None:
    """The failure mode pyobjc could not have covered: not an exception, an answer that never
    comes (ADR 0028 §2). The wait is the process's own, so nothing here polls a clock."""
    code, output = await spawn([sys.executable, "-c", "import time; time.sleep(30)"], 0.05)

    assert (code, output) == (TIMED_OUT, "")


async def test_output_that_is_not_utf8_does_not_raise() -> None:
    """A child that dies mid-write can leave a broken byte sequence behind; that is the adapter's
    problem to name, not an exception to propagate."""
    code, output = await spawn(
        [sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe')"], 10
    )

    assert code == 0
    assert output


async def test_a_cancelled_wait_kills_the_child_instead_of_orphaning_it() -> None:
    """Cancelling the caller must not leave the helper running (M11.1, criterio 9).

    ``asyncio.wait_for`` cancels the coroutine that reads the child's pipes; it does not touch
    the child, so the natural spelling leaves a process that keeps going after the caller gave
    up. For the probe that is a stray reader; for the voice it is **ELA that does not stop
    talking when it has been told to stop**, which is the worse half of the problem decision F
    postponed to the barge-in.

    Written as a marker file the child creates *after* the moment it should already be dead: if
    the kill happened, the file never appears.
    """
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "still-alive"
        child = (
            "import pathlib, time\n"
            "time.sleep(0.6)\n"
            f"pathlib.Path({str(marker)!r}).write_text('x')\n"
        )
        task = asyncio.create_task(spawn([sys.executable, "-c", child], 30))
        await asyncio.sleep(0.15)  # long enough for the child to exist, short enough to be early
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.9)  # past the instant the child would have written

        assert not marker.exists(), "the child outlived the cancelled call"
