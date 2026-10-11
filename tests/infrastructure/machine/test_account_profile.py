"""The profile of the browser with the user's accounts, **without a browser** (M13.9, ADR 0063).

What the adapter does to the folder and reads from it is asserted here on folders the test
builds: no process is started, so these run wherever the suite runs — the system is handed to the
adapter as the composition hands it. What only the real binary can say is in
``test_account_browser.py``.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from ela.infrastructure.machine import account
from ela.infrastructure.machine.account import (
    LAUNCH_ARGUMENTS,
    LAUNCH_OPTIONS,
    PREFERENCES,
    WINDOW_ARGUMENTS,
    AccountChrome,
    linked_in,
    lock_holder,
    saved_in,
    with_preferences,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    AccountBrowser,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
)
from ela.testing.fakes import FakeStop

VARIABLE = "ELA_BROWSER_PROFILE_DIR"


class Kept:
    async def __call__(self) -> None:
        await asyncio.Event().wait()


def chrome(profile: Path | None, *, system: str = "Darwin", shown: bool = False) -> AccountChrome:
    """The adapter on ``profile``, as the composition builds it — and nothing started."""
    return AccountChrome(
        asyncio.Event(),
        environment={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"},
        kept=Kept(),
        system=system,
        profile=profile,
        shown=lambda: shown,
    )


def locked_by(profile: Path, pid: int, host: str | None = None) -> None:
    """The link a browser leaves in its folder while it runs, as the test says it."""
    (profile / "SingletonLock").symlink_to(
        f"{socket.gethostname() if host is None else host}-{pid}"
    )


def a_dead_pid() -> int:
    """The pid of a process that has ended and been collected: the kernel knows it no more."""
    import subprocess
    import sys

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


def test_the_adapter_is_the_port() -> None:
    assert isinstance(chrome(None), AccountBrowser)


# ----------------------------------------------------------------------------------------
# What the profile does not keep: the preferences, before every launch
# ----------------------------------------------------------------------------------------


def test_the_preferences_are_the_closed_table_of_the_decision() -> None:
    """Decision 22, and G4/G5 of the measure: these, and not the binary, keep the browser away
    from a Google account and from saving passwords."""
    assert PREFERENCES == {
        "credentials_enable_service": False,
        "credentials_enable_autosignin": False,
        "profile": {"password_manager_leak_detection": False},
        "autofill": {"profile_enabled": False, "credit_card_enabled": False},
        "signin": {"allowed": False, "allowed_on_next_startup": False},
    }


def test_they_are_written_over_what_a_profile_says_and_nothing_else_of_it_is_touched() -> None:
    found = {
        "credentials_enable_service": True,
        "profile": {"password_manager_leak_detection": True, "name": "ELA"},
        "signin": {"allowed": True},
        "autofill": "not an object any more",
        "browser": {"window_placement": {"left": 10}},
    }

    written = with_preferences(found)

    assert written["credentials_enable_service"] is False
    assert written["credentials_enable_autosignin"] is False
    assert written["profile"] == {"password_manager_leak_detection": False, "name": "ELA"}
    assert written["signin"] == {"allowed": False, "allowed_on_next_startup": False}
    assert written["autofill"] == {"profile_enabled": False, "credit_card_enabled": False}
    assert written["browser"] == {"window_placement": {"left": 10}}
    assert found["credentials_enable_service"] is True, "what was read is not what is changed"
    assert found["profile"]["password_manager_leak_detection"] is True


@pytest.mark.parametrize("found", [None, [], "text", 7], ids=repr)
def test_a_file_that_held_no_object_is_replaced_by_the_table(found: object) -> None:
    assert with_preferences(found) == PREFERENCES


@pytest.mark.parametrize("driven", [True, False], ids=["a-page", "the-window"])
def test_before_a_launch_the_file_is_rewritten_for_its_owner_alone(
    tmp_path: Path, driven: bool
) -> None:
    file = tmp_path / "Default" / "Preferences"
    file.parent.mkdir()
    file.write_text(json.dumps({"signin": {"allowed": True}, "kept": 1}), encoding="utf-8")
    file.chmod(0o644)

    account._prepared(tmp_path, driven=driven)

    written = json.loads(file.read_text(encoding="utf-8"))
    assert written["signin"] == {"allowed": False, "allowed_on_next_startup": False}
    assert written["kept"] == 1
    assert file.stat().st_mode & 0o777 == 0o600
    assert sorted(found.name for found in file.parent.iterdir()) == ["Preferences"], (
        "the file is replaced whole, and nothing is left beside it"
    )


def test_before_the_first_launch_the_file_and_its_folder_are_made(tmp_path: Path) -> None:
    account._prepared(tmp_path, driven=True)

    file = tmp_path / "Default" / "Preferences"
    assert json.loads(file.read_text(encoding="utf-8")) == PREFERENCES
    assert file.parent.stat().st_mode & 0o777 == 0o700


def test_a_file_that_is_not_json_is_replaced(tmp_path: Path) -> None:
    file = tmp_path / "Default" / "Preferences"
    file.parent.mkdir()
    file.write_text("{ half a file", encoding="utf-8")

    account._prepared(tmp_path, driven=False)

    assert json.loads(file.read_text(encoding="utf-8")) == PREFERENCES


# ----------------------------------------------------------------------------------------
# The service workers: gone before a launch Playwright drives
# ----------------------------------------------------------------------------------------


def test_before_a_driven_launch_the_service_workers_are_gone_and_before_the_window_they_stay(
    tmp_path: Path,
) -> None:
    """The gate is a route of Playwright's, and a worker answers without it (measure 8): gone
    before a page of ELA's. The window has no gate — it is the user's hands —, and its sites keep
    theirs."""
    workers = tmp_path / "Default" / "Service Worker"
    (workers / "ScriptCache").mkdir(parents=True)
    (workers / "ScriptCache" / "index").write_text("a worker", encoding="utf-8")

    account._prepared(tmp_path, driven=False)
    assert (workers / "ScriptCache" / "index").is_file()

    account._prepared(tmp_path, driven=True)
    assert not workers.exists()


def test_a_link_where_the_workers_would_be_is_taken_away_and_not_followed(tmp_path: Path) -> None:
    """The link goes — a browser launched on it would find, through it, whatever workers the
    folder it leads to holds —, and what it points at is nobody's to remove."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "kept").write_text("somebody's", encoding="utf-8")
    profile = tmp_path / "profile"
    (profile / "Default").mkdir(parents=True)
    workers = profile / "Default" / "Service Worker"
    workers.symlink_to(elsewhere)

    account._prepared(profile, driven=False)
    assert workers.is_symlink(), "before the window nothing of the workers is touched"

    account._prepared(profile, driven=True)

    assert not workers.is_symlink() and not workers.exists()
    assert (elsewhere / "kept").is_file()


