"""How the Anthropic provider is configured, from the environment (ADR 0001, ADR 0020 §3).

Five variables, all with the ``ELA_`` prefix, in the shape ``PersistenceSettings``,
``WorkspaceSettings`` and ``DeviceSettings`` already have; M8.1 will unify the four.

The one that matters most is the key, and the reason is not obvious: the SDK, given no
``api_key``, finds credentials **by itself** — ``ANTHROPIC_API_KEY``, then
``ANTHROPIC_AUTH_TOKEN``, then an OAuth profile written on disk by ``ant auth login``, then
workload identity federation. On a developer machine at least one of those is usually present.
So ELA reads its own variable, and builds the client only with an explicit ``api_key=``: what
ELA has not been given, ELA does not use.

The key is a ``SecretStr`` so that printing a settings object — in a traceback, in a log, in a
debugger — cannot print the secret.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ela.providers.anthropic.models import DEFAULT_MODEL, MODELS

__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "AnthropicSettings",
]

DEFAULT_TIMEOUT_SECONDS: Final = 60.0
"""A minute. The SDK waits ten by default, and an assistant that waits ten minutes for one
sentence is an assistant that has stopped assisting."""
MAX_TIMEOUT_SECONDS: Final = 600.0
"""The SDK's own ceiling for a non-streaming call: past it the request is expected to fail."""
DEFAULT_MAX_RETRIES: Final = 2
MAX_RETRIES_CEILING: Final = 10
DEFAULT_MAX_OUTPUT_TOKENS: Final = 4096


class AnthropicSettings(BaseSettings):
    """Anthropic configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr | None = None
    """``ELA_ANTHROPIC_API_KEY``. Absent means the provider registers as UNAVAILABLE."""

    anthropic_model: str = DEFAULT_MODEL
    """The model used when a request names no profile. Must be one ELA knows (:data:`MODELS`)."""

    anthropic_timeout_seconds: Annotated[float, Field(gt=0, le=MAX_TIMEOUT_SECONDS)] = (
        DEFAULT_TIMEOUT_SECONDS
    )

    anthropic_max_retries: Annotated[int, Field(ge=0, le=MAX_RETRIES_CEILING)] = DEFAULT_MAX_RETRIES
    """How many times a *retryable* failure is tried again. ``0`` disables retrying."""

    anthropic_max_output_tokens: Annotated[int, Field(gt=0)] = DEFAULT_MAX_OUTPUT_TOKENS
    """The output budget of a call that does not ask for one."""

    @field_validator("anthropic_api_key")
    @classmethod
    def _blank_key_is_no_key(cls, value: SecretStr | None) -> SecretStr | None:
        """``ELA_ANTHROPIC_API_KEY=""`` is an absent key, not an empty one (§33)."""
        if value is not None and value.get_secret_value().strip() == "":
            return None
        return value

    @field_validator("anthropic_model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        if value not in MODELS:
            raise ValueError(f"unknown model {value!r}: expected one of {sorted(MODELS)}")
        return value

    @model_validator(mode="after")
    def _budget_fits_the_model(self) -> AnthropicSettings:
        """A default budget larger than the default model can produce is a misconfiguration."""
        limit = MODELS[self.anthropic_model].max_output_tokens
        if self.anthropic_max_output_tokens > limit:
            raise ValueError(
                f"anthropic_max_output_tokens {self.anthropic_max_output_tokens} exceeds "
                f"the {limit} tokens {self.anthropic_model} can produce"
            )
        return self
