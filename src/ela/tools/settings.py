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
    "CAPTURE_TIMEOUT_IS_MEASURED",
    "DEFAULT_CAPTURE_MAX_BYTES",
    "DEFAULT_CAPTURE_MAX_COUNT",
    "DEFAULT_CAPTURE_TIMEOUT_SECONDS",
    "DEFAULT_CAPTURE_TTL_SECONDS",
    "DEFAULT_VOICE_NAME",
    "DEFAULT_VOICE_TIMEOUT_SECONDS",
    "MAX_CAPTURE_TTL",
    "MAX_SPOKEN_CHARACTERS",
    "CaptureSettings",
    "VoiceSettings",
    "WorkspaceSettings",
    "default_capture_dir",
    "default_voice_enabled",
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
DEFAULT_CAPTURE_TIMEOUT_SECONDS: Final = 5.0
"""How long the capture helper may take before ELA calls the capture failed.

**Measured**, on a granted machine, after M10.2's review (ADR 0029 §14). Fifteen captures of a
2940x1912 display: 88 ms median, 138 ms on the first one (cold), 96 ms at the 95th percentile;
the PNG was 0.8-1.4 MB there and 4.0 MB on a screen full of text — its size follows the content,
not the display. Repeated with twice as many CPU-burning processes as the machine has
cores, it did not move — 81 ms median, 99 ms worst — because the work is ``WindowServer``'s and
userland load does not reach it. That stability is itself part of the answer: the number is not
sitting on a noisy measurement.

Five seconds is **fifty-seven times the median**, which is the ratio ADR 0028 §6 chose for the
probe (2 s over 35 ms) applied to the number this milestone measured, and thirty-six times the
worst case ever observed. It is deliberately not a performance budget: it is the line past which a
``WindowServer`` that is not answering stops being ELA's problem, and past which a step that hangs
would keep a task waiting for no reason.
"""

CAPTURE_TIMEOUT_IS_MEASURED: Final = True
"""Whether the number above was measured or is still a placeholder (M10.2, ADR 0029 §14).

``True`` since the permission was granted and the capture was timed; it was flipped **in the same
edit that replaced the number**, which is the only way it is allowed to move.

It stays here rather than being deleted because it is what a test reads: on a machine where ELA
can see that Screen Recording is granted, a number still declaring itself unmeasured is a red
test; where the permission is missing there is nothing to measure, and the check says "not
applicable" instead of passing quietly. The shape is the one this project uses for a budget —
**the condition is an observable fact, not a date** — and it stays armed for the next number that
needs a machine before it can be honest.
"""


DEFAULT_OCR_TIMEOUT_SECONDS: Final = 10.0
"""How long the recognition helper may take before ELA calls the reading failed.

**Measured on 2026-09-08 on this machine** — 10 cores, macOS 26.6 (25G72), display 2940 x 1912 —
and where it was measured is part of the number, not a footnote:

===============================================  ========
a real screen                                    232 ms
a pathological, text-dense image                 1003 ms
**the same, with 20 processes burning CPU**      **2727 ms**, 2959 at worst
===============================================  ========

**The ~57x ratio of ADR 0028 §6 and ADR 0029 §14 is deliberately not inherited**, and this
milestone is what showed it is not a law. That ratio was chosen twice over readings that do *not*
degrade under load — a 35 ms probe, and a capture whose work belongs to ``WindowServer`` — so a
median at rest described the loaded case too. Here the work is in ELA's own process, load reaches
it, and 57x of a median at rest would be a number borrowed from a measurement of something else.

> A ratio between a timeout and a median is not a constant of this project: it depends on **who
> does the work**. Every new timeout is measured against its own work, under the load that work
> will meet.

So the base is the worst case *under load*, 2,96 s, and 10 s leaves 3,4x for a display larger
than this one, where the pixels can be 2,5 times as many. Like the capture's, it is not a
performance budget: it is the line past which a Vision that does not answer stops being ELA's
problem.
"""

