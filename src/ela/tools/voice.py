"""``voice.speak`` (spec §8, §9, §29 MEDIUM; M11.1, ADR 0033): ELA says something out loud.

The first tool whose effect is **outside the screen**. Every tool before it left something a
person could go back and look at — a row, a file that expires, an HTTP response. A spoken
sentence is heard, once, by whoever is in the room, and then it is gone.

Three things happen, in this order, and the order is the design:

1. **The arguments.** ``text`` is a non-empty string no longer than
   :data:`~ela.tools.settings.MAX_SPOKEN_CHARACTERS`; ``purpose`` is a non-empty string. The
   Guardian validated the schema already (ADR 0011 §3); a tool checks again because it never
   trusts its caller (§28).
2. **May it, and can it?** Two questions with two codes, because they are two facts:
   ``ELA_VOICE_ENABLED`` is the user's switch, and
   :meth:`~ela.ports.SpeechPort.available` is whether this machine has a voice at all. Answering
   both with one code would be the ambiguity ADR 0030 §8 says to split before the answer leaves.

   And then **nothing else**, which is the difference from :mod:`ela.tools.screen` worth naming:
   there is no permission to preflight. Speaking asks macOS for nothing — no TCC service covers
   the speakers — so the careful dance of ADR 0029 §7, where a permission is re-read at the
   instant of the action because attempting from a denied state records a permanent denial, has
   no counterpart here. **The whole protection is the capability and the Guardian**, which is
   also why the capability requires an authorization (M11.1 dec. A).
3. **The sentence.** What comes back is an exit status and a duration, never the words: the
   helper writes nothing (architecture rule 40) and this tool keeps nothing.

The output carries what was said only as a **length and a digest**. The words themselves would
otherwise land in an ``ExecutionResult`` that is persisted, which is the accumulation §57 forbids
reached by another route — the same reason ``text`` is not in the capability's
``prompt_arguments`` (M11.1 dec. B). A digest is enough for the verifier to prove ELA said what it
was asked to say, and it is not enough to reconstruct it.

**A cancelled call stops the sound.** :meth:`_run` awaits the helper for the whole sentence, so
cancelling the caller has to kill the child rather than orphan it — otherwise ELA keeps talking
after being told to stop, which is the worse half of what dec. F postponed to the barge-in. That
belongs to :func:`~ela.infrastructure.machine.darwin.spawn`, and is tested there.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping
from ela.ports import Clock, IdGenerator, SpeechPort
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.settings import MAX_SPOKEN_CHARACTERS

__all__ = [
    "VOICE_DISABLED",
    "VOICE_FAILED",
    "VOICE_SPEAK",
    "VOICE_TIMEOUT",
    "VOICE_TOOL_NAME",
    "VOICE_UNSUPPORTED",
    "SpeakTool",
    "digest_of",
    "sentence_of",
]

VOICE_SPEAK: Final = CapabilityId("voice.speak")
VOICE_TOOL_NAME: Final = "voice-speak"

VOICE_UNSUPPORTED: Final = "voice.unsupported"
"""This operating system has no speech helper ELA knows about. Not retryable: nothing about a
later attempt is different."""
VOICE_DISABLED: Final = "voice.disabled"
"""``ELA_VOICE_ENABLED`` is off: the user asked ELA not to speak.

**A code of its own, and not :data:`VOICE_UNSUPPORTED`.** "This machine cannot speak" and "you
told me not to" are different facts, and one of them has something the user can do about it. A
single code for both is the ambiguity ADR 0030 §8 says to split *before* the answer is handed on
— and it is the same shape as ``SensorCause``, where ``OFF`` alone was not allowed to exist
(ADR 0028 §3). Not retryable: nothing changes until a human changes it."""
VOICE_TIMEOUT: Final = "voice.timeout"
"""The helper outstayed its welcome and was killed. Retryable — and note what it does **not**
mean: the sentence was very probably spoken, in part, out loud. A timeout here is not "nothing
happened", it is "ELA stopped mid-word", and the two are different things for whoever heard it."""
VOICE_FAILED: Final = "voice.failed"
"""The helper ran and ended badly. The exit status is in the message; what it *means* is not
ELA's to guess — a voice that is not installed, an audio device that went away, and a system that
refused all land here, and none of them is a claim about the machine."""


