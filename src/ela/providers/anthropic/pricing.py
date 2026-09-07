"""What a call costs, estimated from the tokens it used (§32 "provider usage metadata").

Prices are per million tokens, in USD, from the official pricing table read on **2026-09-07**;
ADR 0020 §6 carries the same numbers and ``tests/docs/test_adr_provider.py`` keeps the two equal.
They are a **stima**: the invoice is Anthropic's, this is what ELA believes it spent.

Two rules keep the estimate honest:

* ``Decimal``, never ``float``: money that goes through binary floating point stops adding up.
* A model the table does not price gives ``None``, never ``0``. Zero is a number and would be
  summed into a total as if the call were free; ``None`` says "I do not know" (§33).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Final

from ela.providers.anthropic.models import HAIKU_4_5, OPUS_5, SONNET_5

__all__ = ["CURRENCY", "PRICES", "Price", "estimate_cost"]

CURRENCY: Final = "USD"
"""Anthropic bills in dollars; the domain keeps the currency next to the amount for that reason."""

PER_MILLION: Final = Decimal(1_000_000)
CENTS_OF_A_MICRO_DOLLAR: Final = Decimal("0.00000001")
"""Eight decimals: a short Haiku call costs less than a millionth of a dollar, and rounding it
to zero would make a long series of cheap calls look free."""


@dataclass(frozen=True, slots=True)
class Price:
    """Dollars per million tokens. ``cache_read`` is 10% of ``input`` on every current model."""

    input: Decimal
    output: Decimal
    cache_read: Decimal


PRICES: Final[Mapping[str, Price]] = MappingProxyType(
    {
        OPUS_5: Price(Decimal("5"), Decimal("25"), Decimal("0.5")),
        SONNET_5: Price(Decimal("2"), Decimal("10"), Decimal("0.2")),
        HAIKU_4_5: Price(Decimal("1"), Decimal("5"), Decimal("0.1")),
    }
)


def estimate_cost(
    model: str, *, input_tokens: int, output_tokens: int, cached_input_tokens: int | None
) -> Decimal | None:
    """What those tokens cost on that model, or ``None`` if the model has no price here.

    Cached input is billed at its own (lower) rate and is *not* part of ``input_tokens``: the API
    reports the two separately, and adding them would charge the cache at the full price.
    """
    price = PRICES.get(model)
    if price is None:
        return None
    cost = (
        price.input * input_tokens
        + price.output * output_tokens
        + price.cache_read * (cached_input_tokens or 0)
    ) / PER_MILLION
    return cost.quantize(CENTS_OF_A_MICRO_DOLLAR)
