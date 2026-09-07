"""``ModelCompleteTool`` (§29, MEDIUM): the capability through which content leaves the machine.

Three things are under test and nothing else, because the tool does nothing else: that it builds
the request the domain describes, that it hands a provider's failure on with the **code** and the
**nature** the provider gave it (ADR 0020 §7, ADR 0021 §4), and that what a call consumed comes
back with it whether the call worked or not (§32).

What is *not* under test here is which model answers: the tool does not choose (ADR 0021 §5), and
the Model Router that will is M7.3.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ela.domain import (
    ErrorMetadata,
    ExecutionStatus,
    PermissionOutcome,
    ProviderRequest,
    ProviderResult,
    ProviderResultId,
    ProviderStatus,
    ProviderUsage,
)
from ela.ports import (
    PROVIDER_ERROR_CODES,
    PROVIDER_RATE_LIMITED,
    PROVIDER_UNAVAILABLE,
    NotAllowedError,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeModelProvider
from ela.tools import (
    ARGUMENTS_INVALID,
    MODEL_COMPLETE,
    MODEL_TOOL_NAME,
    PROVIDER_NO_OUTPUT,
    ModelCompleteTool,
)
from tests.tools.support import allowed

INPUT = "Riassumi le email della riunione."
ARGUMENTS = {"input": INPUT}


def tool_with(provider: FakeModelProvider) -> ModelCompleteTool:
    return ModelCompleteTool(provider, FakeClock(), FakeIdGenerator())


@pytest.fixture
def provider() -> FakeModelProvider:
    return FakeModelProvider(FakeClock(), FakeIdGenerator(), reply="una sintesi")


@pytest.fixture
def tool(provider: FakeModelProvider) -> ModelCompleteTool:
    return tool_with(provider)


# --------------------------------------------------------------------------------------
# The answer
# --------------------------------------------------------------------------------------


async def test_the_answer_comes_back_with_the_provider_the_model_and_the_usage(
    tool: ModelCompleteTool, provider: FakeModelProvider
) -> None:
    result = await tool.execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output["output"] == "una sintesi"
    assert result.output["provider"] == provider.name == tool.provider_name
    assert result.output["model"] == "fake-model"
    assert result.output["finish_reason"] == "end_turn"
    assert result.usage is not None
    assert result.usage.input_tokens > 0
    assert result.error is None
    assert result.tool_name == MODEL_TOOL_NAME
    assert result.capability_id == MODEL_COMPLETE


async def test_the_request_carries_what_the_arguments_said(
    tool: ModelCompleteTool, provider: FakeModelProvider
) -> None:
    await tool.execute(
        allowed(MODEL_COMPLETE),
        {
            "input": INPUT,
            "purpose": "riassunto della riunione",
            "instructions": "in tre righe",
            "model_hint": "cheap",
            "parameters": {"max_output_tokens": 200},
        },
    )

    (request,) = provider.requests
    assert isinstance(request, ProviderRequest)
    assert request.input == INPUT
    assert request.purpose == "riassunto della riunione"
    assert request.instructions == "in tre righe"
    assert request.model_hint == "cheap"
    assert request.parameters == {"max_output_tokens": 200}


async def test_a_request_without_a_purpose_names_the_capability(
    tool: ModelCompleteTool, provider: FakeModelProvider
) -> None:
    """``ProviderRequest.purpose`` is mandatory in the domain and optional in the schema: the
    tool fills it with the capability, never with a guess about the content."""
    await tool.execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    (request,) = provider.requests
    assert request.purpose == "model.complete"
    assert request.instructions is None
    assert request.model_hint is None
    assert request.parameters == {}


async def test_the_tool_does_not_choose_a_model(
    tool: ModelCompleteTool, provider: FakeModelProvider
) -> None:
    """ADR 0021 §5: the hint travels untouched and nothing invents one. M7.3 will choose."""
    await tool.execute(allowed(MODEL_COMPLETE), {**ARGUMENTS, "model_hint": "quality"})
    await tool.execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert [request.model_hint for request in provider.requests] == ["quality", None]


# --------------------------------------------------------------------------------------
# The arguments (§28: a tool never trusts its caller)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"input": 3},
        {"input": None},
        {"input": INPUT, "purpose": 7},
        {"input": INPUT, "instructions": ["a"]},
        {"input": INPUT, "model_hint": 1},
        {"input": INPUT, "parameters": "max_output_tokens=1"},
    ],
    ids=["missing", "not-a-string", "null", "purpose", "instructions", "hint", "parameters"],
)
async def test_bad_arguments_fail_before_the_network(
    tool: ModelCompleteTool, provider: FakeModelProvider, arguments: dict[str, object]
) -> None:
    result = await tool.execute(allowed(MODEL_COMPLETE), arguments)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == ARGUMENTS_INVALID
    assert result.error.retryable is False
    assert provider.requests == ()  # nothing left the machine
    assert result.usage is None


async def test_a_decision_that_does_not_allow_stops_the_tool_before_the_provider(
    tool: ModelCompleteTool, provider: FakeModelProvider
) -> None:
    """The contract of every tool, and the reason rule 25 exists: content leaves only under an
    ALLOWED decision (§27, §57)."""
    with pytest.raises(NotAllowedError):
        await tool.execute(allowed(MODEL_COMPLETE, outcome=PermissionOutcome.DENIED), ARGUMENTS)
    assert provider.requests == ()


# --------------------------------------------------------------------------------------
# A provider failure keeps its code and its nature (ADR 0020 §7, ADR 0021 §4)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("code", sorted(PROVIDER_ERROR_CODES))
@pytest.mark.parametrize("retryable", [True, False], ids=["retryable", "final"])
async def test_every_provider_code_arrives_unchanged(code: str, retryable: bool) -> None:
    error = ErrorMetadata(code=code, message=f"{code} happened", retryable=retryable)
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), error=error)

    result = await tool_with(provider).execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == code
    assert result.error.retryable is retryable  # the nature, not a flattened False
    assert result.error.tool_name == MODEL_TOOL_NAME
    assert result.output.get("output") is None  # no text on a failure


async def test_a_rate_limit_stays_retryable_all_the_way_to_the_result() -> None:
    """The case that made ``Outcome.retryable`` necessary: before M7.2 this was ``False``."""
    error = ErrorMetadata(code=PROVIDER_RATE_LIMITED, message="429", retryable=True)
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), error=error)

    result = await tool_with(provider).execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert result.error is not None
    assert result.error.retryable is True


async def test_an_unconfigured_provider_answers_without_touching_the_network() -> None:
    """ADR 0020 §2 read from the tool's side: no key is a fact, not a crash."""
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), status=ProviderStatus.UNAVAILABLE)

    result = await tool_with(provider).execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert result.error is not None
    assert result.error.code == PROVIDER_UNAVAILABLE
    assert provider.requests == ()


