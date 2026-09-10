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
from collections.abc import Awaitable, Callable
from datetime import timedelta
from pathlib import Path
from typing import Final

from ela.domain import RawSpeech
from ela.infrastructure.machine.darwin import (
    TIMED_OUT,
    Spawn,
    SpawnWithAudio,
    spawn,
    spawn_with_audio,
)
from ela.ports import SPEECH_NO_PLAYER, SPEECH_PLAYBACK_FAILED, SPEECH_PLAYBACK_TIMEOUT
from ela.providers.elevenlabs import Synthesis

__all__ = [
    "AFPLAY",
    "SAY",
    "OnlineSpeechCommand",
    "SaySpeechCommand",
    "Synthesise",
    "Unconfigured",
    "UnsupportedSpeech",
]

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
    cancelled call kills the child, which :func:`~ela.infrastructure.machine.darwin.spawn` now
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


AFPLAY: Final = "/usr/bin/afplay"
"""Apple's player, at an absolute path — the same sentence as :data:`SAY` and the same reason
(ADR 0029 §3): what plays in ELA's voice must not be decided by ``PATH``.

It is here because it is the **only** thing on macOS that can play what a provider returns. A pipe
and a FIFO both fail with ``AudioFileOpen -40`` (measured), and writing a player of our own would
mean CoreAudio inside ELA's own process, which is exactly what the child-process discipline of
ADR 0028 §2 exists to avoid.
"""

Synthesise = Callable[[str], Awaitable[Synthesis]]
"""Text in, audio out. A ``Callable`` and not a port, exactly like ``Spawn``: what the Core
depends on is :class:`~ela.ports.SpeechPort`, and the fact that one implementation of it reaches
a provider is composition (ADR 0034 §6 — the port count does not move)."""

Unconfigured = Callable[[], str | None]
"""Which of the two things the online voice needs is missing, if either is.

A callable and not a boolean read once: the answer belongs to the moment of the call, and it is
**two codes and not one** because "you have not given me a key" and "you have not chosen a voice"
are two facts with two different things for a person to do (ADR 0034 §5).
"""


class OnlineSpeechCommand:
    """The voice of §9: a provider says the words, this machine plays them (ADR 0034).

    Implements :class:`~ela.ports.SpeechPort` whole — synthesis *and* playback behind one call —
    which is why M11.3 introduces no port: the port M11.1 designed already described this.

    Three properties are worth reading the code for.

    **The two absences answer before the network.** Nothing is sent when there is no key or no
    voice, and the two are reported apart.

    **The playback timeout is derived, not configured.** ``Synthesis.playback_timeout`` is the
    audio's own length plus room to start a process, so no invented number stands between a long
    sentence and being cut off — and there is no knob to get wrong.

    **What is timed is the sound.** ``spoken_seconds`` covers the player and nothing else; the
    round-trip is reported apart. One number carrying both would let a sentence that never played
    look like one that did, to the one verifier that has no other witness (ADR 0033 §5).
    """

    __slots__ = ("_binary", "_directory", "_spawn", "_synthesise", "_unconfigured")

    def __init__(
        self,
        *,
        synthesise: Synthesise,
        unconfigured: Unconfigured,
        directory: Path,
        runner: SpawnWithAudio = spawn_with_audio,
        binary: str = AFPLAY,
    ) -> None:
        self._synthesise = synthesise
        self._unconfigured = unconfigured
        self._directory = directory
        self._spawn = runner
        self._binary = binary

    async def available(self) -> bool:
        """Whether this machine can play audio at all — asks nothing, sends nothing, is silent.

        Deliberately **not** "is the online voice usable": whether there is a key and a voice is
        configuration, and one boolean for both questions is the ambiguity ADR 0030 §8 exists to
        split. This one is about the machine, like its counterpart in :class:`SaySpeechCommand`.
        """
        return os.access(self._binary, os.X_OK) and Path(self._binary).is_file()

    async def speak(self, text: str) -> RawSpeech:
        """Say ``text`` in ELA's voice, and report how it went. Never raises (the port's rule).

        **The order of the two refusals is a decision, not an accident** (M11.3, la correzione
        della CI): the key comes before the player, because the key is *configuration* — something
        the person reading the answer can go and fix — and the player is a property of the machine
        they are on. It is ADR 0033 §9's own reason, applied to a pair it did not have yet: *the
        refusal the user can undo is the one worth hearing when both are true.*

        And it is decided **here**, in the one object that knows both facts, so that nobody
        upstream has to ask them in the right order: the tool passes what this reports straight
        through.
        """
        missing = self._unconfigured()
        if missing is not None:
            return RawSpeech(error=missing)
        if not await self.available():
            return RawSpeech(error=SPEECH_NO_PLAYER)
        said = await self._synthesise(text)
        if said.failure is not None:
            return RawSpeech(
                error=said.failure.code,
                retryable=said.failure.retryable,
                synthesis_seconds=said.seconds,
            )
        return await self.play(said)

    async def play(self, said: Synthesis) -> RawSpeech:
        """Hand the audio to the player, and time the sound and nothing else.

        Public because the audition plays audio it asked for **with a voice of its own choosing**
        (ADR 0034 §9), which :meth:`speak` cannot express and must not: the voice ELA speaks with
        is configuration, and a caller that could pick one could change who appears to be talking.
        """
        started = time.monotonic()
        try:
            code, _ = await self._spawn(
                [self._binary],
                said.audio,
                said.playback_timeout,
                directory=str(self._directory),
            )
        except OSError:  # the player vanished between available() and here
            return RawSpeech(error=SPEECH_PLAYBACK_FAILED, synthesis_seconds=said.seconds)
        elapsed = round(time.monotonic() - started, 3)
        timed_out = code == TIMED_OUT
        error = None
        if timed_out:
            error = SPEECH_PLAYBACK_TIMEOUT
        elif code != 0:
            error = SPEECH_PLAYBACK_FAILED
        return RawSpeech(
            exit_code=code,
            timed_out=timed_out,
            retryable=error is not None,
            spoken_seconds=elapsed,
            synthesis_seconds=said.seconds,
            credits=said.credits,
            history_item_id=said.history_item_id,
            audio_bytes=len(said.audio),
            error=error,
        )
