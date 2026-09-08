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
import platform
from datetime import timedelta
from pathlib import Path

import pytest

from ela.infrastructure.perception import SCREENCAPTURE, ScreenCaptureCommand

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin", reason="the capture helper is macOS's"
)


def test_the_helper_ela_names_is_where_ela_says_it_is() -> None:
    assert Path(SCREENCAPTURE).is_file()
    assert os.access(SCREENCAPTURE, os.X_OK)


async def test_the_adapter_agrees_that_this_machine_can_capture() -> None:
    """``available()`` on the real path, which is the only thing about this machine the adapter
    can learn without asking for a permission or showing anything to anybody."""
    capture = ScreenCaptureCommand(timeout=timedelta(seconds=1))

    assert await capture.available()
