"""How often ELA looks, and whether it looks at all (§10, §11; ADR 0028 §6, §7).

Every cadence is configuration and none of them is a constant, because the three families of
readings differ by two orders of magnitude in cost and by far more in how often they change: the
microphone goes on while you watch, a permission changes when a human clicks in System Settings.

The two defaults that matter are a decision and not a convenience. ``ELA_PERCEPTION_ENABLED`` is
**true**: ELA knows its own machine, and can answer if you ask it. ``ELA_PERCEPTION_LOOP_INTERVAL
_SECONDS`` is **0, off**: ELA does not watch on its own until somebody turns the loop on. It is
§11 applied one level up — nothing active without a reason — and in v0.1 the gesture that turns it
on is configuration; it will be a decision of the Proactive Core (§34) when there is somebody with
a reason to take it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from types import MappingProxyType
from typing import Annotated, Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ela.domain import ProbeFamily

__all__ = [
    "DEFAULT_INTERVALS",
    "DEFAULT_PROBE_TIMEOUT_SECONDS",
    "PerceptionSettings",
]

DEFAULT_INTERVALS: Final[Mapping[ProbeFamily, float]] = MappingProxyType(
    {ProbeFamily.SENSORS: 2.0, ProbeFamily.SESSION: 5.0, ProbeFamily.PERMISSIONS: 30.0}
)
"""Seconds between two readings of a family, by default.

Measured, not guessed (M10.1, "La ricognizione"): the microphone's "in use by anyone" costs
0,03 ms and changes while you watch; a TCC status costs 3,2 ms — it is an XPC call to ``tccd`` —
and changes when a human clicks in System Settings.
"""

DEFAULT_PROBE_TIMEOUT_SECONDS: Final = 2.0
"""How long the helper process may take before ELA calls the answer not observable.

Generous by two orders of magnitude — a full reading measured 35 ms — because this is not a
performance budget: it is the line past which a hung ``tccd`` stops being ELA's problem.
"""


class PerceptionSettings(BaseSettings):
    """Perception configuration, read from ``ELA_*`` variables and an optional ``.env``."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    perception_enabled: bool = True
    """``ELA_PERCEPTION_ENABLED``: false and ELA never looks — no subprocess is ever spawned, and
    every sensor reads ``OFF`` with cause ``NOT_LOOKING``."""

    perception_sensors_interval_seconds: Annotated[float, Field(ge=0)] = DEFAULT_INTERVALS[
        ProbeFamily.SENSORS
    ]
    perception_session_interval_seconds: Annotated[float, Field(ge=0)] = DEFAULT_INTERVALS[
        ProbeFamily.SESSION
    ]
    perception_permissions_interval_seconds: Annotated[float, Field(ge=0)] = DEFAULT_INTERVALS[
        ProbeFamily.PERMISSIONS
    ]
    """Seconds, and fractional ones are allowed: a cadence of half a second is a legitimate way
    to run this, and the whole point of §6 is that these are configuration. Zero is legal too and
    means *always due*: a read observes rather than repeating what it knew."""

    perception_loop_interval_seconds: Annotated[float, Field(ge=0)] = 0
    """``ELA_PERCEPTION_LOOP_INTERVAL_SECONDS``: the continuous loop. **0 is off**, and off is the
    default: ELA observes at start-up and when asked, and does not watch the user on its own."""

    perception_probe_timeout_seconds: Annotated[float, Field(gt=0)] = DEFAULT_PROBE_TIMEOUT_SECONDS

    def interval(self, family: ProbeFamily) -> timedelta:
        """How long a reading of ``family`` stays fresh."""
        seconds: float = {
            ProbeFamily.SENSORS: self.perception_sensors_interval_seconds,
            ProbeFamily.SESSION: self.perception_session_interval_seconds,
            ProbeFamily.PERMISSIONS: self.perception_permissions_interval_seconds,
        }[family]
        return timedelta(seconds=seconds)

    @property
    def loop_enabled(self) -> bool:
        """Whether the continuous loop runs: perception on, and an interval above zero."""
        return self.perception_enabled and self.perception_loop_interval_seconds > 0

    @property
    def loop_interval(self) -> timedelta:
        """How long the loop sleeps between two ticks."""
        return timedelta(seconds=self.perception_loop_interval_seconds)

    @property
    def probe_timeout(self) -> timedelta:
        """How long the probe may take before its answer is "not observable"."""
        return timedelta(seconds=self.perception_probe_timeout_seconds)
