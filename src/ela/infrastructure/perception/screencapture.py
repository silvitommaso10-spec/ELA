"""The screen-capture helper: Apple's own binary, run as a child (M10.2, ADR 0029 §3).

Three ways to photograph a display on macOS 26 were looked at before this one was chosen, and
the measurement is in the milestone:

* ``CGDisplayCreateImage`` and friends, through ``ctypes``: the symbols are still there, and both
  have been deprecated since macOS 14/15 — and macOS 15 added a **periodic re-consent prompt** for
  capture by the legacy path. A permission that comes back to ask every month is not something to
  build on.
* ScreenCaptureKit: the supported path, and asynchronous Objective-C with completion **blocks**.
  Building a block literal from ``ctypes`` would be the most fragile thing in this repository, and
  the subprocess covers a crash but does not make a capture work.
* ``/usr/sbin/screencapture``: present, signed by Apple, writes a file, exits non-zero when it is
  refused.

The argument that decided it is not robustness. It is that **architecture rule 33 becomes vacuous
instead of respected**: "the helper imports only the standard library, never ``ela``" defends a
property — *what has to be able to die on its own must not carry the Core's import graph with it*
— and when the helper is not our code at all, the property is true by construction. It also takes
``ctypes`` out of the riskiest read in the project. The declared price is that the helper prints
no metadata, so the image's dimensions are read from the PNG's own IHDR chunk, twenty lines of
``struct`` that live inside the coverage gate (:mod:`ela.tools.captures`).

Rule 32 puts every process launch in this package, and its content is "ELA touches the operating
system in one place" — the door, not the word "perception". So this adapter lives here even
though a capture is an *action* and its tool lives in :mod:`ela.tools.screen`.

This module names no domain vocabulary (rule 34): it answers with a
:class:`~ela.domain.RawCapture` — an exit status and whether it was killed — and never says what
that means. Whether "exit code 1" is a revoked permission or a full disk is not an adapter's to
decide, and whether anything was actually written is read from the artefact, never from here.
"""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Final

from ela.domain import RawCapture
from ela.infrastructure.perception.darwin import TIMED_OUT, Spawn, spawn

__all__ = ["SCREENCAPTURE", "ScreenCaptureCommand", "UnsupportedScreenCapture"]

SCREENCAPTURE: Final = "/usr/sbin/screencapture"
"""Apple's, at an absolute path. Never resolved through ``PATH``: what photographs the user's
screen must not be decided by an environment variable."""


class ScreenCaptureCommand:
    """Photographs a display with ``screencapture`` (:class:`~ela.ports.ScreenCapturePort`).

    ``spawn`` arrives as a dependency — the same one :class:`~ela.infrastructure.perception.
    darwin.DarwinProbe` uses, and the same reason: a timeout, a child killed by a signal and a
    non-zero exit are all things a test can produce with no hardware and no permission at all.

    Keeps the port's hardest promise: **it does not fail, it reports.** Nothing here raises, and
    nothing here looks at the file — whether a capture happened is the caller's to read from the
    artefact it owns (§20: sending is not succeeding).
    """

    __slots__ = ("_binary", "_spawn", "_timeout")

    def __init__(
        self,
        *,
        timeout: timedelta,
        runner: Spawn = spawn,
        binary: str = SCREENCAPTURE,
    ) -> None:
        self._timeout = timeout.total_seconds()
        self._spawn = runner
        self._binary = binary

    async def available(self) -> bool:
        """Whether the helper is on this machine. Reads nothing, asks for nothing.

        Async because the port is, not because this waits: it is two syscalls, and a port whose
        two members disagreed on colour would be a port that is awkward to implement twice.
        """
        return os.access(self._binary, os.X_OK) and Path(self._binary).is_file()

    async def capture(self, destination: str, display: int) -> RawCapture:
        """Write a PNG of ``display`` to ``destination``, and answer with how it ended.

        ``-x`` silences the shutter — ELA photographing the screen must not sound like the user
        did it — ``-t png`` fixes the format the caller will read back, and ``-D`` selects the
        display, 1-based.
        """
        argv = [self._binary, "-x", "-t", "png", "-D", str(display), destination]
        try:
            code, _ = await self._spawn(argv, self._timeout)
        except OSError:  # the helper vanished between available() and here
            return RawCapture()
        if code == TIMED_OUT:
            return RawCapture(exit_code=code, timed_out=True)
        return RawCapture(exit_code=code)


class UnsupportedScreenCapture:
    """Captures nothing, and says so (:class:`~ela.ports.ScreenCapturePort`).

    ELA runs on Linux in CI and will run on Windows nodes (§4), and neither has this. Written as
    a class rather than an ``if`` somewhere for the reason ADR 0028 gave ``UnsupportedProbe``:
    "ELA on Linux photographs nothing" becomes a thing with a name, a test and an error code the
    user can read, instead of a gap somebody discovers.
    """

    __slots__ = ()

    async def available(self) -> bool:
        """No."""
        return False

    async def capture(self, destination: str, display: int) -> RawCapture:
        """Nothing runs and nothing is written: an empty report, whatever was asked."""
        del destination, display
        return RawCapture()
