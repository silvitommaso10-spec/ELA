"""The adapter that sends what ELA says out of this machine (ADR 0034).

The error cases are not invented: every status and body here was **measured** against the real
API on 2026-09-08, and the most important of them is the one that would be wrong if it had been
guessed — a refused credential arrives as a **400**.
"""

from __future__ import annotations

import httpx
import pytest

from ela.ports import (
    SPEECH_AUTHENTICATION_ERROR,
    SPEECH_ERROR_CODES,
    SPEECH_MALFORMED_RESPONSE,
    SPEECH_NO_KEY,
    SPEECH_NO_VOICE,
    SPEECH_QUOTA_EXCEEDED,
    SPEECH_REJECTED,
    SPEECH_SERVER_ERROR,
    SPEECH_TIMEOUT,
    SPEECH_TOO_MUCH_AUDIO,
    SPEECH_UNKNOWN_MODEL,
    SPEECH_UNKNOWN_VOICE,
    SPEECH_UNREACHABLE,
)
from ela.providers.elevenlabs import AUDIO_FORMAT, DEFAULT_MODEL, ELEVENLABS_API, MAX_AUDIO_BYTES
from ela.providers.elevenlabs.provider import BACKOFF_CAP_SECONDS, PREVIEW_HOSTS, ElevenLabsVoice
from tests.providers.elevenlabs.support import (
    AUDIO,
    RECEIPT,
    SECRET,
    VOICE,
    Answers,
    Sleeper,
    refused,
    settings,
    spoken,
    voice,
)

SENTENCE = "No, questa non è una buona idea."


# --------------------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------------------


async def test_the_request_goes_to_the_declared_endpoint_with_the_key_in_a_header() -> None:
    answers = Answers(spoken())

    await voice(answers).synthesise(SENTENCE)

    sent = answers.last
    assert str(sent.url).startswith(f"{ELEVENLABS_API}/v1/text-to-speech/{VOICE}")
    assert sent.headers["xi-api-key"] == SECRET
    assert sent.url.params["output_format"] == AUDIO_FORMAT


async def test_the_body_carries_the_sentence_and_the_model_and_nothing_else() -> None:
    """ADR 0034 §2: the text, the model, the format. No purpose, no task, no user."""
    answers = Answers(spoken())

    await voice(answers).synthesise(SENTENCE)

    assert answers.body_of(answers.last) == {"text": SENTENCE, "model_id": DEFAULT_MODEL}


async def test_the_audition_may_choose_the_voice_and_the_model() -> None:
    """The one caller that legitimately chooses, because choosing is what an audition is."""
    answers = Answers(spoken())

    await voice(answers).synthesise(
        SENTENCE, voice_id="kavPiGHUq62Aokyp5Tui", model="eleven_multilingual_v2"
    )

    assert "kavPiGHUq62Aokyp5Tui" in str(answers.last.url)
    assert answers.body_of(answers.last)["model_id"] == "eleven_multilingual_v2"


# --------------------------------------------------------------------------------------
# The answer
# --------------------------------------------------------------------------------------


async def test_a_sentence_comes_back_with_its_audio_its_cost_and_its_receipt() -> None:
    answers = Answers(spoken())

    said = await voice(answers).synthesise(SENTENCE)

    assert said.failure is None
    assert said.audio == AUDIO
    assert said.credits == 26
    assert said.history_item_id == RECEIPT
    assert said.seconds == 1.24


async def test_what_the_provider_does_not_state_is_not_guessed() -> None:
    """ADR 0034 §10: credits are a fact the provider asserts, never an estimate ELA computes."""
    answers = Answers(spoken(credits=None, receipt=None))

    said = await voice(answers).synthesise(SENTENCE)

    assert (said.credits, said.history_item_id) == (None, None)


async def test_a_cost_that_is_not_a_number_is_no_cost() -> None:
    answers = Answers(httpx.Response(200, content=AUDIO, headers={"character-cost": "many"}))

    assert (await voice(answers).synthesise(SENTENCE)).credits is None


