"""The voice in ``/diagnostics``, and the two things M11.1 promises leave no trace (ADR 0033).

``/diagnostics`` says *what ELA is connected to*, not *what ELA is doing* (ADR 0028 §8), so
whether ELA has a voice here belongs beside ``providers`` and ``tools``. There is deliberately
**no route that says whether ELA is speaking**: a sentence lasts as long as a sentence, and a
status true for thirty seconds is not one anybody can act on.
"""

from __future__ import annotations

import dataclasses
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela
from ela.domain import RawSpeech
from ela.infrastructure.perception import AUDITION_PHRASES, Audition
from ela.ports import SPEECH_NO_KEY, SPEECH_RATE_LIMITED
from ela.tools.settings import MAX_SPOKEN_CHARACTERS
from tests.api.support import AUTHORIZED, BASE


class Recording:
    """An audition's dependency, doubled: says nothing, records everything it was asked for.

    What it proves is the half a route cannot: **which phrases were sent, in which voice, on
    which model** — and that the phrases are the two of §9 and nothing a caller chose.
    """

    def __init__(self, said: RawSpeech) -> None:
        self._said = said
        self.spoken: list[tuple[str, str, str]] = []
        self.played: list[str] = []

    async def speak(self, phrase: str, voice_id: str, model: str) -> RawSpeech:
        self.spoken.append((phrase, voice_id, model))
        return self._said

    async def play(self, voice_id: str) -> RawSpeech:
        self.played.append(voice_id)
        return self._said


AppWith = Callable[[Ela, Recording], "AsyncIterator[tuple[AsyncClient, Recording]]"]


@pytest.fixture
def app_with() -> AppWith:
    """An application whose audition is doubled, everything else being the real thing."""

    @asynccontextmanager
    async def build(ela: Ela, recording: Recording) -> AsyncIterator[tuple[AsyncClient, Recording]]:
        doubled = dataclasses.replace(
            ela, audition=Audition(speak=recording.speak, play=recording.play)
        )
        app: FastAPI = create_app(doubled)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
        ) as client:
            yield client, recording

    return build  # type: ignore[return-value]


async def test_diagnostics_says_whether_ela_has_a_voice_here(client: AsyncClient, ela: Ela) -> None:
    body = (await client.get("/diagnostics")).json()
    online = ela.settings.elevenlabs

    assert body["voice"] == {
        "enabled": ela.settings.voice.voice_enabled,
        "available": await ela.speech.available(),
        "voice": ela.settings.voice.voice_name,
        "max_characters": MAX_SPOKEN_CHARACTERS,
        "timeout_seconds": ela.settings.voice.voice_timeout_seconds,
        "online": {
            "configured": online.configured,
            "available": await ela.speech_online.available(),
            "voice_id": online.elevenlabs_voice_id,
            "model": online.elevenlabs_model,
            "text_retained_by_provider": True,
            "timeout_seconds": online.elevenlabs_timeout_seconds,
        },
    }


async def test_diagnostics_says_that_the_provider_keeps_what_ela_says(
    client: AsyncClient,
) -> None:
    """The user's addition to the scope, and their reason: *l'ha scelta consapevolmente e la
    scelta deve restare visibile* (ADR 0034 §11).

    Here rather than in a warning before every sentence: a warning that repeats is one people
    learn to skip, and this is a fact about the configuration — so it lives where somebody looks
    at which voice ELA is using.
    """
    online = (await client.get("/diagnostics")).json()["voice"]["online"]

    assert online["text_retained_by_provider"] is True


async def test_the_switch_and_the_machine_are_two_fields(client: AsyncClient) -> None:
    """ "You turned it off" and "this machine has no voice" must be separately readable, or a
    reader cannot tell which one to do something about (ADR 0030 §8)."""
    voice = (await client.get("/diagnostics")).json()["voice"]

    assert "enabled" in voice
    assert "available" in voice


async def test_there_is_still_no_route_that_says_whether_ela_is_speaking(
    client: AsyncClient,
) -> None:
    """The decision of ADR 0033 §10 survives the route M11.3 added, and this is where it is kept.

    M11.1 tested this as ``GET /voice`` answering 404. That route exists now — it says which
    voices ELA has and what the provider keeps — so the assertion moved to the thing that was
    actually decided: **nothing anywhere reports that ELA is speaking right now.** A sentence
    lasts as long as a sentence, and a status true for thirty seconds is not one anybody can act
    on. An absence nobody tests is an absence somebody adds back without noticing.
    """
    body = (await client.get("/voice")).json()
    diagnostics = (await client.get("/diagnostics")).json()["voice"]

    forbidden = {"speaking", "busy", "now", "current_sentence", "playing"}
    assert not forbidden & set(body["voice"])
    assert not forbidden & set(body["voice"]["online"])
    assert not forbidden & set(diagnostics)


