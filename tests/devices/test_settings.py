"""``DeviceSettings`` (ADR 0016 §3): one variable, a sensible default, a strictly positive TTL."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from ela.devices import DEFAULT_HEARTBEAT_TTL_SECONDS, DeviceSettings

VARIABLE = "ELA_DEVICE_HEARTBEAT_TTL_SECONDS"


def test_default_is_a_minute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)
    settings = DeviceSettings(_env_file=None)
    assert settings.device_heartbeat_ttl_seconds == DEFAULT_HEARTBEAT_TTL_SECONDS == 60
    assert settings.heartbeat_ttl == timedelta(seconds=60)


def test_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VARIABLE, "5")
    assert DeviceSettings(_env_file=None).heartbeat_ttl == timedelta(seconds=5)


@pytest.mark.parametrize("value", ["0", "-1"])
def test_a_non_positive_ttl_is_refused(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """A TTL of zero would make every node unavailable the instant it reported."""
    monkeypatch.setenv(VARIABLE, value)
    with pytest.raises(ValidationError):
        DeviceSettings(_env_file=None)


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELA_SOMETHING_ELSE", "1")
    DeviceSettings(_env_file=None)


def test_dotenv_file_is_read_when_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(VARIABLE, raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"{VARIABLE}=30\n", encoding="utf-8")
    assert DeviceSettings(_env_file=dotenv).heartbeat_ttl == timedelta(seconds=30)