async def test_an_answer_with_no_audio_is_unusable_and_says_so() -> None:
    answers = Answers(httpx.Response(200, content=b""))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None
    assert failure.code == SPEECH_MALFORMED_RESPONSE
    assert not failure.retryable


async def test_reading_stops_at_the_ceiling_instead_of_holding_the_whole_body() -> None:
    """§33: a body that does not end is not a sentence, and ELA does not read it to find out."""
    answers = Answers(httpx.Response(200, content=b"x" * (MAX_AUDIO_BYTES + 1)))

    said = await voice(answers).synthesise(SENTENCE)

    assert said.failure is not None
    assert said.failure.code == SPEECH_TOO_MUCH_AUDIO
    assert said.audio == b""


# --------------------------------------------------------------------------------------
# The failures, as they really arrive
# --------------------------------------------------------------------------------------


async def test_a_refused_key_arrives_as_a_400_and_is_still_an_authentication_error() -> None:
    """The measurement that decides the shape of this module (ADR 0034 §1.3).

    Read on the status code alone, this is "your request was malformed", and whoever is
    investigating goes looking at the payload instead of at the credential.
    """
    answers = Answers(
        refused(400, type="authentication_error", code="invalid_api_key", status="invalid_api_key")
    )

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None
    assert failure.code == SPEECH_AUTHENTICATION_ERROR
    assert not failure.retryable
    assert failure.status_code == 400


@pytest.mark.parametrize("status", [400, 404])
async def test_the_same_missing_voice_is_one_code_under_two_status_codes(status: int) -> None:
    """Measured: 404 on the speech endpoint, 400 on the voice endpoint, one fact."""
    answers = Answers(refused(status, type="not_found", status="voice_not_found"))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None
    assert failure.code == SPEECH_UNKNOWN_VOICE


async def test_an_unknown_model_has_its_own_code() -> None:
    answers = Answers(refused(400, status="model_not_found"))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None and failure.code == SPEECH_UNKNOWN_MODEL


async def test_running_out_of_credits_is_not_a_server_problem() -> None:
    answers = Answers(refused(401, status="quota_exceeded"))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None
    assert failure.code == SPEECH_QUOTA_EXCEEDED
    assert not failure.retryable, "what fixes this is a human, not another attempt"


async def test_a_status_the_provider_does_not_name_falls_back_on_the_code() -> None:
    answers = Answers(refused(409, type="conflict"))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None and failure.code == SPEECH_REJECTED


@pytest.mark.parametrize(
    "body", [b"<html>gateway</html>", b'"just a string"', b'{"detail": "a plain sentence"}']
)
async def test_a_body_that_names_nothing_leaves_the_status_code_in_charge(body: bytes) -> None:
    answers = Answers(httpx.Response(503, content=body))

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None and failure.code == SPEECH_SERVER_ERROR


async def test_a_timeout_and_an_unreachable_provider_are_two_answers() -> None:
    """ADR 0030 §8: "I waited and nothing came" and "there is no network" read differently at
    three in the morning, and only one of them is about ElevenLabs."""
    timed_out = Answers(httpx.ReadTimeout("too slow"))
    unreachable = Answers(httpx.ConnectError("no route"))

    first = (await voice(timed_out, elevenlabs_max_retries=0).synthesise(SENTENCE)).failure
    second = (await voice(unreachable, elevenlabs_max_retries=0).synthesise(SENTENCE)).failure

    assert first is not None and first.code == SPEECH_TIMEOUT
    assert second is not None and second.code == SPEECH_UNREACHABLE


async def test_no_failure_ever_carries_the_sentence() -> None:
    """§57 and ADR 0020 §10: a code, a type, a status — never a word of what ELA was going to say.

    The provider's own ``message`` quotes the request back, which is exactly why it is dropped.
    """
    answers = Answers(
        httpx.Response(
            400,
            json={"detail": {"type": "invalid", "message": f"cannot say: {SENTENCE}"}},
        )
    )

    failure = (await voice(answers).synthesise(SENTENCE)).failure

    assert failure is not None
    assert SENTENCE not in failure.message
    assert "buona idea" not in failure.message


