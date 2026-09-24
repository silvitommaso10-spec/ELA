"""The launcher of ``terminal.run``: a program in a process group of its own (M13.2, ADR 0047).

The sister of :func:`~ela.infrastructure.machine.darwin.spawn` — which keeps its children in the
group of whoever started ELA, where they keep receiving that terminal's Ctrl-C — with what only the
terminal needs (dec. 15): the environment, the folder and stdin the tool decided, the streams capped
**while they are read**, and **a session of its own**, so that stopping the command is stopping its
group and not only its first process. The terminal is the first caller of ELA that makes
grandchildren.

**It decides nothing about the command** (rule 34). Every number and every name the command runs
with comes from the :class:`~ela.ports.Command` the tool built — the timeout, the breath, the two
halves of the ceiling, the variables — and what comes back is primitives: how it ended, a code or a
signal, raw bytes. Its own constants bound how long it waits for **the kernel**, never for the
program: they keep a machine in a bad state from holding ELA.

**A command has ended when its first process has.** What it leaves in its group is not the
command: the launcher gives the pipes :data:`REAP_SECONDS` to deliver what is in flight, then
empties the group and closes the pipes — so a descendant that holds one neither holds the launcher
until the timeout nor turns a program that returned 0 into a timeout.

Three ways of stopping to wait before that, and one way of stopping the group:

* **the timeout** — ``SIGTERM`` to the group, the breath, ``SIGKILL`` to the group;
* **the stop signal of ADR 0038 §11**, raised by the signal handler of ``ela serve`` at the instant
  of a Ctrl-C: the same, because the command's group does not receive that Ctrl-C and ``uvicorn``
  would otherwise wait for the request until the timeout («La ripresa» of M13.2);
* **a cancellation** of the caller: the same, and then the cancellation goes on.

The breath ends as soon as the kernel knows no process of the group — asked with
``killpg(group, 0)`` —; otherwise ``SIGKILL`` follows, and the launcher waits for the group to be
empty within :data:`EMPTY_SECONDS`. Past that bound a member is inside the kernel with ``SIGKILL``
pending: it will not run another instruction of its own, and ELA does not wait for it. A grandchild
that left the group (``setsid``, a daemon) survives, as decision 7 declares, and the pipes it holds
are closed from this side.
"""

from __future__ import annotations

import asyncio
import os
import signal
from contextlib import suppress
from typing import Any, Final

from ela.ports import Captured, Command, Ending, Ran

__all__ = ["EMPTY_SECONDS", "ProcessGroupLauncher"]

EMPTY_SECONDS: Final = 5.0
"""How long, after ``SIGKILL``, the launcher waits for the group to be empty, asking every
:data:`LOOK_SECONDS`. A process ``SIGKILL`` does not end at once is one inside the kernel; the bound
is what keeps a machine in that state from holding ELA."""
LOOK_SECONDS: Final = 0.01
REAP_SECONDS: Final = 2.0
"""How long the launcher waits for the pipes once the first process has ended by itself, and for
the first process to be reaped once the group is empty."""


class _Kept:
    """One stream, capped while it is read: the first bytes, the last ones, and how many."""

    def __init__(self, head: int, tail: int) -> None:
        self._head = head
        self._tail = tail
        self.head = bytearray()
        self.tail = bytearray()
        self.total = 0

    def add(self, data: bytes) -> None:
        self.total += len(data)
        room = self._head - len(self.head)
        if room > 0:
            self.head += data[:room]
            data = data[room:]
        if data and self._tail > 0:
            self.tail += data
            del self.tail[: max(0, len(self.tail) - self._tail)]

    def captured(self) -> Captured:
        return Captured(head=bytes(self.head), tail=bytes(self.tail), total=self.total)


