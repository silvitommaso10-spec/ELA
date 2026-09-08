"""The one module of ELA that sends what ELA says out of this machine (M11.3, ADR 0034).

It does exactly two things over the network, both towards :data:`ELEVENLABS_API` and nowhere else
(architecture rule 42):

* :meth:`ElevenLabsVoice.synthesise` — a sentence in, audio out, with what the provider says the
  request cost and **where the copy it kept can be found** (ADR 0034 §10).
* :meth:`ElevenLabsVoice.preview` — the sample the provider already holds for a voice. Nothing of
  the user's is sent: it is a download, and it exists so that hearing twenty voices costs nothing.

Three promises, and they are the port's own, kept here because this is where they can be broken.

**It does not fail, it reports.** Every outcome is a :class:`Synthesis`; nothing raises for a
provider failure, a timeout or a body that is not audio.

**Nothing of the user's leaves in an error.** The text is in the request body and in no other
place: not a message, not a log, not a field of a failure (ADR 0020 §10). What survives a failure
is a status code, the provider's own error type and a request id.

**The answer is read with a ceiling on it.** The audio is accumulated while it streams and reading
stops at :data:`MAX_AUDIO_BYTES` — a body that does not end is not a sentence, and ELA does not
hold it in memory to find that out (§33).

The HTTP client is built per call. It is the shape the reconnaissance measured — DNS, TCP and TLS
were inside every number in ADR 0034 §1.1 — and it means this adapter owns no resource that the
composition root would have to remember to close.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

import httpx

from ela.ports import SPEECH_NO_KEY, SPEECH_NO_VOICE, SPEECH_TOO_MUCH_AUDIO
from ela.providers.elevenlabs.errors import (
    Failure,
    classify_answer,
    retry_after_of,
    transport_failure,
    unusable_answer,
)
from ela.providers.elevenlabs.settings import (
    AUDIO_BYTES_PER_SECOND,
    AUDIO_FORMAT,
    ELEVENLABS_API,
    MAX_AUDIO_BYTES,
    PLAYBACK_SLACK_SECONDS,
    ElevenLabsSettings,
)

__all__ = [
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_CAP_SECONDS",
    "PROVIDER_NAME",
    "ElevenLabsVoice",
    "Synthesis",
]

PROVIDER_NAME: Final = "elevenlabs"

BACKOFF_BASE_SECONDS: Final = 0.5
BACKOFF_CAP_SECONDS: Final = 8.0
"""ADR 0020 §8's policy, unchanged: exponential, deterministic, capped, no jitter. Jitter spreads
a crowd of clients; ELA is one client, and a delay a test can predict is a delay a test can
prove."""

PREVIEW_HOSTS: Final = frozenset({"api.us.elevenlabs.io", "storage.googleapis.com"})
"""The only hosts ELA will follow a **provider-supplied** link to (ADR 0034 §9).

A sample lives on a CDN, so its address does not come from this module: it comes back inside a
voice document, which is a value chosen by somebody else. Following it wherever it points would
make one JSON field enough to send ELA's requests anywhere — so the hosts are declared here, the
scheme must be HTTPS, and anything else is a sample that will not be played.