def test_every_code_this_adapter_can_produce_is_in_the_ports_vocabulary() -> None:
    """A code outside the closed set is exactly what a closed set forbids (ADR 0020 §7)."""
    from ela.providers.elevenlabs import errors

    produced = {errors.STATUS_CODES[name] for name in errors.STATUS_CODES}
    assert produced <= SPEECH_ERROR_CODES


# --------------------------------------------------------------------------------------
# Retrying (ADR 0020 §8, with M11.3's own count)
# --------------------------------------------------------------------------------------


async def test_a_rate_limit_is_tried_again_and_can_succeed() -> None:
    answers = Answers(refused(429), spoken())
    sleeper = Sleeper()

    said = await voice(answers, sleeper=sleeper).synthesise(SENTENCE)

    assert said.failure is None
    assert said.audio == AUDIO
    assert sleeper.waited == [0.5]


async def test_a_server_error_that_never_recovers_reports_the_last_one() -> None:
    answers = Answers(refused(500), refused(500))
    sleeper = Sleeper()

    said = await voice(answers, sleeper=sleeper).synthesise(SENTENCE)

    assert said.failure is not None
    assert said.failure.code == SPEECH_SERVER_ERROR
    assert said.attempts == 2
    assert len(answers.given) == 2


async def test_a_refusal_is_never_tried_again() -> None:
    """Retrying a rejected request rejects it again, and sends the text a second time (§10)."""
    answers = Answers(refused(400, type="authentication_error"))
    sleeper = Sleeper()

    await voice(answers, sleeper=sleeper).synthesise(SENTENCE)

    assert len(answers.given) == 1
    assert sleeper.waited == []


async def test_retries_can_be_switched_off() -> None:
    answers = Answers(refused(429), spoken())

    said = await voice(answers, elevenlabs_max_retries=0).synthesise(SENTENCE)

    assert said.failure is not None
    assert len(answers.given) == 1


async def test_the_provider_may_name_its_own_wait_and_it_is_still_capped() -> None:
    slow = httpx.Response(429, headers={"retry-after": "600"})
    answers = Answers(slow, spoken())
    sleeper = Sleeper()

    await voice(answers, sleeper=sleeper).synthesise(SENTENCE)

    assert sleeper.waited == [BACKOFF_CAP_SECONDS]


async def test_the_backoff_grows_and_stops_growing() -> None:
    answers = Answers(*[refused(500)] * 6)
    sleeper = Sleeper()

    await voice(answers, sleeper=sleeper, elevenlabs_max_retries=5).synthesise(SENTENCE)

    assert sleeper.waited == [0.5, 1.0, 2.0, 4.0, 8.0]


# --------------------------------------------------------------------------------------
# Being configured, or not
# --------------------------------------------------------------------------------------


def test_two_absences_are_two_facts() -> None:
    """Neither is a failure of the network, and neither is the other (ADR 0034 §5)."""
    no_key = ElevenLabsVoice(settings(elevenlabs_api_key=None))
    no_voice = ElevenLabsVoice(settings(elevenlabs_voice_id=None))
    both = ElevenLabsVoice(settings())

    assert not no_key.configured and no_key.voice_id is not None
    assert not no_voice.configured and no_voice.voice_id is None
    assert both.configured


# --------------------------------------------------------------------------------------
# The preview: nothing of the user's is sent, and it is best effort
# --------------------------------------------------------------------------------------


def _voice_document(url: str) -> httpx.Response:
    return httpx.Response(200, json={"name": "Daniela", "preview_url": url})


