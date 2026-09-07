"""The suite cannot reach the network, and the proof is a real client that tries (§57, §58).

M7.1 is the first milestone whose code would send the user's content out of the machine. The
provider tests use a client double; this test checks the floor under them — that a client which
is *not* a double cannot get out either, so a missing double is a failure and never a real call.
"""

from __future__ import annotations

import anthropic
import pytest
from anthropic import AsyncAnthropic

from ela.domain import ProviderStatus
from ela.providers.anthropic import AnthropicSettings, anthropic_provider
from ela.providers.anthropic.provider import PROVIDER_NAME
from ela.testing.fakes import FakeClock, FakeIdGenerator
from tests.conftest import NO_NETWORK
from tests.providers.support import request


async def test_a_real_client_cannot_reach_the_api() -> None:
    """The SDK turns the refusal into its own connection error; the cause is the guard."""
    client = AsyncAnthropic(api_key="sk-ant-test", max_retries=0)
    with pytest.raises(anthropic.APIConnectionError) as raised:
        await client.messages.create(
            model="claude-sonnet-5",
            max_tokens=16,
            messages=[{"role": "user", "content": "hello"}],
        )
    assert isinstance(raised.value.__cause__, AssertionError)
    assert NO_NETWORK in str(raised.value.__cause__)


async def test_a_provider_built_from_the_environment_of_this_machine_never_calls_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whatever this machine has in its environment, the suite does not spend the user's money."""
    monkeypatch.setenv("ELA_ANTHROPIC_API_KEY", "sk-ant-test")
    provider = anthropic_provider(
        FakeClock(), FakeIdGenerator(), settings=AnthropicSettings(_env_file=None)
    )
    assert provider.status is ProviderStatus.AVAILABLE

    result = await provider.complete(request())

    assert result.provider == PROVIDER_NAME
    assert result.error is not None