# ----------------------------------------------------------------------------------------
# Linked to a Google account, read from the file at every question
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("preferences", "linked"),
    [
        ({}, False),
        (None, False),
        ({"account_info": []}, False),
        ({"account_info": [{"email": "somebody"}]}, True),
        ({"google": {"services": {"account_id": ""}}}, False),
        ({"google": {"services": {"account_id": "an id"}}}, True),
        ({"google": {"services": {"consented_to_sync": False}}}, False),
        ({"google": {"services": {"consented_to_sync": True}}}, True),
        ({"google": "not an object"}, False),
        ({"signin": {"allowed": True}}, False),
    ],
    ids=[
        "empty",
        "no-file",
        "no-account",
        "an-account",
        "no-primary",
        "a-primary",
        "no-consent",
        "a-consent",
        "not-an-object",
        "allowed-is-not-linked",
    ],
)
def test_the_browser_is_linked_when_it_knows_an_account(preferences: object, linked: bool) -> None:
    """The keys of G4, as presence: that the sign-in is *allowed* is not that there is one."""
    assert linked_in(preferences) is linked


async def test_linked_is_read_from_the_file_every_time_it_is_asked(tmp_path: Path) -> None:
    """Decision 63: never from a copy. The file changes between two questions, and so does the
    answer."""
    made = chrome(tmp_path / "profile")
    assert await made.linked() is False, "a profile never launched is linked to nothing"
    file = tmp_path / "profile" / "Default" / "Preferences"
    file.parent.mkdir()

    file.write_text(json.dumps({"account_info": [{"email": "somebody"}]}), encoding="utf-8")
    assert await made.linked() is True

    file.write_text(json.dumps({"account_info": []}), encoding="utf-8")
    assert await made.linked() is False


