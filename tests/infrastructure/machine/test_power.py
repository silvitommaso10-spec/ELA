"""The two readers of the power source — ``pmset`` on a Mac, ``PowerStatus`` through
``powershell.exe`` on a PC (M12.3c) — which hand over the machine's own words and decide nothing.

The child is replaced by a fake, so every branch is taken on any machine; what the real binaries
answer is ``test_power_smoke.py``, declared with its ``skipif``. The outputs are P6's, copied from
the files of 2026-09-15 (``docs/milestones/M12.4.md``, «Gli esiti»).
"""

from __future__ import annotations

import base64
import sys
from collections.abc import Sequence

import pytest

from ela.infrastructure.machine.darwin import (
    PMSET,
    POWER_TIMEOUT_SECONDS,
    TIMED_OUT,
    drawn_from,
    pmset_source,
)
from ela.infrastructure.machine.windows import (
    POWER_STATUS,
    POWERSHELL,
    encoded,
    line_and_batteries,
    power_status,
)

PLUGGED = (
    "Now drawing from 'AC Power'\n"
    " -InternalBattery-0 (id=5439587)\t100%; charged; 0:00 remaining present: true\n"
)
UNPLUGGED = (
    "Now drawing from 'Battery Power'\n"
    " -InternalBattery-0 (id=5439587)\t100%; discharging; (no estimate) present: true\n"
)
ON_A_DESKTOP = "Online\r\n0\r\n"
"""The PC of P6: ``PowerLineStatus`` and the number of ``Win32_Battery`` objects, one per line."""

HERE = sys.executable
"""A binary that exists and can be run on every runner, standing in for ``pmset`` or PowerShell."""

NOWHERE = "/nonexistent/ela/power-reader"


class Child:
    """A fake ``spawn``: what it was asked, and the answer it was told to give."""

    def __init__(self, code: int = 0, output: str = "", *, raises: OSError | None = None) -> None:
        self.answer = (code, output)
        self.raises = raises
        self.asked: list[tuple[list[str], float]] = []

    async def __call__(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        self.asked.append((list(argv), timeout))
        if self.raises is not None:
            raise self.raises
        return self.answer


# ----------------------------------------------------------------------------------------
# pmset, on a Mac
# ----------------------------------------------------------------------------------------


def test_the_mac_says_where_it_draws_from_in_its_own_words() -> None:
    assert drawn_from(PLUGGED) == "AC Power"
    assert drawn_from(UNPLUGGED) == "Battery Power"


@pytest.mark.parametrize(
    "output",
    ["", " -InternalBattery-0 (id=5439587)\t100%; charged\n", "Now drawing from AC Power\n"],
    ids=["nothing", "no-first-line", "no-quotes"],
)
def test_an_answer_that_does_not_say_where_it_draws_from_says_nothing(output: str) -> None:
    assert drawn_from(output) is None


async def test_pmset_is_asked_for_the_battery_within_the_timeout() -> None:
    child = Child(0, UNPLUGGED)

    assert await pmset_source(child, binary=HERE) == "Battery Power"
    ((argv, timeout),) = child.asked
    assert argv == [HERE, "-g", "batt"]
    assert timeout == POWER_TIMEOUT_SECONDS


@pytest.mark.parametrize("code", [1, TIMED_OUT], ids=["failed", "timed-out"])
async def test_a_pmset_that_fails_or_does_not_answer_says_nothing(code: int) -> None:
    assert await pmset_source(Child(code, PLUGGED), binary=HERE) is None


async def test_a_pmset_that_vanished_on_the_way_says_nothing() -> None:
    assert await pmset_source(Child(raises=FileNotFoundError()), binary=HERE) is None


async def test_a_machine_without_pmset_says_nothing_and_starts_nothing() -> None:
    child = Child(0, PLUGGED)

    assert await pmset_source(child, binary=NOWHERE) is None
    assert child.asked == []


def test_pmset_is_apple_s_at_an_absolute_path() -> None:
    """Never resolved through ``PATH``, for the reason ``SAY`` gives (ADR 0029 §3)."""
    assert PMSET == "/usr/bin/pmset"


# ----------------------------------------------------------------------------------------
# PowerStatus, on a PC
# ----------------------------------------------------------------------------------------


def test_the_pc_says_its_power_line_and_how_many_batteries_it_has() -> None:
    assert line_and_batteries(ON_A_DESKTOP) == ("Online", 0)
    assert line_and_batteries("Offline\n1\n") == ("Offline", 1)


@pytest.mark.parametrize(
    "output",
    ["", "Online\r\n", "Online\r\nnessuna\r\n", "Online\r\n-1\r\n", "Online\r\n0\r\nancora\r\n"],
    ids=["nothing", "one-line", "not-a-number", "negative", "three-lines"],
)
def test_an_answer_of_another_shape_says_nothing(output: str) -> None:
    assert line_and_batteries(output) is None


async def test_powershell_runs_the_script_encoded_and_nothing_else() -> None:
    child = Child(0, ON_A_DESKTOP)

    assert await power_status(child, binary=HERE) == ("Online", 0)
    ((argv, timeout),) = child.asked
    assert argv == [HERE, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(POWER_STATUS)]
    assert timeout == POWER_TIMEOUT_SECONDS


def test_the_encoding_is_the_one_powershell_reads() -> None:
    """``-EncodedCommand`` takes base64 of UTF-16LE (M12.4 dec. D, P3)."""
    assert base64.b64decode(encoded(POWER_STATUS)).decode("utf-16-le") == POWER_STATUS


def test_the_script_keeps_stderr_raw_and_ends_with_an_exit_code() -> None:
    """P3-bis's shape: progress silenced first, and a ``catch`` that writes the bare message and
    exits ``1`` — so nothing is serialised onto stderr, and the exit code is what decides."""
    assert POWER_STATUS.splitlines()[0] == "$ProgressPreference = 'SilentlyContinue'"
    assert "[Console]::Error.WriteLine($_.Exception.Message)" in POWER_STATUS
    assert "exit 1" in POWER_STATUS


@pytest.mark.parametrize("code", [1, TIMED_OUT], ids=["failed", "timed-out"])
async def test_a_powershell_that_fails_or_does_not_answer_says_nothing(code: int) -> None:
    assert await power_status(Child(code, ON_A_DESKTOP), binary=HERE) is None


async def test_a_powershell_that_vanished_on_the_way_says_nothing() -> None:
    assert await power_status(Child(raises=FileNotFoundError()), binary=HERE) is None


async def test_a_machine_without_powershell_says_nothing_and_starts_nothing() -> None:
    child = Child(0, ON_A_DESKTOP)

    assert await power_status(child, binary=NOWHERE) is None
    assert child.asked == []


def test_powershell_is_the_system_s_at_a_literal_path() -> None:
    """Not ``%SystemRoot%``: what reads the machine is not decided by the environment (dec. D)."""
    assert POWERSHELL == r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
