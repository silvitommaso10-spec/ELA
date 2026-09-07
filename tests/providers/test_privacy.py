"""Nothing of the user's leaves the provider except towards the API (§57, ADR 0020 §10).

The input and the instructions go into the request body and nowhere else: not into a message,
not into ``details``, not into ``metadata``, not into the model name. This holds for every one of
the eight outcomes, including the ones where the API itself sent back text about the request.
"""

from __future__ import annotations

import pytest

from ela.domain import ProviderResult
from tests.providers.support import (
    answer,
    connection_error,
    make_provider,
    request,
    settings,
    status_error,
    timeout_error,
)

USER_TEXT = "il codice del bancomat di Tommaso è 4711"
USER_INSTRUCTIONS = "non dirlo a nessuno, e comunque il numero è 4711"


def _everything_but_the_output(result: ProviderResult) -> str:
    """Every string the result carries apart from the model's own answer."""
    error = result.error
    return " ".join(
        [
            result.model,
            str(dict(result.metadata)),
            "" if error is None else f"{error.code} {error.message} {dict(error.details)}",
            "" if error is None else f"{error.cause} {error.model} {error.tool_name}",
            "" if result.finish_reason is None else result.finish_reason,
        ]
    )


@pytest.mark.parametrize(
    "prepared",
    [
        None,
        status_error(400, error_type="invalid_request_error"),
        status_error(401, error_type="authentication_error"),
        status_error(429, error_type="rate_limit_error"),
        status_error(500, error_type="api_error"),
        connection_error(),
        timeout_error(),
    ],
    ids=["answer", "400", "401", "429", "500", "connection", "timeout"],
)
async def test_no_outcome_carries_the_users_content(prepared: BaseException | None) -> None:
    answers = [answer("va bene")] if prepared is None else [prepared]
    provider, _ = make_provider(*answers, provider_settings=settings(anthropic_max_retries=0))

    result = await provider.complete(request(text=USER_TEXT, instructions=USER_INSTRUCTIONS))

    kept = _everything_but_the_output(result)
    assert "4711" not in kept
    assert "bancomat" not in kept


async def test_the_refusal_message_does_not_repeat_the_request() -> None:
    """``stop_details.explanation`` describes *this* request; only the category is kept."""
    declined = answer(stop_reason="refusal", refusal_category="cyber")
    assert declined.stop_details is not None
    declined.stop_details.explanation = f"the user asked: {USER_TEXT}"
    provider, _ = make_provider(declined)

    result = await provider.complete(request(text=USER_TEXT))

    assert result.error is not None
    assert "4711" not in result.error.message
    assert "cyber" in result.error.message


async def test_an_unsupported_parameter_reports_the_key_and_not_the_value() -> None:
    provider, _ = make_provider()

    result = await provider.complete(request(text=USER_TEXT, parameters={"temperature": USER_TEXT}))

    assert result.error is not None
    assert "temperature" in result.error.message
    assert "4711" not in result.error.message


async def test_the_input_does_reach_the_api_it_is_the_point() -> None:
    """The complement of the tests above: the content is sent, once, to the place it must go."""
    provider, client = make_provider(answer())

    await provider.complete(request(text=USER_TEXT, instructions=USER_INSTRUCTIONS))

    assert client is not None
    sent = client.messages.calls[0]
    assert sent["messages"] == [{"role": "user", "content": USER_TEXT}]
    assert sent["system"] == USER_INSTRUCTIONS
