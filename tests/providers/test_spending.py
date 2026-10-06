"""What the adapter says about money (M14.1, ADR 0057): the worst case, and the two facts.

The month's cap reads three things the adapter writes, and nothing else: the worst case of a
request before it is made, whether a request left this machine (``usage.sent``), and its cost —
``None`` when nobody knows it. Every test here proves one of the three, and the code the second
cap gets when the workspace's monthly limit is the one that stopped a call.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

from ela.domain import ErrorMetadata, WorstCase
from ela.ports import (
    PROVIDER_BAD_REQUEST,
    PROVIDER_RATE_LIMITED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_UNAVAILABLE,
    PROVIDER_UNKNOWN_MODEL_HINT,
    PROVIDER_UNSUPPORTED_PARAMETER,
    PROVIDER_WORKSPACE_LIMIT,
)
from ela.providers.anthropic import pricing
from ela.providers.anthropic.errors import WORKSPACE_LIMIT_PREFIX
from ela.providers.anthropic.models import HAIKU_4_5, MODELS, OPUS_5_5, PROFILES, SONNET_5_5
from tests.providers.support import (
    Sleeper,
    answer,
    connection_error,
    make_provider,
    request,
    settings,
    status_error,
    timeout_error,
    unparseable_answer,
)

WORKSPACE = "wrkspc_01TEST"


# --------------------------------------------------------------------------------------
# The worst case: the payload's own max_tokens, the rest of the window, the model's price
# --------------------------------------------------------------------------------------


async def test_the_worst_case_of_a_plain_request() -> None:
    provider, client = make_provider()

    bound = await provider.worst_case(request())

    assert bound == WorstCase(
        amount=Decimal("2.032768"),
        currency="USD",
        model=SONNET_5_5,
        input_tokens=1_000_000 - 4_096,
        output_tokens=4_096,
    )
    assert client is not None and client.messages.calls == [], "nothing left this machine"


@pytest.mark.parametrize(
    ("hint", "model", "amount"),
    [
        ("planning", OPUS_5_5, Decimal("4.065536")),
        ("balanced", SONNET_5_5, Decimal("2.032768")),
        ("routine", HAIKU_4_5, Decimal("0.216384")),
    ],
)
async def test_the_worst_case_is_the_profiles_model(hint: str, model: str, amount: Decimal) -> None:
    provider, _ = make_provider()

    bound = await provider.worst_case(request(model_hint=hint))

    assert isinstance(bound, WorstCase)
    assert (bound.model, bound.amount) == (model, amount)


@given(
    hint=st.sampled_from([None, *sorted(PROFILES), *sorted(MODELS)]),
    asked=st.one_of(st.none(), st.integers(min_value=1, max_value=64_000)),
    default=st.integers(min_value=1, max_value=128_000),
)
@hypothesis_settings(max_examples=60, deadline=None)
def test_the_output_side_is_the_max_tokens_the_payload_carries(
    hint: str | None, asked: int | None, default: int
) -> None:
    """Not a second estimate (decision D): the bound and the call agree on every request."""
    parameters = {} if asked is None else {"max_output_tokens": asked}
    provider, client = make_provider(
        answer("ok"), provider_settings=settings(anthropic_max_output_tokens=default)
    )

    bound = asyncio.run(provider.worst_case(request(model_hint=hint, parameters=parameters)))
    result = asyncio.run(provider.complete(request(model_hint=hint, parameters=parameters)))

    assert client is not None
    if result.error is not None:
        assert isinstance(bound, ErrorMetadata) and bound.code == result.error.code
        return
    assert isinstance(bound, WorstCase)
    sent = client.messages.calls[0]
    assert bound.output_tokens == sent["max_tokens"]
    assert bound.model == sent["model"]
    assert bound.input_tokens + bound.output_tokens == MODELS[sent["model"]].context_window


async def test_a_request_refused_before_the_network_has_no_worst_case_but_the_same_error() -> None:
    provider, _ = make_provider()

    unknown = await provider.worst_case(request(model_hint="gpt-4"))
    unsupported = await provider.worst_case(request(parameters={"temperature": 0.2}))

    assert isinstance(unknown, ErrorMetadata) and unknown.code == PROVIDER_UNKNOWN_MODEL_HINT
    assert isinstance(unsupported, ErrorMetadata)
    assert unsupported.code == PROVIDER_UNSUPPORTED_PARAMETER


async def test_without_a_key_there_is_no_worst_case_but_the_error_complete_gives() -> None:
    """Nothing leaves this machine to bound a call, and yet a provider without a key does not bound
    one: it cannot make it. Same error, same words, same order as ``complete`` — on a node without
    a key the refusal names the key instead of a price."""
    provider, _ = make_provider(configured=False)

    bound = await provider.worst_case(request(model_hint="gpt-4"))
    answered = await provider.complete(request(model_hint="gpt-4"))

    assert isinstance(bound, ErrorMetadata) and bound.code == PROVIDER_UNAVAILABLE
    assert answered.error is not None
    assert (bound.code, bound.message) == (answered.error.code, answered.error.message)


async def test_a_model_with_no_price_has_a_worst_case_with_no_amount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``None`` is not ``0``: the cap turns this into a call that is not made."""
    monkeypatch.setattr(pricing, "PRICES", {})
    provider, _ = make_provider()

    bound = await provider.worst_case(request())

    assert isinstance(bound, WorstCase)
    assert (bound.amount, bound.currency) == (None, None)


# --------------------------------------------------------------------------------------
# The two facts: did it leave this machine, and does anybody know what it cost
# --------------------------------------------------------------------------------------


