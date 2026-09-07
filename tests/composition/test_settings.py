"""``Settings`` (ADR 0023 §2, §3): one place reads the environment, and says what is wrong.

What is under test is not pydantic. It is that ELA **does not start** on a configuration it
cannot honour, that each refusal names the variable and what to do with it, and that the five
settings classes that existed before M8.1 still work on their own.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from ela.composition import (
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_ORPHAN_AFTER_SECONDS,
    DEFAULT_USER_NAME,
    MIN_TOKEN_LENGTH,
    ApiSettings,
    ConfigurationError,
    CoreSettings,
    Settings,
)
from ela.devices.settings import DeviceSettings
from ela.executive import DEFAULT_APPROVAL_TTL, MAX_APPROVAL_TTL
from ela.permissions import DEFAULT_AUTHORIZATION_TTL, MAX_AUTHORIZATION_TTL
from ela.routing import DEFAULT_ROUTES
from tests.composition.support import API_TOKEN, TOKEN, declare


def loaded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> Settings:
    declare(monkeypatch, tmp_path, **extra)
    return Settings.load()


def refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, **extra: str) -> str:
    declare(monkeypatch, tmp_path, **extra)
    with pytest.raises(ConfigurationError) as raised:
        Settings.load()
    return str(raised.value)


# ----------------------------------------------------------------------------------------
# What ELA reads when nobody configured anything
# ----------------------------------------------------------------------------------------


def test_the_defaults_are_the_ones_the_adr_documents(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = loaded(monkeypatch, tmp_path)

    assert settings.api.api_host == DEFAULT_API_HOST == "127.0.0.1"
    assert settings.api.api_port == DEFAULT_API_PORT
    assert settings.api.token == TOKEN
    assert settings.core.user_name == DEFAULT_USER_NAME
    assert settings.core.authorization_ttl == DEFAULT_AUTHORIZATION_TTL
    assert settings.core.approval_ttl == DEFAULT_APPROVAL_TTL
    assert settings.core.orphan_after == timedelta(seconds=DEFAULT_ORPHAN_AFTER_SECONDS)
    assert settings.routing.model_routes == dict(DEFAULT_ROUTES)
    assert settings.anthropic.anthropic_api_key is None  # ELA starts without a key


def test_the_seven_are_composed_and_each_still_stands_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unifying the point of reading, not the classes: ADR 0023 §2."""
    settings = loaded(monkeypatch, tmp_path, ELA_DEVICE_HEARTBEAT_TTL_SECONDS="30")

    assert settings.devices.heartbeat_ttl == timedelta(seconds=30)
    assert DeviceSettings().heartbeat_ttl == settings.devices.heartbeat_ttl


def test_settings_are_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = loaded(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="frozen"):
        settings.api = settings.api  # type: ignore[misc]


def test_the_environment_overrides_every_new_variable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = loaded(
        monkeypatch,
        tmp_path,
        ELA_API_HOST="::1",
        ELA_API_PORT="9000",
        ELA_USER_NAME="tommaso",
        ELA_AUTHORIZATION_TTL_SECONDS="60",
        ELA_APPROVAL_TTL_SECONDS="120",
        ELA_TASK_ORPHAN_AFTER_SECONDS="30",
    )

    assert settings.api.api_host == "::1"
    assert settings.api.api_port == 9000
    assert settings.core.user_name == "tommaso"
    assert settings.core.authorization_ttl == timedelta(seconds=60)
    assert settings.core.approval_ttl == timedelta(seconds=120)
    assert settings.core.orphan_after == timedelta(seconds=30)


# ----------------------------------------------------------------------------------------
# The token: ELA does not open an unauthenticated API
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["", "   "], ids=["empty", "blank"])
def test_a_missing_token_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    message = refused(monkeypatch, tmp_path, ELA_API_TOKEN=value)

    assert API_TOKEN in message
    assert "secrets.token_urlsafe" in message  # it says how to make one


def test_no_token_at_all_stops_ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    declare(monkeypatch, tmp_path)
    monkeypatch.delenv(API_TOKEN)

    with pytest.raises(ConfigurationError) as raised:
        Settings.load()
    assert API_TOKEN in str(raised.value)


def test_a_short_token_stops_ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    message = refused(monkeypatch, tmp_path, ELA_API_TOKEN="x" * (MIN_TOKEN_LENGTH - 1))

    assert API_TOKEN in message
    assert str(MIN_TOKEN_LENGTH) in message