class _Watching(asyncio.SubprocessProtocol):
    """What the loop tells about a child: its bytes, its pipes closing, its end."""

    def __init__(self, loop: asyncio.AbstractEventLoop, stdout: _Kept, stderr: _Kept) -> None:
        self._streams = {1: stdout, 2: stderr}
        self._open = {1, 2}
        self.closed: asyncio.Future[None] = loop.create_future()
        self.exited: asyncio.Future[None] = loop.create_future()

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        self._streams[fd].add(data)

    def pipe_connection_lost(self, fd: int, exc: Exception | None) -> None:
        self._open.discard(fd)
        if not self._open and not self.closed.done():
            self.closed.set_result(None)

    def process_exited(self) -> None:
        if not self.exited.done():
            self.exited.set_result(None)


class ProcessGroupLauncher:
    """Starts a program in a group of its own and empties the group whenever ELA stops waiting.

    Implements :class:`~ela.ports.CommandLauncher`. ``stopping`` is the event of ADR 0038 §11, the
    one ``api/server.py`` raises at the instant of the signal; the composition hands the same event
    to the pages' long-polls and to this launcher.
    """

    __slots__ = ("_stopping",)

    def __init__(self, stopping: asyncio.Event) -> None:
        self._stopping = stopping

    async def run(self, command: Command) -> Ran:
        if self._stopping.is_set():
            return Ran(Ending.STOPPED)
        loop = asyncio.get_running_loop()
        stdout, stderr = _Kept(command.head, command.tail), _Kept(command.head, command.tail)
        try:
            transport, watching = await loop.subprocess_exec(
                lambda: _Watching(loop, stdout, stderr),
                *command.argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=dict(command.environment),
                cwd=command.folder,
                start_new_session=True,
            )
        except OSError as refused:
            return Ran(Ending.NOT_STARTED, failure=f"{type(refused).__name__}: {refused}")
        group = transport.get_pid()
        stop = asyncio.ensure_future(self._stopping.wait())
        ending: Ending | None = None
        racing: set[asyncio.Future[Any]] = {watching.exited, stop}
        try:
            done, _ = await asyncio.wait(
                racing, timeout=command.timeout, return_when=asyncio.FIRST_COMPLETED
            )
            if watching.exited in done:
                with suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(watching.closed), REAP_SECONDS)
            else:
                ending = Ending.STOPPED if stop in done else Ending.TIMED_OUT
            await _stop(group, watching, command.grace)
        except asyncio.CancelledError:
            await _stop(group, watching, command.grace)
            raise
        finally:
            stop.cancel()
            transport.close()
        code = transport.get_returncode()
        exited = code if code is not None and code >= 0 else None
        killed = -code if code is not None and code < 0 else None
        if ending is None:
            ending = Ending.EXITED if exited is not None else Ending.SIGNALLED
        return Ran(
            ending,
            code=exited,
            signal=killed,
            stdout=stdout.captured(),
            stderr=stderr.captured(),
        )


async def _stop(group: int, watching: _Watching, grace: float) -> None:
    """``SIGTERM`` to the group, the breath, ``SIGKILL`` to the group, and the group emptied.

    On a group that is already empty — a program that ended and left nothing — every step is one
    question to the kernel that answers «nobody».
    """
    _signal(group, signal.SIGTERM)
    if not await _emptied(group, grace):
        _signal(group, signal.SIGKILL)
        await _emptied(group, EMPTY_SECONDS)
    with suppress(TimeoutError):
        await asyncio.wait_for(asyncio.shield(watching.exited), REAP_SECONDS)


def _signal(group: int, sent: int) -> None:
    """Signal every process of ``group``; one that is already gone is the outcome wanted."""
    with suppress(ProcessLookupError, PermissionError):
        os.killpg(group, sent)


async def _emptied(group: int, within: float) -> bool:
    """Whether the kernel knows no process of ``group``, asked every :data:`LOOK_SECONDS` until
    ``within`` seconds have passed on the loop's clock — a deadline and not a count of questions,
    because a sleep of ten milliseconds lasts longer than ten, and two hundred of them are not the
    breath of 2 s."""
    deadline = asyncio.get_running_loop().time() + within
    while True:
        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            pass  # a member exists that this user may not signal: it still counts as a member
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(LOOK_SECONDS)
