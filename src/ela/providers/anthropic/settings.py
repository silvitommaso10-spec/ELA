"""How the Anthropic provider is configured, from the environment (ADR 0001, ADR 0020 §3).

Four variables, all with the ``ELA_`` prefix, in the shape ``PersistenceSettings``,
``WorkspaceSettings`` and ``DeviceSettings`` already have; M8.1 will unify the four. A fifth,
``ELA_ANTHROPIC_MODEL``, was **retired** in M7.3 and is refused rather than ignored (see
:data:`RETIRED_SETTINGS`).

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

from collections.abc import Mapping
from types import MappingProxyType
from typing import Annotated, Final

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ela.providers.anthropic.models import LARGEST_OUTPUT_TOKENS

__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "RETIRED_SETTINGS",
    "AnthropicSettings",
]

RETIRED_SETTINGS: Final[Mapping[str, str]] = MappingProxyType(
    {"ELA_ANTHROPIC_MODEL": "ELA_MODEL_ROUTES and ELA_MODEL_DEFAULT_ROUTE"}
)
"""Variables ELA used to read, and what replaces them (ADR 0022 §8).

A retired variable is **refused**, not ignored: ``extra="ignore"`` would let a machine that still
sets ``ELA_ANTHROPIC_MODEL=claude-opus-5`` start and quietly answer with whatever the routing
table says, and the operator would have no way to learn that the knob stopped working. A setting
that silently does nothing is worse than one that is gone, so it is gone *and* it says so — once,
at start-up, naming the replacement (§33).

The field stays declared below so the refusal covers every source pydantic-settings reads: the
environment, a ``.env`` file, and a keyword argument.
"""

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

    anthropic_model: str | None = None
    """``ELA_ANTHROPIC_MODEL``, **retired** in M7.3: a tombstone, never a value.

    Which model answers is the routing table's decision (§25, ADR 0022): the profile of the route
    reaches the adapter as ``ProviderRequest.model_hint`` and is translated there (ADR 0020 §5).
    Setting this variable is refused with the name of what to set instead."""

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

    @model_validator(mode="after")
    def _no_retired_setting(self) -> AnthropicSettings:
        """A retired variable stops ELA at start-up and names its replacement (ADR 0022 §8)."""
        if self.anthropic_model is not None:
            variable, replacement = next(iter(RETIRED_SETTINGS.items()))
            raise ValueError(
                f"{variable} was retired in M7.3: which model answers is decided by the routing "
                f"table (spec §25, ADR 0022). Remove it and set {replacement} instead."
            )
        return self

    @model_validator(mode="after")
    def _budget_fits_a_model(self) -> AnthropicSettings:
        """A default budget larger than **any** model can produce is a misconfiguration.

        Not "larger than the default model": there is no configured default model any more, and a
        budget above one model but within another is clamped per model when the payload is built
        (``payload.build_payload``), which is a smaller model answering, not an error.
        """
        if self.anthropic_max_output_tokens > LARGEST_OUTPUT_TOKENS:
            raise ValueError(
                f"anthropic_max_output_tokens {self.anthropic_max_output_tokens} exceeds "
                f"the {LARGEST_OUTPUT_TOKENS} tokens the largest model can produce"
            )
        return self
