"""The voice of a PC, tested without speakers and without a PC (M12.4 dec. D; criteria 10, 11).

``powershell.exe`` is replaced by a fake that answers as told, so every way the speaker can end is
taken on any runner; what the real binary does is ``test_sapi_smoke.py``, declared with its
``skipif``. The outputs are P3's and P3-bis's, from the files of 2026-09-15 (``M12.4.md``, «Gli
esiti»): a script that times ``Speak`` and writes the seconds, in the invariant culture.

Two properties are worth the tests more than the rest. **The sentence never reaches the command
line**, which on Windows every process of the user can read. And **what is timed is the sound**:
``spoken_seconds`` is the script's stopwatch, never the life of the child — the start of
``powershell.exe`` alone was worth 0.55-1.43 s on the PC, more than the verifier's floor for any
sentence under a hundred characters.
"""

from __future__ import annotations

import base64
import sys
from collections.abc import Sequence
from datetime import timedelta

import pytest

from ela.infrastructure.machine import POWERSHELL, SapiSpeechCommand
from ela.infrastructure.machine.darwin import TIMED_OUT, spawn_with_input
from ela.infrastructure.machine.windows import SPEAK, encoded

SENTENCE = "È già l'una: questa frase la dice il PC."
"""P3's sentence, forty characters with the accents whose code points P3 checked."""

ELSA = "Microsoft Elsa Desktop"
"""The only ``it-IT`` voice SAPI 5 lists on the PC (P3), and ``ELA_VOICE_NAME`` there."""

HERE = sys.executable
"""A binary that exists on every runner, standing in for ``powershell.exe`` where it must exist."""


class Child:
    """A fake ``spawn_with_input``: what it was asked, and the answer it was told to give."""

    def __init__(self, code: int = 0, output: str = "", *, raises: OSError | None = None) -> None:
        self.answer = (code, output)
        self.raises = raises
        self.asked: list[tuple[list[str], bytes, float]] = []

    async def __call__(self, argv: Sequence[str], data: bytes, timeout: float) -> tuple[int, str]:
        self.asked.append((list(argv), data, timeout))
        if self.raises is not None:
            raise self.raises
        return self.answer


def speaker(child: Child, *, voice: str = ELSA, seconds: int = 60) -> SapiSpeechCommand:
    return SapiSpeechCommand(timeout=timedelta(seconds=seconds), voice=voice, runner=child)


async def test_the_command_line_is_the_same_for_every_sentence_and_holds_none() -> None:
    """Criterion 10. ``Win32_Process.CommandLine`` is readable by every process of the user, as
    ``ps`` is on a Mac: the text goes through stdin, and the command is a fixed script."""
    child = Child(0, "1.0\r\n")
    command = speaker(child)

    await command.speak(SENTENCE)
    await command.speak("Un'altra frase, del tutto diversa.")

    (first, _, _), (second, _, _) = child.asked
    assert (
        first
        == second
        == [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(SPEAK)]
    )
    assert not any("frase" in part for part in first)
    assert "frase" not in base64.b64decode(first[-1]).decode("utf-16-le")


async def test_the_voice_and_then_the_sentence_travel_on_stdin_in_utf8() -> None:
    """Criterion 10. The voice on the first line, the sentence after it, as bytes of UTF-8 — which
    the script decodes itself, whatever the console's code page (P3 read back the code points
    ``224,232,236,242,249,32,233``)."""
    child = Child(0, "1.0\r\n")

    await speaker(child).speak(SENTENCE)

    ((_, data, _),) = child.asked
    assert data == f"{ELSA}\n{SENTENCE}".encode()


async def test_an_exit_0_is_a_sentence_said_for_as_long_as_the_script_timed_it() -> None:
    """Criterion 11. P3-bis on the PC: the script said 3.5192556 s, the child lived 4.953 s. The
    first is what goes in the report."""
    report = await speaker(Child(0, "3.5192556\r\n")).speak(SENTENCE)

    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (0, False, 3.519)


async def test_a_non_zero_exit_is_a_failure_that_carries_its_status_and_no_duration() -> None:
    """Criterion 11. P3-bis's voice that does not exist: ``exit 1``."""
    report = await speaker(Child(1, "")).speak(SENTENCE)

    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (1, False, None)


