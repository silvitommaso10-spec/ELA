"""The cost estimate (ADR 0020 §6, ADR 0057): Decimal money, ``None`` where the price is unknown,
and the worst case a cap reserves before a call (M14.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ela.providers.anthropic import pricing
from ela.providers.anthropic.models import HAIKU_4_5, MODELS, OPUS_5_5, SONNET_5_5, Model
from ela.providers.anthropic.pricing import CURRENCY, PRICES, Price, estimate_cost, worst_cost


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # 1000 input + 400 output, priced per million: e.g. (1000×$4 + 400×$20) / 1_000_000.
        (OPUS_5_5, Decimal("0.012")),
        (SONNET_5_5, Decimal("0.006")),
        (HAIKU_4_5, Decimal("0.003")),
    ],
)
def test_a_thousand_in_and_four_hundred_out(model: str, expected: Decimal) -> None:
    cost = estimate_cost(model, input_tokens=1_000, output_tokens=400, cached_input_tokens=None)
    assert cost == expected


def test_cached_input_is_billed_at_its_own_rate() -> None:
    """A cached token is a tenth of an input token; adding the two would overcharge the cache."""
    full = estimate_cost(SONNET_5_5, input_tokens=1_000, output_tokens=0, cached_input_tokens=None)
    cached = estimate_cost(SONNET_5_5, input_tokens=0, output_tokens=0, cached_input_tokens=1_000)
    assert full == Decimal("0.002")
    assert cached == Decimal("0.0002")


def test_no_tokens_costs_nothing_on_a_known_model() -> None:
    assert estimate_cost(SONNET_5_5, input_tokens=0, output_tokens=0, cached_input_tokens=0) == 0


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


def test_the_cache_read_rate_is_a_twentieth_on_opus_5_5_and_a_tenth_elsewhere() -> None:
    """The pricing page of 2026-10-06: Opus 5.5 reads its cache at 0.05×, the other two at 0.1×."""
    assert PRICES[OPUS_5_5].cache_read == PRICES[OPUS_5_5].input / 20
    assert PRICES[SONNET_5_5].cache_read == PRICES[SONNET_5_5].input / 10
    assert PRICES[HAIKU_4_5].cache_read == PRICES[HAIKU_4_5].input / 10


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # (window − 4096) × input + 4096 × output, per million: the numbers of ADR 0057.
        (OPUS_5_5, Decimal("4.065536")),
        (SONNET_5_5, Decimal("2.032768")),
        (HAIKU_4_5, Decimal("0.216384")),
    ],
)
def test_the_worst_case_fills_the_window_with_input_and_the_budget_with_output(
    model: str, expected: Decimal
) -> None:
    assert worst_cost(MODELS[model], output_tokens=4_096) == expected


def test_the_worst_case_is_never_below_a_call_that_fits_the_window() -> None:
    """Any split of the window under the budget costs no more than the worst case: the bound holds
    because an output token costs more than an input one."""
    model = MODELS[HAIKU_4_5]
    worst = worst_cost(model, output_tokens=4_096)
    assert worst is not None
    for output in (0, 1, 2_048, 4_096):
        cost = estimate_cost(
            HAIKU_4_5,
            input_tokens=model.context_window - output,
            output_tokens=output,
            cached_input_tokens=None,
        )
        assert cost is not None and cost <= worst


def test_a_model_with_no_price_has_no_worst_case() -> None:
    """``None`` is not ``0``: with a cap, a call nobody can bound is a call that is not made."""
    unknown = Model("gpt-4", max_output_tokens=4_096, supports_effort=False, context_window=8_192)
    assert worst_cost(unknown, output_tokens=1_000) is None


def test_the_worst_case_is_rounded_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bound rounded down is not a bound: what lies beyond the eighth decimal goes up.

    Today's prices are whole dollars per million and never reach the ninth decimal, so the price
    that does is the test's own."""
    third = Price(Decimal("0.000000333"), Decimal("0.000000333"), Decimal("0"))
    monkeypatch.setattr(pricing, "PRICES", {HAIKU_4_5: third})
    model = Model(HAIKU_4_5, max_output_tokens=3, supports_effort=False, context_window=3)
    assert worst_cost(model, output_tokens=1) == Decimal("0.00000001")
