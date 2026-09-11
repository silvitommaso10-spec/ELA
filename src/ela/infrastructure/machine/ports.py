"""Who holds a TCP port on this machine, when the machine can say (M12.1, the bind that fails).

The question a taken port raises is *who*: on 2026-09-11 it was a ``python3`` left over from a
trial, and a message that named it would have said what to stop. ``lsof`` answers on macOS and on
most Linux systems; where it is not installed, fails, or does not answer within
:data:`LOOKUP_TIMEOUT_SECONDS`, the answer is ``None`` and the caller says less — never a guess.

It lives here because starting a process is this package's alone (architecture rule 32), and it
starts it through :func:`~ela.infrastructure.machine.darwin.spawn`, which kills a child that does
not answer in time: a lookup made to explain a failed start must not become a hung one.
"""

from __future__ import annotations

import shutil
from typing import Final

from ela.infrastructure.machine.darwin import Spawn, spawn

__all__ = ["LOOKUP_TIMEOUT_SECONDS", "holder_from", "port_holder"]

LOOKUP_TIMEOUT_SECONDS: Final = 2.0
"""Long enough for ``lsof`` on a busy machine, short enough not to stretch a failed start."""


async def port_holder(port: int, run: Spawn = spawn) -> str | None:
    """The process listening on TCP ``port``, as ``name (pid N)``; ``None`` if it cannot be told."""
    lsof = shutil.which("lsof")
    if lsof is None:
        return None
    code, output = await run(
        [lsof, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fpc"], LOOKUP_TIMEOUT_SECONDS
    )
    if code != 0:
        return None
    return holder_from(output)


def holder_from(output: str) -> str | None:
    """The first process of ``lsof -F pc`` output — ``p<pid>`` then ``c<command>`` — or ``None``."""
    pid: str | None = None
    command: str | None = None
    for line in output.splitlines():
        if line.startswith("p") and pid is None:
            pid = line[1:]
        elif line.startswith("c") and pid is not None and command is None:
            command = line[1:]
    if pid is None:
        return None
    return f"{command or 'a process'} (pid {pid})"
