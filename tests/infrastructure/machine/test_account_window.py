"""The window of the browser with the user's accounts, **as a process** (M13.9, ADR 0063 §4, §8).

The window is the binary on the folder with nothing attached, and ELA keeps one thing of it: the
wait for its end. What the adapter does to that process — what it starts it with, that nothing of
it reaches ELA's own streams, that it is told at ELA's stop, waited for within the grace and then
killed with its group, that whoever is told of its end is told once — is asserted here on a
program of the tests that stands where the binary would be (``fake_window.py``): no browser, no
window on a screen, on every machine the suite runs on.

**A window is never left behind**: not by a caller that went away while it was being started, not
by a close that arrived while it was being started, not by a row that could not be written. And
not by a test that fails — whatever a test of this file started is taken away when it ends
(decision 71).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from ela.infrastructure.machine import account
from ela.infrastructure.machine.account import (
    WINDOW_ARGUMENTS,
    WINDOW_NAME,
    AccountChrome,
    reports_in,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    SHUT_KILLED,
    SHUT_QUIT,
    SHUT_TOLD,
    BrowserFailed,
    BrowserStopped,
    ProfileBusy,
)
from ela.testing.fakes import FakeStop
from tests.browser_leftovers import running

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a process group is POSIX's")

SOURCE = Path(__file__).with_name("fake_window.py")
ENVIRONMENT = {"PATH": "/usr/bin:/bin", "HOME": "/nowhere", "LANG": "C.UTF-8"}
APPLE = {"__CF_USER_TEXT_ENCODING", "__CFBundleIdentifier"}
"""What macOS adds to the environment of a process by itself."""
ADDRESS = "https://accounts.example/"
PATIENCE = 20.0
"""How long a test waits for something that has to happen: a deadline for a test that is red,
never a time a green one takes."""


class Window:
    """The program of one test where the binary would be: what it does, and what it was started
    with."""

    def __init__(self, registry: Path) -> None:
        from ela.infrastructure.machine.browser import registry_folder

        folder = registry_folder("chromium", {"PLAYWRIGHT_BROWSERS_PATH": str(registry)}, "Darwin")
        assert folder is not None
        self.folder = folder.joinpath(
            "chrome-mac-arm64", "Google Chrome for Testing.app", "Contents", "MacOS"
        )
        self.folder.mkdir(parents=True)
        self.binary = self.folder / "Google Chrome for Testing"
        source = SOURCE.read_text(encoding="utf-8")
        self.binary.write_text(f"#!{sys.executable}\n{source}", encoding="utf-8")
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.started: list[int] = []
        """The pid of every process the test started, counted where it is started: one that was
        ended before it could say it was ready is here all the same."""

    def set(self, **behaviour: bool) -> None:
        (self.folder / "behaviour.json").write_text(json.dumps(behaviour), encoding="utf-8")

    def let_go(self) -> None:
        """Let the process a program started for itself (``child``) end by itself."""
        (self.folder / "release").write_text("", encoding="utf-8")

    def launched(self) -> list[dict[str, Any]]:
        file = self.folder / "launched.jsonl"
        if not file.exists():
            return []
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()]

    async def launches(self, count: int) -> list[dict[str, Any]]:
        """What was started, once ``count`` of them have said they are ready."""

        async def said() -> list[dict[str, Any]]:
            while len(self.launched()) < count:
                await asyncio.sleep(0.02)
            return self.launched()

        return await asyncio.wait_for(said(), PATIENCE)


@pytest.fixture
def window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Window]:
    """The program where the binary would be — and, when the test is over, nothing of what it
    started: a test that fails leaves no process either (decision 71)."""
    registry = tmp_path / "registry"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(registry))
    made = Window(registry)
    start = asyncio.create_subprocess_exec

    async def counted(*arguments: Any, **options: Any) -> Any:
        process = await start(*arguments, **options)
        made.started.append(process.pid)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", counted)
    try:
        yield made
    finally:
        for pid in (*made.started, *(one.get("child") or 0 for one in made.launched())):
            if pid and running(pid):
                os.kill(pid, signal.SIGKILL)


class Kept:
    async def __call__(self) -> None:
        await asyncio.Event().wait()


class Told:
    """Who is told that a window ended: on which address it was opened, and how long it lasted."""

    def __init__(self, failing: BaseException | None = None) -> None:
        self.said: list[tuple[str | None, float]] = []
        self.failing = failing

    async def __call__(self, address: str | None, seconds: float) -> None:
        self.said.append((address, seconds))
        if self.failing is not None:
            raise self.failing


def chrome(profile: Path, told: Told | None = None) -> AccountChrome:
    return AccountChrome(
        asyncio.Event(),
        environment=ENVIRONMENT,
        kept=Kept(),
        system="Darwin",
        profile=profile,
        shown=lambda: False,
        **({} if told is None else {"ended": told}),
    )


@pytest.fixture
def born_deaf() -> Iterator[None]:
    """A process started while this holds ignores ``SIGTERM`` **from its first instant** — what
    is ignored is inherited by a child —: a window that is told before it has run a line of its
    own stays, as the browser that does not end when told."""
    before = signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, before)


async def never() -> None:
    """A grace that does not end while a test waits: whatever returns, returned for another
    reason."""
    await asyncio.Event().wait()


async def at_once() -> None:
    """A grace that is over already."""


async def gone(pid: int) -> bool:
    deadline = asyncio.get_running_loop().time() + PATIENCE
    while running(pid) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.02)
    return not running(pid)


# ----------------------------------------------------------------------------------------
# What the window is started with, and what ELA keeps of it
# ----------------------------------------------------------------------------------------


async def test_the_window_is_the_binary_on_the_folder_with_the_closed_list_and_nothing_attached(
    window: Window, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"
    worker = profile / "Default" / "Service Worker" / "ScriptCache" / "index"
    worker.parent.mkdir(parents=True)
    worker.write_text("a worker of a site the user signed in to", encoding="utf-8")
    profile.chmod(0o700)
    made = chrome(profile)

    await made.window(ADDRESS)
    (one,) = await window.launches(1)

    assert one["argv"] == [
        f"--user-data-dir={profile}",
        reports_in(profile),
        *WINDOW_ARGUMENTS,
        ADDRESS,
    ]
    assert reports_in(profile) == f"--breakpad-dump-location={profile}/Crashpad"
    assert "--profile-directory=Default" in one["argv"]
    assert worker.is_file(), "the window has no gate to go round: its sites keep their workers"
    received = {name: value for name, value in one["environment"].items() if name not in APPLE}
    assert received == ENVIRONMENT, "the closed environment, and nothing of ELA's own"
    assert one["session"] == one["pid"], "the leader of a session of its own, and not in ELA's"
    assert one["nowhere"] == [True, True, True], "its three streams go nowhere"
    assert await made.occupied() == PROFILE_WINDOW
    written = json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8"))
    assert written["signin"] == {"allowed": False, "allowed_on_next_startup": False}

    made._stopping.set()
    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()


@pytest.mark.parametrize("address", [None, "http://127.0.0.1:8080/a-page"])
async def test_a_window_with_no_address_is_started_with_none_and_one_of_this_machine_with_it(
    window: Window, tmp_path: Path, address: str | None
) -> None:
    profile = tmp_path / "profile"
    made = chrome(profile)

    await made.window(address)
    (one,) = await window.launches(1)

    expected = [f"--user-data-dir={profile}", reports_in(profile), *WINDOW_ARGUMENTS]
    assert one["argv"] == (expected if address is None else [*expected, address])
    made._stopping.set()
    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()


@pytest.mark.parametrize(
    "address",
    [
        "--remote-debugging-port=9222",
        "--user-data-dir=/somewhere/else",
        "ftp://accounts.example/",
        "javascript:alert(1)",
        "file:///etc/hosts",
        "chrome://settings/passwords",
        "https://",
        "https:///a-path-and-no-site",
        "accounts.example",
        "",
        " https://accounts.example/",
        "https://accounts.example/ --remote-debugging-port=9222",
        "https://" + "@".join(("somebody:a-word", "accounts.example/")),
        "https://[not-an-address/",
    ],
)
async def test_the_window_opens_on_the_address_of_a_site_or_on_none(
    window: Window, tmp_path: Path, address: str
) -> None:
    """The list of what the window receives is closed **by the adapter**, whoever calls it: what
    is not the address of a site is not handed to the binary — where it would be an argument of
    the browser's own, or would open what is not a site. *Which* site, and that it is ``https``,
    is the caller's to say (``tests/api/test_browser_routes.py``)."""
    made = chrome(tmp_path / "profile")

    with pytest.raises(BrowserFailed, match="the address of a site"):
        await made.window(address)

    assert window.launched() == [] and made._window is None
    assert await made.occupied() is None


