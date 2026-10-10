"""The helper that takes away what a test of the real browser left (M13.4e, decisions 60 and 71).

Built **without a browser**: a process that names a folder in its arguments is all a browser is to
:mod:`tests.browser_leftovers`, and what is asserted here is the helper — that it sees what was
left, in the two cases a walk of the test's own descendants misses, and that after it nothing is.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.browser_leftovers import PROFILE, Left, left, named, scratch, sweep

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="ps, SIGSTOP and SIGKILL are POSIX's"
)

SLEEPS = "import time; time.sleep(600)"
HOLDS = (
    "import subprocess, sys, time; "
    "child = subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
    "print(child.pid, flush=True); time.sleep(600)"
)


@pytest.fixture
def folder() -> Iterator[Path]:
    made = scratch()
    try:
        yield made
    finally:
        sweep(made)
        for other in made.iterdir():
            other.rmdir()
        made.rmdir()


def state(pid: int) -> str:
    """The first letter of what ``ps`` says of ``pid``: ``Z`` for one that ended, uncollected."""
    said = subprocess.run(
        ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return said[:1]


def running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_a_scratch_folder_is_new_short_and_its_own(folder: Path) -> None:
    assert folder.is_dir() and list(folder.iterdir()) == []
    assert len(str(folder)) < 40, "short: a profile of Chrome holds a socket"
    assert not left(folder)


def test_a_stopped_browser_nobody_is_the_parent_of_is_seen_and_taken_away(folder: Path) -> None:
    """The case found on 2026-10-10: a process of the browser's, stopped, whose parent has died. It
    is nobody's descendant, and it names its profile: by that it is found, killed, and its profile
    taken away."""
    profile = folder / f"{PROFILE}una"
    profile.mkdir()
    (profile / "Cookies").write_text("x", encoding="utf-8")
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDS, SLEEPS, f"--user-data-dir={profile}"],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    orphan = int(holder.stdout.readline())
    try:
        os.kill(orphan, signal.SIGSTOP)
        holder.kill()
        holder.wait()

        assert named(folder) == [orphan], "found by the folder it names, whoever its parent is"
        found = left(folder)
        assert found == Left((orphan,), (profile,)) and found, "the negative case: it is seen"

        sweep(folder)

        assert not left(folder)
        assert named(folder) == [] and not profile.exists()
    finally:
        if running(orphan):
            os.kill(orphan, signal.SIGKILL)


def test_a_driver_names_nothing_and_is_killed_by_its_pid(folder: Path) -> None:
    driver = subprocess.Popen([sys.executable, "-c", SLEEPS])
    try:
        assert named(folder) == []

        sweep(folder, also=(driver.pid,))

        assert driver.wait(timeout=10) == -signal.SIGKILL
    finally:
        driver.kill()
        driver.wait()


def test_a_pid_that_is_already_gone_does_not_stop_the_sweep(folder: Path) -> None:
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()
    profile = folder / f"{PROFILE}due"
    profile.mkdir()

    sweep(folder, also=(gone.pid,))

    assert not left(folder)


def test_a_process_that_has_ended_and_waits_to_be_collected_is_not_left(folder: Path) -> None:
    """A killed child of this very process stays in the kernel's table until it is collected: it
    runs nothing, and a fixture that counted it would fail on every test that killed its driver."""
    ended = subprocess.Popen([sys.executable, "-c", "pass", f"--user-data-dir={folder}/x"])
    try:
        deadline = time.monotonic() + 10
        while state(ended.pid) != "Z" and time.monotonic() < deadline:
            time.sleep(0.01)
        assert state(ended.pid) == "Z", "ended, and not collected: nobody has waited for it"
        assert running(ended.pid), "the kernel still has its entry"

        assert named(folder) == [] and not left(folder)
    finally:
        ended.wait()


def test_only_a_profile_of_playwright_s_is_taken_away_and_a_link_is_never_followed(
    folder: Path, tmp_path: Path
) -> None:
    kept = folder / "something-else"
    kept.mkdir()
    elsewhere = tmp_path / "somebody-s"
    elsewhere.mkdir()
    (elsewhere / "file").write_text("x", encoding="utf-8")
    link = folder / f"{PROFILE}link"
    link.symlink_to(elsewhere, target_is_directory=True)
    assert left(folder).profiles == (link,)

    sweep(folder)

    assert kept.is_dir(), "not a profile: not the sweep's"
    assert not link.exists() and not link.is_symlink()
    assert (elsewhere / "file").read_text(encoding="utf-8") == "x", "the link, never its target"
    assert not left(folder)


def test_a_folder_that_is_not_there_has_nothing_left(tmp_path: Path) -> None:
    assert not left(tmp_path / "never-made")
