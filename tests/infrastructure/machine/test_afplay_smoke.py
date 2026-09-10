"""``afplay`` is where ELA expects it, on the machine that has it (M11.3, ADR 0034 §7).

Asserts the **contract** and never a sound, exactly like its sibling for ``say``: the binary is
at its absolute path and is executable. Nothing here plays anything — a test that made a runner
make a noise would be a test that changes the machine it runs on.

The other half of the contract is the one the reconnaissance had to establish by hand, because no
documentation states it: ``afplay`` opens its argument with the AudioFile API, which **seeks**, so
a pipe and a FIFO are both refused with ``AudioFileOpen -40`` and an unlinked descriptor reached
through ``/dev/fd/N`` is not. That is why the audio ELA plays has no name, and it is measured in
``tests/infrastructure/machine/test_spawn.py`` on every platform with a child of our own.
"""

from __future__ import annotations

import platform
from pathlib import Path

import pytest

from ela.infrastructure.machine import AFPLAY, OnlineSpeechCommand
from ela.providers.elevenlabs import Synthesis

pytestmark = pytest.mark.skipif(platform.system() != "Darwin", reason="afplay(1) is macOS's")


async def _never(text: str) -> Synthesis:  # pragma: no cover - available() never synthesises
    raise AssertionError("asking whether the machine can play must not ask for any audio")


async def test_the_player_is_apples_at_an_absolute_path_and_executable(tmp_path: Path) -> None:
    command = OnlineSpeechCommand(synthesise=_never, unconfigured=lambda: None, directory=tmp_path)

    assert Path(AFPLAY).is_absolute()
    assert await command.available() is True