async def test_while_the_window_is_open_the_folder_is_its_own(
    window: Window, tmp_path: Path
) -> None:
    made = chrome(tmp_path / "profile")
    await made.window(None)
    await window.launches(1)

    with pytest.raises(ProfileBusy) as second:
        await made.window(None)
    with pytest.raises(ProfileBusy) as page:
        await made.open(ADDRESS, lambda address: True, FakeStop())

    assert second.value.by == PROFILE_WINDOW and page.value.by == PROFILE_WINDOW
    assert len(window.launched()) == 1 and not made._drivers
    made._stopping.set()
    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()


# ----------------------------------------------------------------------------------------
# Its end: told once, to whoever sees every end
# ----------------------------------------------------------------------------------------


async def test_a_window_its_user_quits_is_told_once_and_the_folder_is_free(
    window: Window, tmp_path: Path
) -> None:
    told = Told()
    made = chrome(tmp_path / "profile", told)
    await made.window(ADDRESS)
    (one,) = await window.launches(1)

    os.kill(one["pid"], signal.SIGTERM)  # what a quit is to the process: it ends by itself
    watched = made._watched
    assert watched is not None
    await asyncio.wait_for(watched, PATIENCE)

    assert [address for address, _ in told.said] == [ADDRESS]
    assert told.said[0][1] >= 0
    assert await made.occupied() is None
    made._stopping.set()
    assert await made.settle(at_once) == ()
    assert len(told.said) == 1, "the close of ELA does not tell it a second time"


async def test_at_ela_s_stop_the_window_is_told_and_waited_for_and_its_end_is_said(
    window: Window, tmp_path: Path
) -> None:
    """``SIGTERM``, to which a browser exits by itself writing its cookies: with a grace that
    does not end, the close returns because the window ended — and only because it was told."""
    told = Told()
    made = chrome(tmp_path / "profile", told)
    await made.window(ADDRESS)
    (one,) = await window.launches(1)

    made._stopping.set()
    names = await asyncio.wait_for(made.settle(never), PATIENCE)

    assert names == (), "it ended by itself: nothing was killed"
    assert await gone(one["pid"])
    assert [address for address, _ in told.said] == [ADDRESS]