Nothing of ELA's is ever sent to them: the key is not attached, and the request is a download.
"""

COST_HEADER: Final = "character-cost"
RECEIPT_HEADER: Final = "history-item-id"
REQUEST_HEADER: Final = "request-id"

Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]


@dataclass(frozen=True, slots=True)
class Synthesis:
    """What one attempt at a sentence produced — audio, or a named failure, never an exception."""

    audio: bytes = b""
    seconds: float = 0.0
    """How long the audio took to arrive. Never mixed with how long it takes to *play*: the
    verifier compares playback against the length of the words, and a duration carrying a
    round-trip would make a sentence that never played look like one that did (ADR 0034 §6)."""
    credits: int | None = None
    """What the provider says it cost, from its own header — a fact it asserts, not an estimate
    ELA computes from a table that would go stale (ADR 0034 §10)."""
    history_item_id: str | None = None
    """The receipt: where the copy the provider kept can be found."""
    failure: Failure | None = None
    attempts: int = 0

    @property
    def expected_seconds(self) -> float:
        """How long this audio will play, from its size alone (ADR 0034 §1.4).

        True because ELA asks for exactly one format: at ``mp3_44100_128`` the stream is 16 000
        bytes a second, and the prediction was checked against ``afinfo`` on two real sentences
        with an error below 0,1%. It lives here, next to the format that makes it true, so that
        the player needs no constant of the provider's to know how long to wait.
        """
        return len(self.audio) / AUDIO_BYTES_PER_SECOND

    @property
    def playback_timeout(self) -> float:
        """How long the player may take: the sentence, plus room to start a process."""
        return self.expected_seconds + PLAYBACK_SLACK_SECONDS


class ElevenLabsVoice:
    """The voice of §9, behind an HTTP request (ADR 0034).

    Holds no client and no socket: it holds settings, and builds a client for the length of one
    request. ``sleep`` and ``monotonic`` arrive as dependencies for the reason ADR 0020 gave —
    a test proves the backoff without waiting, and a duration is measured on a clock that cannot
    step backwards (ADR 0003 §4).

    ``transport`` exists so the tests can answer without a socket: the suite makes the real HTTP
    transports raise (``tests/conftest.py``), so an adapter that could not be given a double would
    be an adapter with no tests at all.
    """

    __slots__ = ("_monotonic", "_settings", "_sleep", "_transport")

    def __init__(
        self,
        settings: ElevenLabsSettings,
        *,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        self._monotonic = monotonic
        self._transport = transport

    @property
    def api_key_missing(self) -> bool:
        """Whether there is no key at all — the first of the two absences (ADR 0034 §5)."""
        return self._settings.elevenlabs_api_key is None

    def unconfigured(self) -> str | None:
        """Which of the two things the online voice needs is missing, if either is.

        A method and not a value read at start-up: settings are read once, but the answer belongs
        to the moment of the call. **Two codes and not one** — "you have not given me a key" and
        "you have not chosen a voice" are two facts with two different things for a person to do,
        which is ADR 0030 §8 applied to an error instead of a reading (ADR 0034 §5).
        """
        if self.api_key_missing:
            return SPEECH_NO_KEY
        if self.voice_id is None:
            return SPEECH_NO_VOICE
        return None

    @property
    def configured(self) -> bool:
        """Whether there is both a key and a voice. Which of the two is missing is the caller's
        to report, because the two absences are two facts (ADR 0034 §5)."""
        return self._settings.elevenlabs_api_key is not None and self.voice_id is not None

    @property
    def voice_id(self) -> str | None:
        return self._settings.elevenlabs_voice_id

    @property
    def model(self) -> str:
        return self._settings.elevenlabs_model

    async def synthesise(
        self, text: str, *, voice_id: str | None = None, model: str | None = None
    ) -> Synthesis:
        """Ask for ``text`` in a voice, and answer with the audio or with a named failure.

        ``voice_id`` and ``model`` are here for the audition — the one caller that legitimately
        chooses them, because choosing is the whole point of an audition (ADR 0034 §9). Everything
        else leaves them out and gets the configured ones: which voice ELA speaks with is
        configuration of this machine, never an argument of a caller.
        """
        chosen = voice_id or self.voice_id
        assert chosen is not None, "callers check `configured` first"
        body = {"text": text, "model_id": model or self.model}
        url = f"{ELEVENLABS_API}/v1/text-to-speech/{chosen}"
        return await self._attempt(url, body)

    async def preview(self, voice_id: str) -> Synthesis:
        """The sample the provider already holds for ``voice_id``. **Nothing of ELA's is sent.**

        Two requests, both downloads: the voice's metadata, then the sample it points at. It costs
        no credits and puts no text on the wire, which is what makes it the first step of choosing
        a voice (ADR 0034 §9).

        **Best effort, and measured why**: for a library voice the metadata answers
        ``voice_not_found`` sometimes and ``200`` other times — the same voice, minutes apart, on
        2026-09-08. A sample that is not there is a failure with a name, and the audition is the
        step that always works.
        """
        answer = await self._get(f"{ELEVENLABS_API}/v1/voices/{voice_id}")
        if answer.failure is not None:
            return answer
        url = _preview_url(answer.audio)
        if url is None:
            return Synthesis(failure=unusable_answer("this voice has no sample to play"))
        return await self._get(url, key=False)

    async def _attempt(self, url: str, body: dict[str, str]) -> Synthesis:
        """The request, and ADR 0020 §8's retry policy over it."""
        started = self._monotonic()
        attempts = 1 + self._settings.elevenlabs_max_retries
        answer = Synthesis()
        for attempt in range(attempts):
            answer = await self._post(url, body)
            failure = answer.failure
            if failure is None or not failure.retryable:
                break
            if attempt < attempts - 1:
                await self._sleep(_backoff(attempt, failure.retry_after))
        return Synthesis(
            audio=answer.audio,
            seconds=round(self._monotonic() - started, 3),
            credits=answer.credits,
            history_item_id=answer.history_item_id,
            failure=answer.failure,
            attempts=attempts if answer.failure is not None and answer.failure.retryable else 1,
        )

    async def _post(self, url: str, body: dict[str, str]) -> Synthesis:
        key = self._settings.elevenlabs_api_key
        assert key is not None, "callers check `configured` first"
        headers = {
            "xi-api-key": key.get_secret_value(),
            "content-type": "application/json",
        }
        return await self._read(
            "POST", url, headers=headers, params={"output_format": AUDIO_FORMAT}, json=body
        )

    async def _get(self, url: str, *, key: bool = True) -> Synthesis:
        headers = {}
        secret = self._settings.elevenlabs_api_key
        if key and secret is not None:
            headers["xi-api-key"] = secret.get_secret_value()
        return await self._read("GET", url, headers=headers, params=None, json=None)

    async def _read(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None,
        json: dict[str, str] | None,
    ) -> Synthesis:
        """One request, read to the end or to the ceiling, whichever comes first."""
        timeout = self._settings.elevenlabs_timeout_seconds
        try:
            async with (
                httpx.AsyncClient(timeout=timeout, transport=self._transport) as client,
                client.stream(method, url, headers=headers, params=params, json=json) as answer,
            ):
                payload, complete = await _collect(answer)
                if answer.status_code != httpx.codes.OK:
                    return Synthesis(
                        failure=classify_answer(
                            answer.status_code,
                            payload,
                            request_id=answer.headers.get(REQUEST_HEADER),
                            retry_after=retry_after_of(answer.headers.get("retry-after")),
                        )
                    )
                if not complete:
                    return Synthesis(failure=_too_much())
                if not payload:
                    return Synthesis(failure=unusable_answer("the answer carried no audio"))
                return Synthesis(
                    audio=payload,
                    credits=_number(answer.headers.get(COST_HEADER)),
                    history_item_id=answer.headers.get(RECEIPT_HEADER),
                )
        except httpx.TimeoutException:
            return Synthesis(failure=transport_failure(timed_out=True))
        except httpx.HTTPError:
            return Synthesis(failure=transport_failure(timed_out=False))


