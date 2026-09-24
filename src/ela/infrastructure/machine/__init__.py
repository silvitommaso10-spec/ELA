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

M11.3 adds a fifth (``afplay(1)``, Apple's), and with it the only thing here that hands a child
**bytes**: the audio a provider returned, through a file that has no name (ADR 0034 §7). It is in
this package for the same reason as all the others — rule 32 — and it is in ``darwin.py`` rather
than beside the voice so that architecture rule 41 can forbid the modules holding ELA's words to
touch a filesystem at all, with no exception to remember.

M12.3c adds two readings of the power source — ``pmset(1)``, Apple's, in ``darwin.py``, and
``powershell.exe``, Microsoft's, in ``windows.py`` — which makes this the package of **two**
systems. Both hand over the machine's own words; ``ela.devices.local`` decides what they are worth.
M12.4 gives the second system a voice, System.Speech through the same ``powershell.exe``, and the
first child that receives its words on stdin (``spawn_with_input``).

M13.2 adds the first launcher of **somebody else's** programs — the ones the user declared in
``ELA_TERMINAL_PROGRAMS`` —, in ``launcher.py``: a process group of its own, emptied whenever ELA
stops waiting, and nothing decided here (rule 34).

M11.1 adds a fourth, and it is Apple's again (``say(1)``) — and the first that **acts outside
the screen** rather than reading the machine. It lives here because rule 32's content is *ELA
touches the operating system in one place*: the door, not the word "perception". That makes
this package's name narrower than its contents for the second time (ADR 0029 put the capture
here first); the third time it gets renamed. Rule 40 keeps that helper from ever being asked
to write a file instead of speaking.
"""

from ela.infrastructure.machine.audition import (
    AUDITION_PHRASES,
    CANDIDATES,
    Audition,
    Candidate,
    Heard,
    Play,
    Speak,
)
from ela.infrastructure.machine.darwin import (
    PMSET,
    POWER_TIMEOUT_SECONDS,
    PROBE_MODULE,
    SPEECH_FILE_PREFIX,
    TIMED_OUT,
    DarwinProbe,
    Spawn,
    pmset_source,
    spawn,
    spawn_with_audio,
    spawn_with_input,
    sweep_speech_files,
)
from ela.infrastructure.machine.launcher import ProcessGroupLauncher
from ela.infrastructure.machine.listening import (
    DarwinListening,
    UnsupportedListening,
    digest_of,
)
from ela.infrastructure.machine.ports import (
    LOOKUP_TIMEOUT_SECONDS,
    port_holder,
)
from ela.infrastructure.machine.screencapture import (
    SCREENCAPTURE,
    ScreenCaptureCommand,
    UnsupportedScreenCapture,
)
from ela.infrastructure.machine.speech import (
    AFPLAY,
    SAY,
    OnlineSpeechCommand,
    SaySpeechCommand,
    UnsupportedSpeech,
)
from ela.infrastructure.machine.textrecognition import (
    VISION_MODULE,
    UnsupportedTextRecognition,
    VisionTextRecognition,
)
from ela.infrastructure.machine.unsupported import UnsupportedProbe
from ela.infrastructure.machine.windows import POWERSHELL, SapiSpeechCommand, power_status

__all__ = [
    "AFPLAY",
    "AUDITION_PHRASES",
    "CANDIDATES",
    "PMSET",
    "POWERSHELL",
    "POWER_TIMEOUT_SECONDS",
    "PROBE_MODULE",
    "SAY",
    "SPEECH_FILE_PREFIX",
    "Audition",
    "Candidate",
    "Heard",
    "Play",
    "Speak",
    "OnlineSpeechCommand",
    "ProcessGroupLauncher",
    "spawn_with_audio",
    "sweep_speech_files",
    "SCREENCAPTURE",
    "TIMED_OUT",
    "VISION_MODULE",
    "DarwinListening",
    "DarwinProbe",
    "SapiSpeechCommand",
    "SaySpeechCommand",
    "ScreenCaptureCommand",
    "Spawn",
    "UnsupportedListening",
    "UnsupportedProbe",
    "UnsupportedScreenCapture",
    "UnsupportedSpeech",
    "UnsupportedTextRecognition",
    "VisionTextRecognition",
    "digest_of",
    "pmset_source",
    "power_status",
    "spawn",
    "spawn_with_input",
    "LOOKUP_TIMEOUT_SECONDS",
    "port_holder",
]