async def test_a_window_that_does_not_end_when_told_is_killed_at_the_grace_and_named(
    window: Window, tmp_path: Path
) -> None:
    window.set(deaf=True)
    told = Told()
    made = chrome(tmp_path / "profile", told)
    await made.window(None)
    (one,) = await window.launches(1)

    made._stopping.set()
    names = await asyncio.wait_for(made.settle(at_once), PATIENCE)

    assert names == (WINDOW_NAME,)
    assert await gone(one["pid"])
    assert [address for address, _ in told.said] == [None], "killed or not, its end is said"


async def test_a_group_that_has_ended_and_is_not_collected_yet_is_a_group_with_nothing_to_kill(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The grace runs out on a window that has just ended and that the loop has not collected.
    Asked to kill such a group, macOS answers «not permitted» — measured on 2026-10-11, where
    Linux answers nothing. **The test gives that answer on every system**, once the group has
    been ended for real: the close of ELA goes on, and does not end there with the system's
    error."""
    window.set(deaf=True)
    made = chrome(tmp_path / "profile")
    await made.window(None)
    (one,) = await window.launches(1)
    killpg = os.killpg

    def not_permitted(group: int, sent: int) -> None:
        killpg(group, sent)
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "killpg", not_permitted)

    made._stopping.set()
    names = await asyncio.wait_for(made.settle(at_once), PATIENCE)

    assert names == (WINDOW_NAME,)
    assert await gone(one["pid"])


async def test_an_end_nobody_could_write_down_does_not_stop_ela_s_close(
    window: Window, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Whoever is told may fail — the audit, with a database that went away. The close of ELA
    still waits for the window, kills what has to be killed and returns: the failure is logged
    where it happened, and is not kept to be raised hours later by the close."""
    told = Told(failing=OSError("the audit could not be written"))
    made = chrome(tmp_path / "profile", told)
    await made.window(ADDRESS)
    (one,) = await window.launches(1)

    made._stopping.set()
    with caplog.at_level(logging.ERROR):
        names = await asyncio.wait_for(made.settle(never), PATIENCE)

    assert names == ()
    assert await gone(one["pid"])
    assert len(told.said) == 1
    assert "window" in caplog.text and "OSError" in caplog.text
    assert ADDRESS not in caplog.text, "the address is the user's: the log names what failed"


# ----------------------------------------------------------------------------------------
# The command that ends it (decision 80): told, waited for, killed only past the grace
# ----------------------------------------------------------------------------------------


async def test_the_window_ela_started_is_told_and_waited_for_and_the_folder_is_free(
    window: Window, tmp_path: Path
) -> None:
    """The red button of the window closes the window and leaves the browser running: the folder
    stays held until somebody ends the process. The command does — and with a grace that does not
    end, it returns because the window ended, and only because it was told."""
    told = Told()
    made = chrome(tmp_path / "profile", told)
    await made.window(ADDRESS)
    (one,) = await window.launches(1)

    assert await asyncio.wait_for(made.shut(never), PATIENCE) == SHUT_QUIT

    assert await gone(one["pid"])
    assert [address for address, _ in told.said] == [ADDRESS], "its end is said by who waits"
    assert await made.occupied() is None
    made._stopping.set()
    assert await made.settle(at_once) == ()
    assert len(told.said) == 1, "the close of ELA does not tell it a second time"


async def test_a_window_that_does_not_quit_when_told_is_killed_only_once_the_grace_is_over(
    window: Window, tmp_path: Path
) -> None:
    window.set(deaf=True)
    told = Told()
    made = chrome(tmp_path / "profile", told)
    await made.window(None)
    (one,) = await window.launches(1)
    over = asyncio.Event()

    async def the_grace() -> None:
        await over.wait()

    shutting = asyncio.ensure_future(made.shut(the_grace))
    await asyncio.sleep(0.3)
    assert not shutting.done() and running(one["pid"]), "told and waited for: not killed yet"
    assert await made.occupied() == PROFILE_WINDOW

    over.set()
    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_KILLED
    assert await gone(one["pid"])
    assert [address for address, _ in told.said] == [None], "killed or not, its end is said"
    assert await made.occupied() is None


async def test_with_nothing_on_the_folder_the_command_tells_nobody(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    signalled: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sent: signalled.append((pid, sent)))
    made = chrome(tmp_path / "profile")

    assert await made.shut(never) is None

    assert signalled == [] and window.launched() == []


async def test_a_step_of_ela_s_is_not_what_the_command_ends(window: Window, tmp_path: Path) -> None:
    """A page ELA drives ends with its step, or with the stop of its task: the command is for
    the browser a hand may be on."""
    made = chrome(tmp_path / "profile")
    made._opening = 1

    with pytest.raises(ProfileBusy) as busy:
        await made.shut(never)

    assert busy.value.by == PROFILE_STEP


async def test_once_ela_is_stopping_the_command_is_refused_and_the_close_ends_the_window(
    window: Window, tmp_path: Path
) -> None:
    made = chrome(tmp_path / "profile")
    await made.window(None)
    (one,) = await window.launches(1)
    made._stopping.set()

    with pytest.raises(BrowserStopped):
        await made.shut(never)

    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()
    assert await gone(one["pid"])


async def test_a_window_that_is_being_started_is_waited_for_and_then_told(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    starting = Starting(monkeypatch, hold="after")
    made = chrome(tmp_path / "profile")
    asking = asyncio.ensure_future(made.window(None))
    await asyncio.wait_for(starting.reached.wait(), PATIENCE)
    (one,) = await window.launches(1)

    shutting = asyncio.ensure_future(made.shut(never))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not shutting.done() and running(one["pid"]), "a launch is in flight: it is waited for"
    starting.release.set()

    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_QUIT
    await asyncio.wait_for(asking, PATIENCE)
    assert await gone(one["pid"])


def told(pid: int, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Every signal sent to ``pid`` from now on, by this process — the question «do you live?»
    aside —, sent for real."""
    sent: list[int] = []
    kill, killpg = os.kill, os.killpg

    def counted(target: int, number: int) -> None:
        if target == pid and number != 0:
            sent.append(number)
        kill(target, number)

    def counted_group(group: int, number: int) -> None:
        if group == pid:
            sent.append(number)
        killpg(group, number)

    monkeypatch.setattr(os, "kill", counted)
    monkeypatch.setattr(os, "killpg", counted_group)
    return sent


async def test_the_window_is_told_once_however_many_ask(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured on 2026-10-11: the browser has one shot at ending by itself — a second
    ``SIGTERM`` twenty milliseconds after the first killed it, where one alone let it end. Two
    clicks on the button, or the command twice, would have been a kill before the grace, and
    said as «it quit». Told once: whoever asks again waits with the first."""
    window.set(deaf=True)
    made = chrome(tmp_path / "profile")
    await made.window(None)
    (one,) = await window.launches(1)
    signals = told(one["pid"], monkeypatch)
    over = asyncio.Event()

    async def the_grace() -> None:
        await over.wait()

    first = asyncio.ensure_future(made.shut(the_grace))
    second = asyncio.ensure_future(made.shut(the_grace))
    await asyncio.sleep(0.2)

    assert signals == [signal.SIGTERM], "one, for the two that asked"
    over.set()
    assert await asyncio.wait_for(asyncio.gather(first, second), PATIENCE) == [
        SHUT_KILLED,
        SHUT_KILLED,
    ], "and what became of it is said the same to both"
    assert await gone(one["pid"])
    assert made._was_told == set(), "what has ended is not remembered as told: a pid comes back"


async def test_a_window_the_command_told_is_not_told_again_by_ela_s_stop(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.set(deaf=True)
    made = chrome(tmp_path / "profile")
    await made.window(None)
    (one,) = await window.launches(1)
    signals = told(one["pid"], monkeypatch)
    shutting = asyncio.ensure_future(made.shut(never))
    await asyncio.sleep(0.2)
    assert signals == [signal.SIGTERM]

    made._stopping.set()
    names = await asyncio.wait_for(made.settle(at_once), PATIENCE)

    assert names == (WINDOW_NAME,)
    assert signals == [signal.SIGTERM, signal.SIGKILL], "told once, then killed at the grace"
    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_KILLED
    assert await gone(one["pid"])


class Says:
    """What the system would say of a process, one answer after the other, the last for ever."""

    def __init__(self, *answers: str | None) -> None:
        self.answers = list(answers)
        self.of: list[int] = []

    async def __call__(self, pid: int) -> str | None:
        self.of.append(pid)
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


async def a_browser_ela_did_not_start(window: Window, profile: Path) -> dict[str, Any]:
    """The program of the tests, started **by the test** on ``profile`` — a window that
    relaunched itself, one left by an ELA that was killed —, with the lock a browser leaves."""
    profile.mkdir(mode=0o700, exist_ok=True)
    await asyncio.create_subprocess_exec(
        str(window.binary), f"--user-data-dir={profile}", start_new_session=True
    )
    (one,) = await window.launches(1)
    (profile / "SingletonLock").symlink_to(f"a-machine-{one['pid']}")
    return one


async def test_a_browser_ela_did_not_start_is_told_when_it_is_ela_s_binary_on_the_folder(
    window: Window, tmp_path: Path
) -> None:
    """The same check that says the folder is held says whether ELA may tell that process: its
    command line is ELA's own binary on this folder (decisions 80 and 82)."""
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    assert await made.occupied() == PROFILE_PROCESS

    assert await asyncio.wait_for(made.shut(never), PATIENCE) == SHUT_QUIT

    assert await gone(one["pid"])
    assert await made.occupied() is None, "the lock it left names nobody"


@pytest.mark.parametrize(
    "said",
    ["/Applications/Another Browser --user-data-dir={profile}", None],
    ids=["another-program", "a-command-line-nobody-could-read"],
)
async def test_a_process_that_is_not_ela_s_browser_is_told_nothing(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, said: str | None
) -> None:
    """ELA signals nothing it cannot name: the folder is held, the command says so, and the
    process is the user's to end."""
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(None if said is None else said.format(profile=profile))
    signals = told(one["pid"], monkeypatch)

    with pytest.raises(ProfileBusy) as busy:
        await made.shut(at_once)

    assert busy.value.by == PROFILE_PROCESS
    assert signals == [], "asked whether it lives, at most"
    assert running(one["pid"])


async def test_a_browser_ela_did_not_start_that_does_not_quit_is_killed_alone(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the grace it is killed **by its pid**: the group of a process ELA did not start is
    not ELA's to kill."""
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    groups: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda group, sent: groups.append(group))

    assert await asyncio.wait_for(made.shut(at_once), PATIENCE) == SHUT_KILLED

    assert await gone(one["pid"])
    assert groups == []
    assert await made.occupied() is None


async def test_a_browser_that_dropped_its_lock_and_stays_is_still_the_one_that_was_told(
    window: Window, tmp_path: Path
) -> None:
    """The re-read of the round: what is asked again when the grace ends is **the process that
    was told**, not whatever the lock names by then. A browser that took its lock away and did
    not end was said to have quit, with the folder said free under it."""
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    over = asyncio.Event()

    async def the_grace() -> None:
        (profile / "SingletonLock").unlink()
        await over.wait()

    shutting = asyncio.ensure_future(made.shut(the_grace))
    await asyncio.sleep(0.2)
    assert not shutting.done() and running(one["pid"])
    over.set()

    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_KILLED
    assert await gone(one["pid"])


async def test_a_browser_ela_cannot_name_any_more_when_the_grace_ends_is_told_and_not_killed(
    window: Window, tmp_path: Path
) -> None:
    """The system cannot be asked when the grace ends: ELA does not kill what it cannot name,
    **and does not say it quit** — it says it was told, which is all it knows."""
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}", None)

    assert await asyncio.wait_for(made.shut(at_once), PATIENCE) == SHUT_TOLD

    assert running(one["pid"])
    assert await made.occupied() == PROFILE_PROCESS, "and the folder is still said held"


async def test_a_browser_ela_did_not_start_is_not_killed_while_the_grace_lasts(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It is no child of ELA's, so the kernel is asked whether it is still there — as many times
    as the grace lasts, and never a number of times: asked a thousand times in the instant this
    test looks, it is still not killed."""
    monkeypatch.setattr(account, "GONE_EVERY", 0.0002)
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    signals = told(one["pid"], monkeypatch)
    over = asyncio.Event()

    async def the_grace() -> None:
        await over.wait()

    shutting = asyncio.ensure_future(made.shut(the_grace))
    await asyncio.sleep(0.4)

    assert not shutting.done() and running(one["pid"])
    assert signals == [signal.SIGTERM], "told, and nothing else while the grace lasts"
    over.set()
    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_KILLED
    assert signals == [signal.SIGTERM, signal.SIGKILL]


async def test_a_browser_ela_did_not_start_is_told_once_too(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    signals = told(one["pid"], monkeypatch)
    over = asyncio.Event()

    async def the_grace() -> None:
        await over.wait()

    first = asyncio.ensure_future(made.shut(the_grace))
    second = asyncio.ensure_future(made.shut(the_grace))
    await asyncio.sleep(0.2)

    assert signals == [signal.SIGTERM]
    over.set()
    assert set(await asyncio.wait_for(asyncio.gather(first, second), PATIENCE)) <= {
        SHUT_KILLED,
        SHUT_QUIT,
    }
    assert signals.count(signal.SIGTERM) == 1
    assert await gone(one["pid"])


async def test_once_ela_is_stopping_a_browser_it_did_not_start_is_not_signalled(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At its own close ELA signals only what it started (decision 80). The stop raised while
    the system was being asked what that process is — the look took its time —: nothing is
    sent."""
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    signals = told(one["pid"], monkeypatch)

    async def stopped_meanwhile(pid: int) -> str:
        made._stopping.set()
        return f"{window.binary} --user-data-dir={profile}"

    made._said_of = stopped_meanwhile

    with pytest.raises(BrowserStopped):
        await made.shut(never)

    assert signals == [] and running(one["pid"])


async def test_a_stop_during_the_grace_of_a_browser_ela_did_not_start_kills_nobody(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = asked = Says(f"{window.binary} --user-data-dir={profile}")
    signals = told(one["pid"], monkeypatch)
    shutting = asyncio.ensure_future(made.shut(never))
    await asyncio.sleep(0.2)
    assert signals == [signal.SIGTERM]

    made._stopping.set()

    assert await asyncio.wait_for(shutting, PATIENCE) == SHUT_TOLD
    assert signals == [signal.SIGTERM] and running(one["pid"]), "told before the stop: not killed"
    assert asked.of == [one["pid"]], (
        "and nothing more is launched once ELA is stopping: the system is not asked again"
    )


async def test_a_browser_of_another_user_is_not_ela_s_to_signal(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The system refuses the signal: the refusal is the command's own — the folder is held by
    what ELA may not end —, and never the system's error."""
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    kill = os.kill

    def not_permitted(pid: int, sent: int) -> None:
        if pid == one["pid"] and sent != 0:
            raise PermissionError(1, "Operation not permitted")
        kill(pid, sent)

    # Undone before the test ends: what takes this test's process away is a signal too.
    with monkeypatch.context() as refusing:
        refusing.setattr(os, "kill", not_permitted)
        with pytest.raises(ProfileBusy) as busy:
            await made.shut(at_once)

    assert busy.value.by == PROFILE_PROCESS


async def test_a_pid_that_is_no_longer_that_browser_when_the_grace_ends_is_not_killed(
    window: Window, tmp_path: Path
) -> None:
    """The grace is seconds, and a pid is the system's to give again: what is killed is asked
    of the system once more, right before, and anything but that browser is left alone."""
    window.set(deaf=True)
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = asked = Says(
        f"{window.binary} --user-data-dir={profile}", "a program that has nothing to do with it"
    )

    async def the_table_of_that_world() -> dict[int, tuple[int, str]]:
        # The same world, as the system's table says it: that pid is another program's by now,
        # and nothing names the folder (decision 153: the answer waits for that, too).
        return {one["pid"]: (one["pid"], "a program that has nothing to do with it")}

    made._tabled = the_table_of_that_world

    assert await asyncio.wait_for(made.shut(at_once), PATIENCE) == SHUT_QUIT

    assert asked.of == [one["pid"], one["pid"]]
    assert running(one["pid"]), "whatever has that pid now was not killed"


# ----------------------------------------------------------------------------------------
# A window is never left behind
# ----------------------------------------------------------------------------------------


class Starting:
    """The start of a process, held where a test says: before the process exists, or between its
    existing and its being handed to whoever asked for it."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, hold: str) -> None:
        self.reached = asyncio.Event()
        self.release = asyncio.Event()
        real = asyncio.create_subprocess_exec

        async def held(*arguments: Any, **options: Any) -> Any:
            if hold == "before":
                self.reached.set()
                await self.release.wait()
                return await real(*arguments, **options)
            process = await real(*arguments, **options)
            self.reached.set()
            await self.release.wait()
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", held)


async def test_a_caller_that_goes_away_while_the_window_starts_does_not_leave_it_behind(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The process exists and whoever asked for it is cancelled before it is handed over — a
    request dropped at a second signal. The window is the adapter's all the same: the folder is
    held by it, and ELA's close tells it, waits for it and finds nothing left."""
    starting = Starting(monkeypatch, hold="after")
    told = Told()
    made = chrome(tmp_path / "profile", told)
    asking = asyncio.ensure_future(made.window(ADDRESS))
    await asyncio.wait_for(starting.reached.wait(), PATIENCE)
    (one,) = await window.launches(1)

    asking.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asking
    starting.release.set()

    assert await made.occupied() == PROFILE_WINDOW, "the folder is still held, and said so"
    made._stopping.set()
    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()
    assert await gone(one["pid"]), "and nothing of it is left"
    assert [address for address, _ in told.said] == [ADDRESS]


async def test_a_close_that_arrives_while_the_window_starts_waits_for_it_and_ends_it(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, born_deaf: None
) -> None:
    """The stop is raised when the launch has passed its last look at it and the process does not
    exist yet. The close does not call the folder free while a window is being started on it: it
    waits for the launch, and the window it started is told, waited for and — deaf from its
    first instant, because it is told in its first instant — killed."""
    window.set(deaf=True)
    starting = Starting(monkeypatch, hold="before")
    made = chrome(tmp_path / "profile")
    asking = asyncio.ensure_future(made.window(None))
    await asyncio.wait_for(starting.reached.wait(), PATIENCE)
    assert await made.occupied() == PROFILE_WINDOW, "held from before the process exists"

    made._stopping.set()
    settling = asyncio.ensure_future(made.settle(at_once))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not settling.done(), "a launch is in flight: the close waits for it"
    starting.release.set()
    names = await asyncio.wait_for(settling, PATIENCE)
    await asyncio.wait_for(asking, PATIENCE)

    # The window first; after it, the system's own program, asked which processes name the
    # folder once the window was killed (decision 153).
    started, *_asked = window.started
    assert names == (WINDOW_NAME,)
    assert await gone(started)


async def test_a_stop_raised_while_the_folder_is_prepared_starts_no_window(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second look at the stop, right before the process is started: the first was before the
    folder was looked at, and preparing it is a wait."""
    made = chrome(tmp_path / "profile")
    loop = asyncio.get_running_loop()
    prepared = account._prepared

    def stopped_meanwhile(profile: Path, *, driven: bool) -> None:
        prepared(profile, driven=driven)
        raised = threading.Event()
        loop.call_soon_threadsafe(lambda: (made._stopping.set(), raised.set()))
        assert raised.wait(PATIENCE)

    monkeypatch.setattr(account, "_prepared", stopped_meanwhile)

    with pytest.raises(BrowserStopped):
        await made.window(None)

    assert window.launched() == [] and made._window is None
    assert await made.settle(at_once) == ()


# ----------------------------------------------------------------------------------------
# When a close returns, no process names the folder any more (decision 153, 2026-10-13)
# ----------------------------------------------------------------------------------------


def naming(profile: Path) -> list[int]:
    """The processes of this machine that name ``profile`` as a browser names its folder: the
    test's own look, with the system's ``ps``."""
    said = subprocess.run(
        ["/bin/ps", "-ww", "-A", "-o", "pid=,args="], capture_output=True, text=True, check=False
    ).stdout
    wanted = f"--user-data-dir={profile}"
    return [int(line.split()[0]) for line in said.splitlines() if wanted in line]


TURNS = 10
"""How many times the loop is let turn once the adapter has seen the main process end: a close
that waited for nothing else has returned by then."""


async def seen_to_end(made: AccountChrome, watched: asyncio.Task[None]) -> None:
    """The adapter's own wait for the window has ended — and the loop has turned since."""
    await asyncio.wait_for(asyncio.wait({watched}), PATIENCE)
    for _ in range(TURNS):
        await asyncio.sleep(0)


async def with_a_child(window: Window, made: AccountChrome) -> dict[str, Any]:
    """The window, whose program started a process of its own that names the folder and stays."""
    window.set(child=True)
    await made.window(None)
    (one,) = await window.launches(1)
    assert running(one["child"]) and one["child"] in naming(made._profile), (  # type: ignore[arg-type]
        "the control: what the window started is there, and names the folder"
    )
    return one


async def test_at_ela_s_stop_the_close_waits_for_what_the_window_started_too(
    window: Window, tmp_path: Path
) -> None:
    """Decision 153. Seen on the CI of macOS on 2026-10-13, twice: the window was told, its main
    process left by itself, the close returned — and processes the browser had started for
    itself were still there, naming the folder. **When the close returns no process names the
    folder any more**: with a grace that does not end, it returns because what the window had
    started left too, and nothing was killed."""
    profile = tmp_path / "profile"
    made = chrome(profile, Told())
    one = await with_a_child(window, made)
    watched = made._watched
    assert watched is not None

    made._stopping.set()
    settling = asyncio.ensure_future(made.settle(never))
    await seen_to_end(made, watched)
    returned_early = settling.done()
    still_there = running(one["child"])
    window.let_go()
    names = await asyncio.wait_for(settling, PATIENCE)
    left = naming(profile)

    assert not running(one["pid"]) and still_there, "the control: the main left, its child not"
    assert not returned_early, "the close returned with a process still naming the folder"
    assert names == (), "everything left by itself: nothing was killed"
    assert left == [], "and when it returned nothing named the folder"


async def test_at_ela_s_stop_what_the_window_started_and_does_not_leave_is_killed_at_the_grace(
    window: Window, tmp_path: Path
) -> None:
    """Past the grace the rule there already is: the group of the window is ELA's own — ELA
    started it —, and ELA kills it, and says so."""
    profile = tmp_path / "profile"
    told = Told()
    made = chrome(profile, told)
    one = await with_a_child(window, made)
    watched = made._watched
    assert watched is not None
    over = asyncio.Event()

    made._stopping.set()
    settling = asyncio.ensure_future(made.settle(over.wait))
    await seen_to_end(made, watched)
    returned_early = settling.done()
    over.set()
    names = await asyncio.wait_for(settling, PATIENCE)
    left = naming(profile)

    assert not returned_early
    assert names == (WINDOW_NAME,), "what would not leave was killed, and the close says so"
    assert left == [] and await gone(one["child"])
    assert len(told.said) == 1, "and the end of the window is said once all the same"


async def test_the_command_answers_only_when_what_the_window_started_has_left_too(
    window: Window, tmp_path: Path
) -> None:
    """``ela browser close`` says «it quit: the profile is free»: not while a process the
    window started still names the folder."""
    profile = tmp_path / "profile"
    made = chrome(profile, Told())
    one = await with_a_child(window, made)
    watched = made._watched
    assert watched is not None

    shutting = asyncio.ensure_future(made.shut(never))
    await seen_to_end(made, watched)
    answered_early = shutting.done()
    window.let_go()
    how = await asyncio.wait_for(shutting, PATIENCE)
    left = naming(profile)

    assert not answered_early, "the command answered with a process still naming the folder"
    assert how == SHUT_QUIT and left == []
    assert await gone(one["child"])


async def test_the_command_kills_the_group_it_started_when_the_grace_is_over_and_says_killed(
    window: Window, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"
    made = chrome(profile, Told())
    one = await with_a_child(window, made)
    watched = made._watched
    assert watched is not None
    over = asyncio.Event()

    shutting = asyncio.ensure_future(made.shut(over.wait))
    await seen_to_end(made, watched)
    answered_early = shutting.done()
    over.set()
    how = await asyncio.wait_for(shutting, PATIENCE)

    assert not answered_early
    assert how == SHUT_KILLED, "the main had quit; what it started was killed: said as killed"
    assert naming(profile) == [] and await gone(one["child"])


class Known:
    """The kernel's answer to «is this process still there», as the adapter asks it — and the
    moment it first says no of one process."""

    def __init__(self, made: AccountChrome, pid: int) -> None:
        self.gone = asyncio.Event()
        self._asking, self._pid = made._known, pid

    def __call__(self, pid: int) -> bool:
        there = self._asking(pid)
        if pid == self._pid and not there:
            self.gone.set()
        return there


async def another_with_a_child(
    window: Window, profile: Path
) -> tuple[AccountChrome, dict[str, Any], Known]:
    """A browser ELA did not start, which the system says is ELA's binary on the folder, and
    whose program started a process of its own that stays."""
    window.set(child=True)
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    known = Known(made, one["pid"])
    made._known = known  # type: ignore[method-assign]
    return made, one, known


async def test_a_browser_ela_did_not_start_has_quit_only_when_nothing_of_it_names_the_folder(
    window: Window, tmp_path: Path
) -> None:
    """The same sentence for a browser ELA did not start: told, its main process ends — and the
    answer waits for what it had started, within the same grace."""
    profile = tmp_path / "profile"
    made, one, known = await another_with_a_child(window, profile)

    shutting = asyncio.ensure_future(made.shut(never))
    await asyncio.wait_for(known.gone.wait(), PATIENCE)
    for _ in range(TURNS):
        await asyncio.sleep(0)
    answered_early = shutting.done()
    window.let_go()
    how = await asyncio.wait_for(shutting, PATIENCE)

    assert not answered_early, "it answered «quit» with a process still naming the folder"
    assert how == SHUT_QUIT and naming(profile) == []


async def test_what_a_browser_ela_did_not_start_left_behind_is_not_killed_and_not_called_gone(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Past the grace the rule there already is: ELA kills only what it can still name. What
    that browser had started is not ELA's browser, and its group is not ELA's: **nothing is
    killed, and the answer is «told», not «quit»** — the folder is not said free."""
    profile = tmp_path / "profile"
    made, one, known = await another_with_a_child(window, profile)
    signals = told(one["child"], monkeypatch)
    groups: list[int] = []
    monkeypatch.setattr(os, "killpg", lambda group, sent: groups.append(group))
    over = asyncio.Event()

    shutting = asyncio.ensure_future(made.shut(over.wait))
    await asyncio.wait_for(known.gone.wait(), PATIENCE)
    over.set()
    how = await asyncio.wait_for(shutting, PATIENCE)

    assert how == SHUT_TOLD, "the main process ended, and something of it still names the folder"
    assert running(one["child"]) and one["child"] in naming(profile)
    assert signals == [] and groups == [], "nothing ELA cannot name was signalled"


async def test_a_look_at_the_processes_that_fails_is_a_doubt_and_not_an_empty_folder(
    window: Window, tmp_path: Path
) -> None:
    """Fail-safe: the system could not say which processes there are. That is not «none names
    the folder»: the close waits its grace, and then kills the group it started."""
    profile = tmp_path / "profile"
    made = chrome(profile, Told())
    await made.window(None)
    await window.launches(1)
    watched = made._watched
    assert watched is not None
    asked: list[None] = []

    async def nobody_says() -> None:
        asked.append(None)

    made._tabled = nobody_says  # type: ignore[assignment]
    over = asyncio.Event()

    made._stopping.set()
    settling = asyncio.ensure_future(made.settle(over.wait))
    await seen_to_end(made, watched)
    returned_early = settling.done()
    over.set()
    names = await asyncio.wait_for(settling, PATIENCE)

    assert asked, "the control: the system was asked"
    assert not returned_early, "a look that failed was taken for an empty folder"
    assert names == (WINDOW_NAME,)


async def nobody_may_ask() -> None:
    raise AssertionError("the system was asked which processes there are")


async def test_a_window_its_user_quit_is_nothing_a_later_close_looks_for(
    window: Window, tmp_path: Path
) -> None:
    """The wait is for what a close of ELA's ended. A window its user quit ended with nobody of
    ELA's having told it: hours later ELA's stop finds nothing to wait for, and does not ask the
    system which processes there are — whatever is on the folder by then is not that window."""
    made = chrome(tmp_path / "profile", Told())
    await made.window(None)
    (one,) = await window.launches(1)
    watched = made._watched
    assert watched is not None

    os.kill(one["pid"], signal.SIGTERM)  # what a quit is to the process: it ends by itself
    await asyncio.wait_for(watched, PATIENCE)
    made._tabled = nobody_may_ask
    made._stopping.set()

    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()


async def test_a_window_a_command_has_seen_gone_is_not_looked_for_again_at_ela_s_stop(
    window: Window, tmp_path: Path
) -> None:
    made = chrome(tmp_path / "profile", Told())
    await made.window(None)
    await window.launches(1)

    assert await asyncio.wait_for(made.shut(never), PATIENCE) == SHUT_QUIT
    made._tabled = nobody_may_ask
    made._stopping.set()

    assert await asyncio.wait_for(made.settle(never), PATIENCE) == ()


async def test_a_command_that_cannot_see_the_processes_says_told_and_not_that_the_folder_is_free(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doubt, for the command: the window ended, and the system would not say which
    processes there are — before the kill of the group ELA started, and after it. ELA kills
    what is its own, **and does not say the profile is free**: «told»."""
    made = chrome(tmp_path / "profile", Told())
    await made.window(None)
    (one,) = await window.launches(1)

    async def nobody_says() -> None:
        return None

    made._tabled = nobody_says  # type: ignore[assignment]
    monkeypatch.setattr(account, "GONE_TURNS", 3)  # the turns a killed process is looked for

    how = await asyncio.wait_for(made.shut(at_once), PATIENCE)

    assert how == SHUT_TOLD
    assert await gone(one["pid"])


async def test_a_stop_that_arrives_while_the_group_is_read_signals_nobody(
    window: Window, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """At its own close ELA signals only what it started, and **no wait stands between the last
    look at the stop and a signal**. The group of a browser ELA did not start is read before
    that look, not after it: a stop that arrives while the system is asked refuses the command,
    and the browser is told nothing."""
    profile = tmp_path / "profile"
    one = await a_browser_ela_did_not_start(window, profile)
    made = chrome(profile)
    made._said_of = Says(f"{window.binary} --user-data-dir={profile}")
    signals = told(one["pid"], monkeypatch)
    tabled = made._tabled

    async def a_stop_meanwhile() -> Any:
        made._stopping.set()
        return await tabled()

    made._tabled = a_stop_meanwhile

    with pytest.raises(BrowserStopped):
        await asyncio.wait_for(made.shut(never), PATIENCE)

    assert signals == [], "nothing ELA did not start was signalled at its stop"
    assert running(one["pid"])
