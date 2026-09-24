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

**A skip on the kernel a test covers turns the suite red.** A ``skipif`` shows in the summary as a
number, and a number nobody reads is how a test stops proving the thing it exists for without
anybody noticing. So the two tests on the kernel are watched by one that is never skipped: on its
own kernel no ``skipif`` of theirs may fire, and anywhere else the one that fires is the one that
says the kernel is missing (review of M13.2, before the proof by hand).
"""

from __future__ import annotations

import asyncio
import dataclasses
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

NO_TRUE = "/usr/bin/true is not on this machine"
NOT_MACOS = "the total measured to the byte is macOS's kernel's"
NO_LIMIT_OF_ONE = "no MAX_ARG_STRLEN on this kernel: only Linux limits one argument apart"


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


@pytest.mark.skipif(sys.platform != "darwin", reason=NOT_MACOS)
@pytest.mark.skipif(not TRUE.exists(), reason=NO_TRUE)
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


@pytest.mark.skipif(sys.platform != "linux", reason=NO_LIMIT_OF_ONE)
@pytest.mark.skipif(not TRUE.exists(), reason=NO_TRUE)
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


# ----------------------------------------------------------------------------------------
# The watch on the two tests above: never skipped, and red at a skip on the kernel they cover
# ----------------------------------------------------------------------------------------


def fired(test: Callable[..., Any]) -> list[str]:
    """The reasons of the ``skipif`` marks of ``test`` whose condition holds on this machine."""
    return [
        mark.kwargs["reason"]
        for mark in getattr(test, "pytestmark", [])
        if mark.name == "skipif" and mark.args[0]
    ]


def skip_problems(test: Callable[..., Any], kernel: str, absent: str) -> list[str]:
    """What is wrong with how ``test`` skips on this machine, for a test that covers ``kernel``.

    On ``kernel`` nothing may skip it — a missing ``/usr/bin/true`` included: that would be the
    silent skip. Anywhere else it must skip, and ``absent`` — the reason that names the missing
    kernel — must be among the reasons.
    """
    reasons = fired(test)
    elsewhere = sys.platform != kernel
    problems = []
    if bool(reasons) is not elsewhere:
        problems.append(f"{test.__name__} on {sys.platform}: skipped for {reasons}")
    if (absent in reasons) is not elsewhere:
        problems.append(f"{test.__name__} on {sys.platform}: the missing kernel is not the reason")
    return problems


@pytest.mark.parametrize(
    ("test", "kernel", "absent"),
    [
        (
            test_on_linux_the_longest_argument_asked_about_starts_and_one_byte_more_does_not,
            "linux",
            NO_LIMIT_OF_ONE,
        ),
        (
            test_on_macos_the_last_command_asked_about_starts_and_one_byte_more_does_not,
            "darwin",
            NOT_MACOS,
        ),
    ],
    ids=["one-argument-on-linux", "total-on-macos"],
)
def test_a_test_on_the_kernel_is_never_skipped_on_its_kernel_and_elsewhere_says_why(
    test: Callable[..., Any], kernel: str, absent: str
) -> None:
    assert skip_problems(test, kernel, absent) == []


@pytest.mark.skipif(True, reason=NO_TRUE)
def a_test_silently_skipped_here() -> None:
    """Not collected (its name does not start with ``test``): the negative case of the watch."""


@pytest.mark.skipif(True, reason="the other kernel is missing")
def a_test_skipped_for_its_kernel() -> None:
    """Not collected: skipped, and for the kernel it names."""


def a_test_that_never_skips() -> None:
    """Not collected: no ``skipif`` at all."""


def test_the_watch_turns_red_at_a_skip_on_the_kernel_the_test_covers() -> None:
    """The negative cases of the watch (CLAUDE.md: what runs in ``make check`` proves it can fail).
    On its own kernel — this one, whatever it is — a test skipped for a missing binary is a
    problem; off its kernel, a test that does not skip, or skips for another reason, is one too."""
    here, elsewhere = sys.platform, "plan9"

    assert skip_problems(a_test_silently_skipped_here, here, "the kernel is missing") != []
    assert skip_problems(a_test_that_never_skips, elsewhere, "the kernel is missing") != []
    assert skip_problems(a_test_silently_skipped_here, elsewhere, "the kernel is missing") != []
    assert (
        skip_problems(a_test_skipped_for_its_kernel, elsewhere, "the other kernel is missing") == []
    )
    assert skip_problems(a_test_that_never_skips, here, "the kernel is missing") == []
