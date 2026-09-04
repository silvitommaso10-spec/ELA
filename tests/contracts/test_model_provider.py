"""Contract of ``ModelProvider`` (spec §26, §50): a request in, a result with its cost out."""

from __future__ import annotations

from ela.domain import ProviderResult
from ela.ports import ModelProvider
from tests.domain.examples import PROVIDER_REQUEST


def test_has_a_name(provider: ModelProvider) -> None:
    assert isinstance(provider.name, str)
    assert provider.name.strip() != ""


async def test_complete_answers_the_request(provider: ModelProvider) -> None:
    result = await provider.complete(PROVIDER_REQUEST)
    assert isinstance(result, ProviderResult)
    assert result.request_id == PROVIDER_REQUEST.id
    assert result.provider == provider.name
    assert result.created_at.tzinfo is not None


async def test_usage_is_accounted(provider: ModelProvider) -> None:
    result = await provider.complete(PROVIDER_REQUEST)
    assert result.usage.input_tokens >= 0
    assert result.usage.output_tokens >= 0
