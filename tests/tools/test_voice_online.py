"""``voice.speak_online``: ELA speaks in the voice of §9, and the words leave (ADR 0034).

Two families of test, and only one of them is about the sound. The other is about what a result
carries — a receipt and never a word — because that is the half a reader of the audit trail, or
of ``ela task results``, will ever see.
"""

from __future__ import annotations

import pytest

from ela.domain import PermissionOutcome, RawSpeech
from ela.ports import (
    SPEECH_ERROR_CODES,
    SPEECH_NO_KEY,
    SPEECH_NO_PLAYER,
    SPEECH_NO_VOICE,
    SPEECH_PLAYBACK_TIMEOUT,
    SPEECH_RATE_LIMITED,
    NotAllowedError,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeSpeech
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.settings import MAX_SPOKEN_CHARACTERS
from ela.tools.voice import VOICE_DISABLED, digest_of
from ela.tools.voice_online import VOICE_SPEAK_ONLINE, SpeakOnlineTool
from tests.tools.support import allowed

SENTENCE = "No, questa non è una buona idea."
VOICE_ID = "VZOd9FMXDnXRZpGn0thg"
MODEL = "eleven_flash_v2_5"
DECISION = allowed(VOICE_SPEAK_ONLINE)
ARGUMENTS = {"text": SENTENCE, "purpose": "dire l'esito del task"}

SPOKEN = RawSpeech(
    exit_code=0,
    spoken_seconds=2.4,
    synthesis_seconds=0.31,
    credits=16,
    history_item_id="bZ7h4eUtFFJyXt7MbkwH",
    audio_bytes=38_400,
)


def tool(
    speech: FakeSpeech, *, enabled: bool = True, voice_id: str | None = VOICE_ID
) -> SpeakOnlineTool:
    return SpeakOnlineTool(
        speech,
        FakeClock(),
        FakeIdGenerator(),
        voice_id=voice_id,
        model=MODEL,
        enabled=enabled,
    )


async def test_the_sentence_is_said_and_the_result_carries_its_receipt() -> None:
    speech = FakeSpeech(report=SPOKEN)

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert speech.said == (SENTENCE,)
    assert result.output == {
        "characters": len(SENTENCE),
        "sha256": digest_of(SENTENCE),
        "voice": VOICE_ID,
        "model": MODEL,
        "credits": 16,
        "history_item_id": "bZ7h4eUtFFJyXt7MbkwH",
        "synthesis_seconds": 0.31,
        "spoken_seconds": 2.4,
        "audio_bytes": 38_400,
    }


async def test_the_result_never_carries_the_words() -> None:
    """§57 twice over: an ``ExecutionResult`` is persisted, and the audit trail is forever."""
    result = await tool(FakeSpeech(report=SPOKEN)).execute(DECISION, ARGUMENTS)

    assert SENTENCE not in str(result.output)
    assert "buona idea" not in str(result.output)
    assert result.output["sha256"] == digest_of(SENTENCE)


async def test_the_receipt_is_what_makes_the_retention_checkable() -> None:
    """ADR 0034 §10: a cost accepted that nobody can find again is a cost that was described.

    The provider keeps the text; this id is where that copy is. Without it the retention would be
    a sentence in a document, and with it it is a row somebody can go and look at.
    """
    result = await tool(FakeSpeech(report=SPOKEN)).execute(DECISION, ARGUMENTS)

    assert result.output["history_item_id"] == "bZ7h4eUtFFJyXt7MbkwH"
    assert result.output["credits"] == 16, "what the provider stated, not what ELA estimated"


async def test_a_decision_for_the_local_voice_does_not_authorise_this_one() -> None:
    """**The test of decision A** (ADR 0034 §3): the two permissions do not substitute.

    A grant that says "you may speak" must not become "you may send my words to a supplier", and
    the mechanism is not documentation: the tool refuses a decision about another capability.
    """
    from ela.tools.voice import VOICE_SPEAK

    speech = FakeSpeech(report=SPOKEN)

    with pytest.raises(NotAllowedError):
        await tool(speech).execute(allowed(VOICE_SPEAK), ARGUMENTS)

    assert speech.said == (), "nothing was said, and nothing was sent"


async def test_a_denied_decision_sends_nothing() -> None:
    speech = FakeSpeech(report=SPOKEN)
    denied = allowed(VOICE_SPEAK_ONLINE, outcome=PermissionOutcome.DENIED)

    with pytest.raises(NotAllowedError):
        await tool(speech).execute(denied, ARGUMENTS)

    assert speech.said == ()


async def test_the_switch_covers_this_voice_too() -> None:
    """``ELA_VOICE_ENABLED`` is "ELA may make a sound", and a sound synthesised elsewhere is
    still a sound in the room."""
    speech = FakeSpeech(report=SPOKEN)

    result = await tool(speech, enabled=False).execute(DECISION, ARGUMENTS)

    assert result.error is not None and result.error.code == VOICE_DISABLED
    assert speech.said == (), "switched off means nothing is sent, not only nothing is heard"


async def test_a_machine_with_no_player_says_which_thing_it_lacks() -> None:
    speech = FakeSpeech(report=SPOKEN, there=False)

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert result.error is not None and result.error.code == SPEECH_NO_PLAYER
    assert speech.said == ()


@pytest.mark.parametrize("code", [SPEECH_NO_KEY, SPEECH_NO_VOICE])
async def test_the_two_absences_reach_the_caller_apart(code: str) -> None:
    """ADR 0034 §5, and the user's own words: two facts with two different things to do."""
    speech = FakeSpeech(report=RawSpeech(error=code))

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert result.error is not None
    assert result.error.code == code
    assert not result.error.retryable


async def test_a_message_says_what_to_do_when_there_is_something_to_do() -> None:
    speech = FakeSpeech(report=RawSpeech(error=SPEECH_NO_VOICE))

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert result.error is not None
    assert "ela voice audition" in result.error.message


async def test_a_retryable_failure_stays_retryable() -> None:
    """The nature of the failure travels with it (ADR 0020 §7): the provider said "later"."""
    speech = FakeSpeech(report=RawSpeech(error=SPEECH_RATE_LIMITED, retryable=True))

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert result.error is not None
    assert result.error.code == SPEECH_RATE_LIMITED
    assert result.error.retryable


async def test_being_cut_off_mid_word_is_not_nothing_happened() -> None:
    """ADR 0033 §9's distinction, on the new path: for whoever heard it, these are two things."""
    speech = FakeSpeech(
        report=RawSpeech(error=SPEECH_PLAYBACK_TIMEOUT, retryable=True, timed_out=True)
    )

    result = await tool(speech).execute(DECISION, ARGUMENTS)

    assert result.error is not None
    assert "cut off mid-word" in result.error.message


async def test_the_ceiling_is_the_same_one_the_local_voice_has() -> None:
    """Two permissions over one limit: a second spelling of it is where they would drift."""
    speech = FakeSpeech(report=SPOKEN)

    result = await tool(speech).execute(
        DECISION, {"text": "a" * (MAX_SPOKEN_CHARACTERS + 1), "purpose": "troppo"}
    )

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert speech.said == (), "refused before a byte was sent, and before a credit was spent"


@pytest.mark.parametrize(
    "arguments",
    [
        {"purpose": "no text"},
        {"text": "", "purpose": "empty"},
        {"text": 42, "purpose": "not a string"},
        {"text": SENTENCE},
        {"text": SENTENCE, "purpose": ""},
    ],
)
async def test_bad_arguments_are_refused_before_anything_leaves(
    arguments: dict[str, object],
) -> None:
    speech = FakeSpeech(report=SPOKEN)

    result = await tool(speech).execute(DECISION, arguments)

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert speech.said == ()


async def test_the_tool_is_not_idempotent_and_says_so() -> None:
    """Saying a thing twice is saying it twice — and paying twice, and leaving a second copy."""
    assert SpeakOnlineTool.idempotent is False


def test_every_error_code_is_declared() -> None:
    assert SpeakOnlineTool.error_codes >= SPEECH_ERROR_CODES
    assert VOICE_DISABLED in SpeakOnlineTool.error_codes
    assert ARGUMENTS_INVALID in SpeakOnlineTool.error_codes


async def test_the_output_keys_are_the_ones_declared() -> None:
    result = await tool(FakeSpeech(report=SPOKEN)).execute(DECISION, ARGUMENTS)

    assert set(result.output) == SpeakOnlineTool.output_keys