# ----------------------------------------------------------------------------------------
# The passwords the browser saved: counted, never read
# ----------------------------------------------------------------------------------------


def logins(profile: Path, rows: int) -> Path:
    file = profile / "Default" / "Login Data"
    file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(file) as database:
        database.execute("create table logins (origin_url text, password_value blob)")
        database.executemany(
            "insert into logins values (?, ?)",
            [(f"https://{n}.example", b"x") for n in range(rows)],
        )
    return file


@pytest.mark.parametrize("rows", [0, 3])
async def test_the_saved_passwords_are_counted(tmp_path: Path, rows: int) -> None:
    profile = tmp_path / "profile"
    logins(profile, rows)
    profile.chmod(0o700)

    assert saved_in(profile) == rows
    assert await chrome(profile).saved() == rows


def test_a_profile_never_launched_has_saved_none(tmp_path: Path) -> None:
    assert saved_in(tmp_path) == 0


def test_a_file_that_cannot_be_counted_is_said_and_never_called_none(tmp_path: Path) -> None:
    file = tmp_path / "Default" / "Login Data"
    file.parent.mkdir()
    file.write_bytes(b"this is not a database at all")

    with pytest.raises(BrowserFailed, match="cannot be counted"):
        saved_in(tmp_path)


def test_counting_does_not_wait_for_a_browser_that_holds_the_file(tmp_path: Path) -> None:
    """A browser that runs keeps its database locked: the count reads the file as it is."""
    file = logins(tmp_path, 2)
    holding = sqlite3.connect(file)
    try:
        holding.execute("begin exclusive")

        assert saved_in(tmp_path) == 2
    finally:
        holding.close()


# ----------------------------------------------------------------------------------------
# The folder: the user's own, for the user alone
# ----------------------------------------------------------------------------------------


async def test_without_a_declared_folder_every_use_says_which_line_to_write() -> None:
    made = chrome(None)

    for use in (made.occupied, made.linked, made.saved, lambda: made.window(None)):
        with pytest.raises(ProfileUndeclared, match=VARIABLE):
            await use()
    with pytest.raises(ProfileUndeclared, match=VARIABLE):
        await made.open("https://example.com/", lambda address: True, FakeStop())
    assert not made._drivers, "and nothing was started"


async def test_a_folder_that_is_not_there_is_made_for_its_owner_alone(tmp_path: Path) -> None:
    """With the folders above it, when they are not there either: the place the guide proposes is
    beside the node's secret, in a folder a first start may not have made yet."""
    profile = tmp_path / "state" / "browser-profile"

    assert await chrome(profile).occupied() is None

    assert profile.is_dir()
    assert profile.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("umask", [0o000, 0o022, 0o277], ids=oct)
async def test_the_folder_ela_makes_is_0700_whatever_the_umask(tmp_path: Path, umask: int) -> None:
    """Exactly ``0700``: not wider under a umask that hides nothing, not narrower under one that
    would take a bit of the owner's away."""
    profile = tmp_path / "browser-profile"
    old = os.umask(umask)
    try:
        assert await chrome(profile).occupied() is None
    finally:
        os.umask(old)

    assert profile.stat().st_mode & 0o7777 == 0o700


