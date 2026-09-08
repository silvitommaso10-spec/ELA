"""Where the workspace lives, from the environment (ADR 0001: pydantic-settings + ``.env``).

``ELA_WORKSPACE_DIR``: the directory every path a tool writes is relative to
(ADR 0013 §12). The default is a folder under the user's home, created by the first tool that
needs it. Same shape as ``PersistenceSettings`` (ADR 0006 §3); the Configuration milestone (M8.1)
will unify them.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "DEFAULT_CAPTURE_MAX_BYTES",
    "DEFAULT_CAPTURE_MAX_COUNT",
    "DEFAULT_CAPTURE_TIMEOUT_SECONDS",
    "DEFAULT_CAPTURE_TTL_SECONDS",
    "MAX_CAPTURE_TTL",
    "CaptureSettings",
    "WorkspaceSettings",
    "default_capture_dir",
    "default_workspace_dir",
]


def default_workspace_dir() -> Path:
    """``<home>/.ela/workspace``: absolute, computed when asked, never at import time."""
    return Path.home() / ".ela" / "workspace"


class WorkspaceSettings(BaseSettings):
    """Workspace configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    workspace_dir: Path = Field(default_factory=default_workspace_dir)


MAX_CAPTURE_TTL: Final = timedelta(hours=1)
"""The ceiling ``ELA_CAPTURE_TTL_SECONDS`` may not pass (M10.2, ADR 0029 §1).

A screen capture is the user's content with nobody's name on it: nobody dictated it, and after
the step that asked for it nobody is looking at it. Past an hour it has stopped being a working
file and has become a record — and a record of what was on somebody's screen is precisely what
§57 says ELA must not accumulate without deciding to. The same shape as
:data:`~ela.permissions.MAX_DECISION_TTL`: a ceiling exists so that a knob cannot quietly turn
one kind of thing into another.
"""

DEFAULT_CAPTURE_TTL_SECONDS: Final = 300.0
DEFAULT_CAPTURE_MAX_COUNT: Final = 20
DEFAULT_CAPTURE_MAX_BYTES: Final = 200 * 1024 * 1024
DEFAULT_CAPTURE_TIMEOUT_SECONDS: Final = 10.0
"""How long the capture helper may take before ELA calls the capture failed.

**A declared placeholder, not a measured default** (M10.2, ADR 0029 §14): at the time this was
written the Screen Recording permission was denied on the development machine, so no capture had
ever run and no honest number existed. It is replaced by a measured one in the commit in which
the permission is granted. A provisional default nobody re-measures is a threshold put in "for
now", and this project knows how that ends.
"""


def default_capture_dir() -> Path:
    """``<home>/.ela/captures``: a sibling of the database, never inside the workspace.

    The choice is a **permanent constraint** and not this milestone's convenience (ADR 0029 §1):
    the workspace is the folder §23 describes as synchronised, and content that lands in a folder
    something may one day sync leaves the machine *without anybody having decided it*. "Nobody
    decided it" is the exact opposite of §57.
    """
    return Path.home() / ".ela" / "captures"


class CaptureSettings(BaseSettings):
    """Where screen captures live and for how long, from ``ELA_CAPTURE_*`` (M10.2)."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    capture_dir: Path = Field(default_factory=default_capture_dir)
    capture_ttl_seconds: Annotated[float, Field(gt=0, le=MAX_CAPTURE_TTL.total_seconds())] = (
        DEFAULT_CAPTURE_TTL_SECONDS
    )
    capture_max_count: Annotated[int, Field(ge=1)] = DEFAULT_CAPTURE_MAX_COUNT
    capture_max_bytes: Annotated[int, Field(ge=1)] = DEFAULT_CAPTURE_MAX_BYTES
    """The two ceilings. They **refuse, they do not evict** (ADR 0029 §15): when the store is
    full of captures that have not expired, the new capture fails. Deleting one somebody may
    still be using in order to make room is acting on something else, which is not the fail-safe
    of §33."""
    capture_timeout_seconds: Annotated[float, Field(gt=0)] = DEFAULT_CAPTURE_TIMEOUT_SECONDS

    @property
    def capture_ttl(self) -> timedelta:
        """How long a capture stays before the next purge takes it."""
        return timedelta(seconds=self.capture_ttl_seconds)

    @property
    def capture_timeout(self) -> timedelta:
        """How long the capture helper may run."""
        return timedelta(seconds=self.capture_timeout_seconds)
