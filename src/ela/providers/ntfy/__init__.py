"""The bell of the companion: ntfy.sh, one topic, one voice (M12.5 dec. E; ADR 0043 §8)."""

from ela.providers.ntfy.bell import BELL_TITLE, HOME, VOICES, NtfyBell, tailnet_url
from ela.providers.ntfy.settings import (
    BELL_TIMEOUT_SECONDS,
    DEFAULT_NTFY_URL,
    MAX_BELL_TIMEOUT_SECONDS,
    TOPIC_BYTES,
    NtfySettings,
)

__all__ = [
    "BELL_TIMEOUT_SECONDS",
    "BELL_TITLE",
    "DEFAULT_NTFY_URL",
    "HOME",
    "MAX_BELL_TIMEOUT_SECONDS",
    "TOPIC_BYTES",
    "VOICES",
    "NtfyBell",
    "NtfySettings",
    "tailnet_url",
]