DEFAULT_OCR_LANGUAGES: Final = ("it-IT", "en-US")
"""Which languages the recognition is asked for. Both verified present among the thirty this
macOS supports — and the helper checks, every time, because an unsupported language does not
fail: it answers "this screen has no text" (ADR 0030 §8)."""


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
    ocr_timeout_seconds: Annotated[float, Field(gt=0)] = DEFAULT_OCR_TIMEOUT_SECONDS
    ocr_languages: tuple[str, ...] = DEFAULT_OCR_LANGUAGES
    """``ELA_OCR_LANGUAGES``, comma-separated. There is no recognition **level**: ``fast`` was
    measured and does not ship (ADR 0030 §9), and a knob with one good value is not a knob."""

    @property
    def capture_ttl(self) -> timedelta:
        """How long a capture stays before the next purge takes it."""
        return timedelta(seconds=self.capture_ttl_seconds)

    @property
    def capture_timeout(self) -> timedelta:
        """How long the capture helper may run."""
        return timedelta(seconds=self.capture_timeout_seconds)

    @property
    def ocr_timeout(self) -> timedelta:
        """How long the recognition helper may run."""
        return timedelta(seconds=self.ocr_timeout_seconds)


MAX_SPOKEN_CHARACTERS: Final = 600
"""The longest sentence ELA may say in one call (M11.1 dec. E).

**Measured on 2026-09-08 on this machine** (macOS 26.6, voice ``Alice``), speaking exactly 600
characters of ordinary Italian prose:

=========================  ===========  ===============
rate                       spoken       characters/s
=========================  ===========  ===============
default                    **31,5 s**   19,1
``-r 150``                 34,6 s       17,3
``-r 100`` (slow)          37,8 s       15,9
=========================  ===========  ===============

Half a minute is already a long time to be talked at, and the ceiling is not about politeness:
**until the barge-in exists there is no way to stop ELA in the middle** (dec. F). A cap is what
stands in for an interrupt that has not been built, so it is chosen against the worst thing that
can happen with no interrupt — not against how much a model might want to say.

Refused by the capability's own schema, before the Guardian and before the child: a sentence too
long is an argument that is wrong, not an action that fails.
"""

DEFAULT_VOICE_NAME: Final = "Alice"
"""Which voice, when nothing says otherwise.

The only female Italian voice ``say`` offers on this machine — 9 Italian of 184, one of them
female — and it is **not the voice §9 describes**. §9 asks for a *presenza femminile e
professionale*; Alice is dated concatenative synthesis. M11.1 delivers *that ELA speaks*, not
*that ELA sounds like §9* (dec. D), and M11.3 is where that is reopened along with the four
answers of §57 that sending ELA's words anywhere would require.
"""

DEFAULT_VOICE_TIMEOUT_SECONDS: Final = 60.0
"""How long the speech helper may run before ELA calls the sentence failed.

**This timeout does not inherit a ratio, and the reason is the one ADR 0030 §14 wrote down**:
*a ratio between a timeout and a median is not a constant of this project — it depends on who
does the work.* Here the work is not computation at all. The call lasts as long as the **speech**
lasts, so the wait is the deliverable and not overhead, and a multiple of a median would be a
number about the wrong thing.

It is derived instead: the longest legal sentence is :data:`MAX_SPOKEN_CHARACTERS`, which was
measured at **31,5 s** at the default rate and 37,8 s at the slowest rate ``say`` offers. Sixty
seconds is 1,9x the first and 1,6x the second. Past it, a ``say`` that is not finishing has
stopped being about speech.

**There is no rate knob**, and that is what makes the number above derivable rather than a guess:
a configurable rate would make the longest legal sentence a function of a setting, and the
timeout would then be guarding a duration nobody had measured.
"""


def default_voice_enabled() -> bool:
    """``ELA_VOICE_ENABLED``, default ``True`` (M11.1 dec. J).

    The precedent is ADR 0028 §7 — perception enabled, loop off — read for a milestone that has
    no loop: **ELA never speaks of its own accord.** A sentence happens only when a step asks for
    it and the Guardian allows it, so the knob that matters is already the Guardian, and a second
    one defaulting to off would be a switch that hides a door rather than locking it.
    """
    return True


class VoiceSettings(BaseSettings):
    """Whether ELA may speak, with which voice, and for how long, from ``ELA_VOICE_*`` (M11.1)."""

    model_config = SettingsConfigDict(env_prefix="ELA_", env_file=".env", extra="ignore")

    voice_enabled: bool = Field(default_factory=default_voice_enabled)
    voice_name: Annotated[str, Field(min_length=1)] = DEFAULT_VOICE_NAME
    voice_timeout_seconds: Annotated[float, Field(gt=0)] = DEFAULT_VOICE_TIMEOUT_SECONDS

    @property
    def voice_timeout(self) -> timedelta:
        """How long the speech helper may run."""
        return timedelta(seconds=self.voice_timeout_seconds)
