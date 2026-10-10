"""What a test that starts a real browser may leave behind, and how it is taken away (M13.4e,
decisions 60 and 71).

**A test that freezes or kills a browser leaves neither a process nor a folder, even when it
fails.** Two facts made that a criterion and not a habit (2026-10-10):

* a browser killed instead of closed **leaves the temporary profile** Playwright made for it —
  ``playwright_chromiumdev_profile-*``, in the temporary folder of whoever started the driver;
* a browser that is **stopped** (``SIGSTOP``) when its driver dies is nobody's descendant any more,
  and stays stopped for ever: a cleanup that walks the test's own descendants cannot see it.

So a test of the real browser gives the driver **a temporary folder of its own** — :func:`scratch`,
through ``TMPDIR`` —, and everything it may leave is found **by that folder**: the profiles are in
it, and a process of the browser's names it in its arguments, whoever its parent is now.
:func:`sweep` takes both away, and :func:`left` says what is still there — which is what a fixture
asserts is nothing.

The folder is short on purpose, under ``/tmp``: a profile of Chrome holds a socket, and a long
path does not fit in one.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PROFILE", "Left", "left", "named", "running", "scratch", "sweep"]

PS = "/bin/ps"
PROFILE = "playwright_chromiumdev_profile-"
"""How Playwright names the folder of the profile it makes for a browser of one page."""
GONE_SECONDS = 10.0
LOOK_SECONDS = 0.02


def scratch() -> Path:
    """A new, short folder for a driver's ``TMPDIR``: where its browsers' profiles will be."""
    return Path(tempfile.mkdtemp(prefix="ela-pw-", dir="/tmp")).resolve()  # noqa: S108 — short on purpose


def _table() -> list[tuple[int, str, str]]:
    """Every process the kernel knows: its pid, its state, its whole command line."""
    out = subprocess.run(
        [PS, "-A", "-ww", "-o", "pid=,stat=,args="], capture_output=True, text=True, check=True
    ).stdout
    rows: list[tuple[int, str, str]] = []
    for line in out.split("\n"):
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit():
            rows.append((int(fields[0]), fields[1], fields[2]))
    return rows


def running(pid: int) -> bool:
    """Whether the kernel knows ``pid`` as a process **that has not ended** — running or stopped.
    One that ended and nobody has collected yet runs nothing: it is its parent's to collect, in
    its own time, and how long that takes is the machine's."""
    return any(known == pid and not state.startswith("Z") for known, state, _ in _table())


def named(folder: Path) -> list[int]:
    """The processes that name ``folder`` in their arguments and are not yet collected: a browser
    started with its profile there, and what that browser started — whoever their parent is now,
    running or stopped. A process that has ended and waits to be collected (``Z``) is not one."""
    inside = f"{folder}{os.sep}"
    return [pid for pid, state, args in _table() if inside in args and not state.startswith("Z")]


@dataclass(frozen=True)
class Left:
    """What is still there of the browsers that used a folder."""

    processes: tuple[int, ...]
    profiles: tuple[Path, ...]

    def __bool__(self) -> bool:
        return bool(self.processes or self.profiles)


def left(folder: Path) -> Left:
    """What a test left of the browsers whose driver had ``folder`` as its ``TMPDIR``."""
    profiles = sorted(folder.glob(f"{PROFILE}*")) if folder.is_dir() else []
    return Left(tuple(named(folder)), tuple(profiles))


def sweep(folder: Path, also: tuple[int, ...] = ()) -> None:
    """Kill what still names ``folder`` — and ``also``, by pid: a driver names nothing —, wait
    until the kernel has none of them running or stopped, and take the profiles away. By pid and
    by this folder, and nothing else of the machine."""
    doomed = sorted({*named(folder), *also})
    for pid in doomed:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:  # gone on its own in between
            continue
    deadline = time.monotonic() + GONE_SECONDS
    while doomed and named(folder) and time.monotonic() < deadline:
        time.sleep(LOOK_SECONDS)
    for profile in folder.glob(f"{PROFILE}*"):
        if profile.is_symlink():
            profile.unlink()  # the link, never what it points at
        else:
            shutil.rmtree(profile, ignore_errors=True)
