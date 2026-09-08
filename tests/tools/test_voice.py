"""``voice.speak``: the first tool whose effect is outside the screen (M11.1, ADR 0033).

No runner has speakers, and none is needed: every path of this tool is something a
:class:`~ela.testing.fakes.FakeSpeech` produces — a helper that is not there, one that timed out,
one that exited badly, one that worked. What the tests watch for is not a sound but a **call**:
``said`` is empty when ELA must not speak, and holds exactly the sentence when it must.
"""

from __future__ import annotations

import pytest

from ela.domain import ExecutionStatus, PermissionOutcome, RawSpeech
from ela.permissions.capabilities import MAX_SPOKEN_CHARACTERS as CATALOGUE_MAX
from ela.ports import NotAllowedError
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeSpeech
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.settings import MAX_SPOKEN_CHARACTERS
from ela.tools.voice import (
    VOICE_DISABLED,
    VOICE_FAILED,
    VOICE_SPEAK,
    VOICE_TIMEOUT,
    VOICE_UNSUPPORTED,
    SpeakTool,
    digest_of,
)
from tests.tools.support import allowed

SENTENCE = "Ho spostato la riunione a giovedì."


DECISION = allowed(VOICE_SPEAK)


def tool(speech: FakeSpeech, *, enabled: bool = True) -> SpeakTool:
    return SpeakTool(speech, FakeClock(), FakeIdGenerator(), voice="Alice", enabled=enabled)


async def run(speech: FakeSpeech, arguments: dict[str, object], *, enabled: bool = True):  # type: ignore[no-untyped-def]
    return await tool(speech, enabled=enabled).execute(DECISION, arguments)


# --------------------------------------------------------------------------------------
# The two limits that are checked before anything happens
# --------------------------------------------------------------------------------------


async def test_the_sentence_is_said_and_the_result_carries_no_words() -> None:
    """The property the whole milestone rests on: what ELA said is a length and a digest.

    A result carries the words only if somebody puts them there, and this is where they would
    have gone — an ``ExecutionResult`` is persisted (M11.1 dec. 7).
    """
    speech = FakeSpeech(report=RawSpeech(exit_code=0, spoken_seconds=1.65))

    result = await run(speech, {"text": SENTENCE, "purpose": "confermare"})

    assert result.status is ExecutionStatus.SUCCEEDED
    assert speech.said == (SENTENCE,)
    assert result.output == {
        "characters": len(SENTENCE),
        "sha256": digest_of(SENTENCE),
        "voice": "Alice",
        "spoken_seconds": 1.65,
    }
    assert SENTENCE not in str(result.output)


@pytest.mark.parametrize(
    "arguments,reason",
    [
        ({"purpose": "x"}, "no text at all"),
        ({"text": "", "purpose": "x"}, "an empty sentence"),
        ({"text": 7, "purpose": "x"}, "a number"),
        ({"text": SENTENCE}, "no purpose"),
        ({"text": SENTENCE, "purpose": ""}, "an empty purpose"),
    ],
)
async def test_a_bad_argument_is_refused_and_nothing_is_said(
    arguments: dict[str, object], reason: str
) -> None:
    speech = FakeSpeech()

    result = await run(speech, arguments)

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID, reason
    assert speech.said == ()


async def test_a_sentence_past_the_ceiling_is_refused_before_the_helper() -> None:
    """The ceiling stands in for an interrupt that does not exist yet (M11.1 dec. E, F).

    Refused here **and** by the capability's schema: the tool never trusts its caller (§28), and
    a Guardian is not the only way this tool can be reached in a test.
    """
    speech = FakeSpeech()

    result = await run(speech, {"text": "a" * (MAX_SPOKEN_CHARACTERS + 1), "purpose": "x"})

    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert str(MAX_SPOKEN_CHARACTERS) in result.error.message
    assert speech.said == ()


