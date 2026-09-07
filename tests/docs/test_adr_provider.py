"""The tables of ADR 0020 and ``ela.providers`` say the same thing.

Four tables, four row shapes, so none is mistaken for another: §3 (the settings and their
defaults), §4 (the models, their limits and their prices), §5 (``model_hint`` -> model) and §7
(the SDK exceptions mapped onto ELA's error vocabulary). Prices and model limits are facts read
from a vendor's documentation on a given day: what this test can hold is that the document and
the code never drift apart, and the date in the ADR says when a human last checked the world.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

import ela.ports
import ela.tools
import ela.tools.model
from ela.ports import (
    PROVIDER_AUTHENTICATION_ERROR,
    PROVIDER_BAD_REQUEST,
    PROVIDER_ERROR_CODES,
    PROVIDER_MALFORMED_RESPONSE,
    PROVIDER_NO_OUTPUT,
    PROVIDER_RATE_LIMITED,
    PROVIDER_REFUSAL,
    PROVIDER_REJECTED,
    PROVIDER_SERVER_ERROR,
    PROVIDER_TIMEOUT,
    PROVIDER_UNAVAILABLE,
    PROVIDER_UNKNOWN_MODEL,
    PROVIDER_UNKNOWN_MODEL_HINT,
    PROVIDER_UNREACHABLE,
    PROVIDER_UNSUPPORTED_PARAMETER,
)
from ela.providers.anthropic.models import DEFAULT_MODEL, MODELS, PROFILES, model_for_hint
from ela.providers.anthropic.pricing import PRICES
from ela.providers.anthropic.provider import BACKOFF_BASE_SECONDS, BACKOFF_CAP_SECONDS
from ela.providers.anthropic.settings import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    RETIRED_SETTINGS,
    AnthropicSettings,
)

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0020-provider-anthropic.md"
MODEL_ROW = re.compile(
    r"^\| Claude [\w.\s]+ \| `([\w.-]+)` \| \S+ \| (\d+) \| (\d+) \| (\d+) \| (sì|no) \|$"
)
HINT_ROW = re.compile(r"^\| ((?:`\w+`(?:, )?)+) \| `([\w.-]+)` \|$")
ERROR_ROW = re.compile(r"^\| (.+) \| (.+) \| `(provider\.\w+)` \| (\*\*sì\*\*|no) \|$")
SETTING_ROW = re.compile(r"^\| `(ELA_\w+)` \| (.+) \| `?([\w.-]+)`? \| (.+) \|$")
CHECKED_ON = re.compile(r"^- \*\*Listino verificato il:\*\* (\d{4}-\d{2}-\d{2})")
MAX_PRICE_AGE_DAYS = 180
"""Six months. Prices are a fact about the world, and no test can watch the world: what the gate
can do is refuse to let the last human check drift out of sight (review of M7.1)."""
NAME = re.compile(r"`(\w+)`")
ABSENT = "assente"
"""How the §3 table writes a variable that has no default: the key is one of them."""


def adr_text() -> str:
    return ADR_PATH.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------------------
# §4 — the models and their prices
# ----------------------------------------------------------------------------------------


def documented_models(text: str) -> dict[str, tuple[int, Decimal, Decimal, bool]]:
    rows = {
        match.group(1): (
            int(match.group(2)),
            Decimal(match.group(3)),
            Decimal(match.group(4)),
            match.group(5) == "sì",
        )
        for line in text.splitlines()
        if (match := MODEL_ROW.match(line)) is not None
    }
    assert rows, "ADR 0020 §4 must contain the model table"
    return rows


def test_the_model_table_matches_the_code() -> None:
    rows = documented_models(adr_text())
    assert set(rows) == set(MODELS) == set(PRICES)
    for model_id, (max_output, price_in, price_out, effort) in rows.items():
        assert MODELS[model_id].max_output_tokens == max_output
        assert MODELS[model_id].supports_effort is effort
        assert PRICES[model_id].input == price_in
        assert PRICES[model_id].output == price_out


def documented_price_check(text: str) -> date:
    match = next(
        (CHECKED_ON.match(line) for line in text.splitlines() if CHECKED_ON.match(line)), None
    )
    assert match is not None, "ADR 0020 §6 must say when the prices were last checked"
    return date.fromisoformat(match.group(1))


def price_check_problem(checked: date, today: date) -> str | None:
    """Why this price check is not good enough, or ``None`` if it is (review of M7.1)."""
    if checked > today:
        return f"ADR 0020 §6 says the prices were checked on {checked}, which is in the future"
    age = (today - checked).days
    if age > MAX_PRICE_AGE_DAYS:
        return (
            f"the Anthropic prices in ADR 0020 §4 were last checked {age} days ago ({checked}). "
            "Re-verify them on platform.claude.com/docs/en/about-claude/pricing, update the table "
            "and ela/providers/anthropic/pricing.py if they changed, then update the date in §6."
        )
    return None


def test_the_prices_have_been_checked_recently() -> None:
    """The one thing no test can verify is whether the world still agrees with the table.

    So the gate holds the *reminder* instead: when the last human check is older than six months,
    this fails and says what to do. A constraint that lives in someone's memory has already
    expired.
    """
    assert price_check_problem(documented_price_check(adr_text()), date.today()) is None


def test_an_old_or_impossible_price_check_is_detected() -> None:
    """The negative case of the gate above, without waiting six months for it."""
    today = date(2027, 1, 1)
    fresh = today - timedelta(days=MAX_PRICE_AGE_DAYS)
    assert price_check_problem(fresh, today) is None

    stale = price_check_problem(fresh - timedelta(days=1), today)
    assert stale is not None
    assert "platform.claude.com" in stale
    assert str(MAX_PRICE_AGE_DAYS + 1) in stale

    ahead = price_check_problem(today + timedelta(days=1), today)
    assert ahead is not None and "in the future" in ahead

    with pytest.raises(AssertionError, match="when the prices were last checked"):
        documented_price_check("# 0020. Un ADR senza data\n")


def test_the_cache_read_rate_of_the_adr_is_a_tenth_of_the_input_price() -> None:
    """The ADR states the rule in words; the code states it in numbers, model by model."""
    assert "10% dell'input" in adr_text()
    for model_id, price in PRICES.items():
        assert price.cache_read == price.input / 10, model_id


def test_the_expensive_model_is_not_the_default() -> None:
    """The decision of §4, in the code: what starts by itself is the balanced profile.

    Since M7.3 that default is a constant and not a setting (ADR 0022 §8): what it answers is a
    request that names no profile, and the router names one on every call it makes."""
    assert "Il default è `claude-sonnet-5`, non il modello più potente" in adr_text()
    assert DEFAULT_MODEL == "claude-sonnet-5"
    model = model_for_hint(None)
    assert model is not None and model.id == DEFAULT_MODEL


def test_the_model_the_adr_leaves_out_is_not_in_the_code() -> None:
    assert "`claude-fable-5-1` resta fuori" in adr_text()
    assert "claude-fable-5-1" not in MODELS


# ----------------------------------------------------------------------------------------
# §5 — model_hint -> model
# ----------------------------------------------------------------------------------------


def documented_hints(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        match = HINT_ROW.match(line)
        if match is not None:
            for hint in NAME.findall(match.group(1)):
                rows[hint] = match.group(2)
    assert rows, "ADR 0020 §5 must contain the hint table"
    return rows


def test_the_hint_table_matches_the_code() -> None:
    rows = documented_hints(adr_text())
    assert rows == dict(PROFILES)
    for hint, model_id in rows.items():
        model = model_for_hint(hint)
        assert model is not None and model.id == model_id


def test_an_unmapped_hint_is_an_error_and_not_the_default() -> None:
    assert "`provider.unknown_model_hint`, **nessuna chiamata**" in adr_text()
    assert model_for_hint("telepathy") is None


# ----------------------------------------------------------------------------------------
# §7 — the error vocabulary
# ----------------------------------------------------------------------------------------


def documented_errors(text: str) -> dict[str, bool]:
    rows = {
        match.group(3): match.group(4) == "**sì**"
        for line in text.splitlines()
        if (match := ERROR_ROW.match(line)) is not None
    }
    assert rows, "ADR 0020 §7 must contain the error table"
    return rows


def test_the_error_table_is_exactly_the_vocabulary_of_the_port() -> None:
    assert set(documented_errors(adr_text())) == set(PROVIDER_ERROR_CODES)
    assert len(PROVIDER_ERROR_CODES) == 14


def test_an_answer_with_no_text_is_in_the_vocabulary_and_not_beside_it() -> None:
    """Review of M7.2: ``provider.no_output`` was a constant of ``ela.tools.model``.

    A code that names a provider failure and lives outside the closed set is what the closed set
    exists to forbid — a caller could not tell it from a code of its own making, which is the
    dependency §26 removes. The odd thing about it stays true and is written in §7: it is the one
    row that names a result nobody reported, an answer that arrived with nothing in it.
    """
    assert PROVIDER_NO_OUTPUT in PROVIDER_ERROR_CODES
    assert documented_errors(adr_text())[PROVIDER_NO_OUTPUT] is False
    assert "PROVIDER_NO_OUTPUT" in ela.ports.__all__
    assert "PROVIDER_NO_OUTPUT" not in ela.tools.model.__all__
    assert "PROVIDER_NO_OUTPUT" not in ela.tools.__all__


def test_a_turned_down_request_and_an_unreadable_answer_are_two_different_things() -> None:
    """Review of M7.1: a serialisation bug must not read as "your request was rejected"."""
    assert PROVIDER_REJECTED != PROVIDER_MALFORMED_RESPONSE
    assert {PROVIDER_REJECTED, PROVIDER_MALFORMED_RESPONSE} <= set(documented_errors(adr_text()))


def test_what_the_table_calls_retryable() -> None:
    """The rule of the milestone, read from the document: 429, 5xx and transport, no more."""
    rows = documented_errors(adr_text())
    retryable = {code for code, again in rows.items() if again}
    assert retryable == {
        PROVIDER_RATE_LIMITED,
        PROVIDER_SERVER_ERROR,
        PROVIDER_TIMEOUT,
        PROVIDER_UNREACHABLE,
    }
    assert not retryable & {
        PROVIDER_NO_OUTPUT,
        PROVIDER_AUTHENTICATION_ERROR,
        PROVIDER_BAD_REQUEST,
        PROVIDER_UNKNOWN_MODEL,
        PROVIDER_REJECTED,
        PROVIDER_MALFORMED_RESPONSE,
        PROVIDER_REFUSAL,
        PROVIDER_UNAVAILABLE,
        PROVIDER_UNKNOWN_MODEL_HINT,
        PROVIDER_UNSUPPORTED_PARAMETER,
    }


# ----------------------------------------------------------------------------------------
# §3 and §8 — the settings and the backoff
# ----------------------------------------------------------------------------------------


def documented_settings(text: str) -> dict[str, str]:
    rows = {
        match.group(1): match.group(3)
        for line in text.splitlines()
        if (match := SETTING_ROW.match(line)) is not None
    }
    assert rows, "ADR 0020 §3 must contain the settings table"
    return rows


def test_the_settings_table_matches_the_defaults() -> None:
    """ADR 0020 §3 documented five variables; ADR 0022 §8 retired one of them, and an ADR is not
    rewritten. What the code must have is what §3 declared **minus** what a later ADR retired."""
    rows = documented_settings(adr_text())
    assert set(rows) == {
        "ELA_ANTHROPIC_API_KEY",
        "ELA_ANTHROPIC_MODEL",
        "ELA_ANTHROPIC_TIMEOUT_SECONDS",
        "ELA_ANTHROPIC_MAX_RETRIES",
        "ELA_ANTHROPIC_MAX_OUTPUT_TOKENS",
    }
    assert set(rows) - set(RETIRED_SETTINGS) == {
        f"ELA_{name.upper()}"
        for name in AnthropicSettings.model_fields
        if name not in {"anthropic_model"}
    }
    settings = AnthropicSettings(_env_file=None)
    assert rows["ELA_ANTHROPIC_API_KEY"] == ABSENT
    assert settings.anthropic_api_key is None
    assert rows["ELA_ANTHROPIC_MODEL"] == DEFAULT_MODEL  # what it meant while it existed
    assert int(rows["ELA_ANTHROPIC_TIMEOUT_SECONDS"]) == DEFAULT_TIMEOUT_SECONDS == 60
    assert int(rows["ELA_ANTHROPIC_MAX_RETRIES"]) == DEFAULT_MAX_RETRIES == 2
    assert int(rows["ELA_ANTHROPIC_MAX_OUTPUT_TOKENS"]) == DEFAULT_MAX_OUTPUT_TOKENS == 4096


def test_the_retired_variable_is_the_one_a_later_adr_retired() -> None:
    """The settings a live ``AnthropicSettings`` reads are §3's minus ``ELA_ANTHROPIC_MODEL``,
    which ADR 0022 §8 retired and which is refused rather than ignored."""
    assert set(RETIRED_SETTINGS) == {"ELA_ANTHROPIC_MODEL"}
    assert "ELA_ANTHROPIC_MODEL" in documented_settings(adr_text())
    with pytest.raises(ValidationError, match="retired"):
        AnthropicSettings(_env_file=None, anthropic_model=DEFAULT_MODEL)


def test_the_backoff_of_the_adr_is_the_backoff_of_the_code() -> None:
    assert "`0.5 × 2ⁿ` secondi, con tetto **8 s**" in adr_text()
    assert BACKOFF_BASE_SECONDS == 0.5
    assert BACKOFF_CAP_SECONDS == 8.0
