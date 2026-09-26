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
    spawn_powershell,
    without_module_path,
)

SMOKE_WAIT_SECONDS = 60.0
"""How long the smoke waits for a reading on the runner: a VM's cold PowerShell, not the PC's."""


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
    """ELA's launcher and environment (M12.3d), and **a wait of a minute, not ELA's five seconds**.

    Measured on the Windows job (runs 36178451554 and 36178717970, 2026-09-25): the runner's first,
    cold Windows PowerShell overruns :data:`POWER_TIMEOUT_SECONDS` — ``None`` after 5.01 s — and
    the same script right after answers ``Online`` and ``0`` in 2.91-3.03 s. The budget is the PC's,
    measured by P6 at 0.25-0.4 s, and it stays the product's; what this smoke asserts is what its
    module says, the shape of the answer — the thing M12.3d repaired (decision of the review of
    M13.3's implementation, 2026-09-25)."""
    started = time.monotonic()
    answered = await power_status(run=lambda argv, _: spawn_powershell(argv, SMOKE_WAIT_SECONDS))
    took = time.monotonic() - started

    assert answered is not None, f"power_status: None in {took:.2f} s; then {what_the_pc_said()}"
    line, batteries = answered
    assert line in {"Online", "Offline", "Unknown"}
    assert batteries >= 0
