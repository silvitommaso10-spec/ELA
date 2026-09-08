"""Where ELA touches the operating system — the only place in ``src/ela`` that does (M10.1).

Architecture rule 32 keeps ``ctypes`` and process spawning inside this package: perception is the
first thing in ELA that reads the machine rather than the database, and one door is easier to
guard than a habit. Rule 33 keeps every **child** here — a module with a ``__main__`` guard,
derived rather than listed since M10.3 — importing nothing but the standard library, and rule 34
keeps every module here from naming a domain state: the adapter reports primitives and the core
decides what they mean (ADR 0028 §1). Rule 36 keeps a window title from ever being read.

Two of the three helpers are ours (``probe.py``, ``vision.py``) and one is Apple's
(``screencapture(1)``), which is not an inconsistency but the answer to a question asked twice:
when macOS ships a binary that does the job, using it makes rule 33 true by construction; when it
does not — and it does not for OCR — the child is ours and the rule earns its keep.
"""

from ela.infrastructure.perception.darwin import PROBE_MODULE, TIMED_OUT, DarwinProbe, Spawn, spawn
from ela.infrastructure.perception.screencapture import (
    SCREENCAPTURE,
    ScreenCaptureCommand,
    UnsupportedScreenCapture,
)
from ela.infrastructure.perception.textrecognition import (
    VISION_MODULE,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)
from ela.infrastructure.perception.unsupported import UnsupportedProbe

__all__ = [
    "PROBE_MODULE",
    "SCREENCAPTURE",
    "TIMED_OUT",
    "VISION_MODULE",
    "DarwinProbe",
    "ScreenCaptureCommand",
    "Spawn",
    "UnsupportedProbe",
    "UnsupportedScreenCapture",
    "UnsupportedTextRecognition",
    "VisionTextRecognition",
    "spawn",
]
