"""The Windows adapter: what a PC answers and what it says, through ``powershell.exe`` (M12.3c).

One module per system, as ADR 0039 §1 wrote it — «un modulo per sistema dietro una porta, mai un
``if platform.system()`` dentro il ciclo» — and the first one named for a system that is not the one
ELA was written on. M12.3c brought it one reading, the power source; M12.4 dec. D brings the voice
beside it, which puts this module among the voice's (architecture rules 35, 40 and 41).

**The same door as** :mod:`~ela.infrastructure.machine.darwin`: a binary of the system at a literal
path, started as a child through :func:`~ela.infrastructure.machine.darwin.spawn` — or, for the
voice, :func:`~ela.infrastructure.machine.darwin.spawn_with_input` —, killed if it overstays, and
nothing of it loaded into ELA's process (architecture rule 32). ``powershell.exe`` is
Windows PowerShell 5.1, present on every Windows and signed by Microsoft. Not ``%SystemRoot%``: an
environment variable is a door too (M12.4 dec. D).

**Each script is a constant in clear, in P3-bis's shape** (M12.4 dec. D): progress silenced before
anything else, and the body in a ``try`` whose ``catch`` writes the bare message to stderr and exits
``1``. The exit code decides, and a message is never read to decide anything: ``spawn`` discards
stderr, as it does for every child, and ``spawn_with_input`` leaves it to the node's terminal. The
script is encoded at the moment of starting, base64 of UTF-16LE, which is what ``-EncodedCommand``
reads: so whoever reads this module reads the script as PowerShell does.

Measured on the user's PC on 2026-09-15 (P6), with the same two lines and no ``try``: ``Online`` and
``0`` in five readings out of five, 0.25-0.36 s each, stderr empty; and on 2026-09-17 (P6-bis) in
this module's form, 0.265-0.406 s.

Nothing here decides: the answer is the machine's word for its power line and a count, and
:mod:`ela.devices.local` says what they are worth; the voice answers with a
:class:`~ela.domain.RawSpeech` and never says what it means.
"""

from __future__ import annotations

import base64
import math
import os
from datetime import timedelta
from pathlib import Path
from typing import Final

from ela.domain import RawSpeech
from ela.infrastructure.machine.darwin import (
    POWER_TIMEOUT_SECONDS,
    TIMED_OUT,
    Spawn,
    SpawnWithInput,
    spawn,
    spawn_with_input,
)

__all__ = [
    "POWERSHELL",
    "POWER_STATUS",
    "SPEAK",
    "SapiSpeechCommand",
    "encoded",
    "line_and_batteries",
    "power_status",
    "seconds_spoken",
]

POWERSHELL: Final = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
"""Windows PowerShell 5.1, at a literal path. On a Windows installed elsewhere it is not there, and
the reading is ``None`` — the power source ``UNKNOWN`` — rather than a binary ``PATH`` chose."""

POWER_STATUS: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.Windows.Forms
  [Console]::Out.WriteLine([System.Windows.Forms.SystemInformation]::PowerStatus.PowerLineStatus)
  [Console]::Out.WriteLine(@(Get-CimInstance Win32_Battery).Count)
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""Two lines on stdout: ``PowerLineStatus`` (``Online``, ``Offline``, ``Unknown``) and how many
``Win32_Battery`` objects the machine has. The count is read and not ``BatteryLifePercent``, which
on the PC of P6 — a desktop, ``NoSystemBattery`` — answered ``1``."""


def encoded(script: str) -> str:
    """``script`` as ``-EncodedCommand`` takes it: base64 of its UTF-16LE bytes."""
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


async def power_status(run: Spawn = spawn, binary: str = POWERSHELL) -> tuple[str, int] | None:
    """What this PC says of its power line, and how many batteries it has — or ``None`` (M12.3c).

    ``None`` for every way of not knowing: no ``powershell.exe``, a script that failed or
    overstayed, an answer of another shape.
    """
    if not (os.access(binary, os.X_OK) and Path(binary).is_file()):
        return None
    argv = [binary, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(POWER_STATUS)]
    try:
        code, output = await run(argv, POWER_TIMEOUT_SECONDS)
    except OSError:  # the binary vanished between the check and here
        return None
    if code != 0:
        return None
    return line_and_batteries(output)


def line_and_batteries(output: str) -> tuple[str, int] | None:
    """The two lines of :data:`POWER_STATUS`, as a word and a count; ``None`` for another shape."""
    words = output.split()
    if len(words) != 2 or not words[1].isdecimal():
        return None
    return words[0], int(words[1])


SPEAK: Final = """$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'
try {
  $ms = New-Object System.IO.MemoryStream
  [Console]::OpenStandardInput().CopyTo($ms)
  $all = [System.Text.Encoding]::UTF8.GetString($ms.ToArray())
  $cut = $all.IndexOf("`n")
  $voice = $all.Substring(0, $cut).TrimEnd("`r")
  $text = $all.Substring($cut + 1)
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  try {
    if ($voice) { $s.SelectVoice($voice) }
    $s.SetOutputToDefaultAudioDevice()
    $w = [System.Diagnostics.Stopwatch]::StartNew()
    $s.Speak($text)
    $w.Stop()
    [Console]::Out.WriteLine($w.Elapsed.TotalSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture))
  } finally { $s.Dispose() }
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
"""
"""P3-bis's script, as it was measured on the PC (2026-09-15): the voice on the first line of
stdin, the sentence after it, both decoded from UTF-8 by the script itself; ``Speak`` to the default
audio device, timed by a stopwatch whose seconds go to stdout in the invariant culture.

