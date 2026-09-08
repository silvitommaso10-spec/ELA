"""The macOS adapter: run the probe, read primitives, never decide (M10.1, ADR 0028 §1, §2).

Two pieces with very different jobs, and the split is the whole design:

* :func:`spawn` starts the helper, waits with a timeout and kills it if it overstays. It is
  ordinary ``asyncio`` and knows nothing about macOS, so it is exercised on every runner —
  Ubuntu included — by spawning a trivial Python command.
* :class:`DarwinProbe` turns whatever came back into a :class:`~ela.domain.RawObservation`. It
  receives ``spawn`` as a dependency, so a timeout, a dead child and a mouthful of nonsense are
  all things a test can produce without any hardware at all.

What is left that no runner can execute is one file, :mod:`ela.infrastructure.perception.probe`,
and even that one is *run* in CI on macOS to prove the contract it must keep (exit 0, JSON,
known keys) without asserting anything about hardware nobody has.

This module names no domain vocabulary — no ``SensorState``, no ``PermissionState`` — and
architecture rule 34 makes that a rule instead of a promise. An adapter that does not know the
words cannot use them wrongly, and that is what lets it stay outside the coverage gate honestly.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta
from typing import Final

from ela.domain import ProbeFamily, RawObservation

__all__ = ["PROBE_MODULE", "TIMED_OUT", "DarwinProbe", "Spawn", "spawn"]

PROBE_MODULE: Final = "ela.infrastructure.perception.probe"
"""The child, started with this interpreter so a virtual environment is inherited."""

TIMED_OUT: Final = -1
"""The exit code :func:`spawn` reports for a child it had to kill. Any non-zero would do; a name
is worth more than a magic number in the one place where "no answer" is the answer."""

Spawn = Callable[[Sequence[str], float], Awaitable[tuple[int, str]]]
"""Start a command, wait at most ``timeout`` seconds, answer ``(exit code, stdout)``."""


async def spawn(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Run ``argv``, kill it past ``timeout``, and answer with its exit code and output.

    ``stderr`` is discarded on purpose: a child that dies of an Objective-C exception writes a
    stack trace to it, and that trace is neither ELA's to interpret nor something to carry into a
    perception snapshot. What matters is that it did not answer.
    """
    process = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        return TIMED_OUT, ""
    code = TIMED_OUT if process.returncode is None else process.returncode
    return code, stdout.decode(errors="replace")


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
