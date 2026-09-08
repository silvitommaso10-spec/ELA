"""``SpeakVerifier`` (spec §63; M11.1 dec. C): what it proves, and what it says it does not.

The point of this file is not the passing cases. It is that a verifier of a **sound** — with no
artefact to re-read and no runner with ears — has to be honest about its reach rather than look
as strong as its siblings. The last test asserts that the honesty is written down where the next
person will read it, because a limit that lives only in a review is a limit nobody inherits.
"""

from __future__ import annotations

import pytest

from ela.domain import ErrorMetadata, ExecutionResult, ExecutionStatus
from ela.ports import VERIFICATION_UNKNOWN_CONDITION
from ela.tools import (
    COMMON_FAILURE_CODES,
    VERIFICATION_ARGUMENTS_INVALID,
    VOICE_SPEAK,
    SpeakVerifier,
    digest_of,
)
from ela.tools.verifiers import (
    MIN_SECONDS_PER_CHARACTER,
    SPEECH_TEXT_MATCHES,
    SPEECH_TEXT_MISMATCH,
    SPEECH_TOO_FAST,
    SPEECH_TOOK_REAL_TIME,
)
from tests.tools.test_verifiers import succeeded

SENTENCE = "Ho spostato la riunione a giovedì."
BOTH = (SPEECH_TOOK_REAL_TIME, SPEECH_TEXT_MATCHES)
TIMING = (SPEECH_TOOK_REAL_TIME,)
DIGEST = (SPEECH_TEXT_MATCHES,)
ARGUMENTS = {"text": SENTENCE, "purpose": "confermare"}


def spoken(**update: object) -> ExecutionResult:
    """A result that says the sentence was said, at a plausible speed."""
    output = {
        "characters": len(SENTENCE),
        "sha256": digest_of(SENTENCE),
        "voice": "Alice",
        "spoken_seconds": 1.65,
        **update,
    }
    return succeeded(VOICE_SPEAK, output=output)


@pytest.fixture
def verifier() -> SpeakVerifier:
    return SpeakVerifier()


def test_it_declares_itself(verifier: SpeakVerifier) -> None:
    assert verifier.capability_id == VOICE_SPEAK
    assert verifier.conditions == {SPEECH_TOOK_REAL_TIME, SPEECH_TEXT_MATCHES}
    assert verifier.failure_codes == (
        COMMON_FAILURE_CODES | {SPEECH_TOO_FAST, SPEECH_TEXT_MISMATCH}
    )


async def test_a_sentence_that_was_said_passes_both_conditions(verifier: SpeakVerifier) -> None:
    assert await verifier.verify(BOTH, ARGUMENTS, spoken()) == ()


# --------------------------------------------------------------------------------------
# The condition that catches the failure this verifier exists for
# --------------------------------------------------------------------------------------


async def test_a_helper_that_returned_too_fast_did_not_speak(verifier: SpeakVerifier) -> None:
    """An exit status of zero that means "nothing came out". Speech is played in real time, so
    there is no faster machine that speaks faster: returning early is returning without playing.
    """
    failures = await verifier.verify(BOTH, ARGUMENTS, spoken(spoken_seconds=0.0))

    assert [f.code for f in failures] == [SPEECH_TOO_FAST]
    assert failures[0].retryable
    assert failures[0].details["at_least"] == round(len(SENTENCE) * MIN_SECONDS_PER_CHARACTER, 3)


async def test_the_floor_is_ten_times_below_the_slowest_measured_speech() -> None:
    """Measured 2026-09-08: 600 characters took 31,5 s at the default rate and 37,8 s at the
    slowest — 52 and 63 ms per character. The floor is not a performance budget; it is the line
    under which the only explanation is silence, so it sits an order of magnitude below."""
    assert MIN_SECONDS_PER_CHARACTER * 10 < 0.052


