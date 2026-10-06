"""Contract of ``ModelProvider`` (spec §26, §50): a request in, a result with its cost out."""

from __future__ import annotations

from ela.domain import ErrorMetadata, ProviderResult, ProviderStatus, WorstCase
from ela.ports import PROVIDER_ERROR_CODES, PROVIDER_UNAVAILABLE, ModelProvider
from tests.domain.examples import PROVIDER_REQUEST


def test_has_a_name(provider: ModelProvider) -> None:
    assert isinstance(provider.name, str)
    assert provider.name.strip() != ""


def test_says_whether_it_can_be_used(provider: ModelProvider) -> None:
    """ADR 0020 §2: a provider declares its configuration, so a caller need not call to find out."""
    assert isinstance(provider.status, ProviderStatus)


async def test_an_unavailable_provider_answers_instead_of_raising(provider: ModelProvider) -> None:
    """Whatever the provider is, being unconfigured is a result — never a crash at start-up."""
    result = await provider.complete(PROVIDER_REQUEST)
    if provider.status is ProviderStatus.UNAVAILABLE:
        assert result.error is not None
        assert result.error.code == PROVIDER_UNAVAILABLE
        assert result.output == ""


async def test_a_failure_uses_the_shared_vocabulary(provider: ModelProvider) -> None:
    result = await provider.complete(PROVIDER_REQUEST)
    if result.error is not None:
        assert result.error.code in PROVIDER_ERROR_CODES


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


# --------------------------------------------------------------------------------------
# The worst case (M14.1, ADR 0057): a bound before the call, and an answer within it
# --------------------------------------------------------------------------------------


async def test_a_bound_is_a_worst_case_or_the_reason_there_is_none(
    provider: ModelProvider,
) -> None:
    """Never an exception and never the network: a provider that cannot bound a call says why,
    in the shared vocabulary, and the call is not made."""
    bound = await provider.worst_case(PROVIDER_REQUEST)
    assert isinstance(bound, WorstCase | ErrorMetadata)
    if isinstance(bound, ErrorMetadata):
        assert bound.code in PROVIDER_ERROR_CODES
    if provider.status is ProviderStatus.UNAVAILABLE:
        assert isinstance(bound, ErrorMetadata) and bound.code == PROVIDER_UNAVAILABLE


async def test_an_answer_never_costs_more_than_the_worst_case_of_its_request(
    provider: ModelProvider,
) -> None:
    """The bound is a bound: what the request then consumed, and what it cost, stay within it."""
    bound = await provider.worst_case(PROVIDER_REQUEST)
    result = await provider.complete(PROVIDER_REQUEST)
    if isinstance(bound, WorstCase):
        assert result.usage.input_tokens <= bound.input_tokens
        assert result.usage.output_tokens <= bound.output_tokens
        if bound.amount is not None and result.usage.cost is not None:
            assert result.usage.cost <= bound.amount
