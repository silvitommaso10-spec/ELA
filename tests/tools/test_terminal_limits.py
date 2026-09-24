"""The limits ``terminal.run`` checks before the question are the kernel's (review of M13.2, 5b).

The tool refuses what would not start **before** asking — ADR 0045 §6-bis: no yes for what would
not start —, and this file asserts, on the real kernel, that the line it draws is the kernel's line:
the last command the tool asks about starts, and the same command with one byte more is refused by
``execve`` as well as by the tool.

Each half needs the machine it is about, and says so with a ``skipif`` on ``sys.platform`` — the
kernel itself, which ``tests/foreign_machine.py`` does not pretend (ADR 0031 §6):

* **macOS** has one limit, the total, and ELA's count is the kernel's to the byte: measured on
  2026-09-24, with two paths of different length (``.git/m13.2-reference/measure/``);
* **Linux** has a second one, ``MAX_ARG_STRLEN``, for one argument: 32 pages, the closing NUL
  included. Its total is a declared residual (ADR 0047 §5), and is not asserted here.
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ela.composition.system import argument_limits
from ela.domain import DecisionId, PermissionDecision, PermissionOutcome, RiskLevel
from ela.infrastructure.machine import ProcessGroupLauncher
from ela.permissions import TERMINAL_RUN
from ela.ports import Command, Ending
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeLauncher
from ela.tools.programs import Programs
from ela.tools.terminal import ARGUMENTS_UNPASSABLE, ArgumentLimits, Terminal, TerminalRunTool

TRUE = Path("/usr/bin/true")
NOW = datetime(2026, 9, 24, 10, 0, tzinfo=UTC)
REFUSED = "Argument list too long"
"""What ``execve`` says with ``E2BIG``, on both kernels."""

pytestmark = pytest.mark.skipif(not TRUE.exists(), reason="/usr/bin/true is not on this machine")


def a_tool(root: Path, limits: ArgumentLimits, launcher: FakeLauncher) -> TerminalRunTool:
    """The tool with the limits of the kernel the test declares — named, never read from
    ``platform.system()``, which ``make check-linux`` pretends."""
    (root / "ELA").mkdir(parents=True)
    terminal = Terminal(
        programs=Programs.fixed(["usr/bin/true"]),
        root=root,
        scope="ELA",
        timeout_seconds=30,
        output_max_bytes=64,
        home="/Users/tu",
        temporary="/tmp/tu",
        argument_limits=limits,
    )
    return TerminalRunTool(terminal, launcher, FakeClock(NOW), FakeIdGenerator())


def call(argument: str) -> dict[str, object]:
    return {"program": "usr/bin/true", "args": [argument], "purpose": "il limite"}


def allowed() -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=NOW,
        capability_id=TERMINAL_RUN,
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=NOW.replace(hour=11),
    )


async def asked(tool: TerminalRunTool, size: int) -> bool:
    return (await tool.prospect(call("a" * size))).refusal is None


async def the_last_asked(tool: TerminalRunTool, high: int) -> int:
    """The longest argument the tool still asks about, by bisection over ``prospect``."""
    low = 0
    while high - low > 1:
        middle = (low + high) // 2
        if await asked(tool, middle):
            low = middle
        else:
            high = middle
    return low


async def the_command_of(tool: TerminalRunTool, launcher: FakeLauncher, size: int) -> Command:
    """The command the tool would hand the launcher for an argument of ``size`` bytes."""
    await tool.execute(allowed(), call("a" * size))
    return launcher.commands[-1]


def one_byte_more(command: Command) -> Command:
    *before, last = command.argv
    return dataclasses.replace(command, argv=(*before, last + "a"))


@pytest.mark.skipif(sys.platform != "darwin", reason="the total of macOS's kernel")
async def test_on_macos_the_last_command_asked_about_starts_and_one_byte_more_does_not(
    tmp_path: Path,
) -> None:
    launcher = FakeLauncher()
    limits = argument_limits("Darwin")
    tool = a_tool(tmp_path / "files", limits, launcher)
    last = await the_last_asked(tool, limits.total)
    command = await the_command_of(tool, launcher, last)
    real = ProcessGroupLauncher(asyncio.Event())

    started = await real.run(command)
    refused = await real.run(one_byte_more(command))

    assert (started.ending, started.code) == (Ending.EXITED, 0)
    assert refused.ending is Ending.NOT_STARTED
    assert refused.failure is not None and REFUSED in refused.failure


@pytest.mark.skipif(sys.platform != "linux", reason="the limit of one argument of Linux's kernel")
async def test_on_linux_the_longest_argument_asked_about_starts_and_one_byte_more_does_not(
    tmp_path: Path,
) -> None:
    launcher = FakeLauncher()
    limits = argument_limits("Linux")
    tool = a_tool(tmp_path / "files", limits, launcher)
    one = limits.one
    refusal = (await tool.prospect(call("a" * one))).refusal
    command = await the_command_of(tool, launcher, one - 1)
    real = ProcessGroupLauncher(asyncio.Event())

    started = await real.run(command)
    refused = await real.run(one_byte_more(command))

    assert refusal is not None and refusal.code == ARGUMENTS_UNPASSABLE
    assert "in one argument" in refusal.message
    assert (started.ending, started.code) == (Ending.EXITED, 0)
    assert refused.ending is Ending.NOT_STARTED
    assert refused.failure is not None and REFUSED in refused.failure
