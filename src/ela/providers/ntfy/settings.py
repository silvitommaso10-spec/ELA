"""Where the bell rings, and the one credential it needs (M12.5 dec. E; ADR 0043 §8).

Two variables, and the first of them is a secret: on ntfy.sh **the topic is the password of the
topic** — whoever knows it reads the bells and can ring false ones — so it is a ``SecretStr``,
kept out of the audit and out of every URL, and architecture rule 46 knows its name.

Without a topic ELA simply does not ring: no bell is a configuration, not a failure (§33), and it
is what every machine that has never been configured does.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "BELL_TIMEOUT_SECONDS",
    "DEFAULT_NTFY_URL",
    "MAX_BELL_TIMEOUT_SECONDS",
    "TOPIC_BYTES",
    "NtfySettings",
]

DEFAULT_NTFY_URL: Final = "https://ntfy.sh"
"""The free service the measures were made against, and a setting because a topic on somebody's
own ntfy is the same protocol at another address (docs.ntfy.sh/publish)."""

BELL_TIMEOUT_SECONDS: Final = 5.0
"""How long a run may be held while the bell rings, and it is a **measured** number.

The bell rings on the path of the run — the executor rings where the question is born — so this
is time the user waits for. P4, on 2026-09-20 from this Mac: ntfy.sh answered ``200`` in 0,43 s,
then 0,42 and 0,33. Five seconds is a dozen times the worst of those: enough not to fail on the
first slow network, short enough that a provider that stopped answering cannot hold a step open.
A test with a slow fake provider proves the run is not held longer than this.
"""
MAX_BELL_TIMEOUT_SECONDS: Final = 30.0
"""The ceiling on the knob, in the shape of every other ceiling in ELA: a timeout nobody bounded
is a way to make one notification hold a run for an afternoon."""

TOPIC_BYTES: Final = 16
"""128 bits of randomness for a topic, and ``secrets.token_urlsafe`` writes them in the alphabet
ntfy accepts. What mints one is ``docs/GETTING_STARTED.md``: it writes it into ``.env`` — already
``0o600`` — and puts it in the clipboard **without printing it** (ADR 0024 §8)."""


class NtfySettings(BaseSettings):
    """The bell, from ``ELA_NTFY_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    ntfy_topic: SecretStr | None = None
    """``ELA_NTFY_TOPIC``. A credential, and a durable one, unlike an enrolment code: whoever has
    it can read every bell and ring a false one with a URL of their own."""

    ntfy_url: str = DEFAULT_NTFY_URL

    ntfy_timeout_seconds: Annotated[float, Field(gt=0, le=MAX_BELL_TIMEOUT_SECONDS)] = (
        BELL_TIMEOUT_SECONDS
    )

    @property
    def configured(self) -> bool:
        """Whether a bell can ring at all: without a topic, ELA is silent and says so."""
        return self.ntfy_topic is not None

    @field_validator("ntfy_topic")
    @classmethod
    def _blank_topic_is_no_topic(cls, value: SecretStr | None) -> SecretStr | None:
        """``ELA_NTFY_TOPIC=""`` is no topic, not an empty one (§33)."""
        if value is not None and value.get_secret_value().strip() == "":
            return None
        return value

    @field_validator("ntfy_url")
    @classmethod
    def _an_address_with_a_scheme(cls, value: str) -> str:
        """A URL, and one ELA can post to: anything else stops the start-up with a sentence."""
        if not value.startswith(("http://", "https://")):
            raise ValueError(f"ELA_NTFY_URL must start with http:// or https://, not {value!r}")
        return value.rstrip("/")
