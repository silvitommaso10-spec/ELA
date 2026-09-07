"""The eight outcomes of ``AnthropicProvider.complete`` (ADR 0020 §9), none of them an exception.

Every test here proves one row of that table: what ELA answers, what it recorded, and — for the
three that happen before the network — that nothing was sent at all.
"""

from __future__ import annotations

from decimal import Decimal

from anthropic.types import TextBlock

from ela.domain import ProviderStatus
from ela.ports import (
    PROVIDER_AUTHENTICATION_ERROR,
    PROVIDER_BAD_REQUEST,
    PROVIDER_ERROR_CODES,
    PROVIDER_RATE_LIMITED,
    PROVIDER_REFUSAL,
    PROVIDER_REJECTED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_TIMEOUT,
    PROVIDER_UNAVAILABLE,
    PROVIDER_UNKNOWN_MODEL,
    PROVIDER_UNKNOWN_MODEL_HINT,
    PROVIDER_UNREACHABLE,
    PROVIDER_UNSUPPORTED_PARAMETER,
)
from ela.providers.anthropic.models import OPUS_5, SONNET_5
from ela.providers.anthropic.pricing import CURRENCY
from ela.providers.anthropic.provider import PROVIDER_NAME
from tests.providers.support import (
    REQUEST_ID,
    Ticks,
    answer,
    connection_error,
    make_provider,
    request,
    settings,
    status_error,
    timeout_error,
    unparseable_answer,
)


async def test_an_answer_becomes_a_result() -> None:
    provider, client = make_provider(answer("ecco", request_id=REQUEST_ID))
    assert provider.status is ProviderStatus.AVAILABLE

    result = await provider.complete(request())

    assert result.request_id == request().id
    assert result.provider == PROVIDER_NAME
    assert result.model == SONNET_5
    assert result.output == "ecco"
    assert result.finish_reason == "end_turn"
    assert result.error is None
    assert result.metadata == {"attempts": 1, "request_id": REQUEST_ID}
    assert client is not None and len(client.messages.calls) == 1


async def test_several_text_blocks_are_one_output() -> None:
    blocks = [TextBlock(text="uno", type="text"), TextBlock(text=" due", type="text")]
    provider, _ = make_provider(answer(blocks=blocks))
    assert (await provider.complete(request())).output == "uno due"


async def test_usage_carries_tokens_cost_currency_and_latency() -> None:
    provider, _ = make_provider(
        answer(input_tokens=1_200, output_tokens=340, cached_input_tokens=800),
        monotonic=Ticks(step=0.25),
    )

    usage = (await provider.complete(request())).usage

    assert (usage.input_tokens, usage.output_tokens, usage.cached_input_tokens) == (1200, 340, 800)
    # 1200×$2 + 340×$10 + 800×$0.2 per million, on claude-sonnet-5.
    assert usage.cost == Decimal("0.00596")
    assert usage.currency == CURRENCY
    assert usage.latency_ms == 250


async def test_a_model_outside_the_price_table_costs_none_never_zero() -> None:
    provider, _ = make_provider(answer(model="claude-something-new"))

    usage = (await provider.complete(request())).usage

    assert usage.cost is None
    assert usage.currency is None


async def test_without_a_key_the_provider_is_unavailable_and_sends_nothing() -> None:
    provider, client = make_provider(configured=False)
    assert provider.status is ProviderStatus.UNAVAILABLE

    result = await provider.complete(request())

    assert client is None
    assert result.error is not None
    assert result.error.code == PROVIDER_UNAVAILABLE
    assert result.error.retryable is False
    assert result.error.model is None
    assert result.model == ""
    assert result.output == ""
    assert result.usage.input_tokens == result.usage.output_tokens == 0
    assert result.usage.cost is None
    assert result.metadata == {"attempts": 0}


async def test_an_unknown_hint_stops_before_the_network() -> None:
    provider, client = make_provider()

    result = await provider.complete(request(model_hint="telepathy"))

    assert result.error is not None
    assert result.error.code == PROVIDER_UNKNOWN_MODEL_HINT
    assert result.error.retryable is False
    assert result.model == ""
    assert client is not None and client.messages.calls == []


