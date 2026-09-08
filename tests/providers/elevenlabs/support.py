"""What the ElevenLabs tests build on: a transport double, a sleeper, a clock.

No test in this package opens a socket — ``tests/conftest.py`` makes the real transports raise,
and what is injected here is ``httpx.MockTransport``, which answers in this process.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Final

import httpx
from pydantic import SecretStr

from ela.providers.elevenlabs import ElevenLabsSettings
from ela.providers.elevenlabs.provider import ElevenLabsVoice

SECRET: Final = "sk_test_key"
VOICE: Final = "VZOd9FMXDnXRZpGn0thg"
AUDIO: Final = b"ID3\x04audio-bytes"
REQUEST_ID: Final = "Sld38WIBRBr0AHzHN5Of"
RECEIPT: Final = "bZ7h4eUtFFJyXt7MbkwH"


def settings(**overrides: object) -> ElevenLabsSettings:
    """Settings with a key and a voice, unless a test says otherwise."""
    values: dict[str, object] = {
        "elevenlabs_api_key": SecretStr(SECRET),
        "elevenlabs_voice_id": VOICE,
        "elevenlabs_max_retries": 1,
        "_env_file": None,
    }
    values.update(overrides)
    return ElevenLabsSettings(**values)  # type: ignore[arg-type]


def spoken(
    *,
    credits: int | None = 26,
    receipt: str | None = RECEIPT,
    audio: bytes = AUDIO,
) -> httpx.Response:
    """A successful answer, with the headers the provider really sends."""
    headers = {"request-id": REQUEST_ID}
    if credits is not None:
        headers["character-cost"] = str(credits)
    if receipt is not None:
        headers["history-item-id"] = receipt
    return httpx.Response(200, content=audio, headers=headers)


def refused(http_status: int, /, **detail: str) -> httpx.Response:
    """An error answer in the provider's own shape, measured on 2026-09-08.

    Positional-only, because ``status`` is one of the provider's own body fields and a keyword of
    the same name would be two different things spelled the same.
    """
    return httpx.Response(
        http_status,
        json={"detail": {**detail, "request_id": "40ede4fc"}},
        headers={"request-id": REQUEST_ID},
    )


class Answers:
    """A transport that replies from a list, and remembers every request it was given."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.given: list[httpx.Request] = []
        self._answers = list(answers)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    @property
    def last(self) -> httpx.Request:
        return self.given[-1]

    def body_of(self, request: httpx.Request) -> dict[str, object]:
        parsed = json.loads(request.content)
        assert isinstance(parsed, dict)
        return parsed

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.given.append(request)
        answer = self._answers.pop(0) if self._answers else httpx.Response(500)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Sleeper:
    """Records what it was asked to wait, and waits for none of it."""

    def __init__(self) -> None:
        self.waited: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waited.append(seconds)


def ticking(*times: float) -> Callable[[], float]:
    """A monotonic clock that returns the given readings in order, then repeats the last."""
    readings: Sequence[float] = times or (0.0,)
    remaining = list(readings)

    def read() -> float:
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return read


def voice(
    answers: Answers, *, sleeper: Sleeper | None = None, **overrides: object
) -> ElevenLabsVoice:
    return ElevenLabsVoice(
        settings(**overrides),
        sleep=sleeper or Sleeper(),
        monotonic=ticking(0.0, 1.24),
        transport=answers.transport,
    )
