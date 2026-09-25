"""What a running ELA takes from the system: a clock, a source of ids, and what the machine runs on.

Until M8.1 the only implementations of the first two ports were the fakes in :mod:`ela.testing`,
which no production module may import (contract 5): ELA could be tested but not run. These are
the two the composition root builds, and they are as small as the ports are — a real clock and a
real source of ids, with no policy of their own.

M12.3c adds the third, the power source, and it is **chosen by naming the system** (ADR 0031 §3):
``pmset`` on Darwin, ``powershell.exe`` on Windows, nobody elsewhere. The readers hand over the
machine's words (``ela.infrastructure.machine``), ``ela.devices.local`` says what they are worth,
and what is here only puts the two together — so a node and ``local`` read the same machine the
same way.

M13.2 adds the limits of what a launch passes to a program, chosen the same way: ``execve``'s on a
POSIX system — the total, and on Linux one more for a single argument —, the command line of
``CreateProcess`` on Windows, where ``os.sysconf`` does not exist.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Final
from uuid import UUID, uuid4

from ela.devices import power_drawn_from, power_on_the_line
from ela.domain import PowerSource
from ela.infrastructure.machine import (
    PMSET,
    POWERSHELL,
    Spawn,
    pmset_source,
    power_status,
    spawn,
    spawn_powershell,
)
from ela.tools.terminal import ArgumentLimits

__all__ = [
    "LINUX_PAGES_IN_ONE_ARGUMENT",
    "WINDOWS_COMMAND_LINE",
    "PowerReading",
    "SystemClock",
    "UuidGenerator",
    "argument_limits",
    "power_nobody_reads",
    "power_of_a_mac",
    "power_of_a_pc",
    "power_reading",
]


class SystemClock:
    """The wall clock, always **aware and in UTC** (ADR 0003 §4).

    Never ``datetime.now()`` without a timezone: a naive instant compared with a stored one is a
    comparison between two different questions, and the domain refuses to hold one at all.
    """

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


class UuidGenerator:
    """Random ids (``uuid4``): no host address, no sequence, nothing to correlate (§57)."""

    __slots__ = ()

    def new_uuid(self) -> UUID:
        return uuid4()


PowerReading = Callable[[], Awaitable[PowerSource]]
"""What this machine runs on, read **now** (M12.3c).

A ``Callable`` and not a port, the shape of ``Spawn``: what reads the machine is composition, and
the port count does not move. Asked by both things that write a heartbeat — a node on every sign
of life, ``local`` at start-up and on every run — and never cached: a laptop is unplugged in the
middle of a session, and a reading kept from an hour ago is a fact nobody observed.
"""


async def power_of_a_mac(run: Spawn = spawn, binary: str = PMSET) -> PowerSource:
    """``pmset -g batt``, through the Mac's map. ``run`` and ``binary`` are what a test names."""
    return power_drawn_from(await pmset_source(run, binary))


async def power_of_a_pc(run: Spawn = spawn_powershell, binary: str = POWERSHELL) -> PowerSource:
    """``PowerStatus`` through ``powershell.exe``, through the PC's map — started without the
    ``PSModulePath`` a PowerShell 7 would hand it (M12.3d)."""
    return power_on_the_line(await power_status(run, binary))


async def power_nobody_reads() -> PowerSource:
    """A system ELA has no reader for: ``UNKNOWN``, said out loud and worth zero points.

    A function with a name rather than an absent argument, for the reason ``UnsupportedSpeech`` is a
    class: "ELA on Linux does not know what it runs on" is a thing with a test, not a gap.
    """
    return PowerSource.UNKNOWN


def power_reading(system: str) -> PowerReading:
    """The reader for the system named, which is what ``platform.system()`` answers.

    An ``if`` per system and never a ternary (architecture rule 37): the arm a conditional
    expression does not take costs the branch gate nothing, and each arm here is proved by a test
    that names it.
    """
    if system == "Darwin":
        return power_of_a_mac
    if system == "Windows":
        return power_of_a_pc
    return power_nobody_reads


WINDOWS_COMMAND_LINE: Final = 32767
"""The longest command line ``CreateProcess`` takes, in characters. The terminal does not run on a
PC before M13.3 (ADR 0047 §13); the number is here so that ``build`` starts there, and it is the
real one, not a placeholder."""


LINUX_PAGES_IN_ONE_ARGUMENT: Final = 32
"""``MAX_ARG_STRLEN`` is ``PAGE_SIZE * 32`` (``include/uapi/linux/binfmts.h``): one argument, its
closing NUL included, whatever the total allows — 128 KiB with pages of 4 KiB."""


def argument_limits(system: str) -> ArgumentLimits:
    """What a launch may pass to a program on the system named (ADR 0047 §5): an ``if`` per system,
    as :func:`power_reading`, so the arm this suite does not run on is proved by name.

    macOS has no limit of its own for one argument — measured on 2026-09-24: one argument of
    1 048 412 bytes starts, and the kernel's count is ELA's to the byte —, so there ``one`` is the
    total, as it is for a system nobody measured.
    """
    if system == "Windows":
        return ArgumentLimits(total=WINDOWS_COMMAND_LINE, one=WINDOWS_COMMAND_LINE)
    total = os.sysconf("SC_ARG_MAX")
    if system == "Linux":
        return ArgumentLimits(
            total=total, one=os.sysconf("SC_PAGESIZE") * LINUX_PAGES_IN_ONE_ARGUMENT
        )
    return ArgumentLimits(total=total, one=total)
