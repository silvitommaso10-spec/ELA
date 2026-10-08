"""Haiku 5.5 and its two tiers of price (M14.6, ADR 0061): the tier is chosen by every input token
of the prompt, the true cost applies it to every token of the call, and the worst case of a call
is the dearest tier the window minus the output reaches.

The pricing page read on 2026-10-08: «Claude Haiku 5.5 is priced by prompt length: a prompt of
over 100,000 tokens pays higher prices» — up to 100 000 tokens $0.10 in, $0.50 out, $0.01 a cache
read per million; over, $0.50, $2.50 and $0.05.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ela.providers.anthropic import pricing
from ela.providers.anthropic.models import HAIKU_4_5, HAIKU_5_5, MODELS, OPUS_5_5, SONNET_5_5
from ela.providers.anthropic.pricing import (
    PRICES,
    TIERS,
    Price,
    estimate_cost,
    price_for,
    worst_cost,
)

MILLION = Decimal(1_000_000)
LOW = Price(Decimal("0.10"), Decimal("0.50"), Decimal("0.01"))
HIGH = Price(Decimal("0.50"), Decimal("2.50"), Decimal("0.05"))


def test_haiku_5_5_has_the_profile_the_models_page_gives() -> None:
    """``claude-haiku-5-5``: a window of a million tokens, 128K out, ``effort`` accepted."""
    model = MODELS[HAIKU_5_5]
    assert HAIKU_5_5 == "claude-haiku-5-5"
    assert (model.context_window, model.max_output_tokens, model.supports_effort) == (
        1_000_000,
        128_000,
        True,
    )


def test_the_two_tiers_are_the_prices_of_the_page() -> None:
    assert PRICES[HAIKU_5_5] == LOW
    assert TIERS[HAIKU_5_5] == ((100_000, HIGH),)


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [(0, LOW), (1, LOW), (100_000, LOW), (100_001, HIGH), (991_808, HIGH)],
)
def test_the_tier_is_the_one_of_the_prompt_s_input_tokens(tokens: int, expected: Price) -> None:
    assert price_for(HAIKU_5_5, tokens) == expected


def test_a_model_with_one_price_has_it_at_every_length() -> None:
    for model in (OPUS_5_5, SONNET_5_5, HAIKU_4_5):
        assert price_for(model, 0) == price_for(model, 999_999) == PRICES[model]


def test_a_model_with_no_price_has_no_tier() -> None:
    assert price_for("gpt-4", 10) is None


def test_the_true_cost_applies_the_tier_to_every_token_of_the_call() -> None:
    """«a prompt of over 100,000 tokens pays higher prices»: the whole prompt, not the part over."""
    low = estimate_cost(HAIKU_5_5, input_tokens=100_000, output_tokens=1_000, cached_input_tokens=0)
    high = estimate_cost(
        HAIKU_5_5, input_tokens=100_001, output_tokens=1_000, cached_input_tokens=0
    )
    assert low == (100_000 * LOW.input + 1_000 * LOW.output) / MILLION
    assert high == (100_001 * HIGH.input + 1_000 * HIGH.output) / MILLION


def test_the_tier_counts_the_tokens_read_from_the_cache_too() -> None:
    """Decision 27: every input token of the prompt, cache included — the reading that cannot
    choose a tier lower than the one billed."""
    cost = estimate_cost(
        HAIKU_5_5, input_tokens=60_000, output_tokens=0, cached_input_tokens=50_000
    )
    assert cost == (60_000 * HIGH.input + 50_000 * HIGH.cache_read) / MILLION


@pytest.mark.parametrize(
    ("output", "expected"),
    [(8_192, Decimal("0.516384")), (4_096, Decimal("0.508192"))],
)
def test_the_worst_case_of_haiku_5_5_is_the_high_tier_on_the_window(
    output: int, expected: Decimal
) -> None:
    """The window minus the output reaches the high tier at every allowed budget."""
    assert worst_cost(MODELS[HAIKU_5_5], output_tokens=output) == expected


def test_the_worst_case_is_the_dearest_tier_reached_not_the_last_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tier above that cost *less* — no page says so today — would not lower the bound: the worst
    case is the maximum over the tiers the input can reach."""
    cheaper = Price(Decimal("0.01"), Decimal("0.01"), Decimal("0"))
    monkeypatch.setattr(pricing, "TIERS", {HAIKU_5_5: ((100_000, cheaper),)})
    model = MODELS[HAIKU_5_5]
    assert (
        worst_cost(model, output_tokens=8_192)
        == ((model.context_window - 8_192) * LOW.input + 8_192 * LOW.output) / MILLION
    )


def test_a_tier_the_window_cannot_reach_is_not_the_worst_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dearer = Price(Decimal("100"), Decimal("100"), Decimal("0"))
    monkeypatch.setattr(pricing, "TIERS", {HAIKU_5_5: ((2_000_000, dearer),)})
    model = MODELS[HAIKU_5_5]
    assert (
        worst_cost(model, output_tokens=8_192)
        == ((model.context_window - 8_192) * LOW.input + 8_192 * LOW.output) / MILLION
    )