def test_the_voice_writes_nothing_anywhere_it_could(ela: Ela) -> None:
    """Criterion 3 of M11.1, and the reason rule 40 exists: there is no store to design because
    there is nothing to keep.

    Asserted against the two directories a voice could plausibly have leaked into — the capture
    store, which is the only place ELA keeps content, and the workspace — plus the absence of a
    setting that would name a third.
    """
    assert not hasattr(ela.settings.voice, "voice_dir")
    assert set(type(ela.settings.voice).model_fields) == {
        "voice_enabled",
        "voice_name",
        "voice_timeout_seconds",
    }


# --------------------------------------------------------------------------------------
# Choosing a voice: three routes, and none of them can be told what to say (ADR 0034 §9)
# --------------------------------------------------------------------------------------


async def test_the_route_lists_the_voices_and_what_an_audition_would_say(
    client: AsyncClient,
) -> None:
    body = (await client.get("/voice")).json()

    assert [one["name"] for one in body["candidates"]][0].startswith("Daniela")
    assert body["phrases"] == [
        "No, questa non è una buona idea.",
        "Stai cercando di risolvere il problema sbagliato.",
    ]


async def test_no_route_of_the_voice_has_a_field_for_words(app: FastAPI) -> None:
    """**The schema is the first place the decision is written** (ADR 0034 §9).

    Rule 43 says it about the code; this says it about the wire, and it is the stronger of the
    two here: a caller cannot ask this API to say something, because there is nowhere to put it.
    """
    schema = app.openapi()["components"]["schemas"]

    for name in ("AuditionIn", "PreviewIn"):
        fields = set(schema[name]["properties"])
        assert not fields & {"text", "phrase", "message", "say", "words"}, name


async def test_an_audition_with_no_key_says_so_and_sends_nothing(client: AsyncClient) -> None:
    """The suite has no key — and this is the answer a person gets before they set one."""
    body = (await client.post("/voice/audition", json={"voice_id": "abc"})).json()

    assert [one["error"] for one in body["heard"]] == [SPEECH_NO_KEY]
    assert body["credits"] is None


async def test_a_preview_with_no_key_says_so(client: AsyncClient) -> None:
    body = (await client.post("/voice/preview", json={"voice_id": "abc"})).json()

    assert body["heard"][0]["error"] == SPEECH_NO_KEY
    assert body["credits"] is None


async def test_an_audition_needs_a_voice_to_audition(client: AsyncClient) -> None:
    assert (await client.post("/voice/audition", json={"voice_id": ""})).status_code == 422
    assert (await client.post("/voice/audition", json={})).status_code == 422


async def test_an_audition_says_both_sentences_and_reports_what_it_cost(
    ela: Ela, app_with: AppWith
) -> None:
    """The happy path, with the provider replaced: two phrases, one voice, one model."""
    said = RawSpeech(exit_code=0, spoken_seconds=2.2, synthesis_seconds=0.3, credits=16)
    async with app_with(ela, Recording(said)) as (client, recording):
        body = (await client.post("/voice/audition", json={"voice_id": "abc"})).json()

    assert [one["phrase"] for one in body["heard"]] == list(AUDITION_PHRASES)
    assert body["credits"] == 32
    assert recording.spoken == [(phrase, "abc", "eleven_flash_v2_5") for phrase in AUDITION_PHRASES]


async def test_both_models_means_the_configured_one_first(ela: Ela, app_with: AppWith) -> None:
    """ADR 0034 §9: the question is not "which of these two", it is "is the other one worth the
    silence" — so the one in use is heard first."""
    said = RawSpeech(exit_code=0, spoken_seconds=2.2)
    async with app_with(ela, Recording(said)) as (client, recording):
        await client.post("/voice/audition", json={"voice_id": "abc", "both_models": True})

    assert [model for _, _, model in recording.spoken] == [
        "eleven_flash_v2_5",
        "eleven_flash_v2_5",
        "eleven_multilingual_v2",
        "eleven_multilingual_v2",
    ]


async def test_an_audition_stops_at_the_first_failure(ela: Ela, app_with: AppWith) -> None:
    """Paying to be told the same thing four times is not an audition."""
    async with app_with(ela, Recording(RawSpeech(error=SPEECH_RATE_LIMITED, retryable=True))) as (
        client,
        recording,
    ):
        body = (await client.post("/voice/audition", json={"voice_id": "abc"})).json()

    assert len(body["heard"]) == 1
    assert len(recording.spoken) == 1
