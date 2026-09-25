"""The two readers of the power source against the real machine that has the binary (M12.3c).

Each is declared with its ``skipif`` (ADR 0031 §6), and ``test_power.py`` already proves what ELA
does where the binary is missing. Nothing here asserts **which** source: whether this Mac is plugged
in is a fact of the afternoon, not of the code. What is asserted is that the answer has the shape
the reader reads.
"""

from __future__ import annotations

import os
import platform
import subprocess
import time

import pytest

from ela.infrastructure.machine.darwin import POWER_TIMEOUT_SECONDS, pmset_source
from ela.infrastructure.machine.windows import (
    POWER_STATUS,
    POWERSHELL,
    encoded,
    power_status,
    without_module_path,
)


@pytest.mark.skipif(platform.system() != "Darwin", reason="pmset(1) is macOS's")
async def test_pmset_answers_in_words_the_reader_can_read() -> None:
    assert await pmset_source() is not None


def what_the_pc_said() -> str:
    """The script of the reading run as ELA runs it — the literal binary, the environment without
    ``PSModulePath`` (M12.3d) — with what ELA's launcher throws away: the exit code, stdout,
    stderr and the seconds it took. A failure prints it, the way the ACL smoke prints its SDDL:
    the reader answers ``None`` for every way of not knowing, and ``None`` says nothing of which."""
    started = time.monotonic()
    done = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(POWER_STATUS)],
        capture_output=True,
        timeout=120,
        check=False,
        env=without_module_path(os.environ),
    )
    took = time.monotonic() - started
    return (
        f"exit {done.returncode} in {took:.2f} s (ELA waits {POWER_TIMEOUT_SECONDS} s); "
        f"stdout {done.stdout.decode('utf-8', errors='replace')!r}; "
        f"stderr {done.stderr.decode('utf-8', errors='replace')!r}"
    )


@pytest.mark.skipif(platform.system() != "Windows", reason="PowerStatus is Windows's")
async def test_powershell_answers_in_words_the_reader_can_read() -> None:
    answered = await power_status()

    assert answered is not None, what_the_pc_said()
    line, batteries = answered
    assert line in {"Online", "Offline", "Unknown"}
    assert batteries >= 0