async def _collect(answer: httpx.Response) -> tuple[bytes, bool]:
    """Read the body up to the ceiling; the flag says whether it ended by itself."""
    payload = bytearray()
    async for chunk in answer.aiter_bytes():
        payload += chunk
        if len(payload) > MAX_AUDIO_BYTES:
            return bytes(payload[:MAX_AUDIO_BYTES]), False
    return bytes(payload), True


def _too_much() -> Failure:
    return Failure(
        SPEECH_TOO_MUCH_AUDIO,
        f"the answer went past {MAX_AUDIO_BYTES} bytes and reading stopped there",
        retryable=False,
    )


def _preview_url(body: bytes) -> str | None:
    """The ``preview_url`` of a voice document — if it points somewhere ELA agreed to go.

    Written without a single literal that starts with ``http``, which is not a stylistic choice:
    architecture rule 42 reads exactly those literals, and a module that needed one to check a
    URL would have had to weaken the rule that keeps ELA's words at one address.
    """
    try:
        parsed = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    url = parsed.get("preview_url")
    if not isinstance(url, str) or not url:
        return None
    address = httpx.URL(url)
    if address.scheme != "https" or address.host not in PREVIEW_HOSTS:
        return None
    return url


def _number(raw: str | None) -> int | None:
    """A header the provider states, or ``None`` — never a guess (ADR 0034 §10)."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _backoff(attempt: int, retry_after: float | None) -> float:
    """ADR 0020 §8: exponential and capped, unless the provider named a wait of its own."""
    if retry_after is not None:
        return min(float(retry_after), BACKOFF_CAP_SECONDS)
    return min(BACKOFF_BASE_SECONDS * float(2**attempt), BACKOFF_CAP_SECONDS)
