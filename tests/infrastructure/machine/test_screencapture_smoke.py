"""The capture helper is there, and this test does not use it (M10.2, ADR 0029 §3).

``screencapture(1)`` is Apple's binary, not ELA's, so the contract worth proving on a real Mac is
narrow on purpose: it exists at the absolute path ELA names, and this process could run it.

**Nothing here captures anything, and that is a decision.** Running it from a process without the
Screen Recording grant can raise the system prompt, and a prompt nobody sees records a
*permanent* denial that then has to be undone by hand in System Settings. A CI runner is exactly
"nobody sees it". So the smoke test stops at the door, and what happens beyond it is the tool's,
under a permission a human granted (ADR 0029 §7).
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from ela.infrastructure.machine import SCREENCAPTURE, ScreenCaptureCommand
from ela.tools.settings import CAPTURE_TIMEOUT_IS_MEASURED
from tests import machines
from tests.tools.test_settings import overdue

pytestmark = machines.needs(machines.DARWIN, why="the capture helper is macOS's")


def test_the_helper_ela_names_is_where_ela_says_it_is() -> None:
    assert Path(SCREENCAPTURE).is_file()
    assert os.access(SCREENCAPTURE, os.X_OK)


async def test_the_adapter_agrees_that_this_machine_can_capture() -> None:
    """``available()`` on the real path, which is the only thing about this machine the adapter
    can learn without asking for a permission or showing anything to anybody."""
    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1))

    assert await capture.available()


@machines.needs(machines.SCREEN_RECORDING, why="nothing can be timed")
def test_the_placeholder_timeout_is_gone_once_this_machine_could_measure_it() -> None:
    """ADR 0029 §14: the reminder is an **observable fact**, not a date.

    ``ELA_CAPTURE_TIMEOUT_SECONDS`` was written as a declared placeholder because the permission
    was denied and no capture had ever run. The failure mode of a placeholder is that nobody comes
    back to it, and a note in a docstring does not come back on its own — so what is checked is
    the condition under which it *becomes* wrong: **the moment ELA can read that Screen Recording
    is granted on this machine, a number that is still a placeholder is a red test.**

    Where the permission is missing there is nothing to measure, and the summary says so rather
    than the test passing quietly: a check that is vacuously true is the shape this project spends
    its milestones removing. The permission is read the way ELA reads it — the real probe, which
    asks and never prompts (ADR 0028 §2) —, **by the condition of the one place**
    (:data:`tests.machines.SCREEN_RECORDING`, M9.5): until 2026-11-17 it was read here, and the skip
    was an ``if`` in the body of the test, against ADR 0031 §6. So what fires the test is the same
    fact the tool acts on, not a second opinion about the machine; and on the runner of macOS a
    permission that is missing is a red, not a skip. The decision itself is
    :func:`~tests.tools.test_settings.overdue`, which is pure and has its negative case there.
    """
    reason = overdue(granted=True, measured=CAPTURE_TIMEOUT_IS_MEASURED)
    assert reason is None, reason
