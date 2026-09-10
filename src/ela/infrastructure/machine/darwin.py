"""The macOS adapter: run the probe, read primitives, never decide (M10.1, ADR 0028 §1, §2).

Two pieces with very different jobs, and the split is the whole design:

* :func:`spawn` starts the helper, waits with a timeout and kills it if it overstays. It is
  ordinary ``asyncio`` and knows nothing about macOS, so it is exercised on every runner —
  Ubuntu included — by spawning a trivial Python command.
* :class:`DarwinProbe` turns whatever came back into a :class:`~ela.domain.RawObservation`. It
  receives ``spawn`` as a dependency, so a timeout, a dead child and a mouthful of nonsense are
  all things a test can produce without any hardware at all.

What is left that no runner can execute is one file, :mod:`ela.infrastructure.machine.probe`,
and even that one is *run* in CI on macOS to prove the contract it must keep (exit 0, JSON,
known keys) without asserting anything about hardware nobody has.

This module names no domain vocabulary — no ``SensorState``, no ``PermissionState`` — and
architecture rule 34 makes that a rule instead of a promise. An adapter that does not know the
words cannot use them wrongly, and that is what lets it stay outside the coverage gate honestly.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import Final, Protocol

from ela.domain import ProbeFamily, RawObservation

__all__ = [
    "PROBE_MODULE",
    "SPEECH_FILE_PREFIX",
    "TIMED_OUT",
    "DarwinProbe",
    "Spawn",
    "SpawnWithAudio",
    "spawn",
    "spawn_with_audio",
    "sweep_speech_files",
]

PROBE_MODULE: Final = "ela.infrastructure.machine.probe"
"""The child, started with this interpreter so a virtual environment is inherited."""

TIMED_OUT: Final = -1
"""The exit code :func:`spawn` reports for a child it had to kill. Any non-zero would do; a name
is worth more than a magic number in the one place where "no answer" is the answer."""

Spawn = Callable[[Sequence[str], float], Awaitable[tuple[int, str]]]
"""Start a command, wait at most ``timeout`` seconds, answer ``(exit code, stdout)``."""


class SpawnWithAudio(Protocol):
    """The same, with bytes handed to the child as a file that has no name (ADR 0034 §7).

    A ``Protocol`` rather than an alias only because of the keyword: what the Core depends on is
    :class:`~ela.ports.SpeechPort`, and how an implementation of it reaches a player is
    composition, exactly as :data:`Spawn` is.
    """

    async def __call__(
        self, argv: Sequence[str], audio: bytes, timeout: float, *, directory: str | None = None
    ) -> tuple[int, str]:
        """Run ``argv`` with ``audio`` as its last argument, and answer as :data:`Spawn` does."""


SPEECH_FILE_PREFIX: Final = "ela-speech-"
"""What a leftover of :func:`spawn_with_audio` is called, so that :func:`sweep_speech_files` can
find it. Nothing normally wears this name for longer than one syscall."""


async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Run ``argv``, kill it past ``timeout``, and answer with its exit code and output.

    ``stderr`` is discarded on purpose: a child that dies of an Objective-C exception writes a
    stack trace to it, and that trace is neither ELA's to interpret nor something to carry into a
    perception snapshot. What matters is that it did not answer.

    Both ways of giving up kill the child — see :func:`_wait`. It was a latent fault for the probe
    and for the capture, where the residue is a stray reader. It is not latent for the voice
    (M11.1, criterio 9): an orphaned ``say`` is **ELA that keeps talking after being told to
    stop**. Fixed once for every caller, and there are four of them now.
    """
    process = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    return await _wait(process, timeout)