async def test_an_unsupported_parameter_stops_before_the_network() -> None:
    """The case the domain example used to carry: ``temperature`` is a 400 known in advance."""
    provider, client = make_provider()

    result = await provider.complete(request(parameters={"temperature": 0.2}))

    assert result.error is not None
    assert result.error.code == PROVIDER_UNSUPPORTED_PARAMETER
    assert "temperature" in result.error.message
    assert result.model == SONNET_5
    assert result.error.model == SONNET_5
    assert client is not None and client.messages.calls == []


async def test_a_refusal_is_a_named_outcome_with_its_real_usage() -> None:
    provider, _ = make_provider(
        answer(stop_reason="refusal", refusal_category="cyber", input_tokens=90, output_tokens=0)
    )

    result = await provider.complete(request())

    assert result.output == ""
    assert result.finish_reason == "refusal"
    assert result.error is not None
    assert result.error.code == PROVIDER_REFUSAL
    assert result.error.retryable is False
    assert "cyber" in result.error.message
    assert result.usage.input_tokens == 90


async def test_a_refusal_without_a_category_still_says_what_happened() -> None:
    provider, _ = make_provider(answer(stop_reason="refusal"))

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_REFUSAL
    assert result.error.message == "the model declined to answer"


async def test_an_authentication_failure_is_named_and_never_retried() -> None:
    """ADR 0020 §2: M7.2 can mark the provider unusable from the code, without the SDK."""
    provider, client = make_provider(status_error(401, error_type="authentication_error"))

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_AUTHENTICATION_ERROR
    assert result.error.retryable is False
    assert result.error.details["status_code"] == 401
    assert result.error.details["request_id"] == REQUEST_ID
    assert result.error.details["attempts"] == 1
    assert client is not None and len(client.messages.calls) == 1


async def test_a_permission_failure_is_the_same_named_error() -> None:
    provider, _ = make_provider(status_error(403, error_type="permission_error"))
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_AUTHENTICATION_ERROR


async def test_a_bad_request_is_not_retried() -> None:
    provider, client = make_provider(status_error(400))
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_BAD_REQUEST
    assert client is not None and len(client.messages.calls) == 1


async def test_an_unknown_model_is_a_not_found() -> None:
    provider, _ = make_provider(status_error(404, error_type="not_found_error"))
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_UNKNOWN_MODEL


async def test_any_other_client_error_is_a_rejection() -> None:
    provider, _ = make_provider(status_error(409, error_type="conflict_error"))
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_REJECTED
    assert result.error.retryable is False


async def test_an_answer_the_sdk_cannot_parse_is_a_rejection_and_not_a_retry() -> None:
    """Neither a status nor a transport failure: a 200 that is not a message. Trying again on it
    would just fetch the same unusable body."""
    provider, client = make_provider(unparseable_answer())

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_REJECTED
    assert result.error.retryable is False
    assert "APIResponseValidationError" in result.error.message
    assert client is not None and len(client.messages.calls) == 1


async def test_a_failure_still_reports_the_model_it_was_going_to_use() -> None:
    provider, _ = make_provider(status_error(400), provider_settings=settings())
    result = await provider.complete(request(model_hint=OPUS_5))
    assert result.model == OPUS_5
    assert result.usage.cost == Decimal("0")
    assert result.usage.currency == CURRENCY


async def test_the_codes_come_from_the_vocabulary_of_the_port() -> None:
    """Every failure a caller can see is one a caller can recognise without knowing the vendor."""
    outcomes = [
        (make_provider(configured=False), PROVIDER_UNAVAILABLE),
        (
            make_provider(
                status_error(429, retry_after="0"),
                provider_settings=settings(anthropic_max_retries=0),
            ),
            PROVIDER_RATE_LIMITED,
        ),
        (
            make_provider(status_error(500), provider_settings=settings(anthropic_max_retries=0)),
            PROVIDER_SERVER_ERROR,
        ),
        (
            make_provider(connection_error(), provider_settings=settings(anthropic_max_retries=0)),
            PROVIDER_UNREACHABLE,
        ),
        (
            make_provider(timeout_error(), provider_settings=settings(anthropic_max_retries=0)),
            PROVIDER_TIMEOUT,
        ),
    ]
    for (provider, _), expected in outcomes:
        result = await provider.complete(request())
        assert result.error is not None
        assert result.error.code == expected
        assert result.error.code in PROVIDER_ERROR_CODES
