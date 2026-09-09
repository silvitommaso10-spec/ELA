"""``voice.speak_online`` (§9, §29 MEDIUM, §57; M11.3, ADR 0034): ELA parla, e le parole escono.

The second tool of the voice, and the difference from :mod:`ela.tools.voice` is not the sound —
it is that **this one sends the sentence to somebody else's computer**, which keeps it. Everything
else follows from that:

* it is a **capability of its own**, so an authorization for speaking locally cannot be spent
  here (ADR 0034 §3): the Guardian consumes grants by ``capability_id``, and there is no
  path-shaped scope to protect this one with;
* the result carries a **receipt** — ``history_item_id``, the address of the copy the provider
  kept, and ``credits``, the cost the provider itself states. A retention the user accepted and
  nobody can then find again is a retention that was described rather than shown (ADR 0034 §10);
* and it carries **no word of the text**, exactly like its local sister: a length, a digest, and
  facts about the call. The words are in the request body and in nothing that is persisted.

What this tool does not do is choose between the two voices. Nothing falls back: if the online
voice cannot speak, it says so with a name, and whether ELA then says the same sentence in the
local voice is a decision for whoever wrote the plan — never a substitution made quietly under a
permission that was given for something else (ADR 0034 §5).
"""

from __future__ import annotations

from typing import ClassVar, Final

from ela.domain import CapabilityId, JsonMapping, RawSpeech
from ela.ports import (
    SPEECH_ERROR_CODES,
    SPEECH_NO_KEY,
    SPEECH_NO_PLAYER,
    SPEECH_NO_VOICE,
    SPEECH_PLAYBACK_TIMEOUT,
    Clock,
    IdGenerator,
    SpeechPort,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool
from ela.tools.voice import VOICE_DISABLED, digest_of, sentence_of

__all__ = ["VOICE_ONLINE_TOOL_NAME", "VOICE_SPEAK_ONLINE", "SpeakOnlineTool"]

VOICE_SPEAK_ONLINE: Final = CapabilityId("voice.speak_online")
VOICE_ONLINE_TOOL_NAME: Final = "voice-speak-online"

WHAT_TO_DO: Final = {
    SPEECH_NO_KEY: "no speech provider key is configured; set ELA_ELEVENLABS_API_KEY",
    SPEECH_NO_VOICE: "no voice has been chosen; run `ela voice audition` and set "
    "ELA_ELEVENLABS_VOICE_ID",
    SPEECH_PLAYBACK_TIMEOUT: "the player was stopped and the sentence was cut off mid-word",
    SPEECH_NO_PLAYER: "this operating system has no audio player ELA can use",
}
"""The failures a person can do something about, in the words of what to do.

Everything else keeps the code's own meaning, which the port already documents: a message that
restated it would be a second place for the same sentence to go stale. Only three are here
because only three have an action attached — and the last one is here because "it timed out" and
"you heard half a sentence" are not the same news (ADR 0033 §9).
"""


class SpeakOnlineTool(Tool):
    """Says one sentence in ELA's own voice, through a provider (§29 MEDIUM; ADR 0034).

    Holds a :class:`~ela.ports.SpeechPort` and nothing else — no client, no key, no store. That
    the port reaches a network is the composition root's knowledge and not this module's, which
    is also what keeps architecture rule 35 true here: a tool holding the user's words may not
    name an HTTP client or a router.
    """

    error_codes: ClassVar[frozenset[str]] = (
        frozenset({ARGUMENTS_INVALID, VOICE_DISABLED}) | SPEECH_ERROR_CODES
    )
    """The user's switch, a bad argument, and the port's whole closed vocabulary — passed through
    rather than translated: a caller that had to learn a second set of names for the same
    failures would be a caller that knows about the provider (ADR 0020 §7).

    ``voice.unsupported`` of M11.1 is **not** among them, and the difference is real: that code
    says this machine has no *voice*, and what is missing here is a *player* for audio somebody
    else synthesised (:data:`~ela.ports.SPEECH_NO_PLAYER`)."""

    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "characters",
            "sha256",
            "voice",
            "model",
            "credits",
            "history_item_id",
            "synthesis_seconds",
            "spoken_seconds",
            "audio_bytes",
        }
    )
    """What was said, and never a word of it. ``spoken_seconds`` is the **playback** and nothing
    else — the verifier weighs it against the length of the words, and a number that carried the
    round-trip would make a sentence that never played look like one that did."""

    idempotent: ClassVar[bool] = False
    """Saying a thing twice is saying it twice — and paying twice, and leaving a second copy with
    the provider. Runs under the STARTED protocol of ADR 0021 §1, like its local sister."""

    def __init__(
        self,
        speech: SpeechPort,
        clock: Clock,
        ids: IdGenerator,
        *,
        voice_id: str | None,
        model: str,
        enabled: bool,
        name: str = VOICE_ONLINE_TOOL_NAME,
    ) -> None:
        super().__init__(VOICE_SPEAK_ONLINE, clock, ids, name=name)
        self._speech = speech
        self._voice_id = voice_id
        self._model = model
        self._enabled = enabled

    async def _run(self, arguments: JsonMapping) -> Outcome:
        asked = sentence_of(arguments)
        if isinstance(asked, Outcome):
            return asked
        # The user's switch covers **both** voices: ELA_VOICE_ENABLED is "ELA may make a sound",
        # and a sound made with somebody else's synthesis is still a sound in the room.
        if not self._enabled:
            return Outcome(
                {},
                VOICE_DISABLED,
                "ELA's voice is switched off; set ELA_VOICE_ENABLED=true to turn it on",
            )
        # **No availability check here, and that is the fix of 2026-09-09.** Asking the machine
        # first would put "this Mac cannot play audio" in front of "you have not given me a key",
        # which is the wrong way round: the key is configuration and the player is the machine.
        # The port answers both, in the decided order, because it is the one object that knows
        # them both (:class:`~ela.infrastructure.perception.speech.OnlineSpeechCommand`).
        return self._reported(asked, await self._speech.speak(asked))

    def _reported(self, text: str, said: RawSpeech) -> Outcome:
        """Turn the report into a result, keeping the receipt and dropping the words."""
        if said.error is not None:
            return Outcome({}, said.error, WHAT_TO_DO.get(said.error, said.error), said.retryable)
        return Outcome(
            {
                "characters": len(text),
                "sha256": digest_of(text),
                "voice": self._voice_id,
                "model": self._model,
                "credits": said.credits,
                "history_item_id": said.history_item_id,
                "synthesis_seconds": said.synthesis_seconds,
                "spoken_seconds": said.spoken_seconds,
                "audio_bytes": said.audio_bytes,
            }
        )
