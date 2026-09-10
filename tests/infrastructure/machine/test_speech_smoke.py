"""``say`` is where ELA expects it, on the machine that has it (M11.1, ADR 0033).

Asserts the **contract** and never a sound: that the binary is at its absolute path and is
executable. It cannot assert that anybody heard anything — no runner has ears, and saying so is
the whole shape of this milestone's verifier.

Nothing here speaks. A test that made a CI runner talk would be a test that changes the machine
it runs on, and the adapter's ``available()`` is precisely the answer that costs nothing.
"""

from __future__ import annotations

import platform
from datetime import timedelta
from pathlib import Path

import pytest

from ela.infrastructure.machine import SAY, SaySpeechCommand

pytestmark = pytest.mark.skipif(platform.system() != "Darwin", reason="say(1) is macOS's")


async def test_the_helper_is_apple_s_at_an_absolute_path_and_executable() -> None:
    command = SaySpeechCommand(timeout=timedelta(seconds=1), voice="Alice")

    assert Path(SAY).is_absolute()
    assert await command.available() is True
