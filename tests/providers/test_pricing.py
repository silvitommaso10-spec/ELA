"""The cost estimate (ADR 0020 §6): Decimal money, and ``None`` where the price is unknown."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ela.providers.anthropic.models import HAIKU_4_5, MODELS, OPUS_5, SONNET_5
from ela.providers.anthropic.pricing import CURRENCY, PRICES, estimate_cost


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # 1000 input + 400 output, priced per million: e.g. (1000×$5 + 400×$25) / 1_000_000.
        (OPUS_5, Decimal("0.015")),
        (SONNET_5, Decimal("0.006")),
        (HAIKU_4_5, Decimal("0.003")),
    ],
)
def test_a_thousand_in_and_four_hundred_out(model: str, expected: Decimal) -> None:
    cost = estimate_cost(model, input_tokens=1_000, output_tokens=400, cached_input_tokens=None)
    assert cost == expected


def test_cached_input_is_billed_at_its_own_rate() -> None:
    """A cached token is a tenth of an input token; adding the two would overcharge the cache."""
    full = estimate_cost(SONNET_5, input_tokens=1_000, output_tokens=0, cached_input_tokens=None)
    cached = estimate_cost(SONNET_5, input_tokens=0, output_tokens=0, cached_input_tokens=1_000)
    assert full == Decimal("0.002")
    assert cached == Decimal("0.0002")


def test_no_tokens_costs_nothing_on_a_known_model() -> None:
    assert estimate_cost(SONNET_5, input_tokens=0, output_tokens=0, cached_input_tokens=0) == 0


def test_an_unknown_model_has_no_price_and_no_zero() -> None:
    """``0`` would be summed into a total as if the call were free; ``None`` says: unknown."""
    assert estimate_cost("gpt-4", input_tokens=10, output_tokens=10, cached_input_tokens=0) is None


def test_a_small_call_is_not_rounded_down_to_free() -> None:
    cost = estimate_cost(HAIKU_4_5, input_tokens=3, output_tokens=1, cached_input_tokens=None)
    assert cost is not None and cost > 0


def test_money_is_decimal_not_float() -> None:
    for price in PRICES.values():
        assert isinstance(price.input, Decimal)
        assert isinstance(price.output, Decimal)
        assert isinstance(price.cache_read, Decimal)


def test_every_model_ela_uses_has_a_price() -> None:
    assert set(PRICES) == set(MODELS)
    assert CURRENCY == "USD"


def test_the_cache_read_rate_is_a_tenth_of_the_input_rate() -> None:
    for price in PRICES.values():
        assert price.cache_read == price.input / 10