async def test_exactly_the_ceiling_is_allowed() -> None:
    """The bound is closed on the legal side: a limit nobody can reach is a smaller limit."""
    speech = FakeSpeech()

    result = await run(speech, {"text": "a" * MAX_SPOKEN_CHARACTERS, "purpose": "x"})

    assert result.status is ExecutionStatus.SUCCEEDED
    assert speech.said == ("a" * MAX_SPOKEN_CHARACTERS,)


def test_the_catalogue_and_the_settings_agree_on_the_ceiling() -> None:
    """``ela.permissions`` may not import the settings module, so the number is written twice.

    Two spellings of "how long ELA may talk" is one of them being wrong later; this is what makes
    the divergence a failing test instead of a silent disagreement.
    """
    assert CATALOGUE_MAX == MAX_SPOKEN_CHARACTERS


# --------------------------------------------------------------------------------------
# The two refusals, and they are two facts
# --------------------------------------------------------------------------------------


async def test_a_voice_switched_off_says_so_and_never_calls_the_helper() -> None:
    speech = FakeSpeech()

    result = await run(speech, {"text": SENTENCE, "purpose": "x"}, enabled=False)

    assert result.error is not None
    assert result.error.code == VOICE_DISABLED
    assert not result.error.retryable
    assert speech.said == ()


async def test_a_machine_without_a_voice_says_something_different() -> None:
    """The distinction ADR 0030 §8 exists for: "you turned it off" and "this machine cannot" are
    different facts, and a single code for both is an answer nobody can act on."""
    speech = FakeSpeech(there=False)

    result = await run(speech, {"text": SENTENCE, "purpose": "x"})

    assert result.error is not None
    assert result.error.code == VOICE_UNSUPPORTED
    assert speech.said == ()


async def test_the_switch_is_answered_before_the_machine_is_asked() -> None:
    """Both true: the one the user can undo is the one worth hearing."""
    speech = FakeSpeech(there=False)

    result = await run(speech, {"text": SENTENCE, "purpose": "x"}, enabled=False)

    assert result.error is not None
    assert result.error.code == VOICE_DISABLED


# --------------------------------------------------------------------------------------
# The two ways the helper ends badly
# --------------------------------------------------------------------------------------


async def test_a_helper_that_overstayed_says_it_stopped_mid_sentence() -> None:
    """A timeout here does not mean "nothing happened": part of it was said out loud, and for
    whoever heard it those are different things."""
    speech = FakeSpeech(report=RawSpeech(exit_code=-1, timed_out=True, spoken_seconds=60.0))

    result = await run(speech, {"text": SENTENCE, "purpose": "x"})

    assert result.error is not None
    assert result.error.code == VOICE_TIMEOUT
    assert result.error.retryable
    assert "mid-sentence" in result.error.message


async def test_a_helper_that_exited_badly_reports_the_status_and_guesses_nothing() -> None:
    speech = FakeSpeech(report=RawSpeech(exit_code=3, spoken_seconds=0.1))

    result = await run(speech, {"text": SENTENCE, "purpose": "x"})

    assert result.error is not None
    assert result.error.code == VOICE_FAILED
    assert "3" in result.error.message


async def test_a_helper_that_never_ran_is_a_failure_and_not_a_success() -> None:
    """``RawSpeech()`` — every field at its default — is "the helper never ran". A tool that read
    that as success would report a sentence nobody said (§33)."""
    speech = FakeSpeech(report=RawSpeech())

    result = await run(speech, {"text": SENTENCE, "purpose": "x"})

    assert result.error is not None
    assert result.error.code == VOICE_FAILED


# --------------------------------------------------------------------------------------
# The contract every tool keeps
# --------------------------------------------------------------------------------------


async def test_a_decision_that_does_not_allow_stops_it_before_a_sound() -> None:
    speech = FakeSpeech()
    denied = allowed(VOICE_SPEAK, outcome=PermissionOutcome.DENIED)

    with pytest.raises(NotAllowedError):
        await tool(speech).execute(denied, {"text": SENTENCE, "purpose": "x"})

    assert speech.said == ()


def test_speaking_twice_is_not_the_same_as_speaking_once() -> None:
    """There is no artefact whose second write is harmless: the effect is the sound."""
    assert SpeakTool.idempotent is False