class Appearing(type(Path())):  # type: ignore[misc]
    """A folder somebody makes between ELA's look and ELA's making: not there at the first look,
    there at every one after."""

    looks = 0

    def lstat(self) -> os.stat_result:
        type(self).looks += 1
        if type(self).looks == 1:
            raise FileNotFoundError(str(self))
        return super().lstat()  # type: ignore[no-any-return]


@pytest.mark.parametrize(("mode", "accepted"), [(0o700, True), (0o755, False)])
async def test_a_folder_that_appears_while_ela_is_making_it_is_looked_at_like_any_other(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: int, accepted: bool
) -> None:
    """Two openings at once, the first time ever: both find no folder, one makes it, and the
    other finds it made — *seen on this machine, as a FileExistsError out of a test of the real
    browser*. Whoever finds it made looks at it again, and trusts nothing about who made it."""
    monkeypatch.setattr(Appearing, "looks", 0)
    profile = Appearing(tmp_path / "profile")
    Path(profile).mkdir()
    Path(profile).chmod(mode)
    made = chrome(profile)

    if accepted:
        assert await made.occupied() is None
    else:
        with pytest.raises(ProfileUnsafe, match="does not narrow it"):
            await made.occupied()
    assert Path(profile).stat().st_mode & 0o777 == mode


@pytest.mark.parametrize("mode", [0o750, 0o705, 0o701, 0o777, 0o1700])
async def test_a_folder_found_wider_is_refused_and_not_narrowed(tmp_path: Path, mode: int) -> None:
    """ELA does not narrow it by itself: a folder somebody widened was widened by somebody."""
    profile = tmp_path / "profile"
    profile.mkdir()
    profile.chmod(mode)
    made = chrome(profile)

    with pytest.raises(ProfileUnsafe, match="does not narrow it") as refused:
        await made.occupied()
    with pytest.raises(ProfileUnsafe):
        await made.open("https://example.com/", lambda address: True, FakeStop())

    assert profile.stat().st_mode & 0o7777 == mode
    assert str(profile) not in str(refused.value), "the folder is not named outside its adapter"
    assert VARIABLE in str(refused.value)
    assert not made._drivers


async def test_a_folder_narrower_than_its_owner_s_whole_is_the_owner_s_business(
    tmp_path: Path,
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)

    assert await chrome(profile).occupied() is None


async def test_a_link_or_a_file_where_the_folder_would_be_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(real)
    file = tmp_path / "file"
    file.write_text("not a folder", encoding="utf-8")

    for found in (link, file):
        with pytest.raises(ProfileUnsafe, match="a link, or is not a folder"):
            await chrome(found).occupied()


async def test_a_folder_of_another_user_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built by saying who asks: the folder is this user's, and the one who asks is another."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    monkeypatch.setattr(os, "getuid", lambda: os.stat(profile).st_uid + 1)

    with pytest.raises(ProfileUnsafe, match="another user"):
        await chrome(profile).occupied()


async def test_where_the_browser_is_not_installed_it_says_so_and_no_window_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A look at a file, where Playwright would launch the browser from: a registry that holds
    nothing holds no Chrome for Testing. The folder of the profile is not made for it."""
    from ela.ports import BrowserNotInstalled

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "an-empty-registry"))
    made = chrome(tmp_path / "profile")

    assert await made.installed() is False
    with pytest.raises(BrowserNotInstalled):
        await made.window(None)
    assert made._window is None and not (tmp_path / "profile").exists()


def test_where_it_is_installed_is_a_file_in_the_registry_of_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Built: a registry with the folder of the lock's revision and the binary in it — whatever
    the processor's folder is called."""
    import asyncio as loop

    from ela.infrastructure.machine.browser import registry_folder

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    folder = registry_folder("chromium", os.environ, "Darwin")
    assert folder is not None and folder.parent == tmp_path
    binary = folder.joinpath("chrome-mac-x64", "Google Chrome for Testing.app", "Contents", "MacOS")
    binary.mkdir(parents=True)
    made = chrome(tmp_path / "profile")
    assert loop.run(made.installed()) is False, "a folder is not a browser"

    (binary / "Google Chrome for Testing").write_bytes(b"a binary")

    assert loop.run(made.installed()) is True


