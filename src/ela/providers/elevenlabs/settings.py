"""Where ELA's words are allowed to go, and what it costs to send them (M11.3, ADR 0034).

Written **before** the code that sends them, and it is not an accident of ordering: this module
holds :data:`ELEVENLABS_API`, and architecture rule 42 — *the voice goes only where it is
declared* — is a rule about this constant. A rule whose subject does not exist yet is a defence
with nobody behind it (ADR 0026 §7), so the constant and the rule arrive together, one commit
before anything makes a request.

**The endpoint is a constant and not a setting.** A configurable base URL is the shortest way for
what ELA says to end up on somebody else's server without a single line of a diff showing it —
the same sentence ADR 0029 §3 wrote about the absolute path of ``say``: *what speaks for the user
must not be decided by an environment variable.*

**There is no price table here, and that is a decision** (M11.3 dec. K). ADR 0020 §6 had to
estimate the cost of a call from a dated table, with a test that expires after 180 days because
no test notices that a vendor changed its prices. This provider *states* the cost of every
request in a ``character-cost`` header, so ELA reports the number it was given — in credits,
which the provider asserts, and never in currency, which would depend on a plan ELA would have
to keep up with.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "AUDIO_BYTES_PER_SECOND",
    "AUDIO_FORMAT",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "ELEVENLABS_API",
    "MAX_AUDIO_BYTES",
    "MAX_RETRIES_CEILING",
    "MAX_TIMEOUT_SECONDS",
    "MODELS",
    "PLAYBACK_SLACK_SECONDS",
    "TEXT_IS_RETAINED",
    "ElevenLabsSettings",
]

ELEVENLABS_API: Final = "https://api.elevenlabs.io"
"""The one host ELA's words may reach. A constant, guarded by architecture rule 42."""

MODELS: Final = frozenset({"eleven_multilingual_v2", "eleven_flash_v2_5"})
"""The models ELA has **measured**, and a closed set for the reason ADR 0020 §5 closed the
parameters: an unmeasured model would be paid for at the first request and its silence before the
first syllable would be nobody's number.

Measured on 2026-09-08, at the 600-character ceiling, from this machine:

===========================  ==================  ==================  ================
Model                        Whole response      Spoken             Credits/character
===========================  ==================  ==================  ================
``eleven_multilingual_v2``   5,62 s              37,15 s             1
``eleven_flash_v2_5``        **1,24 s**          38,82 s             **0,5**
===========================  ==================  ==================  ================
"""

DEFAULT_MODEL: Final = "eleven_flash_v2_5"
"""What speaks when nobody has listened yet.

Not the better-sounding model, and the number is the argument: at the ceiling, multilingual v2
leaves **5,6 seconds of silence** before the first syllable and costs twice as much. A default is
what runs when nobody has made a choice, and dead air is the part of a spoken answer the user
pays for. Which model ELA ends up with is decided **by ear**, in an audition, and written here by
the person who listened — that is what ``ELA_ELEVENLABS_MODEL`` is for.
"""

AUDIO_FORMAT: Final = "mp3_44100_128"
"""The only format ELA asks for, and asking for exactly one is what makes the next constant true."""

AUDIO_BYTES_PER_SECOND: Final = 16_000
"""128 kbit/s, in bytes: **the length of the audio is the length of the sentence.**

Because the format is fixed, ``len(audio) / AUDIO_BYTES_PER_SECOND`` is how long the audio plays,
and ELA knows it *before* playing. Verified against ``afinfo`` on 2026-09-08: 594 799 bytes gave
37,17 s against 37,146 measured, and 621 549 gave 38,85 against 38,818 — an error below 0,1%.

That is why the online voice needs no playback timeout of its own: it derives one per sentence
(:data:`PLAYBACK_SLACK_SECONDS`), instead of guessing a number that would have to be right for
every voice at every speed.
"""

PLAYBACK_SLACK_SECONDS: Final = 5.0
"""What is added to the audio's own length before the player is called overdue.

It covers starting a process and opening an audio device, both measured in tens of milliseconds,
and nothing else — there is nothing else to cover, because the rest of the wait *is* the sentence.
"""

MAX_AUDIO_BYTES: Final = 2 * 1024 * 1024
"""The most audio ELA will read from one answer, enforced **while reading** and not after.

600 characters produced 622 KB at the worst measured; two mebibytes is 3,2 times that, about two
minutes of speech. It is not a budget — it is the line past which a response that does not end
stops being ELA's problem (§33).
"""

DEFAULT_TIMEOUT_SECONDS: Final = 15.0
"""How long ELA waits for the audio of one sentence.

**Measured, and derived against a different criterion from the local voice's.** ADR 0033 §6 could
say that for ``say`` *the wait is the delivery*, so a timeout was a multiple of a sentence's own
length. Here the wait is **silence before** the delivery, so the number is chosen against how much
silence still has a point, and then checked against the measurement: the worst at the ceiling was
5,62 s (multilingual v2, 600 characters), and this is 2,7 times that.
"""
MAX_TIMEOUT_SECONDS: Final = 120.0
"""A ceiling on the knob, in the shape of every other ceiling in ELA: a timeout nobody bounded is
a way to make one sentence hold a step open for an afternoon."""