async def test_a_duration_at_exactly_the_floor_passes(verifier: SpeakVerifier) -> None:
    """The bound is closed on the passing side: a verifier that failed at the floor would fail a
    sentence that was spoken, which is worse than one that misses a sentence that was not."""
    exactly = len(SENTENCE) * MIN_SECONDS_PER_CHARACTER

    assert (
        await verifier.verify((SPEECH_TOOK_REAL_TIME,), ARGUMENTS, spoken(spoken_seconds=exactly))
        == ()
    )


async def test_a_duration_that_is_not_a_number_is_refused(verifier: SpeakVerifier) -> None:
    failures = await verifier.verify(
        (SPEECH_TOOK_REAL_TIME,), ARGUMENTS, spoken(spoken_seconds="1.6")
    )

    assert [f.code for f in failures] == [VERIFICATION_ARGUMENTS_INVALID]


async def test_a_boolean_is_not_a_duration(verifier: SpeakVerifier) -> None:
    """``True`` is an ``int`` in Python, and a verifier that accepted it would be reading a flag
    as a number of seconds."""
    failures = await verifier.verify(
        (SPEECH_TOOK_REAL_TIME,), ARGUMENTS, spoken(spoken_seconds=True)
    )

    assert [f.code for f in failures] == [VERIFICATION_ARGUMENTS_INVALID]


# --------------------------------------------------------------------------------------
# The condition that proves ELA said what it was asked to say
# --------------------------------------------------------------------------------------


async def test_a_different_sentence_fails_and_neither_one_is_printed(
    verifier: SpeakVerifier,
) -> None:
    """A message carrying what ELA said would put it in the audit trail, which is exactly what
    the tool went out of its way not to do (§57)."""
    failures = await verifier.verify(
        (SPEECH_TEXT_MATCHES,), ARGUMENTS, spoken(sha256=digest_of("altro"))
    )

    assert [f.code for f in failures] == [SPEECH_TEXT_MISMATCH]
    assert SENTENCE not in failures[0].message
    assert "altro" not in failures[0].message


async def test_a_missing_digest_fails_rather_than_passing(verifier: SpeakVerifier) -> None:
    """A result without the digest must not read as agreement (§33)."""
    output = dict(spoken().output)
    del output["sha256"]

    failures = await verifier.verify(DIGEST, ARGUMENTS, succeeded(VOICE_SPEAK, output=output))

    assert [f.code for f in failures] == [SPEECH_TEXT_MISMATCH]


@pytest.mark.parametrize("arguments", [{}, {"text": ""}, {"text": 7}])
async def test_a_bad_argument_is_refused_by_either_condition(
    verifier: SpeakVerifier, arguments: dict[str, object]
) -> None:
    failures = await verifier.verify(BOTH, arguments, spoken())

    assert {f.code for f in failures} == {VERIFICATION_ARGUMENTS_INVALID}


async def test_a_condition_it_does_not_know_is_refused(verifier: SpeakVerifier) -> None:
    failures = await verifier.verify(("speech.was_heard",), ARGUMENTS, spoken())

    assert [f.code for f in failures] == [VERIFICATION_UNKNOWN_CONDITION]


async def test_a_result_that_did_not_succeed_is_never_verified(verifier: SpeakVerifier) -> None:
    failed = spoken().model_copy(
        update={
            "status": ExecutionStatus.FAILED,
            "error": ErrorMetadata(code="voice.failed", message="", tool_name=None),
        }
    )

    assert [f.code for f in await verifier.verify(BOTH, ARGUMENTS, failed)] != []


# --------------------------------------------------------------------------------------
# The declaration itself
# --------------------------------------------------------------------------------------


def test_it_says_in_its_own_words_that_it_does_not_prove_anybody_heard() -> None:
    """M11.1 dec. C, asserted rather than trusted.

    The reach of this verifier is smaller than the reach of its siblings, and the difference is
    not something a reader can infer from the conditions: ``speech.took_real_time`` sounds like
    proof of speaking. It is proof that time passed. That has to be written where somebody
    changing this file will read it, and a docstring is only a promise until a test holds it.
    """
    documented = SpeakVerifier.__doc__ or ""

    assert "does not prove that anybody heard" in documented
    assert "no runner has ears" in documented