async def test_a_preview_is_downloaded_and_the_key_never_reaches_the_sample() -> None:
    sample = "https://storage.googleapis.com/eleven-public-prod/sample.mp3"
    answers = Answers(_voice_document(sample), httpx.Response(200, content=AUDIO))

    said = await voice(answers).preview(VOICE)

    assert said.failure is None and said.audio == AUDIO
    assert "xi-api-key" in answers.given[0].headers
    assert "xi-api-key" not in answers.given[1].headers, "a CDN gets no credential of ELA's"


async def test_a_preview_costs_nothing_and_says_nothing() -> None:
    """The whole reason the first step exists: twenty voices, zero characters sent."""
    sample = "https://api.us.elevenlabs.io/v1/voices/x/previews/audio?payload=e30"
    answers = Answers(_voice_document(sample), httpx.Response(200, content=AUDIO))

    await voice(answers).preview(VOICE)

    assert all(request.method == "GET" for request in answers.given)
    assert all(not request.content for request in answers.given)


async def test_a_voice_whose_metadata_is_refused_is_a_named_outcome() -> None:
    """Measured, and the reason the preview is best effort: the same library voice answered 400
    and then 200 minutes apart on 2026-09-08."""
    answers = Answers(refused(400, type="not_found", status="voice_not_found"))

    failure = (await voice(answers).preview(VOICE)).failure

    assert failure is not None and failure.code == SPEECH_UNKNOWN_VOICE


@pytest.mark.parametrize(
    "document",
    [
        httpx.Response(200, json={"name": "no sample here"}),
        httpx.Response(200, json={"preview_url": ""}),
        httpx.Response(200, json={"preview_url": 42}),
        httpx.Response(200, json=["not", "a", "document"]),
        httpx.Response(200, content=b"not json at all"),
    ],
)
async def test_a_document_with_no_playable_sample_is_not_followed(
    document: httpx.Response,
) -> None:
    answers = Answers(document)

    failure = (await voice(answers).preview(VOICE)).failure

    assert failure is not None and failure.code == SPEECH_MALFORMED_RESPONSE
    assert len(answers.given) == 1, "nothing was fetched"


@pytest.mark.parametrize(
    "sample",
    [
        "https://somewhere-else.example.com/sample.mp3",
        "http://storage.googleapis.com/sample.mp3",
    ],
)
async def test_a_sample_somewhere_ela_did_not_declare_is_not_fetched(sample: str) -> None:
    """One JSON field must not be enough to point ELA's requests anywhere (ADR 0034 §9)."""
    answers = Answers(_voice_document(sample))

    failure = (await voice(answers).preview(VOICE)).failure

    assert failure is not None and failure.code == SPEECH_MALFORMED_RESPONSE
    assert len(answers.given) == 1


def test_the_hosts_ela_will_follow_are_two_and_are_written_down() -> None:
    assert {"api.us.elevenlabs.io", "storage.googleapis.com"} == PREVIEW_HOSTS


def test_a_wait_the_provider_writes_as_a_date_leaves_the_backoff_in_charge() -> None:
    """ADR 0020 §8: a hint ELA cannot read is not an error, it is one fewer hint."""
    from ela.providers.elevenlabs.errors import retry_after_of

    assert retry_after_of("Wed, 09 Sep 2026 07:00:00 GMT") is None
    assert retry_after_of(None) is None
    assert retry_after_of("2.5") == 2.5


def test_the_provider_says_which_of_the_two_things_it_is_missing() -> None:
    """One method, three answers, and the middle one is the whole point (ADR 0034 §5).

    "You have not given me a key" and "you have not chosen a voice" are two facts with two
    different things for a person to do — and the second one has an answer that is an audition
    away, which is not something to say to somebody whose key was refused.
    """
    assert ElevenLabsVoice(settings(elevenlabs_api_key=None)).unconfigured() == SPEECH_NO_KEY
    assert ElevenLabsVoice(settings(elevenlabs_voice_id=None)).unconfigured() == SPEECH_NO_VOICE
    assert ElevenLabsVoice(settings()).unconfigured() is None
