"""What ELA sends: which model a hint chooses, and which parameters are allowed (§25, §26).

The hint is a *profile* — the vocabulary of §25 — not a vendor's model id, and the translation is
closed: what nobody mapped is refused, never silently replaced by the default.
"""

from __future__ import annotations

import pytest

from ela.providers.anthropic.models import (
    DEFAULT_MODEL,
    HAIKU_4_5,
    MODELS,
    OPUS_5,
    PROFILES,
    SONNET_5,
    model_for_hint,
)
from ela.providers.anthropic.payload import ALLOWED_PARAMETERS
from tests.providers.support import answer, make_provider, request, settings


def test_no_hint_is_the_configured_default() -> None:
    model = model_for_hint(None, DEFAULT_MODEL)
    assert model is not None and model.id == SONNET_5


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("reasoning", OPUS_5),
        ("planning", OPUS_5),
        ("coding", OPUS_5),
        ("quality", OPUS_5),
        ("analysis", OPUS_5),
        ("balanced", SONNET_5),
        ("classification", HAIKU_4_5),
        ("extraction", HAIKU_4_5),
        ("cheap", HAIKU_4_5),
        ("fast", HAIKU_4_5),
        ("routine", HAIKU_4_5),
    ],
)
def test_the_profiles_of_the_spec(hint: str, expected: str) -> None:
    model = model_for_hint(hint, DEFAULT_MODEL)
    assert model is not None and model.id == expected


def test_a_model_id_is_accepted_as_itself() -> None:
    model = model_for_hint(OPUS_5, DEFAULT_MODEL)
    assert model is not None and model.id == OPUS_5


def test_an_unknown_hint_resolves_to_nothing() -> None:
    assert model_for_hint("telepathy", DEFAULT_MODEL) is None


def test_every_profile_points_at_a_model_ela_knows() -> None:
    assert set(PROFILES.values()) <= set(MODELS)


async def test_the_body_of_a_plain_request() -> None:
    provider, client = make_provider(answer())

    await provider.complete(request(text="ciao"))

    assert client is not None
    assert client.messages.calls == [
        {
            "model": SONNET_5,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": "ciao"}],
        }
    ]


async def test_instructions_become_the_system_prompt() -> None:
    provider, client = make_provider(answer())

    await provider.complete(request(instructions="Rispondi per punti."))

    assert client is not None and client.messages.calls[0]["system"] == "Rispondi per punti."


async def test_the_output_budget_can_be_asked_for() -> None:
    provider, client = make_provider(answer())

    await provider.complete(request(parameters={"max_output_tokens": 800}))

    assert client is not None and client.messages.calls[0]["max_tokens"] == 800


async def test_the_default_budget_never_exceeds_what_the_model_can_produce() -> None:
    provider, client = make_provider(
        answer(model=HAIKU_4_5), provider_settings=settings(anthropic_max_output_tokens=64_000)
    )

    await provider.complete(request(model_hint="cheap"))

    assert client is not None and client.messages.calls[0]["max_tokens"] == 64_000


@pytest.mark.parametrize("value", [0, -1, "800", 1.5, True])
async def test_an_impossible_budget_is_refused(value: object) -> None:
    provider, client = make_provider()

    result = await provider.complete(request(parameters={"max_output_tokens": value}))

    assert result.error is not None
    assert "max_output_tokens" in result.error.message
    assert client is not None and client.messages.calls == []


async def test_a_budget_larger_than_the_model_is_refused() -> None:
    provider, _ = make_provider()

    result = await provider.complete(request(parameters={"max_output_tokens": 200_000}))

    assert result.error is not None
    assert "128000" in result.error.message


async def test_effort_is_sent_only_when_asked_for() -> None:
    provider, client = make_provider(answer())

    await provider.complete(request(parameters={"effort": "low"}))

    assert client is not None
    assert client.messages.calls[0]["output_config"] == {"effort": "low"}


async def test_an_invalid_effort_is_refused() -> None:
    provider, _ = make_provider()

    result = await provider.complete(request(parameters={"effort": "enormous"}))

    assert result.error is not None
    assert "effort" in result.error.message


async def test_effort_on_a_model_that_has_none_is_refused() -> None:
    """Haiku 4.5 answers a 400 to ``effort``: ELA knows that before spending a round trip."""
    provider, client = make_provider()

    result = await provider.complete(
        request(model_hint="classification", parameters={"effort": "high"})
    )

    assert result.error is not None
    assert HAIKU_4_5 in result.error.message
    assert client is not None and client.messages.calls == []


def test_the_allowlist_is_exactly_two_keys() -> None:
    assert set(ALLOWED_PARAMETERS) == {"max_output_tokens", "effort"}


async def test_thinking_and_sampling_are_never_sent() -> None:
    """Removed on every current model: sending either is a 400 (ADR 0020 §5)."""
    provider, client = make_provider(answer())

    await provider.complete(request(parameters={"effort": "max"}))

    assert client is not None
    sent = client.messages.calls[0]
    assert "thinking" not in sent
    assert "temperature" not in sent
    assert "stream" not in sent
    assert "tools" not in sent
