"""The speaking helper: Apple's own binary, run as a child (M11.1, ADR 0033).

``/usr/bin/say`` is present on every macOS, signed by Apple, needs no permission of any kind and
adds no dependency. Measured on this machine before the milestone was specified: 360-513 ms to
synthesise, and **flat in the length of the text** — 0.54 s, 1.65 s and 9.30 s of speech all came
from about 380 ms of work. The wait before the first syllable does not grow with the answer.

The argument that put it here rather than in a library is ADR 0029 §3's, and it is about rule 33
rather than about robustness: *what has to be able to die on its own must not carry the Core's
import graph with it*, and when the helper is not our code at all the property is true by
construction. There is no ``ctypes`` in this file and nothing in it can take ELA down.

**Rule 32 is why speaking lives in a package called perception.** That rule's content is "ELA
touches the operating system in one place" — the door, not the word — and ADR 0029 already put
the screen *capture* here for the same reason even though a capture is an action. This is the
second time the package's name is narrower than its contents (M11.1 dec. G). The third renames it.

**Rule 40 is why there is no path in this module.** ``say -o out.aiff`` renders to a file instead
of speaking, and a directory of everything ELA has ever said would be a record of everything ELA
knew, with no TTL, no ceiling and no store, because nobody designed one. The user's decision was
*mai su disco per la voce in uscita*; the rule is what keeps it true after everyone has forgotten
it was decided.

This module names no domain vocabulary (rule 34): it answers with a
:class:`~ela.domain.RawSpeech` — how the child ended and how long it lived — and never says what
that means. Whether "exit code 1" is a voice that is not installed or an audio device that went
away is not an adapter's to decide.
"""

from __future__ import annotations

import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Final

from ela.domain import RawSpeech
from ela.infrastructure.perception.darwin import TIMED_OUT, Spawn, spawn

__all__ = ["SAY", "SaySpeechCommand", "UnsupportedSpeech"]

SAY: Final = "/usr/bin/say"
"""Apple's, at an absolute path. Never resolved through ``PATH``: what speaks in ELA's voice must
not be decided by an environment variable (ADR 0029 §3, the same sentence about the screen)."""

END_OF_OPTIONS: Final = "--"
"""What separates the flags from the text, and it is not politeness.

``say`` reads its remaining arguments as the string to speak, and a sentence that begins with a
hyphen would otherwise be read as a flag — including, precisely, the flags rule 40 exists to keep
out. Without this, a text starting ``-o …`` is an argument-injection into the one command whose
arguments the rule cares about, coming from the very place the text comes from: a model.
"""


class SaySpeechCommand:
    """Says a sentence with ``say`` (:class:`~ela.ports.SpeechPort`).

    ``spawn`` arrives as a dependency — the same one the probe and the capture use, for the same
    reason: a timeout, a child killed by a signal and a non-zero exit are all things a test can
    produce with no audio hardware at all, which is what every CI runner has.

    Keeps the port's hardest promise — **it does not fail, it reports** — and its second one: a
    cancelled call kills the child, which :func:`~ela.infrastructure.perception.darwin.spawn` now
    does for every one of its callers.
    """

    __slots__ = ("_binary", "_spawn", "_timeout", "_voice")

    def __init__(
        self,
        *,
        timeout: timedelta,
        voice: str,
        runner: Spawn = spawn,
        binary: str = SAY,
    ) -> None:
        self._timeout = timeout.total_seconds()
        self._voice = voice
        self._spawn = runner
        self._binary = binary

    async def available(self) -> bool:
        """Whether the helper is on this machine. Reads nothing, asks for nothing, makes no sound.

        Async because the port is, not because this waits: it is two syscalls, and a port whose
        two members disagreed on colour would be awkward to implement twice.
        """
        return os.access(self._binary, os.X_OK) and Path(self._binary).is_file()

    async def speak(self, text: str) -> RawSpeech:
        """Say ``text``, and answer with how it ended and how long it took.

        ``-v`` names the voice, which comes from configuration and never from the caller. The
        text goes after :data:`END_OF_OPTIONS` so that a sentence cannot become a flag.
        """
        argv = [self._binary, "-v", self._voice, END_OF_OPTIONS, text]
        started = time.monotonic()
        try:
            code, _ = await self._spawn(argv, self._timeout)
        except OSError:  # the helper vanished between available() and here
            return RawSpeech()
        elapsed = round(time.monotonic() - started, 3)
        if code == TIMED_OUT:
            return RawSpeech(exit_code=code, timed_out=True, spoken_seconds=elapsed)
        return RawSpeech(exit_code=code, spoken_seconds=elapsed)


class UnsupportedSpeech:
    """Says nothing, and says so (:class:`~ela.ports.SpeechPort`).

    ELA runs on Linux in CI and will run on Windows nodes (§4), and neither has ``say``. Written
    as a class rather than an ``if`` somewhere for the reason ADR 0028 gave ``UnsupportedProbe``:
    "ELA on Linux says nothing" becomes a thing with a name, a test and an error code the user can
    read, instead of a gap somebody discovers.
    """

    __slots__ = ()

    async def available(self) -> bool:
        """No."""
        return False

    async def speak(self, text: str) -> RawSpeech:
        """Nothing runs and no sound is made: an empty report, whatever was asked."""
        del text
        return RawSpeech()
