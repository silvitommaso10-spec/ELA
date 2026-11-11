"""``ModelCompleteTool.worst_case``: the most a call can cost, before it is made (M14.1, ADR 0057).

The tool takes the steps of a run up to the network — arguments, route, provider, request — and
then asks the provider for its bound instead of its answer. So the request that is bounded is the
request that would be sent, and the codes of a refusal on the way are the codes the run would fail
with: a call that cannot be bounded is a call that is not made. Nothing here reaches a provider's
``complete`` — the fake counts.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

import pytest

from ela.domain import ErrorMetadata, ProviderRequest, WorstCase
from ela.ports import PROVIDER_UNAVAILABLE, PROVIDER_UNKNOWN_MODEL_HINT, ROUTING_UNKNOWN_TASK_TYPE
from ela.providers.anthropic.models import HAIKU_5_5
from ela.providers.anthropic.provider import PROVIDER_NAME
from ela.providers.registry import ProviderRegistry
from ela.routing import DEFAULT_ROUTES, ModelRouter, Route, RoutePolicy
from ela.testing.fakes import (
    FakeClock,
    FakeIdGenerator,
    FakeModelProvider,
    FakeModelRouter,
    FakeProviderRegistry,
    FakeStop,
)
from ela.tools import ARGUMENTS_INVALID, MODEL_COMPLETE, MODEL_TOOL_NAME, ModelCompleteTool
from tests.domain.examples import HAIKU_4_5_ID
from tests.providers.support import FakeAnthropic, make_provider
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


# ----------------------------------------------------------------------------------------
# A hint that names no model: where it is written (M14.6b, decisions 6 and 7)
# ----------------------------------------------------------------------------------------

PINNED: Final = Route(providers=(PROVIDER_NAME,), profile=HAIKU_4_5_ID)
"""A route that pins the id of Haiku 4.5, the way a real ``.env`` may still write it."""


def real_tool(policy: RoutePolicy) -> tuple[ModelCompleteTool, FakeAnthropic]:
    """The tool over the real router on ``policy`` and the real provider on a client double: the
    refusal is the provider's, and the place is the tool's — the only one that knows it."""
    provider, client = make_provider()
    assert client is not None
    registry = ProviderRegistry((provider,))
    tool = ModelCompleteTool(
        ModelRouter(policy, registry), registry, FakeClock(), FakeIdGenerator()
    )
    return tool, client


@pytest.mark.parametrize(
    ("policy", "arguments", "where"),
    [
        (RoutePolicy(), {"input": "x", "model_hint": HAIKU_4_5_ID}, "it is the step's model_hint"),
        (
            RoutePolicy({**DEFAULT_ROUTES, "routine": PINNED}),
            {"input": "x", "task_type": "routine"},
            "it is the profile of the route of task type 'routine' (ELA_MODEL_ROUTES)",
        ),
        (
            RoutePolicy(DEFAULT_ROUTES, PINNED),
            {"input": "x"},
            "it is the profile of the default route (ELA_MODEL_DEFAULT_ROUTE)",
        ),
    ],
    ids=["the-step", "a-route-of-a-task-type", "the-default-route"],
)
async def test_a_hint_that_names_no_model_is_refused_with_where_it_is_written(
    policy: RoutePolicy, arguments: dict[str, object], where: str
) -> None:
    """The provider's code, its ``retryable``, its words — and after them where the id is written,
    which the provider cannot know. Nobody decides by reading it (ADR 0023 §10)."""
    tool, client = real_tool(policy)

    bound = await tool.worst_case(arguments)

    assert isinstance(bound, ErrorMetadata)
    assert bound.code == PROVIDER_UNKNOWN_MODEL_HINT
    assert bound.message == f"no model for hint {HAIKU_4_5_ID!r}: {where}"
    assert client.messages.calls == [], "never the network"


async def test_a_hint_that_names_a_model_is_bounded_and_says_nothing_of_where() -> None:
    """The negative case: the same three places with a model of the list are a worst case."""
    today = Route(providers=(PROVIDER_NAME,), profile=HAIKU_5_5)
    for policy, arguments in (
        (RoutePolicy(), {"input": "x", "model_hint": HAIKU_5_5}),
        (RoutePolicy({**DEFAULT_ROUTES, "routine": today}), {"input": "x", "task_type": "routine"}),
        (RoutePolicy(DEFAULT_ROUTES, today), {"input": "x"}),
    ):
        tool, client = real_tool(policy)

        assert isinstance(await tool.worst_case(arguments), WorstCase)
        assert client.messages.calls == []
