"""``ModelCompleteTool.worst_case``: the most a call can cost, before it is made (M14.1, ADR 0057).

The tool takes the steps of a run up to the network — arguments, route, provider, request — and
then asks the provider for its bound instead of its answer. So the request that is bounded is the
request that would be sent, and the codes of a refusal on the way are the codes the run would fail
with: a call that cannot be bounded is a call that is not made. Nothing here reaches a provider's
``complete`` — the fake counts.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ela.domain import ErrorMetadata, ProviderRequest, WorstCase
from ela.ports import PROVIDER_UNAVAILABLE, ROUTING_UNKNOWN_TASK_TYPE
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeModelProvider,
    FakeModelRouter,
    FakeProviderRegistry,
    FakeStop,
)
from ela.tools import ARGUMENTS_INVALID, MODEL_COMPLETE, MODEL_TOOL_NAME, ModelCompleteTool
from tests.routing.support import routing_for
from tests.tools.support import allowed

ARGUMENTS = {
    "input": "Riassumi le email della riunione.",
    "instructions": "In due righe.",
    "purpose": "sintesi",
    "parameters": {"max_tokens": 512},
}


class Bounding(FakeModelProvider):
    """A fake that also keeps the requests it was asked to bound."""

    def __init__(self, **given: object) -> None:
        super().__init__(FakeClock(), FakeIdGenerator(), reply="una sintesi", **given)  # type: ignore[arg-type]
        self.bounded: tuple[ProviderRequest, ...] = ()

    async def worst_case(self, request: ProviderRequest) -> WorstCase | ErrorMetadata:
        self.bounded = (*self.bounded, request)
        return await super().worst_case(request)


def tool_over(provider: FakeModelProvider) -> ModelCompleteTool:
    router, providers = routing_for(provider)
    return ModelCompleteTool(router, providers, FakeClock(), FakeIdGenerator())


async def test_it_is_the_providers_bound_and_no_call_is_made() -> None:
    bound = WorstCase(
        amount=Decimal("0.5"), currency="USD", model="m", input_tokens=1000, output_tokens=512
    )
    provider = Bounding(worst=bound)

    assert await tool_over(provider).worst_case(ARGUMENTS) == bound
    assert provider.requests == (), "never the network"


async def test_the_request_bounded_is_the_request_the_run_sends() -> None:
    """Same text, same profile, same parameters: only the id and the instant are the run's."""
    provider = Bounding()
    tool = tool_over(provider)

    await tool.worst_case(ARGUMENTS)
    await tool.execute(allowed(MODEL_COMPLETE), ARGUMENTS, FakeStop())

    (bounded,) = provider.bounded
    (sent,) = provider.requests
    keep = {"id", "created_at"}
    assert bounded.model_dump(exclude=keep) == sent.model_dump(exclude=keep)


@pytest.mark.parametrize(
    "arguments",
    [{}, {"input": 7}, {"input": "x", "parameters": []}, {"input": "x", "purpose": 1}],
    ids=["no-input", "input-not-text", "parameters-not-a-mapping", "purpose-not-text"],
)
async def test_arguments_the_run_would_refuse_cannot_be_bounded(
    arguments: dict[str, object],
) -> None:
    provider = Bounding()

    bound = await tool_over(provider).worst_case(arguments)

    assert isinstance(bound, ErrorMetadata)
    assert (bound.code, bound.tool_name) == (ARGUMENTS_INVALID, MODEL_TOOL_NAME)
    assert provider.bounded == ()


async def test_a_task_type_the_router_does_not_know_cannot_be_bounded() -> None:
    provider = Bounding()

    bound = await tool_over(provider).worst_case({"input": "x", "task_type": "astrologia"})

    assert isinstance(bound, ErrorMetadata) and bound.code == ROUTING_UNKNOWN_TASK_TYPE
    assert provider.bounded == ()


async def test_a_route_to_a_provider_nobody_registered_cannot_be_bounded() -> None:
    tool = ModelCompleteTool(
        FakeModelRouter(provider="ghost"), FakeProviderRegistry(), FakeClock(), FakeIdGenerator()
    )

    bound = await tool.worst_case({"input": "x"})

    assert isinstance(bound, ErrorMetadata) and bound.code == PROVIDER_UNAVAILABLE
    assert "ghost" in (bound.message or "")


async def test_a_provider_that_cannot_bound_says_why_and_the_tool_passes_it_on() -> None:
    refusal = ErrorMetadata(code=PROVIDER_UNAVAILABLE, message="no key")
    provider = Bounding(worst=refusal)

    assert await tool_over(provider).worst_case({"input": "x"}) == refusal