async def test_an_answer_was_sent_and_has_a_cost() -> None:
    provider, _ = make_provider(answer("ok"))
    usage = (await provider.complete(request())).usage
    assert usage.sent is True
    assert usage.cost is not None and usage.cost > 0


async def test_a_refusal_was_sent_and_costs_its_tokens() -> None:
    provider, _ = make_provider(answer("", stop_reason="refusal", refusal_category="cyber"))
    usage = (await provider.complete(request())).usage
    assert usage.sent is True
    assert usage.cost is not None and usage.cost > 0


async def test_without_a_key_nothing_was_sent() -> None:
    provider, _ = make_provider(configured=False)
    assert (await provider.complete(request())).usage.sent is False


async def test_a_request_refused_before_the_network_was_not_sent() -> None:
    provider, client = make_provider()
    assert (await provider.complete(request(model_hint="gpt-4"))).usage.sent is False
    assert (await provider.complete(request(parameters={"top_k": 3}))).usage.sent is False
    assert client is not None and client.messages.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        status_error(400),
        status_error(401, error_type="authentication_error"),
        status_error(404, error_type="not_found_error"),
        status_error(409, error_type="conflict_error"),
        status_error(429, error_type="rate_limit_error"),
        status_error(529, error_type="overloaded_error"),
    ],
    ids=["400", "401", "404", "409", "429", "529"],
)
async def test_a_request_the_api_turned_down_was_sent_and_cost_nothing(
    failure: BaseException,
) -> None:
    """A ``4xx`` and the ``529`` are turned down before anything runs (ADR 0057)."""
    provider, _ = make_provider(failure, provider_settings=settings(anthropic_max_retries=0))

    usage = (await provider.complete(request())).usage

    assert usage.sent is True
    assert usage.cost == Decimal(0) and usage.currency == "USD"


@pytest.mark.parametrize(
    "failure",
    [
        status_error(500, error_type="api_error"),
        status_error(504, error_type="timeout_error"),
        timeout_error(),
        connection_error(),
        unparseable_answer(),
    ],
    ids=["500", "504", "timeout", "connection", "unreadable"],
)
async def test_a_failure_nobody_knows_the_outcome_of_has_no_cost(failure: BaseException) -> None:
    """The zero ELA wrote until M14.1 was a number nobody measured: now it is ``None``."""
    provider, _ = make_provider(failure)

    usage = (await provider.complete(request())).usage

    assert usage.sent is True
    assert (usage.cost, usage.currency) == (None, None)
    assert (usage.input_tokens, usage.output_tokens) == (0, 0), "the tokens it reported"


async def test_a_turned_down_try_then_an_unknown_one_has_no_cost() -> None:
    provider, client = make_provider(status_error(429), timeout_error(), sleep=Sleeper())

    result = await provider.complete(request())

    assert client is not None and len(client.messages.calls) == 2
    assert result.usage.cost is None


# --------------------------------------------------------------------------------------
# The second cap: the workspace's monthly limit, with a name of its own
# --------------------------------------------------------------------------------------


async def test_the_workspace_limit_has_a_code_of_its_own() -> None:
    words = f"{WORKSPACE_LIMIT_PREFIX}. You will regain access on 2026-11-01 at 00:00 UTC."
    sleeper = Sleeper()
    provider, client = make_provider(status_error(400, words=words), sleep=sleeper)

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_WORKSPACE_LIMIT
    assert result.error.retryable is False
    assert "console" in result.error.message and "ela spend" in result.error.message
    assert "regain" not in result.error.message, "the server's words are read, never kept"
    assert client is not None and len(client.messages.calls) == 1 and sleeper.delays == []
    assert result.usage.cost == Decimal(0), "turned down: it cost nothing"


@pytest.mark.parametrize(
    "words",
    [
        "You have reached your specified API usage limits.",
        "messages: at least one message is required",
        "",
    ],
)
async def test_any_other_bad_request_is_still_a_bad_request(words: str) -> None:
    """If the sentence ever changes, the answer falls back to what it was before M14.1."""
    provider, _ = make_provider(status_error(400, words=words))

    result = await provider.complete(request())

    assert result.error is not None and result.error.code == PROVIDER_BAD_REQUEST


async def test_a_bad_request_with_no_body_is_a_bad_request() -> None:
    failure = status_error(400)
    failure.body = None
    provider, _ = make_provider(failure)

    result = await provider.complete(request())

    assert result.error is not None and result.error.code == PROVIDER_BAD_REQUEST


async def test_the_workspace_limit_is_not_a_rate_limit() -> None:
    """The tier's spend cap is a ``429`` with no ``retry-after``: still a rate limit, by code."""
    provider, _ = make_provider(
        status_error(429, words=WORKSPACE_LIMIT_PREFIX),
        provider_settings=settings(anthropic_max_retries=0),
    )
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_RATE_LIMITED


# --------------------------------------------------------------------------------------
# Where the call was billed (review decision 12)
# --------------------------------------------------------------------------------------


async def test_the_workspace_of_the_key_travels_with_the_answer() -> None:
    provider, _ = make_provider(answer("ok", workspace=WORKSPACE))
    assert (await provider.complete(request())).workspace == WORKSPACE


async def test_an_answer_with_no_workspace_says_none() -> None:
    provider, _ = make_provider(answer("ok"))
    assert (await provider.complete(request())).workspace is None


async def test_a_failure_has_no_workspace() -> None:
    provider, _ = make_provider(
        status_error(529), provider_settings=settings(anthropic_max_retries=0)
    )
    result = await provider.complete(request())
    assert result.error is not None and result.error.code == PROVIDER_SERVER_ERROR
    assert result.workspace is None
