"""``AnthropicSettings`` (ADR 0020 §3): the key comes from ELA's own variable, or from nowhere."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ela.domain import ProviderStatus
from ela.providers.anthropic import AnthropicSettings, anthropic_provider
from ela.providers.anthropic.models import DEFAULT_MODEL, OPUS_5, SONNET_5
from ela.providers.anthropic.settings import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator

KEY = "ELA_ANTHROPIC_API_KEY"
SDK_KEY = "ANTHROPIC_API_KEY"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        KEY,
        SDK_KEY,
        "ANTHROPIC_AUTH_TOKEN",
        "ELA_ANTHROPIC_MODEL",
        "ELA_ANTHROPIC_TIMEOUT_SECONDS",
        "ELA_ANTHROPIC_MAX_RETRIES",
        "ELA_ANTHROPIC_MAX_OUTPUT_TOKENS",
    ):
        monkeypatch.delenv(variable, raising=False)


def test_defaults() -> None:
    settings = AnthropicSettings(_env_file=None)
    assert settings.anthropic_api_key is None
    assert settings.anthropic_model == DEFAULT_MODEL == SONNET_5
    assert settings.anthropic_timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 60.0
    assert settings.anthropic_max_retries == DEFAULT_MAX_RETRIES == 2
    assert settings.anthropic_max_output_tokens == DEFAULT_MAX_OUTPUT_TOKENS == 4096


def test_the_default_model_is_the_balanced_one_not_the_expensive_one() -> None:
    """§25: the powerful model is chosen for a reason; what starts by itself is the cheap one."""
    assert DEFAULT_MODEL != OPUS_5


def test_the_key_is_read_from_elas_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "sk-ant-from-ela")
    settings = AnthropicSettings(_env_file=None)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-from-ela"


def test_the_secret_does_not_appear_in_the_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "sk-ant-from-ela")
    settings = AnthropicSettings(_env_file=None)
    assert "sk-ant-from-ela" not in repr(settings)
    assert "sk-ant-from-ela" not in str(settings.model_dump())


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_key_is_no_key(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(KEY, value)
    assert AnthropicSettings(_env_file=None).anthropic_api_key is None


def test_the_sdks_own_variable_is_not_a_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """The trap of ADR 0020 §3: the SDK would find this key by itself. ELA does not use it."""
    monkeypatch.setenv(SDK_KEY, "sk-ant-someone-elses")
    settings = AnthropicSettings(_env_file=None)
    assert settings.anthropic_api_key is None

    provider = anthropic_provider(FakeClock(), FakeIdGenerator(), settings=settings)
    assert provider.status is ProviderStatus.UNAVAILABLE


def test_a_key_makes_the_provider_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "sk-ant-from-ela")
    provider = anthropic_provider(FakeClock(), FakeIdGenerator())
    assert provider.status is ProviderStatus.AVAILABLE
    assert provider.name == "anthropic"


def test_an_unknown_model_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_ANTHROPIC_MODEL", "gpt-4")
    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


@pytest.mark.parametrize("value", ["0", "-1", "601"])
def test_an_impossible_timeout_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ELA_ANTHROPIC_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


@pytest.mark.parametrize("value", ["-1", "11"])
def test_an_impossible_retry_count_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ELA_ANTHROPIC_MAX_RETRIES", value)
    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


def test_a_budget_larger_than_the_model_can_produce_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ELA_ANTHROPIC_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("ELA_ANTHROPIC_MAX_OUTPUT_TOKENS", "100000")
    with pytest.raises(ValidationError):
        AnthropicSettings(_env_file=None)


def test_a_budget_the_model_can_produce_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_ANTHROPIC_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("ELA_ANTHROPIC_MAX_OUTPUT_TOKENS", "64000")
    assert AnthropicSettings(_env_file=None).anthropic_max_output_tokens == 64_000


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_SOMETHING_ELSE", "1")
    AnthropicSettings(_env_file=None)


def test_dotenv_file_is_read_when_asked(tmp_path: Path) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"ELA_ANTHROPIC_MODEL={OPUS_5}\n", encoding="utf-8")
    assert AnthropicSettings(_env_file=dotenv).anthropic_model == OPUS_5