def sentence_of(arguments: JsonMapping) -> str | Outcome:
    """The sentence to say, or the refusal that says why there is not one.

    Shared by both voices (M11.3), and shared rather than copied because the two tools must agree
    on the ceiling to the character: ``voice.speak`` and ``voice.speak_online`` are two
    permissions over the *same* limit, and a second spelling of it is the first place they would
    drift apart.

    The Guardian validated the schema already (ADR 0011 §3); a tool checks again because it never
    trusts its caller (§28).
    """
    text = arguments.get("text")
    purpose = arguments.get("purpose")
    if not isinstance(text, str) or not text:
        return Outcome({}, ARGUMENTS_INVALID, "text must be a non-empty string")
    if len(text) > MAX_SPOKEN_CHARACTERS:
        return Outcome(
            {},
            ARGUMENTS_INVALID,
            f"text must be at most {MAX_SPOKEN_CHARACTERS} characters, not {len(text)}",
        )
    if not isinstance(purpose, str) or not purpose:
        return Outcome({}, ARGUMENTS_INVALID, "purpose must be a non-empty string")
    return text


def digest_of(text: str) -> str:
    """The SHA-256 of ``text`` as UTF-8, hex.

    One function because two callers must agree on it byte for byte: the tool writes it into the
    result and the verifier recomputes it from the argument. Two spellings of "the digest of what
    was said" is one of them being wrong later.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SpeakTool(Tool):
    """Says one sentence out loud (§29 MEDIUM; ADR 0033).

    Holds a :class:`~ela.ports.SpeechPort` and nothing else: no store, because there is nothing
    to store; no probe, because there is no permission to read.
    """

    error_codes: ClassVar[frozenset[str]] = frozenset(
        {ARGUMENTS_INVALID, VOICE_DISABLED, VOICE_UNSUPPORTED, VOICE_TIMEOUT, VOICE_FAILED}
    )

    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"characters", "sha256", "voice", "spoken_seconds"}
    )
    """What was said, and never a word of it. ``spoken_seconds`` is how long the helper was alive
    — a measurement, never a claim that anybody heard it (M11.1 dec. C)."""

    idempotent: ClassVar[bool] = False
    """Saying a thing twice is saying it twice. There is no artefact whose second write would be
    harmless: the effect is the sound, and the sound already happened. So this runs under the
    STARTED protocol of ADR 0021 §1 and is never run twice for one step — which is what stops a
    crash between the sentence and its record from making ELA repeat itself."""

    def __init__(
        self,
        speech: SpeechPort,
        clock: Clock,
        ids: IdGenerator,
        *,
        voice: str,
        enabled: bool,
        name: str = VOICE_TOOL_NAME,
    ) -> None:
        super().__init__(VOICE_SPEAK, clock, ids, name=name)
        self._speech = speech
        self._voice = voice
        self._enabled = enabled

    async def _run(self, arguments: JsonMapping) -> Outcome:
        asked = sentence_of(arguments)
        if isinstance(asked, Outcome):
            return asked
        text = asked
        # The user's switch first, the machine's answer second: both are refusals, and the one
        # the user can undo is the one worth hearing when both are true.
        if not self._enabled:
            return Outcome(
                {},
                VOICE_DISABLED,
                "ELA's voice is switched off; set ELA_VOICE_ENABLED=true to turn it on",
            )
        if not await self._speech.available():
            return Outcome(
                {},
                VOICE_UNSUPPORTED,
                "this operating system has no voice ELA can use",
            )
        return await self._say(text)

    async def _say(self, text: str) -> Outcome:
        """Run the helper for the whole sentence, and report how it ended."""
        report = await self._speech.speak(text)
        if report.timed_out:
            return Outcome(
                {},
                VOICE_TIMEOUT,
                "the voice helper did not finish in time and was stopped mid-sentence",
                retryable=True,
            )
        if report.exit_code != 0:
            return Outcome(
                {},
                VOICE_FAILED,
                f"the voice helper exited with {report.exit_code}",
                retryable=True,
            )
        return Outcome(
            {
                "characters": len(text),
                "sha256": digest_of(text),
                "voice": self._voice,
                "spoken_seconds": report.spoken_seconds,
            }
        )