async def test_a_failed_call_still_reports_what_it_consumed() -> None:
    """A refusal costs tokens and a timeout costs latency (ADR 0020 §9): both are recorded."""
    error = ErrorMetadata(code=PROVIDER_RATE_LIMITED, message="429", retryable=True)
    provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), error=error)

    result = await tool_with(provider).execute(allowed(MODEL_COMPLETE), ARGUMENTS)

    assert result.usage is not None
    assert result.usage.input_tokens > 0


# --------------------------------------------------------------------------------------
# An answer that is not an answer
# --------------------------------------------------------------------------------------


class EmptyProvider:
    """A provider that succeeds with no text: not a failure it reported, but nothing usable."""

    name = "empty"
    status = ProviderStatus.AVAILABLE
    usage = ProviderUsage(input_tokens=5, output_tokens=0, cost=Decimal("0.00001"), currency="USD")

    def __init__(self) -> None:
        self.ids = FakeIdGenerator()
        self.clock = FakeClock()

    async def complete(self, request: ProviderRequest) -> ProviderResult:
        return ProviderResult(
            id=ProviderResultId(self.ids.new_uuid()),
            created_at=self.clock.now(),
            request_id=request.id,
            provider=self.name,
            model="empty-model",
            output="",
            usage=self.usage,
            finish_reason="end_turn",
        )


async def test_an_empty_answer_is_refused_here_and_not_one_layer_later() -> None:
    result = await tool_with(EmptyProvider()).execute(  # type: ignore[arg-type]
        allowed(MODEL_COMPLETE), ARGUMENTS
    )

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert result.error.code == PROVIDER_NO_OUTPUT
    assert result.error.code not in PROVIDER_ERROR_CODES  # not a failure the provider reported
    assert result.error.retryable is False
    assert result.usage == EmptyProvider.usage
    assert result.output["model"] == "empty-model"


# --------------------------------------------------------------------------------------
# What does not leave (§57)
# --------------------------------------------------------------------------------------


async def test_no_failure_message_repeats_the_users_content() -> None:
    for code in sorted(PROVIDER_ERROR_CODES):
        error = ErrorMetadata(code=code, message=f"{code} happened", retryable=False)
        provider = FakeModelProvider(FakeClock(), FakeIdGenerator(), error=error)
        result = await tool_with(provider).execute(allowed(MODEL_COMPLETE), ARGUMENTS)
        assert result.error is not None
        assert INPUT not in result.error.message
        assert INPUT not in str(result.error.details)
    bad = await tool_with(FakeModelProvider(FakeClock(), FakeIdGenerator())).execute(
        allowed(MODEL_COMPLETE), {"input": INPUT, "purpose": 7}
    )
    assert bad.error is not None
    assert INPUT not in bad.error.message


async def test_the_tool_is_not_idempotent_and_says_so() -> None:
    """A second call is charged, goes out again and answers something else (ADR 0021 §1)."""
    assert ModelCompleteTool.idempotent is False
