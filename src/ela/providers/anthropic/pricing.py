"""What a call costs, estimated from the tokens it used (§32 "provider usage metadata").

Prices are per million tokens, in USD, from the official pricing table read on **2026-10-08**
(M14.6); ADR 0061 carries the same numbers — it revises ADR 0057 §3, read on 2026-10-06, which
revised ADR 0020 §6 — and ``tests/docs/test_adr_provider.py`` keeps the two equal. They are a
**stima**: the invoice is Anthropic's, this is what ELA believes it spent.

Since M14.6 a model can have **tiers**: Haiku 5.5 "is priced by prompt length: a prompt of over
100,000 tokens pays higher prices". :data:`PRICES` keeps the price of a short prompt, :data:`TIERS`
the prices above it, and :func:`price_for` is the one place that chooses.

Two rules keep the estimate honest:

* ``Decimal``, never ``float``: money that goes through binary floating point stops adding up.
* A model the table does not price gives ``None``, never ``0``. Zero is a number and would be
  summed into a total as if the call were free; ``None`` says "I do not know" (§33).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from types import MappingProxyType
from typing import Final

from ela.providers.anthropic.models import HAIKU_4_5, HAIKU_5_5, OPUS_5_5, SONNET_5_5, Model

__all__ = ["CURRENCY", "PRICES", "TIERS", "Price", "estimate_cost", "price_for", "worst_cost"]

CURRENCY: Final = "USD"
"""Anthropic bills in dollars; the domain keeps the currency next to the amount for that reason."""

PER_MILLION: Final = Decimal(1_000_000)
CENTS_OF_A_MICRO_DOLLAR: Final = Decimal("0.00000001")
"""Eight decimals: a short Haiku call costs less than a millionth of a dollar, and rounding it
to zero would make a long series of cheap calls look free."""


@dataclass(frozen=True, slots=True)
class Price:
    """Dollars per million tokens, for one tier. ``cache_read`` is 5% of ``input`` on Opus 5.5 and
    Sonnet 5.5, 10% on Haiku 4.5 and Haiku 5.5 (the pricing page, 2026-10-08)."""

    input: Decimal
    output: Decimal
    cache_read: Decimal


PRICES: Final[Mapping[str, Price]] = MappingProxyType(
    {
        OPUS_5_5: Price(Decimal("4"), Decimal("20"), Decimal("0.2")),
        SONNET_5_5: Price(Decimal("2"), Decimal("10"), Decimal("0.1")),
        HAIKU_5_5: Price(Decimal("0.10"), Decimal("0.50"), Decimal("0.01")),
        HAIKU_4_5: Price(Decimal("1"), Decimal("5"), Decimal("0.1")),
    }
)
"""Each model's price for a short prompt — the only price of a model without :data:`TIERS`."""

TIERS: Final[Mapping[str, tuple[tuple[int, Price], ...]]] = MappingProxyType(
    {
        HAIKU_5_5: ((100_000, Price(Decimal("0.50"), Decimal("2.50"), Decimal("0.05"))),),
    }
)
"""The prices above a model's first, in ascending order: ``(bound, price)`` is the price of a
prompt of **over** ``bound`` input tokens (M14.6, ADR 0061). The page calls the length "prompt" and
does not count it token by token: ELA counts every input token of the call, cache included — the
reading that can never choose a tier lower than the one billed (review of M14.3, decision 27)."""


def price_for(model: str, input_tokens: int) -> Price | None:
    """The price of a call to ``model`` whose prompt is ``input_tokens`` long, or ``None`` if the
    model has no price here. Every input token counts: the ones billed as input and the ones read
    from the cache."""
    price = PRICES.get(model)
    if price is None:
        return None
    for bound, above in TIERS.get(model, ()):
        if input_tokens > bound:
            price = above
    return price


def estimate_cost(
    model: str, *, input_tokens: int, output_tokens: int, cached_input_tokens: int | None
) -> Decimal | None:
    """What those tokens cost on that model, or ``None`` if the model has no price here.

    Cached input is billed at its own (lower) rate and is *not* part of ``input_tokens``: the API
    reports the two separately, and adding them would charge the cache at the full price. The two
    together are the prompt, and its length chooses the tier, which then prices **every** token of
    the call: "a prompt of over 100,000 tokens pays higher prices" (M14.6).
    """
    price = price_for(model, input_tokens + (cached_input_tokens or 0))
    if price is None:
        return None
    cost = (
        price.input * input_tokens
        + price.output * output_tokens
        + price.cache_read * (cached_input_tokens or 0)
    ) / PER_MILLION
    return cost.quantize(CENTS_OF_A_MICRO_DOLLAR)


def worst_cost(model: Model, *, output_tokens: int) -> Decimal | None:
    """The most a call with this output budget can cost on this model, or ``None`` with no price.

    Input and output billed together fit in the context window, the output stays under
    ``output_tokens``, and an output token costs more than an input one: the worst case is the
    window filled with input up to the output budget, and the budget filled with output (M14.1,
    ADR 0057). No cache is ever asked for, so no cache write is priced. Rounded **up** to the
    eighth decimal: an upper bound that rounded down would not be one.

    With tiers, the bound is the **dearest** tier that input can reach — not the last one, and not
    one the window cannot reach (M14.6, ADR 0061): the input is still the window, never a length
    read from the request (review of M14.3, decision 26).
    """
    price = PRICES.get(model.id)
    if price is None:
        return None
    input_tokens = model.context_window - output_tokens
    reached = [price] + [above for bound, above in TIERS.get(model.id, ()) if input_tokens > bound]
    cost = max(
        (tier.input * input_tokens + tier.output * output_tokens) / PER_MILLION for tier in reached
    )
    return cost.quantize(CENTS_OF_A_MICRO_DOLLAR, rounding=ROUND_CEILING)