@pytest.mark.parametrize("system", ["Linux", "Windows"])
async def test_on_a_system_that_is_not_the_mac_every_use_says_so(
    tmp_path: Path, system: str
) -> None:
    made = chrome(tmp_path / "profile", system=system)

    for use in (made.installed, made.occupied, lambda: made.window(None)):
        with pytest.raises(BrowserUnsupported, match=system):
            await use()
    with pytest.raises(BrowserUnsupported):
        await made.open("https://example.com/", lambda address: True, FakeStop())
    assert not (tmp_path / "profile").exists(), "and no folder was made for a browser that is not"


# ----------------------------------------------------------------------------------------
# One process at a time: who holds the folder, derived
# ----------------------------------------------------------------------------------------


def test_the_lock_names_who_holds_the_folder_only_if_the_kernel_knows_it(tmp_path: Path) -> None:
    assert lock_holder(tmp_path, lambda pid: True) is None, "no lock, nobody"

    locked_by(tmp_path, 4321)
    assert lock_holder(tmp_path, lambda pid: pid == 4321) == 4321
    assert lock_holder(tmp_path, lambda pid: False) is None, "a lock left by a process that is gone"


@pytest.mark.parametrize(
    "left",
    [f"{socket.gethostname()}-not-a-pid", "not-a-pid", "-", ""],
    ids=["a-host-and-no-pid", "no-pid", "a-dash", "empty"],
)
def test_a_lock_that_names_no_pid_holds_nothing(tmp_path: Path, left: str) -> None:
    (tmp_path / "SingletonLock").symlink_to(left)

    assert lock_holder(tmp_path, lambda pid: True) is None


@pytest.mark.parametrize("host", ["192.168.1.4", "another-name.local", "a-name-with-dashes"])
def test_the_lock_is_read_by_its_pid_whatever_it_calls_the_machine(
    tmp_path: Path, host: str
) -> None:
    """Measured on 2026-10-11: this Mac called itself by an address of the network it was on, and
    so did the lock of its browser — a machine's name changes with its network. A browser that
    runs under yesterday's name runs all the same, and a second launch on its folder is the one
    that can kill it."""
    locked_by(tmp_path, 4321, host=host)

    assert lock_holder(tmp_path, lambda pid: pid == 4321) == 4321
    assert lock_holder(tmp_path, lambda pid: False) is None


def test_a_file_where_the_lock_would_be_holds_nothing(tmp_path: Path) -> None:
    (tmp_path / "SingletonLock").write_text(f"{socket.gethostname()}-1", encoding="utf-8")

    assert lock_holder(tmp_path, lambda pid: True) is None