**The text is data, never code**: it is read from stdin into a variable and handed to ``Speak``, so
nothing a model writes can become PowerShell. And **to the speaker and nowhere else** — rule 40
reads this constant for the three methods of System.Speech that write elsewhere."""


class SapiSpeechCommand:
    """Says a sentence with a SAPI 5 voice, through ``powershell.exe`` (M12.4 dec. D).

    A :class:`~ela.ports.SpeechPort`.

    The shape of :class:`~ela.infrastructure.machine.speech.SaySpeechCommand` — a binary of the
    system at a literal path, a child of the node, killed if it overstays — with two differences
    that are both decisions of M12.4 dec. D:

    * **the sentence goes through stdin**, after the voice's name, and the command line is the same
      for every sentence;
    * **``spoken_seconds`` is the script's stopwatch**, and the life of the child is only what the
      timeout watches. Starting ``powershell.exe`` cost 0.55 s and 1.43 s on the PC (P3, P3-bis),
      above the verifier's floor for any sentence under a hundred characters: timed from outside, a
      child that exited ``0`` without a sound would pass.

    Keeps the port's promise — **it does not fail, it reports**. ``exit 0`` with no number on stdout
    is reported as it is, with no duration, and the verifier refuses it (decision of 2026-09-17).
    """

    __slots__ = ("_binary", "_spawn", "_timeout", "_voice")

    def __init__(
        self,
        *,
        timeout: timedelta,
        voice: str,
        runner: SpawnWithInput = spawn_with_input,
        binary: str = POWERSHELL,
    ) -> None:
        self._timeout = timeout.total_seconds()
        self._voice = voice
        self._spawn = runner
        self._binary = binary

    async def available(self) -> bool:
        """Whether ``powershell.exe`` is where ELA looks. Two syscalls; nothing starts."""
        return os.access(self._binary, os.X_OK) and Path(self._binary).is_file()

    async def speak(self, text: str) -> RawSpeech:
        """Say ``text`` with the configured voice, and answer with how the child ended.

        **An overstay carries no duration, and** ``say`` **does otherwise, on purpose** (review of
        2026-09-17). :class:`~ela.infrastructure.machine.speech.SaySpeechCommand` reports the
        child's life on a timeout too, because for ``say`` that life *is* the measure. Here the
        measure is the script's stopwatch, which a killed script never writes — and ``timed_out`` is
        a failure, so a duration beside it would be a number nobody can use well.
        """
        argv = [self._binary, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(SPEAK)]
        data = f"{self._voice}\n{text}".encode()
        try:
            code, output = await self._spawn(argv, data, self._timeout)
        except OSError:  # the binary vanished between available() and here
            return RawSpeech()
        if code == TIMED_OUT:
            return RawSpeech(exit_code=code, timed_out=True)
        if code != 0:
            return RawSpeech(exit_code=code)
        return RawSpeech(exit_code=code, spoken_seconds=seconds_spoken(output))


def seconds_spoken(output: str) -> float | None:
    """The stopwatch the script wrote, in seconds to the millisecond; ``None`` for anything else.

    A number that is not finite or is negative is not a duration either: no stopwatch writes one.
    """
    try:
        seconds = float(output.strip())
    except ValueError:
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return round(seconds, 3)
