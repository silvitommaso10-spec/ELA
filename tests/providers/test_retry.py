"""The retry policy (ADR 0020 §8): again on 429 and 5xx, never on a 4xx, and never blindly.

The reason this policy is ELA's and not the SDK's is visible here: the client is a double, so the
SDK's own retrying would be invisible and untestable. What the tests hold to account is the
sequence of waits and the number of calls — both of which the milestone states as a requirement.
"""

from __future__ import annotations

import pytest

from ela.ports import (
    PROVIDER_BAD_REQUEST,
    PROVIDER_RATE_LIMITED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_TIMEOUT,
    PROVIDER_UNREACHABLE,
)
from ela.providers.anthropic.provider import BACKOFF_BASE_SECONDS, BACKOFF_CAP_SECONDS
from tests.providers.support import (
    Sleeper,
    answer,
    connection_error,
    make_provider,
    request,
    settings,
    status_error,
    timeout_error,
)


async def test_a_server_error_then_an_answer_costs_one_wait() -> None:
    sleeper = Sleeper()
    provider, client = make_provider(
        status_error(500, error_type="api_error"), answer("ok"), sleep=sleeper
    )

    result = await provider.complete(request())

    assert result.error is None
    assert result.output == "ok"
    assert result.metadata["attempts"] == 2
    assert sleeper.delays == [BACKOFF_BASE_SECONDS]
    assert client is not None and len(client.messages.calls) == 2


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        (status_error(429, error_type="rate_limit_error"), PROVIDER_RATE_LIMITED),
        (status_error(529, error_type="overloaded_error"), PROVIDER_SERVER_ERROR),
        (connection_error(), PROVIDER_UNREACHABLE),
        (timeout_error(), PROVIDER_TIMEOUT),
    ],
)
async def test_every_retryable_failure_is_tried_again(failure: BaseException, code: str) -> None:
    sleeper = Sleeper()
    provider, client = make_provider(failure, answer("ok"), sleep=sleeper)

    result = await provider.complete(request())

    assert result.error is None, code
    assert client is not None and len(client.messages.calls) == 2
    assert len(sleeper.delays) == 1


async def test_the_backoff_doubles_and_stops_at_the_cap() -> None:
    failures = [status_error(500) for _ in range(6)]
    sleeper = Sleeper()
    provider, client = make_provider(
        *failures, sleep=sleeper, provider_settings=settings(anthropic_max_retries=5)
    )

    result = await provider.complete(request())

    assert sleeper.delays == [0.5, 1.0, 2.0, 4.0, 8.0]
    assert BACKOFF_CAP_SECONDS == 8.0
    assert client is not None and len(client.messages.calls) == 6
    assert result.error is not None
    assert result.error.code == PROVIDER_SERVER_ERROR
    assert result.error.retryable is True, "the last attempt still says what kind of failure it is"
    assert result.error.details["attempts"] == 6


async def test_the_provider_is_obeyed_when_it_says_how_long_to_wait() -> None:
    sleeper = Sleeper()
    provider, _ = make_provider(
        status_error(429, error_type="rate_limit_error", retry_after="3"),
        answer("ok"),
        sleep=sleeper,
    )

    await provider.complete(request())

    assert sleeper.delays == [3.0]


async def test_a_retry_after_beyond_the_cap_is_capped() -> None:
    sleeper = Sleeper()
    provider, _ = make_provider(status_error(429, retry_after="600"), answer("ok"), sleep=sleeper)

    await provider.complete(request())

    assert sleeper.delays == [BACKOFF_CAP_SECONDS]


async def test_an_unreadable_retry_after_leaves_the_backoff_in_charge() -> None:
    """The header may be an HTTP date; ELA does not parse it, and does not guess either."""
    sleeper = Sleeper()
    provider, _ = make_provider(
        status_error(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT"), answer("ok"), sleep=sleeper
    )

    await provider.complete(request())

    assert sleeper.delays == [BACKOFF_BASE_SECONDS]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
async def test_a_client_error_is_never_retried(status: int) -> None:
    sleeper = Sleeper()
    provider, client = make_provider(status_error(status), sleep=sleeper)

    result = await provider.complete(request())

    assert result.error is not None
    assert sleeper.delays == []
    assert client is not None and len(client.messages.calls) == 1


async def test_retrying_can_be_switched_off() -> None:
    sleeper = Sleeper()
    provider, client = make_provider(
        status_error(500), provider_settings=settings(anthropic_max_retries=0), sleep=sleeper
    )

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_SERVER_ERROR
    assert sleeper.delays == []
    assert client is not None and len(client.messages.calls) == 1


async def test_the_latency_covers_every_attempt() -> None:
    provider, _ = make_provider(status_error(500), status_error(500), answer("ok"))

    result = await provider.complete(request())

    assert result.usage.latency_ms == 250, "one Ticks step from the first call to the answer"
    assert result.error is None


async def test_a_bad_request_after_a_retryable_one_stops_the_loop() -> None:
    sleeper = Sleeper()
    provider, client = make_provider(status_error(500), status_error(400), sleep=sleeper)

    result = await provider.complete(request())

    assert result.error is not None
    assert result.error.code == PROVIDER_BAD_REQUEST
    assert len(sleeper.delays) == 1
    assert client is not None and len(client.messages.calls) == 2