async def test_a_folder_held_by_a_process_the_kernel_knows_is_busy_and_nothing_is_launched(
    tmp_path: Path,
) -> None:
    """ELA does not launch a second process on a folder it found held: it is the launch that can
    kill the first. Here the holder is this very test."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)

    assert await made.occupied() == PROFILE_PROCESS
    with pytest.raises(ProfileBusy) as busy:
        await made.open("https://example.com/", lambda address: True, FakeStop())
    assert busy.value.by == PROFILE_PROCESS
    with pytest.raises(ProfileBusy):
        await made.window(None)
    assert not made._drivers and made._window is None
    assert not (profile / "Default").exists(), "the folder of a browser that runs is not touched"


async def test_a_lock_left_by_a_process_that_is_gone_is_not_busy(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, a_dead_pid())

    assert await chrome(profile).occupied() is None


async def test_what_the_adapter_itself_has_in_flight_holds_the_folder_before_any_lock(
    tmp_path: Path,
) -> None:
    """A page being opened has no lock yet — the browser is starting —, and one being closed may
    have its lock still: both are a step of ELA's, and the folder is theirs."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)

    made._opening = 1
    assert await made.occupied() == PROFILE_STEP
    made._opening = 0

    made._pages["a page"] = object()  # type: ignore[assignment]
    assert await made.occupied() == PROFILE_STEP
    made._pages.clear()

    closing = asyncio.ensure_future(asyncio.sleep(60))
    made._closing.add(closing)
    assert await made.occupied() == PROFILE_STEP
    made._closing.clear()
    closing.cancel()

    made._windowing = True
    assert await made.occupied() == PROFILE_WINDOW
    made._windowing = False

    assert await made.occupied() is None


# ----------------------------------------------------------------------------------------
# What a launch is given: closed lists, and no disguise
# ----------------------------------------------------------------------------------------


def test_the_options_of_a_launch_are_the_closed_set(tmp_path: Path) -> None:
    """No HAR, no tracing, no video — a HAR would keep the body of a ``POST`` —, and no disguise:
    no user agent, no header, nothing injected (decision 19)."""
    options: dict[str, Any] = chrome(tmp_path)._launch()

    assert set(options) == LAUNCH_OPTIONS
    assert options["channel"] == "chromium", "Chrome for Testing of the lock, and no other binary"
    assert options["chromium_sandbox"] is True
    assert options["headless"] is True
    assert options["accept_downloads"] is False
    assert options["service_workers"] == "block"
    assert (options["handle_sigint"], options["handle_sigterm"], options["handle_sighup"]) == (
        False,
        False,
        False,
    )
    assert options["args"] == list(LAUNCH_ARGUMENTS)
    assert options["env"] == {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"}
    forbidden = {"record_har_path", "record_video_dir", "user_agent", "extra_http_headers"}
    assert not forbidden & set(options)


def test_with_or_without_a_window_is_asked_at_every_launch(tmp_path: Path) -> None:
    """The user's switch, read when a browser starts — never fixed when the adapter is built."""
    shown = [False]
    made = AccountChrome(
        asyncio.Event(),
        environment={},
        kept=Kept(),
        system="Darwin",
        profile=tmp_path,
        shown=lambda: shown[0],
    )

    assert made._launch()["headless"] is True
    shown[0] = True
    assert made._launch()["headless"] is False


def test_the_arguments_of_a_launch_and_of_the_window_are_closed_lists() -> None:
    """Never the keychain, never the browser's own sync or sign-in — and nothing that attaches
    anything to the window, or dresses the browser as another."""
    assert LAUNCH_ARGUMENTS == (
        "--use-mock-keychain",
        "--disable-sync",
        "--allow-browser-signin=false",
    )
    assert WINDOW_ARGUMENTS == (
        "--use-mock-keychain",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--allow-browser-signin=false",
    )
    attached = ("--remote-debugging", "--headless", "--enable-automation", "--load-extension")
    disguised = ("--user-agent", "--disable-blink-features")
    for argument in (*LAUNCH_ARGUMENTS, *WINDOW_ARGUMENTS):
        assert not argument.startswith((*attached, *disguised, "--no-sandbox"))


async def test_once_ela_is_stopping_nothing_of_the_profile_is_started(tmp_path: Path) -> None:
    made = chrome(tmp_path / "profile")
    made._stopping.set()

    with pytest.raises(BrowserStopped):
        await made.open("https://example.com/", lambda address: True, FakeStop())
    with pytest.raises(BrowserStopped):
        await made.window(None)
    with pytest.raises(BrowserStopped):
        await made.installed()
    assert not (tmp_path / "profile").exists()
