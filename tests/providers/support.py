"""What the provider tests build on: a client double, a sleeper, a monotonic clock, answers.

No test in this package opens a socket. The SDK client is replaced by an object with the one
method the adapter calls — ``messages.create`` — which either returns a prepared ``Message`` or
raises a prepared SDK exception, in order. ``tests/security/test_no_network.py`` proves that this
is not merely a habit.
"""

from __future__ import annotations

from typing import Any, Final, cast

import anthropic
import httpx2
from anthropic import AsyncAnthropic
from anthropic.types import Message, RefusalStopDetails, TextBlock, Usage
from pydantic import SecretStr

from ela.domain import ProviderRequest, ProviderRequestId, UtcDatetime
from ela.providers.anthropic import AnthropicProvider, AnthropicSettings
from ela.providers.anthropic.models import SONNET_5
from ela.testing.fakes import DEFAULT_START, FakeClock, FakeIdGenerator
from tests.domain.examples import PROVIDER_REQUEST_ID

API_URL: Final = "https://api.anthropic.com/v1/messages"
REQUEST_ID: Final = "req_0123456789"
SECRET: Final = "sk-ant-test"

STATUS_ERRORS: Final = {
    400: anthropic.BadRequestError,
    401: anthropic.AuthenticationError,
    403: anthropic.PermissionDeniedError,
    404: anthropic.NotFoundError,
    409: anthropic.ConflictError,
    422: anthropic.UnprocessableEntityError,
    429: anthropic.RateLimitError,
}


def request(
    *,
    text: str = "Riassumi le email di domani.",
    instructions: str | None = None,
    model_hint: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> ProviderRequest:
    """A request in the domain's terms. ``text`` is the user's content: it must never leak."""
    return ProviderRequest(
        id=ProviderRequestId(PROVIDER_REQUEST_ID),
        created_at=cast(UtcDatetime, DEFAULT_START),
        purpose="test",
        input=text,
        instructions=instructions,
        model_hint=model_hint,
        parameters=parameters or {},
    )


def answer(
    text: str = "ecco il riassunto",
    *,
    model: str = SONNET_5,
    stop_reason: str = "end_turn",
    input_tokens: int = 1_200,
    output_tokens: int = 340,
    cached_input_tokens: int | None = None,
    request_id: str | None = None,
    refusal_category: str | None = None,
    blocks: list[Any] | None = None,
) -> Message:
    """A ``Message`` as the SDK would have parsed one."""
    content = blocks if blocks is not None else [TextBlock(text=text, type="text")]
    details = (
        RefusalStopDetails(type="refusal", category=refusal_category)
        if stop_reason == "refusal"
        else None
    )
    message = Message(
        id="msg_test",
        content=content,
        model=model,
        role="assistant",
        stop_reason=cast(Any, stop_reason),
        stop_details=details,
        type="message",
        usage=Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cached_input_tokens,
        ),
    )
    if request_id is not None:
        message._request_id = request_id
    return message


def status_error(
    status: int, *, error_type: str = "invalid_request_error", retry_after: str | None = None
) -> anthropic.APIStatusError:
    """The exception the SDK raises for an HTTP status, with the headers a real one carries."""
    headers = {"request-id": REQUEST_ID}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    response = httpx2.Response(
        status,
        headers=headers,
        request=httpx2.Request("POST", API_URL),
    )
    body = {"type": "error", "error": {"type": error_type, "message": "server side text"}}
    error_class = STATUS_ERRORS.get(
        status, anthropic.InternalServerError if status >= 500 else anthropic.APIStatusError
    )
    return error_class(f"{status} {error_type}", response=response, body=body)


def unparseable_answer() -> anthropic.APIResponseValidationError:
    """A 200 whose body the SDK cannot make a ``Message`` of: an error that is neither."""
    response = httpx2.Response(
        200, json={"unexpected": True}, request=httpx2.Request("POST", API_URL)
    )
    return anthropic.APIResponseValidationError(response=response, body=None)


def connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx2.Request("POST", API_URL))


def timeout_error() -> anthropic.APITimeoutError:
    return anthropic.APITimeoutError(request=httpx2.Request("POST", API_URL))


class FakeMessages:
    """``client.messages``: hands out prepared answers in order and records what it was sent."""

    def __init__(self, answers: list[Any], *, repeat: bool = False) -> None:
        self._answers = answers
        self._repeat = repeat
        self.calls: list[dict[str, Any]] = []

    async def create(self, **payload: Any) -> Message:
        self.calls.append(payload)
        assert self._answers, "the provider called the API more times than the test prepared"
        prepared = self._answers[0] if self._repeat else self._answers.pop(0)
        if isinstance(prepared, BaseException):
            raise prepared
        return cast(Message, prepared)


class FakeAnthropic:
    """The shape of ``AsyncAnthropic`` the adapter actually uses: ``.messages.create``."""

    def __init__(self, *answers: Any, repeat: bool = False) -> None:
        self.messages = FakeMessages(list(answers), repeat=repeat)


class Sleeper:
    """``asyncio.sleep`` without the sleeping: it remembers what it was asked to wait."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


class Ticks:
    """A monotonic clock that advances by ``step`` seconds at every reading."""

    def __init__(self, step: float = 0.25) -> None:
        self._now = 0.0
        self._step = step

    def __call__(self) -> float:
        now = self._now
        self._now += self._step
        return now


def settings(**overrides: Any) -> AnthropicSettings:
    """Settings with a key and no environment: a test never depends on the machine it runs on."""
    values: dict[str, Any] = {"anthropic_api_key": SecretStr(SECRET)}
    values.update(overrides)
    return AnthropicSettings(_env_file=None, **values)


def make_provider(
    *answers: Any,
    configured: bool = True,
    provider_settings: AnthropicSettings | None = None,
    sleep: Sleeper | None = None,
    monotonic: Ticks | None = None,
) -> tuple[AnthropicProvider, FakeAnthropic | None]:
    """A provider on a client double (or on no client at all, which is UNAVAILABLE)."""
    client = FakeAnthropic(*answers) if configured else None
    provider = AnthropicProvider(
        cast(AsyncAnthropic, client),
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        settings=provider_settings or settings(),
        sleep=sleep or Sleeper(),
        monotonic=monotonic or Ticks(),
    )
    return provider, client