TEXT_IS_RETAINED: Final = True
"""**What ELA says is kept by this provider, and can be read back in the account's dashboard.**

Not a doubt and not a policy quotation — measured on 2026-09-08, twice over:

* ``enable_logging=false``, the flag that would turn retention off, answers **200 and returns a
  ``history-item-id`` anyway** on this plan. Zero Retention Mode is an enterprise feature; asking
  for it here changes nothing, so ELA does not ask and does not pretend.
* ``GET /v1/history`` gave back the reconnaissance sentences **verbatim**.

The user accepted this cost knowingly, and the decision was that **the choice must stay visible**:
this constant is what ``/diagnostics`` and ``ela voice`` say out loud wherever somebody looks at
which voice ELA is using (ADR 0034 §11). Not a warning before every sentence — a warning that
repeats is a warning people learn to skip, and this is a fact about the configuration, not an
event.

The receipt is the other half: every result carries the ``history_item_id`` of the copy that was
kept, so the retention is something a person can go and look at rather than something they were
told about (ADR 0034 §10).
"""

DEFAULT_MAX_RETRIES: Final = 1
"""Half of what the model provider allows (ADR 0020 §8), for a reason that belongs to this
provider only: **every retry is one more copy of the text kept by ElevenLabs**, and one more
stretch of silence on a sentence whose occasion is passing. What is retried, and with what
backoff, is ADR 0020 §8's policy unchanged."""
MAX_RETRIES_CEILING: Final = 5


class ElevenLabsSettings(BaseSettings):
    """The online voice, from ``ELA_ELEVENLABS_*`` variables and an optional ``.env``.

    Two absences, and they are **two facts**: no key and no voice are different things with
    different answers — one is a credential, the other is a choice nobody has made yet — so they
    are reported apart (ADR 0030 §8, and ADR 0034 §6). Either of them means the online voice is
    simply not there, and ELA starts anyway (§33): the local voice of M11.1 is untouched.
    """

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    elevenlabs_api_key: SecretStr | None = None
    """``ELA_ELEVENLABS_API_KEY``. Restrict it, on their console, to text-to-speech and give it a
    credit ceiling: a key without one is a payment card in a dotfile."""

    elevenlabs_voice_id: str | None = None
    """Which voice ELA speaks with online. Configuration of this machine, never an argument of a
    caller — a caller that could choose the voice could change who appears to be speaking."""

    elevenlabs_model: str = DEFAULT_MODEL

    elevenlabs_timeout_seconds: Annotated[float, Field(gt=0, le=MAX_TIMEOUT_SECONDS)] = (
        DEFAULT_TIMEOUT_SECONDS
    )

    elevenlabs_max_retries: Annotated[int, Field(ge=0, le=MAX_RETRIES_CEILING)] = (
        DEFAULT_MAX_RETRIES
    )

    @property
    def configured(self) -> bool:
        """Whether the online voice has both of the things it needs."""
        return self.elevenlabs_api_key is not None and self.elevenlabs_voice_id is not None

    @property
    def text_is_retained(self) -> bool:
        """Whether this provider keeps what ELA says. Read :data:`TEXT_IS_RETAINED`.

        A property, and on the settings object, so that ``/diagnostics`` and ``ela voice`` can
        state the fact **without naming the adapter** — architecture rule 27 keeps concrete
        implementations out of ``ela.api``, and a fact the user has to be shown must not depend
        on a module the API is not allowed to import.
        """
        return TEXT_IS_RETAINED

    @property
    def both_models(self) -> tuple[str, ...]:
        """Every measured model, the configured one first (ADR 0034 §9).

        The order is the decision: an audition that plays the other model first would be asking
        "which of these two", when the question is "is the other one worth 4,4 seconds more
        silence than the one you already have".
        """
        return (self.elevenlabs_model, *sorted(MODELS - {self.elevenlabs_model}))

    @field_validator("elevenlabs_api_key")
    @classmethod
    def _blank_key_is_no_key(cls, value: SecretStr | None) -> SecretStr | None:
        """``ELA_ELEVENLABS_API_KEY=""`` is an absent key, not an empty one (§33)."""
        if value is not None and value.get_secret_value().strip() == "":
            return None
        return value

    @field_validator("elevenlabs_voice_id")
    @classmethod
    def _blank_voice_is_no_voice(cls, value: str | None) -> str | None:
        """The same for the voice: whitespace is nobody's choice."""
        if value is not None and value.strip() == "":
            return None
        return value

    @field_validator("elevenlabs_model")
    @classmethod
    def _only_a_measured_model(cls, value: str) -> str:
        """A model outside :data:`MODELS` stops ELA at start-up instead of being paid for.

        The alternative is discovering at the first sentence that the wait is five seconds and
        the bill is double, which is the kind of thing a configuration error should not be
        allowed to teach anybody (§33).
        """
        if value not in MODELS:
            known = ", ".join(sorted(MODELS))
            raise ValueError(f"unknown model {value!r}: ELA has measured {known}")
        return value