async def spawn_with_audio(
    argv: Sequence[str], audio: bytes, timeout: float, *, directory: str | None = None
) -> tuple[int, str]:
    """Run ``argv`` with ``audio`` handed over as a file that **has no name** (M11.3, ADR 0034 §7).

    The path of the audio is appended to ``argv``, because only this function can know it: it is
    ``/dev/fd/N`` of a descriptor this process holds and the child inherits.

    **Why a file at all**, when nothing ELA says is supposed to touch a disk: ``afplay`` opens its
    argument with the AudioFile API, which seeks. A pipe and a FIFO both fail with
    ``AudioFileOpen -40``; there is no other player on macOS; and writing one in CoreAudio would
    put ``ctypes`` back inside ELA's own process, which is what ADR 0029 §3 spent a milestone
    avoiding. So there is a file, and the whole design is in the two lines after it is made:

    * ``unlink`` immediately, before a single byte is written. From that instant the inode has no
      name in any directory: it cannot be listed, opened by path, backed up or synced, and the
      kernel frees it when the last descriptor closes — **including when ELA is killed.**
    * hand the child ``/dev/fd/N``, which on Darwin opens the very same file, seekable.

    Between ``mkstemp`` and ``unlink`` there is one syscall in which a name exists, and this is
    the only reason ``directory`` and :data:`SPEECH_FILE_PREFIX` exist: the file is made inside
    ELA's own ``0700`` directory, under a prefix, so that the one thing that can survive — a
    crash in that window — is something :func:`sweep_speech_files` can find at the next start-up.
    Not a store (ADR 0029 §1 decided that for artefacts a verifier re-reads, and this one has no
    second reader): **a swept floor.**

    This lives here, and not in the modules that hold what ELA says, for two reasons that are the
    same reason: rule 32 — the operating system is touched in one place — and rule 41, which can
    then forbid those modules from touching a filesystem **with no exception to remember.**
    """
    fd, path = tempfile.mkstemp(prefix=SPEECH_FILE_PREFIX, dir=directory)
    try:
        os.unlink(path)
        _write_all(fd, audio)
        os.lseek(fd, 0, os.SEEK_SET)
        os.set_inheritable(fd, True)
        process = await asyncio.create_subprocess_exec(
            *argv,
            f"/dev/fd/{fd}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            pass_fds=(fd,),
        )
        return await _wait(process, timeout)
    finally:
        os.close(fd)


def _write_all(fd: int, payload: bytes) -> None:
    """``os.write`` may write less than it was given; the audio has to be all of it.

    A short write would hand the player a truncated file, which plays a truncated sentence — a
    failure that would look like a provider's and be ours.
    """
    written = 0
    while written < len(payload):
        written += os.write(fd, payload[written:])


def sweep_speech_files(directory: Path) -> int:
    """Delete leftovers of :func:`spawn_with_audio` and answer how many there were.

    Called at start-up, which is the one moment ELA reaches with certainty (ADR 0029 §1's own
    argument for purging there). There is normally nothing to find: the file loses its name one
    syscall after it is made. What this collects is the crash that lands inside that syscall —
    rare, and exactly the kind of rare thing that stays on a disk for a year.
    """
    if not directory.is_dir():
        return 0
    swept = 0
    for leftover in directory.glob(f"{SPEECH_FILE_PREFIX}*"):
        with suppress(OSError):
            leftover.unlink()
            swept += 1
    return swept


async def _wait(process: asyncio.subprocess.Process, timeout: float) -> tuple[int, str]:
    """Wait for a child, and kill it whichever way the waiting ends badly.

    **Two ways of giving up, and both kill the child.** A timeout is ELA deciding the helper took
    too long, and it answers :data:`TIMED_OUT`. A *cancellation* is the caller itself going away,
    and it re-raises — but not before killing, because ``asyncio.wait_for`` cancels the coroutine
    reading the child's pipes and never touches the child.
    """
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        await _kill(process)
        return TIMED_OUT, ""
    except asyncio.CancelledError:
        await _kill(process)
        raise
    code = TIMED_OUT if process.returncode is None else process.returncode
    return code, stdout.decode(errors="replace")


async def _kill(process: asyncio.subprocess.Process) -> None:
    """Kill a child and reap it; a child that already exited is the outcome that was wanted.

    ``ProcessLookupError`` is the race between the check and the signal, and it is suppressed
    rather than branched on: whether the child was still there is not something this line can
    know without asking, and asking is the same race one line earlier.
    """
    with suppress(ProcessLookupError):
        process.kill()
    await process.wait()


class DarwinProbe:
    """Reads this Mac through a helper process (:class:`~ela.ports.PerceptionProbe`).

    Keeps the port's hardest promise: **it does not fail, it reports.** A timeout, a child killed
    by a signal, output that is not JSON, a key this version does not know — every one of them
    comes back as a :class:`~ela.domain.RawObservation` with every field ``None``, which the core
    reads as "not observable". Nothing here raises, because a perception read must never be able
    to take ELA down with it (§33).
    """

    __slots__ = ("_spawn", "_timeout")

    def __init__(self, *, timeout: timedelta, runner: Spawn = spawn) -> None:
        self._timeout = timeout.total_seconds()
        self._spawn = runner

    async def read(self, families: frozenset[ProbeFamily]) -> RawObservation:
        """Read the requested families; anything that goes wrong reads as nothing observed."""
        if not families:
            return RawObservation()
        argv = [
            sys.executable,
            "-m",
            PROBE_MODULE,
            ",".join(sorted(family.value for family in families)),
        ]
        try:
            code, output = await self._spawn(argv, self._timeout)
            if code != 0:
                return RawObservation()
            return RawObservation.model_validate(json.loads(output))
        except (OSError, ValueError):
            # ValueError covers both halves of "the child did not make sense": a JSONDecodeError
            # and a pydantic ValidationError are both ValueErrors, and neither is ELA's fault.
            return RawObservation()
