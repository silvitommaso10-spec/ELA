"""Where the database lives, from the environment (ADR 0001: pydantic-settings + ``.env``).

One variable, ``ELA_DB_URL``, written without a driver (``sqlite:///…``): alembic uses it as is
and :mod:`ela.infrastructure.persistence.engine` derives the async driver. The default is a file
under the user's home, created on first use.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["PersistenceSettings", "default_db_url"]


def default_db_url() -> str:
    """``sqlite:///<home>/.ela/ela.db``: absolute, computed when asked, never at import time."""
    return f"sqlite:///{(Path.home() / '.ela' / 'ela.db').as_posix()}"


class PersistenceSettings(BaseSettings):
    """Persistence configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    db_url: str = Field(default_factory=default_db_url)