def test_a_token_is_stripped_and_never_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = loaded(monkeypatch, tmp_path, ELA_API_TOKEN=f"  {TOKEN}  ")

    assert settings.api.token == TOKEN
    assert TOKEN not in repr(settings)  # a SecretStr, so a traceback cannot leak it
    assert TOKEN not in str(settings.api.api_token)


# ----------------------------------------------------------------------------------------
# The address: loopback, and nothing else (ADR 0023 §7)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.5", "::1", "localhost"])
def test_loopback_addresses_are_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str
) -> None:
    assert loaded(monkeypatch, tmp_path, ELA_API_HOST=host).api.api_host == host


@pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.4", "192.168.1.10", "example.com", ""])
def test_anything_else_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str
) -> None:
    """A name is not resolved to find out: what a name resolves to can change after the check."""
    message = refused(monkeypatch, tmp_path, ELA_API_HOST=host)

    assert "ELA_API_HOST" in message
    assert "loopback" in message


@pytest.mark.parametrize("port", ["0", "70000", "-1"])
def test_a_port_outside_the_range_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, port: str
) -> None:
    assert "ELA_API_PORT" in refused(monkeypatch, tmp_path, ELA_API_PORT=port)


# ----------------------------------------------------------------------------------------
# The three durations: no TTL without a ceiling (ADR 0012, ADR 0013)
# ----------------------------------------------------------------------------------------


def test_a_grant_may_not_outlive_its_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    over = int(MAX_AUTHORIZATION_TTL.total_seconds()) + 1
    message = refused(monkeypatch, tmp_path, ELA_AUTHORIZATION_TTL_SECONDS=str(over))

    assert "ELA_AUTHORIZATION_TTL_SECONDS" in message
    assert (
        loaded(
            monkeypatch, tmp_path, ELA_AUTHORIZATION_TTL_SECONDS=str(over - 1)
        ).core.authorization_ttl
        == MAX_AUTHORIZATION_TTL
    )


def test_a_request_for_consent_may_not_outlive_its_ceiling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    over = int(MAX_APPROVAL_TTL.total_seconds()) + 1
    message = refused(monkeypatch, tmp_path, ELA_APPROVAL_TTL_SECONDS=str(over))

    assert "ELA_APPROVAL_TTL_SECONDS" in message


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("ELA_AUTHORIZATION_TTL_SECONDS", "0"),
        ("ELA_APPROVAL_TTL_SECONDS", "0"),
        ("ELA_TASK_ORPHAN_AFTER_SECONDS", "0"),
        ("ELA_USER_NAME", ""),
    ],
)
def test_a_duration_of_zero_and_a_nameless_user_stop_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str, value: str
) -> None:
    assert variable in refused(monkeypatch, tmp_path, **{variable: value})


# ----------------------------------------------------------------------------------------
# What the other ADRs already refused, now said in one voice
# ----------------------------------------------------------------------------------------


def test_the_retired_variable_stops_ela_and_names_its_replacement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ADR 0022 §8, through ``Settings.load``: a whole-model check has no field to point at, so
    its own message is quoted as it stands."""
    message = refused(monkeypatch, tmp_path, ELA_ANTHROPIC_MODEL="claude-opus-5")

    assert "ELA_ANTHROPIC_MODEL" in message
    assert "ELA_MODEL_ROUTES" in message
    assert "ELA_ANTHROPIC_MODEL:" not in message  # not a field of a variable, a variable


def test_an_unreadable_routing_table_stops_ela(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Malformed JSON is a ``SettingsError``, not a ``ValidationError``: it must not escape as
    a stack trace either."""
    message = refused(monkeypatch, tmp_path, ELA_MODEL_ROUTES="{not json")

    assert "ELA_MODEL_ROUTES" in message


def test_a_blank_task_type_stops_ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    table = json.dumps({" ": {"providers": ["anthropic"], "profile": "cheap"}})
    message = refused(monkeypatch, tmp_path, ELA_MODEL_ROUTES=table)

    assert "ELA_MODEL_ROUTES" in message


def test_the_settings_of_the_api_and_the_core_are_readable_on_their_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)

    assert ApiSettings().token == TOKEN
    assert CoreSettings().user_name == DEFAULT_USER_NAME
