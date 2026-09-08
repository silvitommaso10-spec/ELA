"""``ElevenLabsSettings`` (ADR 0034 §5, §6): one host, measured models, two absences.

The tests that matter here are not about pydantic. They are about three decisions that would be
invisible in a diff if nobody asserted them: the endpoint is not configurable, the model is one
somebody has measured, and "no key" and "no voice" stay two facts.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ela.providers.elevenlabs import (
    AUDIO_BYTES_PER_SECOND,
    AUDIO_FORMAT,
    DEFAULT_MODEL,
    ELEVENLABS_API,
    MAX_AUDIO_BYTES,
    MODELS,
    ElevenLabsSettings,
)
from ela.providers.elevenlabs.settings import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    PLAYBACK_SLACK_SECONDS,
)

KEY = "ELA_ELEVENLABS_API_KEY"
VOICE = "ELA_ELEVENLABS_VOICE_ID"
MODEL = "ELA_ELEVENLABS_MODEL"


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in (
        KEY,
        VOICE,
        MODEL,
        "ELEVENLABS_API_KEY",
        "ELA_ELEVENLABS_TIMEOUT_SECONDS",
        "ELA_ELEVENLABS_MAX_RETRIES",
    ):
        monkeypatch.delenv(variable, raising=False)


def test_defaults() -> None:
    settings = ElevenLabsSettings(_env_file=None)
    assert settings.elevenlabs_api_key is None
    assert settings.elevenlabs_voice_id is None
    assert settings.elevenlabs_model == DEFAULT_MODEL == "eleven_flash_v2_5"
    assert settings.elevenlabs_timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 15.0
    assert settings.elevenlabs_max_retries == DEFAULT_MAX_RETRIES == 1


def test_the_default_model_is_the_one_that_does_not_leave_the_user_in_silence() -> None:
    """Measured at the ceiling: 1,24 s against 5,62 s, and half the credits (ADR 0034 §5).

    A default is what runs when nobody has listened yet, and dead air is what the user pays.
    """
    assert DEFAULT_MODEL == "eleven_flash_v2_5"
    assert "eleven_multilingual_v2" in MODELS, "still available: the audition decides by ear"


def test_the_key_is_read_from_elas_own_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_someone_elses")
    monkeypatch.setenv(KEY, "sk_elas_own")
    settings = ElevenLabsSettings(_env_file=None)
    assert settings.elevenlabs_api_key is not None
    assert settings.elevenlabs_api_key.get_secret_value() == "sk_elas_own"


def test_the_vendors_own_variable_is_not_a_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0020 §3 applied again: ELA does not spend a credential it was not given."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk_someone_elses")
    assert ElevenLabsSettings(_env_file=None).elevenlabs_api_key is None


def test_the_secret_does_not_appear_in_the_representation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(KEY, "sk_secret_value")
    settings = ElevenLabsSettings(_env_file=None)
    assert "sk_secret_value" not in repr(settings)
    assert "sk_secret_value" not in str(settings.model_dump())


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_key_is_no_key(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(KEY, value)
    assert ElevenLabsSettings(_env_file=None).elevenlabs_api_key is None


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_voice_is_no_voice(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(VOICE, value)
    assert ElevenLabsSettings(_env_file=None).elevenlabs_voice_id is None


def test_a_voice_is_read_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VOICE, "VZOd9FMXDnXRZpGn0thg")
    assert ElevenLabsSettings(_env_file=None).elevenlabs_voice_id == "VZOd9FMXDnXRZpGn0thg"


def test_the_key_and_the_voice_are_two_absences(monkeypatch: pytest.MonkeyPatch) -> None:
    """One is a credential, the other a choice nobody has made: they do not collapse into one."""
    monkeypatch.setenv(KEY, "sk_present")
    settings = ElevenLabsSettings(_env_file=None)
    assert settings.elevenlabs_api_key is not None
    assert settings.elevenlabs_voice_id is None


def test_an_unmeasured_model_stops_ela(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not ignored, not accepted: refused, with the names ELA has actually measured (§33)."""
    monkeypatch.setenv(MODEL, "eleven_v3")
    with pytest.raises(ValidationError, match="unknown model 'eleven_v3'"):
        ElevenLabsSettings(_env_file=None)


@pytest.mark.parametrize("model", sorted(MODELS))
def test_every_measured_model_is_accepted(monkeypatch: pytest.MonkeyPatch, model: str) -> None:
    monkeypatch.setenv(MODEL, model)
    assert ElevenLabsSettings(_env_file=None).elevenlabs_model == model


@pytest.mark.parametrize("value", ["0", "-1", str(MAX_TIMEOUT_SECONDS + 1)])
def test_the_timeout_has_a_floor_and_a_ceiling(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("ELA_ELEVENLABS_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        ElevenLabsSettings(_env_file=None)


@pytest.mark.parametrize("value", ["-1", "6"])
def test_the_retries_have_a_ceiling(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """Every retry is one more copy of the text kept by the provider (ADR 0034 §5)."""
    monkeypatch.setenv("ELA_ELEVENLABS_MAX_RETRIES", value)
    with pytest.raises(ValidationError):
        ElevenLabsSettings(_env_file=None)


def test_the_endpoint_is_not_a_setting() -> None:
    """Architecture rule 42, said once more from the outside: there is no field for the host.

    The rule reads the module; this reads the object. A field added tomorrow would pass the rule
    only if it were called something the rule does not know, and it would still fail here.
    """
    assert ELEVENLABS_API == "https://api.elevenlabs.io"
    assert not [name for name in ElevenLabsSettings.model_fields if "url" in name or "host" in name]


def test_the_audio_arithmetic_is_the_one_that_was_measured() -> None:
    """ADR 0034 §5: because the format is fixed, the byte count *is* the duration.

    594 799 bytes were 37,146 s of speech and 621 549 were 38,818 — measured with ``afinfo`` on
    2026-09-08. The constant has to keep predicting them, or the online playback timeout is
    watching a number that means nothing.
    """
    assert AUDIO_FORMAT == "mp3_44100_128"
    for measured_bytes, measured_seconds in ((594_799, 37.146), (621_549, 38.818)):
        predicted = measured_bytes / AUDIO_BYTES_PER_SECOND
        assert abs(predicted - measured_seconds) / measured_seconds < 0.001


def test_the_audio_ceiling_leaves_room_for_the_longest_sentence() -> None:
    """622 KB was the worst measured at 600 characters; the cap is a fail-safe above it, not a
    budget that a normal sentence could reach."""
    assert MAX_AUDIO_BYTES > 3 * 621_549
    assert PLAYBACK_SLACK_SECONDS > 0
