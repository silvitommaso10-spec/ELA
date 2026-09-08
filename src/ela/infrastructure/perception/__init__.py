"""Where ELA touches the operating system — the only place in ``src/ela`` that does (M10.1).

Architecture rule 32 keeps ``ctypes`` and process spawning inside this package: perception is the
first thing in ELA that reads the machine rather than the database, and one door is easier to
guard than a habit. Rule 33 keeps :mod:`~ela.infrastructure.perception.probe` importing nothing
but the standard library, and rule 34 keeps every module here from naming a domain state — the
adapter reports primitives and the core decides what they mean (ADR 0028 §1).
"""

from ela.infrastructure.perception.darwin import PROBE_MODULE, TIMED_OUT, DarwinProbe, Spawn, spawn
from ela.infrastructure.perception.screencapture import (
    SCREENCAPTURE,
    ScreenCaptureCommand,
    UnsupportedScreenCapture,
)
from ela.infrastructure.perception.unsupported import UnsupportedProbe

__all__ = [
    "PROBE_MODULE",
    "SCREENCAPTURE",
    "TIMED_OUT",
    "DarwinProbe",
    "ScreenCaptureCommand",
    "Spawn",
    "UnsupportedProbe",
    "UnsupportedScreenCapture",
    "spawn",
]
