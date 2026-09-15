"""The Windows adapter: what a PC answers, read through ``powershell.exe`` (M12.3c).

One module per system, as ADR 0039 §1 wrote it — «un modulo per sistema dietro una porta, mai un
``if platform.system()`` dentro il ciclo» — and the first one named for a system that is not the one
ELA was written on. M12.3c brings it one reading, the power source; M12.4's voice arrives beside it.

**The same door as** :mod:`~ela.infrastructure.machine.darwin`: a binary of the system at a literal
path, started as a child through :func:`~ela.infrastructure.machine.darwin.spawn`, killed if it
overstays, and nothing of it loaded into ELA's process (architecture rule 32). ``powershell.exe`` is
Windows PowerShell 5.1, present on every Windows and signed by Microsoft. Not ``%SystemRoot%``: an
environment variable is a door too (M12.4 dec. D).

**The script is a constant in clear, in P3-bis's shape** (M12.4 dec. D): progress silenced before
anything else, and the body in a ``try`` whose ``catch`` writes the bare message to stderr and exits
``1``. ``spawn`` discards stderr, as it does for every child — the exit code decides, and a message
is never read to decide anything. The script is encoded at the moment of starting, base64 of
UTF-16LE, which is what ``-EncodedCommand`` reads: so whoever reads this module reads the script as
PowerShell does.

Measured on the user's PC on 2026-09-15 (P6), with the same two lines and no ``try``: ``Online`` and
``0`` in five readings out of five, 0.25-0.36 s each, stderr empty.

Nothing here decides: the answer is the machine's word for its power line and a count, and
:mod:`ela.devices.local` says what they are worth.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Final

from ela.infrastructure.machine.darwin import POWER_TIMEOUT_SECONDS, Spawn, spawn

__all__ = ["POWERSHELL", "POWER_STATUS", "encoded", "line_and_batteries", "power_status"]

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
