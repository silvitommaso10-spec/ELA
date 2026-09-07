"""The Anthropic adapter: the only place in ELA where the vendor's SDK exists (ADR 0020).

``anthropic_provider`` is how the rest of the world builds one. It reads the configuration, and
builds an SDK client **only** if ELA was given a key — always passing it explicitly, never letting
the SDK look for credentials of its own (``settings.py`` explains why that matters).
"""

from __future__ import annotations

from anthropic import AsyncAnthropic

from ela.ports import Clock, IdGenerator
from ela.providers.anthropic.errors import Failure, UnsupportedRequestError, classify
from ela.providers.anthropic.models import DEFAULT_MODEL, MODELS, PROFILES, Model, model_for_hint
from ela.providers.anthropic.payload import ALLOWED_PARAMETERS, build_payload
from ela.providers.anthropic.pricing import CURRENCY, PRICES, Price, estimate_cost
from ela.providers.anthropic.provider import (
    BACKOFF_BASE_SECONDS,
    BACKOFF_CAP_SECONDS,
    PROVIDER_NAME,
    AnthropicProvider,
)
from ela.providers.anthropic.settings import AnthropicSettings

__all__ = [
    "ALLOWED_PARAMETERS",
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_CAP_SECONDS",
    "CURRENCY",
    "DEFAULT_MODEL",
    "MODELS",
    "PRICES",
    "PROFILES",
    "PROVIDER_NAME",
    "AnthropicProvider",
    "AnthropicSettings",
    "Failure",
    "Model",
    "Price",
    "UnsupportedRequestError",
    "anthropic_provider",
    "build_payload",
    "classify",
    "estimate_cost",
    "model_for_hint",
]


def anthropic_provider(
    clock: Clock, ids: IdGenerator, *, settings: AnthropicSettings | None = None
) -> AnthropicProvider:
    """Build the provider from the environment: with a key it is AVAILABLE, without it is not.

    The SDK's own retrying is switched off (``max_retries=0``): ELA retries, so that the policy
    is one policy and a testable one (ADR 0020 §8).
    """
    settings = AnthropicSettings() if settings is None else settings
    key = settings.anthropic_api_key
    client = (
        None
        if key is None
        else AsyncAnthropic(
            api_key=key.get_secret_value(),
            timeout=settings.anthropic_timeout_seconds,
            max_retries=0,
        )
    )
    return AnthropicProvider(client, clock=clock, ids=ids, settings=settings)
