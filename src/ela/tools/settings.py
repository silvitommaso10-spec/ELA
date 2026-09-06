"""Where the workspace lives, from the environment (ADR 0001: pydantic-settings + ``.env``).

One variable, ``ELA_WORKSPACE_DIR``: the directory every path a tool writes is relative to
(ADR 0013 §12). The default is a folder under the user's home, created by the first tool that
needs it. Same shape as ``PersistenceSettings`` (ADR 0006 §3); the Configuration milestone (M8.1)
will unify them.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["WorkspaceSettings", "default_workspace_dir"]


def default_workspace_dir() -> Path:
    """``<home>/.ela/workspace``: absolute, computed when asked, never at import time."""
    return Path.home() / ".ela" / "workspace"


class WorkspaceSettings(BaseSettings):
    """Workspace configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    workspace_dir: Path = Field(default_factory=default_workspace_dir)