async def test_an_overstay_is_decided_by_the_tool_s_clock_and_not_by_the_exit_code() -> None:
    """Criterion 11. ``TerminateProcess`` leaves an ``exit 1`` behind (P3), which alone would read
    as a failure: what says *overstayed* is the wait that ran out, which ``spawn_with_input``
    reports as :data:`TIMED_OUT`. And no duration: the stopwatch never wrote one."""
    report = await speaker(Child(TIMED_OUT, "")).speak(SENTENCE)

    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (TIMED_OUT, True, None)


@pytest.mark.parametrize("output", ["", "\r\n", "detto", "3,5192556", "nan", "inf", "-1.0"])
async def test_a_stdout_that_is_not_a_duration_is_no_duration(output: str) -> None:
    """Criterion 11, as decided on 2026-09-17: ``exit 0`` and no number is reported as it is — no
    duration — and ``SpeakVerifier`` refuses it (``tests/tools/test_voice_verifier.py``). A comma
    is what a script that forgot the invariant culture would write on an Italian PC."""
    report = await speaker(Child(0, output)).speak(SENTENCE)

    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (0, False, None)


@pytest.mark.parametrize(("code", "spoken"), [(0, 1.25), (1, None)], ids=["said", "failed"])
async def test_stderr_never_decides_and_reaches_the_node_s_terminal(
    code: int, spoken: float | None, capfd: pytest.CaptureFixture[str]
) -> None:
    """Criterion 11, with a real child through the real ``spawn_with_input``: a line on stderr
    leaves a sentence said as said and a failure as failed, and shows up where the person at the
    machine reads it (decision of 2026-09-17)."""
    script = (
        "import sys\n"
        "sys.stderr.write('una diagnosi\\n')\n"
        "print('1.25')\n"
        f"raise SystemExit({code})\n"
    )

    async def a_python_child(argv: Sequence[str], data: bytes, timeout: float) -> tuple[int, str]:
        del argv
        return await spawn_with_input([sys.executable, "-c", script], data, timeout)

    report = await SapiSpeechCommand(
        timeout=timedelta(seconds=30), voice=ELSA, runner=a_python_child
    ).speak(SENTENCE)

    assert (report.exit_code, report.spoken_seconds) == (code, spoken)
    assert "una diagnosi" in capfd.readouterr().err


async def test_a_helper_that_vanished_on_the_way_is_not_an_exception() -> None:
    report = await speaker(Child(raises=FileNotFoundError(POWERSHELL))).speak(SENTENCE)

    assert (report.exit_code, report.timed_out, report.spoken_seconds) == (None, False, None)


async def test_the_timeout_reaches_the_child_in_seconds() -> None:
    """``ELA_VOICE_TIMEOUT_SECONDS``, 60 s fixed also on Windows (P3-bis, 2026-09-15)."""
    child = Child(0, "1.0")

    await speaker(child, seconds=60).speak(SENTENCE)

    ((_, _, timeout),) = child.asked
    assert timeout == 60.0


async def test_available_reads_the_filesystem_and_starts_nothing() -> None:
    child = Child(0, "1.0")
    there = SapiSpeechCommand(timeout=timedelta(seconds=1), voice=ELSA, runner=child, binary=HERE)
    missing = SapiSpeechCommand(
        timeout=timedelta(seconds=1), voice=ELSA, runner=child, binary="/nonexistent/powershell"
    )

    assert await there.available() is True
    assert await missing.available() is False
    assert child.asked == []


def test_the_script_is_p3_bis_s_and_speaks_to_the_default_device() -> None:
    """The shape P3-bis measured on the PC: progress silenced first, the body in a ``try`` whose
    ``catch`` writes the bare message and exits ``1``, ``Speak`` timed by a stopwatch written in
    the invariant culture. And encoded as ``-EncodedCommand`` reads it."""
    assert SPEAK.splitlines()[0] == "$ProgressPreference = 'SilentlyContinue'"
    assert "[Console]::Error.WriteLine($_.Exception.Message)" in SPEAK
    assert "exit 1" in SPEAK
    assert "$s.SetOutputToDefaultAudioDevice()" in SPEAK
    assert "[System.Diagnostics.Stopwatch]::StartNew()" in SPEAK
    assert "[System.Globalization.CultureInfo]::InvariantCulture" in SPEAK
    assert base64.b64decode(encoded(SPEAK)).decode("utf-16-le") == SPEAK
