"""The text-recognition helper: macOS Vision, run as a child of ours (M10.3, ADR 0030 §6).

M10.2's child was Apple's — ``screencapture(1)`` — and that made architecture rule 33 true by
construction. There is no such binary for recognition: nothing shipped with macOS does OCR from a
command line, checked one by one. So the child is ours again
(:mod:`~ela.infrastructure.perception.vision`), rule 33 goes back to being verified rather than
free, and it now verifies a **derived** subject rather than a named file, so the next child is
covered without anybody adding it to a list.

The two things this adapter does not do are the point of it:

* **It does not decide.** It carries lines, confidences, an exit status and the languages the
  child could not use, and never says what any of that means (rule 34). In particular it does not
  decide what "no lines" means — that answer needs the languages, and working it out is
  :mod:`ela.tools.screen_text`'s job, inside the coverage gate.
* **It does not read a permission.** There is none to read: Vision recognises text with no TCC
  grant of any kind — measured from a process that was its own responsible process — so there is
  nothing here to preflight and nothing that can record a denial. The permission was spent by the
  capability that took the capture.

It keeps the port's hardest promise: **it does not fail, it reports.** A timeout, a child killed
by a signal, output that is not JSON, a key this version does not know — all of them come back as
a :class:`~ela.domain.RawRecognition` that says how it ended.

The text does travel through this process, which the pixels never did. That is argued in
:class:`~ela.domain.RawRecognition` and it costs a discipline: what comes back goes into the
caller's file and nowhere else — never into a log line, never into an exception message.
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from typing import Final

from ela.domain import RawRecognition
from ela.infrastructure.perception.darwin import TIMED_OUT, Spawn, spawn

__all__ = ["VISION_MODULE", "UnsupportedTextRecognition", "VisionTextRecognition"]

VISION_MODULE: Final = "ela.infrastructure.perception.vision"


class VisionTextRecognition:
    """Reads text with the Vision framework (:class:`~ela.ports.TextRecognitionPort`).

    ``spawn`` arrives as a dependency, the same one the probe and the capture take, and for the
    same reason: a timeout, a child killed by a signal, a child that printed nonsense are all
    things a test can produce with no framework, no image and no permission.
    """

    __slots__ = ("_spawn", "_timeout")

    def __init__(self, *, timeout: timedelta, runner: Spawn = spawn) -> None:
        self._timeout = timeout.total_seconds()
        self._spawn = runner

    async def available(self) -> bool:
        """Whether this machine has the framework at all.

        ``True`` on Darwin, where the composition root chooses this class; the platform question
        is settled there rather than asked twice. What makes this a member instead of a failure of
        :meth:`recognise` is the same argument as for the capture: "ELA on Linux reads nothing" is
        worth being an answer with a name.
        """
        return True

    async def recognise(
        self, source: str, *, languages: tuple[str, ...], region: tuple[float, ...] | None
    ) -> RawRecognition:
        """Read the text in ``source``, and answer with how it ended."""
        argv = [sys.executable, "-m", VISION_MODULE, source, ",".join(languages)]
        if region is not None:
            argv.extend(str(value) for value in region)
        try:
            code, output = await self._spawn(argv, self._timeout)
        except OSError:  # the interpreter or the module vanished between available() and here
            return RawRecognition()
        if code == TIMED_OUT:
            return RawRecognition(exit_code=code, killed=True)
        if code != 0:
            return RawRecognition(exit_code=code)
        try:
            answer = json.loads(output)
        except ValueError:
            # A truncated answer lands here rather than parsing into a shorter one: JSON Lines and
            # a JSON object are both self-delimiting, which is the property that let the payload
            # cross a pipe at all (ADR 0030 §7).
            return RawRecognition(exit_code=code)
        try:
            return RawRecognition(exit_code=code, **answer)
        except (TypeError, ValueError):
            # A pydantic ValidationError is a ValueError, an unknown key is a TypeError: either
            # way the two sides no longer agree on their JSON object, and that is not a reading.
            return RawRecognition(exit_code=code)


class UnsupportedTextRecognition:
    """Reads nothing, and says so (:class:`~ela.ports.TextRecognitionPort`).

    Beside :class:`VisionTextRecognition` rather than in ``unsupported.py``, following where
    :class:`~ela.infrastructure.perception.screencapture.UnsupportedScreenCapture` lives: a port
    and the answer "not on this operating system" are easier to keep in step when they are read
    together.
    """

    __slots__ = ()

    async def available(self) -> bool:
        """No."""
        return False

    async def recognise(
        self, source: str, *, languages: tuple[str, ...], region: tuple[float, ...] | None
    ) -> RawRecognition:
        """Nothing runs and nothing is read: an empty report, whatever was asked."""
        del source, languages, region
        return RawRecognition()
