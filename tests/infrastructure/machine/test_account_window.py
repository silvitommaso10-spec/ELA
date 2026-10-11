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
    PROFILE_WINDOW,
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
        for pid in made.started:
            if running(pid):
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

    (started,) = window.started
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
