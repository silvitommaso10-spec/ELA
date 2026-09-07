"""The Anthropic provider: the only module of ELA that imports the SDK (ADR 0020, rule 24).

It implements :class:`~ela.ports.ModelProvider` and keeps two promises the port makes.

**A failure is a result.** ``complete`` does not raise for a provider failure: it answers with a
``ProviderResult`` carrying an ``ErrorMetadata`` whose code comes from the closed vocabulary in
``ela.ports``. Eight outcomes, and every one of them is a result: not configured, unknown hint,
unsupported parameter, transport failure, rate limit, server error, refusal, answer.

**Nothing of the user's leaves in an error.** The input and the instructions are sent to the API
and appear nowhere else — not in a message, not in ``details``, not in a log. What ELA keeps of a
failure is a status code, an error *type*, a request id and a count of attempts (§57).

Retrying is done here rather than by the SDK (``max_retries=0`` on the client, ADR 0020 §8): the
rule "again on 429 and 5xx, never on 4xx" is a rule of ELA, and a rule that lives inside a client
nobody can observe is a rule no test can hold to account.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Final

import anthropic
from anthropic import AsyncAnthropic
from anthropic.types import Message

from ela.domain import (
    ErrorMetadata,
    JsonMapping,
    ProviderRequest,
    ProviderResult,
    ProviderResultId,
    ProviderStatus,
    ProviderUsage,
)
from ela.ports import (
    PROVIDER_REFUSAL,
    PROVIDER_UNAVAILABLE,
    PROVIDER_UNKNOWN_MODEL_HINT,
    Clock,
    IdGenerator,
)
from ela.providers.anthropic.errors import Failure, UnsupportedRequestError, classify
from ela.providers.anthropic.models import Model, model_for_hint
from ela.providers.anthropic.payload import build_payload
from ela.providers.anthropic.pricing import CURRENCY, estimate_cost
from ela.providers.anthropic.settings import AnthropicSettings

__all__ = ["BACKOFF_BASE_SECONDS", "BACKOFF_CAP_SECONDS", "PROVIDER_NAME", "AnthropicProvider"]

PROVIDER_NAME: Final = "anthropic"
"""The vendor, not the model family: ``claude-*`` served by Bedrock or Vertex would be another
provider, with its own credentials and its own availability."""

BACKOFF_BASE_SECONDS: Final = 0.5
BACKOFF_CAP_SECONDS: Final = 8.0
"""Exponential, deterministic and capped: 0.5s, 1s, 2s… No jitter — jitter spreads a crowd of
clients, ELA is one client, and a delay a test can predict is a delay a test can prove."""

REFUSAL: Final = "refusal"
TEXT_BLOCK: Final = "text"

Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]


class AnthropicProvider:
    """Claude, behind :class:`~ela.ports.ModelProvider` (spec §26, §50; ADR 0020).

    ``client`` is ``None`` when no API key was configured: the provider still exists, still
    registers, and answers every call with :data:`~ela.ports.PROVIDER_UNAVAILABLE` without
    touching the network. ELA starts on a machine with no key (§33).

    ``sleep`` and ``monotonic`` are injected for the same reason a ``Clock`` is: a test proves the
    backoff without waiting, and latency is measured on a monotonic clock — the wall clock can
    step backwards (ADR 0003 §4) and would then report a negative duration.
    """

    def __init__(
        self,
        client: AsyncAnthropic | None,
        *,
        clock: Clock,
        ids: IdGenerator,
        settings: AnthropicSettings,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
    ) -> None:
        self._client = client
        self._clock = clock
        self._ids = ids
        self._settings = settings
        self._sleep = sleep
        self._monotonic = monotonic

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def status(self) -> ProviderStatus:
        """Configured or not: derived once, from the presence of a key (ADR 0020 §2)."""
        if self._client is None:
            return ProviderStatus.UNAVAILABLE
        return ProviderStatus.AVAILABLE

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        """Answer ``request``, or say why it could not be answered. Never raises for a failure."""
        started = self._monotonic()
        client = self._client
        if client is None:
            unusable = Failure(
                PROVIDER_UNAVAILABLE,
                "no API key configured (ELA_ANTHROPIC_API_KEY)",
                retryable=False,
            )
            return self._failed(request, unusable, model="", started=started, attempts=0)
        try:
            model = self._model_for(request)
            payload = build_payload(request, model, self._settings.anthropic_max_output_tokens)
        except UnsupportedRequestError as refused:
            return self._failed(
                request, refused.failure, model=refused.model, started=started, attempts=0
            )
        return await self._call(client, request, model, payload, started)

    def _model_for(self, request: ProviderRequest) -> Model:
        model = model_for_hint(request.model_hint)
        if model is None:
            raise UnsupportedRequestError(
                Failure(
                    PROVIDER_UNKNOWN_MODEL_HINT,
                    f"no model for hint {request.model_hint!r}",
                    retryable=False,
                )
            )
        return model

    async def _call(
        self,
        client: AsyncAnthropic,
        request: ProviderRequest,
        model: Model,
        payload: dict[str, Any],
        started: float,
    ) -> ProviderResult:
        """One call, retried while the failure is retryable and attempts are left (ADR 0020 §8)."""
        attempts = self._settings.anthropic_max_retries + 1
        attempt = 0
        while True:
            attempt += 1
            try:
                answer = await client.messages.create(**payload)
            except anthropic.APIError as exc:
                failure = classify(exc)
                if not (failure.retryable and attempt < attempts):
                    return self._failed(
                        request, failure, model=model.id, started=started, attempts=attempt
                    )
                await self._sleep(self._delay(attempt, failure.retry_after))
            else:
                return self._answered(request, answer, model, started, attempt)

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        """How long to wait before attempt ``attempt + 1``: what the provider asked, or backoff."""
        if retry_after is not None:
            return min(retry_after, BACKOFF_CAP_SECONDS)
        return min(BACKOFF_BASE_SECONDS * float(2 ** (attempt - 1)), BACKOFF_CAP_SECONDS)

    def _answered(
        self,
        request: ProviderRequest,
        answer: Message,
        model: Model,
        started: float,
        attempts: int,
    ) -> ProviderResult:
        """The API answered. A refusal is an answer too — one that costs tokens and has no text."""
        usage = self._usage(
            answer.model,
            input_tokens=answer.usage.input_tokens,
            output_tokens=answer.usage.output_tokens,
            cached_input_tokens=answer.usage.cache_read_input_tokens,
            started=started,
        )
        error: ErrorMetadata | None = None
        output = ""
        if answer.stop_reason == REFUSAL:
            error = self._error(
                Failure(PROVIDER_REFUSAL, self._refusal_message(answer), retryable=False),
                model=answer.model,
                attempts=attempts,
            )
        else:
            output = "".join(block.text for block in answer.content if block.type == TEXT_BLOCK)
        return ProviderResult(
            id=ProviderResultId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            request_id=request.id,
            provider=PROVIDER_NAME,
            model=answer.model,
            output=output,
            usage=usage,
            finish_reason=answer.stop_reason,
            error=error,
            metadata=self._metadata(attempts, self._request_id_of(answer)),
        )

    @staticmethod
    def _request_id_of(answer: Message) -> str | None:
        """The ``request-id`` the SDK attaches to a parsed response, when there is one.

        Not part of the model's schema: the SDK sets it on the object after parsing, so a message
        that never came from an HTTP response simply has none.
        """
        request_id = getattr(answer, "_request_id", None)
        return request_id if isinstance(request_id, str) else None

    @staticmethod
    def _refusal_message(answer: Message) -> str:
        """Why the model declined, in its own closed vocabulary — never its free-text explanation.

        The category ("cyber", "bio", …) is about the *kind* of request; the explanation would
        describe this request, and this request is the user's (§57).
        """
        details = answer.stop_details
        category = getattr(details, "category", None)
        if category is None:
            return "the model declined to answer"
        return f"the model declined to answer ({category})"

    def _failed(
        self,
        request: ProviderRequest,
        failure: Failure,
        *,
        model: str,
        started: float,
        attempts: int,
    ) -> ProviderResult:
        """A result that carries a failure: no output, real latency, no tokens spent."""
        return ProviderResult(
            id=ProviderResultId(self._ids.new_uuid()),
            created_at=self._clock.now(),
            request_id=request.id,
            provider=PROVIDER_NAME,
            model=model,
            output="",
            usage=self._usage(
                model, input_tokens=0, output_tokens=0, cached_input_tokens=None, started=started
            ),
            error=self._error(failure, model=model, attempts=attempts),
            metadata=self._metadata(attempts, failure.request_id),
        )

    def _usage(
        self,
        model: str,
        *,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int | None,
        started: float,
    ) -> ProviderUsage:
        """Tokens, estimated cost and how long the whole call took, retries included."""
        cost = estimate_cost(
            model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
        )
        return ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cost=cost,
            currency=None if cost is None else CURRENCY,
            latency_ms=self._elapsed_ms(started),
        )

    def _elapsed_ms(self, started: float) -> int:
        """Milliseconds since ``started``; never negative, the clock being monotonic."""
        return int(round((self._monotonic() - started) * 1000))

    @staticmethod
    def _error(failure: Failure, *, model: str, attempts: int) -> ErrorMetadata:
        details: dict[str, Any] = {"attempts": attempts}
        if failure.status_code is not None:
            details["status_code"] = failure.status_code
        if failure.request_id is not None:
            details["request_id"] = failure.request_id
        return ErrorMetadata(
            code=failure.code,
            message=failure.message,
            model=model or None,
            retryable=failure.retryable,
            details=details,
        )

    @staticmethod
    def _metadata(attempts: int, request_id: str | None) -> JsonMapping:
        """What is worth keeping about the call itself: how many tries, and which request it was."""
        metadata: dict[str, Any] = {"attempts": attempts}
        if request_id is not None:
            metadata["request_id"] = request_id
        return metadata
