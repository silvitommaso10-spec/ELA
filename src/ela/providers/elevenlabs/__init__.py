"""The ElevenLabs adapter: where what ELA says leaves this machine (M11.3, ADR 0034).

The second provider of ELA, and the first that is not a model. It exists for one reason, written
in §9: *la voce deve avere una presenza femminile e professionale*, and the only Italian female
voice ``say`` offers is dated concatenative synthesis. Nothing else justifies the request — after
M11.1, "ELA has to speak" is answered on this machine and for free.

What leaves, what is kept and under which permission are the four answers of §57 in ADR 0034 §2.
The shortest of them is the one worth having here too: **the text is retained by the provider**,
it is readable in the account's own history, and no flag on this plan changes that.
"""

from __future__ import annotations

from ela.providers.elevenlabs.provider import PROVIDER_NAME, ElevenLabsVoice, Synthesis
from ela.providers.elevenlabs.settings import (
    AUDIO_BYTES_PER_SECOND,
    AUDIO_FORMAT,
    DEFAULT_MODEL,
    ELEVENLABS_API,
    MAX_AUDIO_BYTES,
    MODELS,
    PLAYBACK_SLACK_SECONDS,
    TEXT_IS_RETAINED,
    ElevenLabsSettings,
)

__all__ = [
    "AUDIO_BYTES_PER_SECOND",
    "AUDIO_FORMAT",
    "DEFAULT_MODEL",
    "ELEVENLABS_API",
    "MAX_AUDIO_BYTES",
    "MODELS",
    "PLAYBACK_SLACK_SECONDS",
    "PROVIDER_NAME",
    "TEXT_IS_RETAINED",
    "ElevenLabsSettings",
    "ElevenLabsVoice",
    "Synthesis",
]
