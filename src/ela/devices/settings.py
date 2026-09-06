"""How long a heartbeat is worth, from the environment (ADR 0001: pydantic-settings + ``.env``).

One variable, ``ELA_DEVICE_HEARTBEAT_TTL_SECONDS``: past it a node is no longer reported
available (ADR 0016 §3). Same shape as ``PersistenceSettings`` and ``WorkspaceSettings``; the
Configuration milestone (M8.1) will unify the three.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["DEFAULT_HEARTBEAT_TTL_SECONDS", "DeviceSettings"]

DEFAULT_HEARTBEAT_TTL_SECONDS: Final = 60
"""A minute of silence is enough to stop calling a node available (ADR 0016 §3)."""


class DeviceSettings(BaseSettings):
    """Device configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    device_heartbeat_ttl_seconds: Annotated[int, Field(gt=0)] = DEFAULT_HEARTBEAT_TTL_SECONDS
    """Strictly positive: a TTL of zero would make every node unavailable the instant it reports."""

    @property
    def heartbeat_ttl(self) -> timedelta:
        """The TTL as the ``timedelta`` :class:`~ela.devices.registry.DeviceRegistry` takes."""
        return timedelta(seconds=self.device_heartbeat_ttl_seconds)
