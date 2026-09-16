"""The voice of a PC, on the machine that has it (M12.4 dec. D, dec. H level 2).

Declared with its ``skipif`` (ADR 0031 §6), and outside the Windows job's list: a CI runner has no
speakers. **This one speaks a syllable**, unlike the smoke test of ``say``: on the PC the question
is not only whether ``powershell.exe`` is where ELA looks, but whether the script as it is in the
code — encoded, fed on stdin — makes ``Speak`` run and report its stopwatch. The voice is the
system's default (an empty name), so the test does not depend on which voices a PC installed.
"""

from __future__ import annotations

import platform
from datetime import timedelta

import pytest

from ela.infrastructure.machine import SapiSpeechCommand

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="System.Speech is Windows's")


async def test_powershell_is_there_and_says_a_syllable_timing_it() -> None:
    command = SapiSpeechCommand(timeout=timedelta(seconds=60), voice="")

    assert await command.available() is True
    report = await command.speak("sì")
    assert (report.exit_code, report.timed_out) == (0, False)
    assert report.spoken_seconds is not None
    assert report.spoken_seconds > 0
