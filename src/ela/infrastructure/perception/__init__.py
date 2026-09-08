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

M11.1 adds a fourth, and it is Apple's again (``say(1)``) — and the first that **acts outside
the screen** rather than reading the machine. It lives here because rule 32's content is *ELA
touches the operating system in one place*: the door, not the word "perception". That makes
this package's name narrower than its contents for the second time (ADR 0029 put the capture
here first); the third time it gets renamed. Rule 40 keeps that helper from ever being asked
to write a file instead of speaking.
"""

from ela.infrastructure.perception.darwin import PROBE_MODULE, TIMED_OUT, DarwinProbe, Spawn, spawn
from ela.infrastructure.perception.screencapture import (
    SCREENCAPTURE,
    ScreenCaptureCommand,
    UnsupportedScreenCapture,
)
from ela.infrastructure.perception.speech import SAY, SaySpeechCommand, UnsupportedSpeech
from ela.infrastructure.perception.textrecognition import (
    VISION_MODULE,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)
from ela.infrastructure.perception.unsupported import UnsupportedProbe

__all__ = [
    "PROBE_MODULE",
    "SAY",
    "SCREENCAPTURE",
    "TIMED_OUT",
    "VISION_MODULE",
    "DarwinProbe",
    "SaySpeechCommand",
    "ScreenCaptureCommand",
    "Spawn",
    "UnsupportedProbe",
    "UnsupportedScreenCapture",
    "UnsupportedSpeech",
    "UnsupportedTextRecognition",
    "VisionTextRecognition",
    "spawn",
]
