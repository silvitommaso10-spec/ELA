"""The profile of the browser with the user's accounts, **without a browser** (M13.9, ADR 0063).

What the adapter does to the folder and reads from it is asserted here on folders the test
builds: **no browser is started**, so these run wherever the suite runs — the system is handed to
the adapter as the composition hands it. What only the real binary can say is in
``test_account_browser.py``.

Since the review of 2026-10-11 the adapter asks the system what a process is, and the tests of
that question start what it starts — the system's own ``ps``, or a small program of the test's in
its place — and one child of the interpreter to ask about: each is collected by the test that
started it.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ela.infrastructure.machine import account
from ela.infrastructure.machine.account import (
    ANOTHER_PROGRAM,
    ELA_S_BROWSER,
    LAUNCH_ARGUMENTS,
    LAUNCH_OPTIONS,
    PREFERENCES,
    WINDOW_ARGUMENTS,
    AccountChrome,
    command_line,
    linked_in,
    lock_holder,
    on_the_folder,
    process_table,
    profiles_in,
    reports_in,
    saved_in,
    with_preferences,
)
from ela.infrastructure.machine.browser import PlaywrightBrowser
from ela.ports import (
    HELD,
    HELD_IN_PART,
    NOT_HELD,
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    AccountBrowser,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    NoWindow,
    Opened,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Secret,
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


def said_by(error: BaseException) -> str:
    """Whatever an exception carries, and whatever it is chained to: the place a path hides."""
    said, seen = [], set()
    todo: list[BaseException | None] = [error]
    while todo:
        one = todo.pop()
        if one is None or id(one) in seen:
            continue
        seen.add(id(one))
        said.append(f"{one!r} {one} {one.args!r} {vars(one)!r}")
        todo.extend([one.__cause__, one.__context__])
    return "\n".join(said)


@pytest.fixture(autouse=True)
def no_browser_of_this_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """«No browser is started» is built, and not hoped for: the registry these tests look in
    holds no browser unless a test puts a file there — so a test that is red, or a mutant of the
    adapter, finds nothing to launch where the machine's own Chrome for Testing would be."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "a-registry-with-nothing-in-it"))


def locked_by(profile: Path, pid: int, host: str | None = None) -> None:
    """The link a browser leaves in its folder while it runs, as the test says it."""
    (profile / "SingletonLock").symlink_to(
        f"{socket.gethostname() if host is None else host}-{pid}"
    )


def a_dead_pid() -> int:
    """The pid of a process that has ended and been collected: the kernel knows it no more."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A registry of Playwright's that holds the browser of the lock's revision — a file where
    the binary would be, which no test launches. **Built, not inherited**: on a machine where
    Chrome for Testing was never installed — every runner but the Mac's — the adapter would say
    so before it looks at anything else, and a test of what comes after would be testing that."""
    from ela.infrastructure.machine.browser import registry_folder

    registry = tmp_path / "registry"
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(registry))
    folder = registry_folder("chromium", os.environ, "Darwin")
    assert folder is not None
    binary = folder.joinpath(
        "chrome-mac-arm64", "Google Chrome for Testing.app", "Contents", "MacOS"
    )
    binary.mkdir(parents=True)
    (binary / "Google Chrome for Testing").write_bytes(b"a file where the binary would be")
    return registry


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


def test_a_link_where_the_new_file_is_written_is_not_followed(tmp_path: Path) -> None:
    """The preferences are written beside the file and moved over it. A link left where they are
    written — by whatever ran in the profile — would have ELA overwrite the file it leads to, at
    every launch, and leave the preferences a link to it."""
    victim = tmp_path / "a-file-of-the-user-s"
    victim.write_text("what the user wrote", encoding="utf-8")
    profile = tmp_path / "profile"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Preferences.ela").symlink_to(victim)

    account._prepared(profile, driven=False)

    assert victim.read_text(encoding="utf-8") == "what the user wrote"
    file = profile / "Default" / "Preferences"
    assert file.is_file() and not file.is_symlink()
    assert json.loads(file.read_text(encoding="utf-8")) == PREFERENCES
    assert sorted(found.name for found in file.parent.iterdir()) == ["Preferences"]


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


@pytest.mark.parametrize("driven", [True, False], ids=["a-driven-launch", "the-window"])
def test_before_every_launch_what_a_crash_left_is_gone_and_nothing_else_of_the_folder(
    tmp_path: Path, driven: bool
) -> None:
    """Decision 90: a report of a crash is memory of the process that held the user's sessions
    — and, in the moment of a login, a password —, it serves nobody, and it does not pass to the
    launch after. Taken away before **every** launch, the window's too: unlike the workers, it
    is no site's. **And only that**: what the browser keeps of the user's stays where it is."""
    reports = tmp_path / "Crashpad"
    (reports / "pending").mkdir(parents=True)
    (reports / "pending" / "a-report.dmp").write_bytes(b"memory of a process that fell")
    (reports / "settings.dat").write_bytes(b"the collector's own settings")
    kept = tmp_path / "Default" / "Cookies"
    kept.parent.mkdir()
    kept.write_bytes(b"the sessions of the user")
    state = tmp_path / "Local State"
    state.write_text("{}", encoding="utf-8")

    account._prepared(tmp_path, driven=driven)

    assert not reports.exists(), "what a crash left is not there for the launch after"
    assert kept.read_bytes() == b"the sessions of the user" and state.is_file()
    assert (tmp_path / "Default" / "Preferences").is_file()


@pytest.mark.parametrize("driven", [True, False], ids=["a-driven-launch", "the-window"])
def test_a_link_where_the_reports_would_be_is_taken_away_and_not_followed(
    tmp_path: Path, driven: bool
) -> None:
    """The link goes — the collector would write, through it, a process's memory into whatever
    folder it leads to —, and what it points at is nobody's to remove."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "kept").write_text("somebody's", encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "Crashpad").symlink_to(elsewhere, target_is_directory=True)

    account._prepared(profile, driven=driven)

    assert not (profile / "Crashpad").is_symlink() and not (profile / "Crashpad").exists()
    assert (elsewhere / "kept").is_file()


def test_a_file_where_the_reports_would_be_is_taken_away_too(tmp_path: Path) -> None:
    (tmp_path / "Crashpad").write_bytes(b"not a folder at all")

    account._prepared(tmp_path, driven=False)

    assert not (tmp_path / "Crashpad").exists()


def test_the_folder_of_the_reports_is_the_one_every_launch_is_told_to_write_in(
    tmp_path: Path,
) -> None:
    """What is taken away and where the collector is told to write are one name: a collector
    told to write elsewhere would leave what nothing takes away."""
    assert reports_in(tmp_path) == f"--breakpad-dump-location={tmp_path / account.REPORTS}"
    (tmp_path / account.REPORTS).mkdir()

    account._prepared(tmp_path, driven=True)

    assert not (tmp_path / account.REPORTS).exists()


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


def logins(profile: Path, rows: int, inside: str = "Default") -> Path:
    file = profile / inside / "Login Data"
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


async def test_the_saved_passwords_are_counted_in_every_profile_the_folder_holds(
    tmp_path: Path,
) -> None:
    """A second profile the user added from inside the window is one ELA neither prepares nor
    uses — and what was saved there was saved in ELA's browser all the same (decision 79)."""
    profile = tmp_path / "profile"
    logins(profile, 3)
    logins(profile, 2, inside="Profile 1")
    (profile / "Crashpad").mkdir()  # a folder of the browser's that is no profile
    profile.chmod(0o700)

    assert saved_in(profile) == 5
    assert await chrome(profile).saved() == 5


@pytest.mark.parametrize("linked", ["a-profile", "its-file"])
def test_what_a_link_leads_to_is_not_counted_and_is_not_called_none(
    tmp_path: Path, linked: str
) -> None:
    """ELA reads the profile of its own browser, and nothing a link leads to: not a profile
    that is a link to another folder, and not a file of the passwords that is a link. **And it
    does not say «none» of it** (the re-read of the round): the browser follows both links, so
    what is there is passwords ELA did not count — said as what cannot be counted."""
    elsewhere = tmp_path / "another-browser"
    logins(elsewhere, 7)
    profile = tmp_path / "profile"
    logins(profile, 1)
    if linked == "a-profile":
        (profile / "Profile 1").symlink_to(elsewhere / "Default", target_is_directory=True)
    else:
        (profile / "Profile 1").mkdir()
        (profile / "Profile 1" / "Login Data").symlink_to(elsewhere / "Default" / "Login Data")

    with pytest.raises(BrowserFailed, match="cannot be counted") as failed:
        saved_in(profile)

    assert str(tmp_path) not in said_by(failed.value)


def test_a_link_the_browser_itself_leaves_in_its_folder_is_nothing_to_count(
    tmp_path: Path,
) -> None:
    """The lock, its cookie and its socket are links the browser makes, and none leads to a
    folder: they are not profiles, and they stop no count."""
    logins(tmp_path, 2)
    locked_by(tmp_path, 4321)
    (tmp_path / "SingletonCookie").symlink_to("12345678901234567890")
    (tmp_path / "RunningChromeVersion").symlink_to("153.0.8010.12:1")

    assert saved_in(tmp_path) == 2


def test_a_second_profile_that_cannot_be_counted_is_said_and_never_left_out(
    tmp_path: Path,
) -> None:
    logins(tmp_path, 2)
    (tmp_path / "Profile 1").mkdir()
    (tmp_path / "Profile 1" / "Login Data").write_bytes(b"this is not a database at all")

    with pytest.raises(BrowserFailed, match="cannot be counted"):
        saved_in(tmp_path)


def listed(folder: Path, *names: str) -> None:
    """The browser's own list of its profiles, as it keeps it in ``Local State`` — with, for
    each, what the test would not want to see leave: a name and an account."""
    cache = {name: {"name": "Persona 1", "user_name": "somebody@example.com"} for name in names}
    (folder / "Local State").write_text(
        json.dumps({"profile": {"info_cache": cache, "last_used": names[-1]}}), encoding="utf-8"
    )


async def test_the_folder_says_how_many_profiles_the_browser_itself_lists(tmp_path: Path) -> None:
    """A profile is what **the browser itself lists** — the names in its ``Local State`` —, not
    whatever folder holds a ``Preferences``: the browser keeps folders of its own beside its
    profiles — the one of its profile picker, the one of a guest window — that are none
    (the re-read of the round). Counted, so that the state can say there is more than the one ELA
    prepares and uses (decision 79); read as presence, never as what a profile is called."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)
    assert profiles_in(profile) == 0 and await made.profiles() == 0, "before the first launch"

    for name in ("Default", "System Profile", "Guest Profile", "Crashpad"):
        (profile / name).mkdir()
        (profile / name / "Preferences").write_text("{}", encoding="utf-8")
    listed(profile, "Default")
    assert profiles_in(profile) == 1 and await made.profiles() == 1

    listed(profile, "Default", "Profile 1")
    assert profiles_in(profile) == 2 and await made.profiles() == 2


@pytest.mark.parametrize(
    "written",
    ["this is not json", "[]", '{"profile": 3}', '{"profile": {"info_cache": []}}'],
    ids=["not-json", "not-an-object", "no-profiles", "a-list-that-is-no-list-of-names"],
)
def test_a_list_of_the_profiles_that_cannot_be_read_is_said_and_never_a_number(
    tmp_path: Path, written: str
) -> None:
    (tmp_path / "Local State").write_text(written, encoding="utf-8")

    with pytest.raises(BrowserFailed, match="cannot be listed") as failed:
        profiles_in(tmp_path)

    assert str(tmp_path) not in said_by(failed.value)


def test_a_list_of_the_profiles_that_is_a_link_is_not_read_through(tmp_path: Path) -> None:
    elsewhere = tmp_path / "another-browser"
    elsewhere.mkdir()
    listed(elsewhere, "Default", "Profile 1", "Profile 2")
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "Local State").symlink_to(elsewhere / "Local State")

    with pytest.raises(BrowserFailed, match="cannot be listed"):
        profiles_in(profile)


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


async def test_without_a_declared_folder_every_use_says_which_line_to_write(
    installed: Path,
) -> None:
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


async def test_a_link_that_appears_while_ela_is_making_the_folder_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second look is the first one's equal: it does not follow a link either."""
    monkeypatch.setattr(Appearing, "looks", 0)
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    profile = Appearing(tmp_path / "profile")
    Path(profile).symlink_to(real)

    with pytest.raises(ProfileUnsafe, match="a link, or is not a folder"):
        await chrome(profile).occupied()


class Watched(type(Path())):  # type: ignore[misc]
    """A folder that says how it was found when ELA came to narrow it."""

    found: list[int] = []  # noqa: RUF012 — one list, emptied by the test that reads it

    def chmod(self, mode: int, *, follow_symlinks: bool = True) -> None:
        type(self).found.append(self.stat().st_mode & 0o7777)
        super().chmod(mode, follow_symlinks=follow_symlinks)


async def test_the_folder_ela_makes_is_never_wider_than_0700_not_even_for_an_instant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Made ``0700`` and then set ``0700`` — the second for a umask that would take a bit of the
    owner's away. Made wider and narrowed after, it would be open to others between the two."""
    monkeypatch.setattr(Watched, "found", [])
    profile = Watched(tmp_path / "profile")
    old = os.umask(0o022)
    try:
        assert await chrome(profile).occupied() is None
    finally:
        os.umask(old)

    assert Watched.found == [0o700]


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
    profile.mkdir()
    profile.chmod(0o500)
    try:
        assert await chrome(profile).occupied() is None
    finally:
        profile.chmod(0o700)


class Unmakeable(type(Path())):  # type: ignore[misc]
    """A folder that is not there and that this user may not make: under a folder that cannot be
    written — a volume that went away, a place of the system's."""

    def mkdir(self, *arguments: Any, **options: Any) -> None:
        raise PermissionError(13, "Permission denied", str(self))


@pytest.mark.parametrize("why", ["under-a-file", "cannot-be-made"])
async def test_a_folder_ela_cannot_look_at_or_make_is_refused_and_never_named(
    tmp_path: Path, installed: Path, why: str
) -> None:
    """Whatever the system says of the folder — a part of its path is a file, a folder above it
    cannot be written — is the adapter's own refusal: **an error of the browser**, which every
    caller already answers, and not one of the system's, which nobody catches and which names
    the path."""
    if why == "under-a-file":
        (tmp_path / "a-file").write_text("not a folder", encoding="utf-8")
        profile = tmp_path / "a-file" / "profile"
    else:
        profile = Unmakeable(tmp_path / "profile")
    made = chrome(profile)

    uses = (
        made.occupied,
        made.linked,
        made.saved,
        lambda: made.window(None),
        lambda: made.open("https://example.com/", lambda address: True, FakeStop()),
    )
    for use in uses:
        with pytest.raises(ProfileUnsafe, match=VARIABLE) as refused:
            await use()
        assert str(tmp_path) not in said_by(refused.value)
    assert not made._drivers and made._window is None


@pytest.mark.parametrize("launch", ["the-window", "a-page"])
async def test_a_folder_that_cannot_be_prepared_is_a_failure_of_the_browser_and_never_named(
    tmp_path: Path, installed: Path, monkeypatch: pytest.MonkeyPatch, launch: str
) -> None:
    """A folder its owner narrowed passes the look, and cannot be written into: what the system
    says of the write does not leave the adapter either."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)

    def unwritable(folder: Path, *, driven: bool) -> None:
        raise PermissionError(13, "Permission denied", str(folder / "Default"))

    monkeypatch.setattr(account, "_prepared", unwritable)
    made = chrome(profile)

    with pytest.raises(BrowserFailed, match="PermissionError") as failed:
        if launch == "the-window":
            await made.window(None)
        else:
            await made._begun(None)  # type: ignore[arg-type]  # refused before the engine is asked

    assert str(tmp_path) not in said_by(failed.value)
    assert made._window is None and await made.occupied() is None


def another_browser(tmp_path: Path) -> Path:
    """The ``Default`` of a browser that is not ELA's, with what a profile keeps in it."""
    other = tmp_path / "another-browser" / "Default"
    (other / "Service Worker" / "ScriptCache").mkdir(parents=True)
    (other / "Service Worker" / "ScriptCache" / "index").write_text("a worker", encoding="utf-8")
    (other / "Preferences").write_text(json.dumps({"signin": {"allowed": True}}), encoding="utf-8")
    logins(other.parent, 4)
    return other


@pytest.mark.parametrize("found", ["a-link", "a-file"])
async def test_a_default_that_is_not_a_folder_of_its_own_is_refused_and_nothing_is_reached(
    tmp_path: Path, installed: Path, found: str
) -> None:
    """The folder is the user's own **below its top too**: with ``Default`` a link, ELA would
    count the passwords of the folder it leads to, rewrite its preferences and take its workers
    away at every launch — the profile of another browser, if that is where it leads."""
    other = another_browser(tmp_path)
    before = (other / "Preferences").read_text(encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    if found == "a-link":
        (profile / "Default").symlink_to(other)
    else:
        (profile / "Default").write_text("not a folder", encoding="utf-8")
    made = chrome(profile)

    uses = (
        made.occupied,
        made.linked,
        made.saved,
        lambda: made.window(None),
        lambda: made.open("https://example.com/", lambda address: True, FakeStop()),
    )
    for use in uses:
        with pytest.raises(ProfileUnsafe, match="Default"):
            await use()

    assert (other / "Preferences").read_text(encoding="utf-8") == before
    assert (other / "Service Worker" / "ScriptCache" / "index").is_file()
    assert not made._drivers and made._window is None


async def test_a_folder_named_as_the_profiles_ela_takes_away_after_a_kill_is_refused(
    tmp_path: Path,
) -> None:
    """After a kill at the grace ELA removes the temporary profiles Playwright made, which it
    knows by their name. A declared folder is never one of them — and so it does not bear the
    name."""
    profile = tmp_path / "playwright_chromiumdev_profile-of-mine"
    profile.mkdir(mode=0o700)

    with pytest.raises(ProfileUnsafe, match="another name"):
        await chrome(profile).occupied()
    assert profile.is_dir()


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

    uses = (made.installed, made.occupied, made.linked, made.saved, lambda: made.window(None))
    for use in uses:
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
    [f"{socket.gethostname()}-not-a-pid", "not-a-pid", "-"],
    ids=["a-host-and-no-pid", "no-pid", "a-dash"],
)
def test_a_lock_that_names_no_pid_holds_nothing(tmp_path: Path, left: str) -> None:
    (tmp_path / "SingletonLock").symlink_to(left)

    assert lock_holder(tmp_path, lambda pid: True) is None


@pytest.mark.parametrize(
    "left",
    ["h-²", "h-٣", "h-" + "9" * 30, "h-0", "h-1", "h-00", "h-4294967296"],
    ids=[
        "a-superscript",
        "a-digit-of-another-script",
        "thirty-nines",
        "zero",
        "one",
        "zeros",
        "2^32",
    ],
)
def test_a_lock_that_names_what_cannot_be_a_browser_s_pid_holds_nothing_and_raises_nothing(
    tmp_path: Path, left: str
) -> None:
    """Asked of the kernel as it is: a number no process can have is an error of the question —
    which nobody catches —, zero is «every process of my group» and one is the system's own
    first process, which answer for ever. None of them is a browser that runs."""
    from ela.infrastructure.machine.browser import _alive

    (tmp_path / "SingletonLock").symlink_to(left)

    assert lock_holder(tmp_path, _alive) is None
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


BINARY = "/a registry/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/the binary"


def a_browser_on(profile: Path, binary: str = BINARY) -> str:
    """What the system prints of a browser that runs on ``profile``: its arguments, joined."""
    return f"{binary} --use-mock-keychain --user-data-dir={profile} --disable-sync about:blank"


@pytest.mark.parametrize(
    ("command", "what"),
    [
        ("{binary} --user-data-dir={profile} --no-first-run", ELA_S_BROWSER),
        ("{binary} --no-first-run --user-data-dir={profile}", ELA_S_BROWSER),
        ("/Applications/Another Browser --user-data-dir={profile}", ANOTHER_PROGRAM),
        ("{binary} Helper --user-data-dir={profile}", ANOTHER_PROGRAM),
        ("{binary} --type=renderer --user-data-dir={profile}", ANOTHER_PROGRAM),
        ("{binary} --user-data-dir={profile}-of-another", None),
        ("{binary} --user-data-dir={profile}/Default", None),
        ("{binary} --user-data-dir=/somewhere/else", None),
        ("{binary}", None),
        ("/usr/sbin/a-daemon --that-has --nothing-to-do-with-it", None),
        ("(the binary)", None),
        ("", None),
    ],
    ids=[
        "ela-s-binary-on-the-folder",
        "the-folder-named-last",
        "another-program-on-the-folder",
        "a-program-whose-path-begins-as-the-binary-s",
        "a-helper-of-the-browser-s-own",
        "a-folder-whose-name-begins-as-this-one-s",
        "a-folder-inside-this-one",
        "the-binary-on-another-folder",
        "the-binary-on-no-folder",
        "a-program-that-has-nothing-to-do-with-it",
        "a-process-that-has-ended-and-is-not-collected",
        "a-process-that-is-gone",
    ],
)
def test_what_a_process_the_lock_names_is_is_read_from_its_command_line(
    tmp_path: Path, command: str, what: str | None
) -> None:
    """One function, for the two things that ask (decisions 80 and 82): the folder is held only
    by a process whose command line names it, and ELA tells to quit only one that is its own
    binary on it."""
    profile = tmp_path / "a profile"
    said = command.format(binary=BINARY, profile=profile)

    assert on_the_folder(said, profile, Path(BINARY)) == what


def test_the_folder_is_the_folder_however_its_path_is_written(tmp_path: Path) -> None:
    """The re-read of the round: a browser started by hand on the folder names it as a shell
    wrote it — with the slash a completion leaves at its end, through a link above it — and it
    is on the folder all the same. Read as text only, it held nothing: a step was launched over
    it, and ELA looked at the screen while a hand could be signing in."""
    real = tmp_path / "real"
    profile = real / "a profile"
    profile.mkdir(parents=True)
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    binary = Path(BINARY)

    assert on_the_folder(f"{BINARY} --user-data-dir={profile}/", profile, binary) == ELA_S_BROWSER
    through = tmp_path / "link" / "a profile"
    assert on_the_folder(f"{BINARY} --user-data-dir={through} --x", profile, binary) == (
        ELA_S_BROWSER
    )
    assert on_the_folder(f"{BINARY} --user-data-dir={profile}/ --x", through, binary) == (
        ELA_S_BROWSER
    )
    other = tmp_path / "another"
    other.mkdir()
    assert on_the_folder(f"{BINARY} --user-data-dir={other}/", profile, binary) is None


@pytest.mark.parametrize(
    "named", ["a profile", "./a profile", "../somewhere/a profile", ""], ids=repr
)
def test_a_folder_named_from_where_the_process_stands_is_a_doubt(
    tmp_path: Path, named: str
) -> None:
    """Where that process stands ELA does not know: a path that does not begin at the root
    cannot be said to be another folder. A doubt holds, and is told nothing."""
    profile = tmp_path / "a profile"

    assert on_the_folder(f"{BINARY} --user-data-dir={named} --x", profile, Path(BINARY)) == (
        ANOTHER_PROGRAM
    )


@pytest.mark.parametrize(
    "command",
    [
        "{binary} --user-data-dir={profile} two --no-first-run",
        "{binary} --user-data-dir={profile} https://accounts.example/",
        "{binary} --remote-debugging-pipe --user-data-dir={profile} about:blank",
        "{binary} --user-data-dir={profile} --remote-debugging-port=9222",
    ],
    ids=[
        "a-longer-folder-or-this-one-and-a-word",
        "this-folder-and-then-what-is-no-switch",
        "a-browser-somebody-drives",
        "a-browser-with-a-port-open",
    ],
)
def test_ela_tells_to_quit_only_what_is_plainly_its_browser_with_nothing_attached(
    tmp_path: Path, command: str
) -> None:
    """The system prints the arguments joined by spaces: where the folder's name ends is plain
    only when a switch follows it, or nothing. And a browser with a driver or a port attached is
    a step of somebody's — another ELA on this folder —, not the browser a hand may be on. Each
    holds the folder; none is told."""
    profile = tmp_path / "a profile"
    said = command.format(binary=BINARY, profile=profile)

    assert on_the_folder(said, profile, Path(BINARY)) == ANOTHER_PROGRAM


def test_a_command_line_nobody_could_read_is_a_doubt_and_a_doubt_holds_the_folder(
    tmp_path: Path,
) -> None:
    """Fail-safe: the lock names a process the kernel knows, and ELA cannot say what it is. The
    folder is held — and that process is not told anything."""
    assert on_the_folder(None, tmp_path, Path(BINARY)) == ANOTHER_PROGRAM


def test_where_the_browser_is_not_installed_no_process_is_ela_s_browser(tmp_path: Path) -> None:
    assert on_the_folder(a_browser_on(tmp_path), tmp_path, None) == ANOTHER_PROGRAM


def test_the_folder_is_named_as_it_was_written_or_as_a_path_is_made_plain(tmp_path: Path) -> None:
    """A driver makes the path it is given plain before it hands it to the browser: the folder
    written with a step back in it is the same folder."""
    profile = tmp_path / "somewhere" / ".." / "a profile"

    assert on_the_folder(a_browser_on(profile), profile, Path(BINARY)) == ELA_S_BROWSER
    assert on_the_folder(a_browser_on(tmp_path / "a profile"), profile, Path(BINARY)) == (
        ELA_S_BROWSER
    )


class Asked:
    """What the system would say of a process, as the test says it — and which it was asked of."""

    def __init__(self, said: str | None, then: Any = None) -> None:
        self.said = said
        self.of: list[int] = []
        self.then = then

    async def __call__(self, pid: int) -> str | None:
        self.of.append(pid)
        await asyncio.sleep(0)
        if self.then is not None:
            self.then()
        return self.said


async def test_a_folder_held_by_a_process_the_kernel_knows_is_busy_and_nothing_is_launched(
    tmp_path: Path, installed: Path
) -> None:
    """ELA does not launch a second process on a folder it found held: it is the launch that can
    kill the first. Here the lock names this very test, and the system is made to say that it is
    a browser on the folder."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)
    made._said_of = asked = Asked(a_browser_on(profile))

    assert await made.occupied() == PROFILE_PROCESS
    assert asked.of == [os.getpid()]
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
    made = chrome(profile)
    made._said_of = asked = Asked(a_browser_on(profile))

    assert await made.occupied() is None
    assert asked.of == [], "nothing is launched to ask about a process that is not there"


@pytest.mark.skipif(sys.platform == "win32", reason="the system's own ps is POSIX's")
async def test_a_lock_whose_pid_went_to_another_process_does_not_hold_the_folder(
    tmp_path: Path, installed: Path
) -> None:
    """A browser that was killed leaves its lock, and the system gives its pid to whatever
    starts next: a process that lasts would hold the folder for ever (decision 82). Here the pid
    is this very test's — which the kernel knows, and which is no browser on the folder: asked of
    the system for real."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)

    assert await made.occupied() is None
    await made._free()  # and a launch would go on: nothing is refused


async def test_a_process_ela_cannot_say_what_it_is_holds_the_folder(
    tmp_path: Path, installed: Path
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)
    made._said_of = Asked(None)

    assert await made.occupied() == PROFILE_PROCESS
    with pytest.raises(ProfileBusy):
        await made.window(None)


async def test_a_system_that_says_nothing_of_a_process_the_kernel_knows_is_a_doubt(
    tmp_path: Path, installed: Path
) -> None:
    """The system's program ends the same way for a process that is gone and for every error of
    its own (measured: a pid too large, a pid that is no number). So «nothing» is believed only
    of a process the kernel does not know any more: of one it still knows, it is a doubt."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)
    made._said_of = Asked("")

    assert await made.occupied() == PROFILE_PROCESS


async def test_another_program_on_the_folder_holds_it_too(tmp_path: Path, installed: Path) -> None:
    """Not ELA's binary, and on the folder all the same: a launch of ELA's would meet it."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)
    made._said_of = Asked(a_browser_on(profile, binary="/Applications/Another Browser"))

    assert await made.occupied() == PROFILE_PROCESS


async def test_the_system_is_asked_what_a_process_is_only_when_a_lock_names_one(
    tmp_path: Path,
) -> None:
    """One launch more, and only when there is a lock (decision 82): not at every capture and
    every listening, which look at the folder too."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)
    made._said_of = asked = Asked(a_browser_on(profile))

    assert await made.occupied() is None, "no lock"
    locked_by(profile, os.getpid())
    made._opening = 1
    assert await made.occupied() == PROFILE_STEP, "a step of ELA's own: its lock is its own"
    made._opening = 0
    made._windowing = True
    assert await made.occupied() == PROFILE_WINDOW
    made._windowing = False
    assert asked.of == []

    assert await made.occupied() == PROFILE_PROCESS
    assert asked.of == [os.getpid()]


async def test_what_the_adapter_has_in_flight_is_looked_at_again_once_the_system_has_answered(
    tmp_path: Path,
) -> None:
    """Asking the system takes its time, and a window may be started meanwhile: the answer this
    ends with is looked at with no wait after it — a second opening that looks now finds the
    first, whatever the lock said."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    locked_by(profile, os.getpid())
    made = chrome(profile)

    def a_window_starts() -> None:
        made._windowing = True

    made._said_of = Asked("a program that has nothing to do with it", then=a_window_starts)

    assert await made.occupied() == PROFILE_WINDOW
    with pytest.raises(ProfileBusy) as busy:
        await made._free()
    assert busy.value.by == PROFILE_WINDOW

    made._windowing = False
    made._said_of = Asked(a_browser_on(profile), then=a_window_starts)
    assert await made.occupied() == PROFILE_WINDOW, "what this adapter has comes first, as ever"


@pytest.mark.skipif(sys.platform == "win32", reason="the system's own ps is POSIX's")
async def test_the_command_line_of_a_process_is_asked_of_the_system(tmp_path: Path) -> None:
    """The one launch the adapter makes to look at a process: its arguments as the system has
    them — and nothing, for a process that is not there any more."""
    named = f"--user-data-dir={tmp_path / 'a profile'}"
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", named])
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    try:
        said = await command_line(child.pid, environment)

        assert said is not None and said.endswith(named) and "time.sleep(60)" in said
    finally:
        child.kill()
        child.wait()
    assert await command_line(child.pid, environment) == ""


@pytest.mark.skipif(sys.platform == "win32", reason="a program that begins with #! is POSIX's")
async def test_a_system_that_cannot_be_asked_says_nothing_and_never_a_guess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No program to ask with, or one that does not answer in its time: ``None``, which the
    adapter reads as a doubt. **And the program that did not answer is not left running**: it is
    killed with its group, and collected."""
    monkeypatch.setattr(account, "PS", str(tmp_path / "no-such-program"))
    assert await command_line(os.getpid(), {}) is None

    failing = tmp_path / "failing"
    failing.write_text(f"#!{sys.executable}\nraise SystemExit(2)\n", encoding="utf-8")
    failing.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(failing))
    assert await command_line(os.getpid(), {}) is None, "it said nothing, and not «no such»"

    slow = tmp_path / "slow"
    slow.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(120)\n", encoding="utf-8")
    slow.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(slow))
    monkeypatch.setattr(account, "PS_SECONDS", 0.2)
    try:
        # The guard is for a program that was not killed: the answer would then wait for it.
        assert await asyncio.wait_for(command_line(os.getpid(), {}), 20) is None
        assert started_as(slow) == [], "killed, and collected: nothing of it is left"
    finally:
        for left in started_as(slow):
            os.kill(left, signal.SIGKILL)


def started_as(program: Path) -> list[int]:
    """The processes of this machine that were started as ``program``."""
    said = subprocess.run(
        ["/bin/ps", "-ww", "-A", "-o", "pid=,args="], capture_output=True, text=True, check=False
    ).stdout
    return [int(line.split()[0]) for line in said.splitlines() if str(program) in line]


@pytest.mark.skipif(sys.platform == "win32", reason="a program that begins with #! is POSIX's")
async def test_a_process_that_is_not_there_is_an_answer_and_not_a_doubt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The system's program ends with 1 and prints nothing for a process that is gone: that is
    «nothing holds the folder», said — given here on every system."""
    gone = tmp_path / "gone"
    gone.write_text(f"#!{sys.executable}\nraise SystemExit(1)\n", encoding="utf-8")
    gone.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(gone))

    assert await command_line(os.getpid(), {}) == ""


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
    assert {
        "channel",
        "headless",
        "chromium_sandbox",
        "args",
        "env",
        "handle_sigint",
        "handle_sigterm",
        "handle_sighup",
        "accept_downloads",
        "service_workers",
    } == LAUNCH_OPTIONS, "the closed set, written here too: one more name is a decision"
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
    assert options["args"] == [*LAUNCH_ARGUMENTS, reports_in(tmp_path)]
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
        "--profile-directory=Default",
    )
    assert WINDOW_ARGUMENTS == (
        "--use-mock-keychain",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--allow-browser-signin=false",
        "--profile-directory=Default",
    )
    attached = ("--remote-debugging", "--headless", "--enable-automation", "--load-extension")
    disguised = ("--user-agent", "--disable-blink-features")
    for argument in (*LAUNCH_ARGUMENTS, *WINDOW_ARGUMENTS):
        assert not argument.startswith((*attached, *disguised, "--no-sandbox"))


def test_every_launch_names_the_one_profile_ela_prepares(tmp_path: Path) -> None:
    """Measured on 2026-10-11: with no name the browser opens the profile that was used last —
    a second one the user added from the window, whose preferences ELA does not rewrite and whose
    workers it does not take away. Named, it is ``Default`` in the window and under the driver
    (decision 79). The name is the folder :data:`~account.PREFERENCES_FILE` is written in."""
    named = f"--profile-directory={account.PREFERENCES_FILE[0]}"

    assert named in LAUNCH_ARGUMENTS and named in WINDOW_ARGUMENTS
    assert named in chrome(tmp_path)._launch()["args"]
    assert account.SERVICE_WORKERS[0] == account.LOGINS[0] == account.PREFERENCES_FILE[0]


def test_the_reports_of_a_crash_are_kept_inside_the_folder_of_the_profile(tmp_path: Path) -> None:
    """Measured on 2026-10-11: this version has no argument that switches its collector of
    crashes off — the one Playwright passes is not listened to on a Mac —, and a crash wrote a
    megabyte of the process's memory in a folder of the binary's own, outside the profile. With
    this argument the collector's folder is inside the folder of the profile, whose rules hold
    for it too (decision 74). Composed with the folder, like the one other argument that names
    it."""
    profile = tmp_path / "a profile"

    assert reports_in(profile) == f"--breakpad-dump-location={profile}/Crashpad"
    assert chrome(profile)._launch()["args"][-1] == reports_in(profile)
    assert not any(one.startswith("--disable-breakpad") for one in LAUNCH_ARGUMENTS), (
        "it switches nothing off here: it is not written as if it did"
    )


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


# ----------------------------------------------------------------------------------------
# A page with a window, whatever the switch says (decision 143 of the review of 2026-10-13)
# ----------------------------------------------------------------------------------------

AN_ADDRESS = "https://posta.example/login"


async def a_screen() -> bool:
    return True


async def no_screen() -> bool:
    return False


async def nobody_may_ask() -> bool:
    raise AssertionError("the system was asked whether there is a screen")


def with_a_screen(
    profile: Path,
    screen: Any,
    *,
    system: str = "Darwin",
    shown: bool = False,
    stopping: asyncio.Event | None = None,
) -> AccountChrome:
    """The adapter, told how the system answers «is this process inside a session of the
    screen» — and nothing started."""
    return AccountChrome(
        asyncio.Event() if stopping is None else stopping,
        environment={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"},
        kept=Kept(),
        system=system,
        profile=profile,
        shown=lambda: shown,
        on_a_screen=screen,
    )


@pytest.fixture
def launches(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Whether each launch the adapter came to was without a window — read where the launch
    reads it, at the moment the opening it inherits is reached; and nothing is launched."""
    seen: list[bool] = []

    async def opened(self: AccountChrome, address: str, allowed: Any, stop: Any) -> Opened:
        seen.append(self._launch()["headless"])
        return Opened(page="page-1", status=200, address=address, left=None)

    monkeypatch.setattr(PlaywrightBrowser, "open", opened)
    return seen


def everywhere(address: str) -> bool:
    return True


async def test_whether_a_window_can_be_had_is_asked_of_the_system_each_time(
    tmp_path: Path,
) -> None:
    """A look, like every other of the profile's: asked at every call and never remembered, and
    nothing is made or started."""
    answers = [True, False]

    async def answer() -> bool:
        return answers.pop(0)

    browser = with_a_screen(tmp_path / "profile", answer)

    assert await browser.can_show() is True
    assert await browser.can_show() is False
    assert answers == [], "asked both times"
    assert not (tmp_path / "profile").exists()


async def test_an_adapter_nobody_told_of_a_screen_has_none(tmp_path: Path) -> None:
    """Fail-safe: whoever builds the adapter without saying how the system answers gets «no»."""
    assert await chrome(tmp_path / "profile").can_show() is False


async def test_a_page_asked_with_a_window_is_launched_with_one_whatever_the_switch_says(
    tmp_path: Path, launches: list[bool]
) -> None:
    """Decision 143. The switch is off — what every start of ELA finds —, and the launch of this
    one opening has a window; the launch after it follows the switch again."""
    browser = with_a_screen(tmp_path / "profile", a_screen)

    opened = await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())
    between = browser._launch()["headless"]
    await browser.open(AN_ADDRESS, everywhere, FakeStop())

    assert opened.address == AN_ADDRESS
    assert launches == [False, True], "with a window for the one, and as the switch says after"
    assert between is True


async def test_with_the_switch_on_every_launch_has_a_window(
    tmp_path: Path, launches: list[bool]
) -> None:
    browser = with_a_screen(tmp_path / "profile", a_screen, shown=True)

    await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())
    await browser.open(AN_ADDRESS, everywhere, FakeStop())

    assert launches == [False, False]


async def test_a_launch_with_a_window_that_fails_leaves_the_next_one_to_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(self: AccountChrome, address: str, allowed: Any, stop: Any) -> Opened:
        raise BrowserFailed("the launch failed")

    monkeypatch.setattr(PlaywrightBrowser, "open", failing)
    browser = with_a_screen(tmp_path / "profile", a_screen)

    with pytest.raises(BrowserFailed):
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())

    assert browser._launch()["headless"] is True


async def test_with_no_screen_a_page_with_a_window_is_refused_and_nothing_is_launched(
    tmp_path: Path, launches: list[bool]
) -> None:
    """Decision 143: it is not launched without. Nothing is launched at all, and nothing is made
    — the folder is not even looked at. A page asked as the switch says is another matter."""
    profile = tmp_path / "profile"
    browser = with_a_screen(profile, no_screen)

    with pytest.raises(NoWindow):
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())

    assert launches == [] and not profile.exists()
    await browser.open(AN_ADDRESS, everywhere, FakeStop())
    assert launches == [True], "without a window, as the switch says: the screen is not asked"


async def test_a_held_folder_refuses_a_page_with_a_window_like_any_other(
    tmp_path: Path, launches: list[bool]
) -> None:
    browser = with_a_screen(tmp_path / "profile", a_screen)
    browser._windowing = True  # what the adapter itself has on the folder: its window

    with pytest.raises(ProfileBusy):
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())

    assert launches == []
    assert browser._launch()["headless"] is True, "and the next launch is the switch's"


async def test_a_page_with_a_window_asked_while_another_opening_is_under_way_gives_it_no_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The window is given to one launch, and no other may read it. An opening as the switch
    says is under way — counted, and about to read how it is launched — when a page with a
    window is asked for: **the one under way launches as the switch says**. What holds it is
    where the window is set: after the last wait of the look at the folder, with no wait before
    the opening is counted (the re-read of 2026-10-13 found no test on that order)."""
    launched: list[bool] = []
    let_go = asyncio.Event()

    async def opened(self: AccountChrome, address: str, allowed: Any, stop: Any) -> Opened:
        await let_go.wait()
        launched.append(self._launch()["headless"])
        return Opened(page="page-1", status=200, address=address, left=None)

    monkeypatch.setattr(PlaywrightBrowser, "_opened", opened)
    browser = with_a_screen(tmp_path / "profile", a_screen)
    under_way = asyncio.ensure_future(browser.open(AN_ADDRESS, everywhere, FakeStop()))
    try:
        while not browser._opening:
            await asyncio.sleep(0)
        # It reads how it is launched at its next turn: the first wait of the other, which is
        # its look at the folder.
        let_go.set()
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())
        await under_way
    finally:
        under_way.cancel()
        watching = browser._watching
        if watching is not None:
            watching.cancel()
        await asyncio.gather(
            under_way, *([] if watching is None else [watching]), return_exceptions=True
        )

    assert launched == [True, False], "as the switch says for the one, with a window for the other"


def test_what_a_field_holds_is_compared_whole_whatever_it_is() -> None:
    """Decisions 144 and 152, and the re-read of 2026-10-13. What a field holds is compared
    whole with what a secret holds, and the answer is one of three: it holds it; **it holds a
    beginning of it and nothing else** — a page that keeps less than it is given —; or it does
    not. A field that holds nothing holds no beginning. And there is an answer for anything a
    field can hold: half of a character, which no encoding takes, is a field that does not hold
    what was typed, and not an error with the field in it."""
    half = "mario" + chr(0xD800)

    assert account._held("mario", Secret("mario")) == HELD
    assert account._held("mari", Secret("mario")) == HELD_IN_PART
    assert account._held("m", Secret("mario")) == HELD_IN_PART
    assert account._held("", Secret("mario")) == NOT_HELD, "nothing is not a beginning"
    assert account._held("mario ", Secret("mario")) == NOT_HELD, "more is not what was typed"
    assert account._held("ario", Secret("mario")) == NOT_HELD, "an end is not a beginning"
    assert account._held("Mari", Secret("mario")) == NOT_HELD
    assert account._held(half, Secret("mario")) == NOT_HELD
    assert account._held(half, Secret(half)) == HELD
    assert account._held("", Secret("")) == HELD


# ----------------------------------------------------------------------------------------
# Which processes name the folder: one reading (decision 153 of the review of 2026-10-13)
# ----------------------------------------------------------------------------------------

CLOSED = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


@pytest.mark.skipif(sys.platform == "win32", reason="the system's own ps is POSIX's")
async def test_the_processes_of_this_user_are_asked_of_the_system_with_their_command_lines() -> (
    None
):
    """The second launch this module makes to look at processes, with the first one's rules:
    the system's own program, the closed environment, the processes **of this user** — a browser
    of ELA's and what it started are no other's. A process this test started is among them, as
    it was started; ended and collected, it is not."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "named so"])
    try:
        table = await process_table(CLOSED)

        assert table is not None
        group, command = table[child.pid]
        assert command.endswith("import time; time.sleep(60) named so")
        assert group == os.getpgid(child.pid), "and the group it is in"
        assert os.getpid() in table
    finally:
        child.kill()
        child.wait()
    after = await process_table(CLOSED)
    assert after is not None and child.pid not in after


PRINTS = """#!{python}
import sys
open({said!r}, 'w').write(repr(sys.argv[1:]))
print('  17    17 /a/program --flag')
print('4242    17 /another one')
print('  --user-data-dir=/the/folder')
print('')
print('   9     9 (ended)')
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a program that begins with #! is POSIX's")
async def test_the_table_is_asked_for_this_user_alone_and_read_line_by_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the program is started with, and how what it prints is read: a process is a line
    that begins with its number and its group's; a line that begins with neither belongs to the
    process above it — an argument may hold a new line —, so a folder named there is still named
    by that process."""
    said = tmp_path / "said"
    program = tmp_path / "ps"
    program.write_text(PRINTS.format(python=sys.executable, said=str(said)), encoding="utf-8")
    program.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(program))

    table = await process_table({})

    assert table == {
        17: (17, "/a/program --flag"),
        4242: (17, "/another one --user-data-dir=/the/folder"),
        9: (9, "(ended)"),
    }
    assert said.read_text(encoding="utf-8") == repr(
        ["-ww", "-U", str(os.getuid()), "-o", "pid=,pgid=,command="]
    )


@pytest.mark.skipif(sys.platform == "win32", reason="a program that begins with #! is POSIX's")
async def test_a_table_the_system_did_not_give_is_none_and_never_an_empty_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No program to ask with, one that fails, one that does not answer in its time: ``None`` —
    a doubt —, never «no process». And the program that did not answer is not left running."""
    monkeypatch.setattr(account, "PS", str(tmp_path / "no-such-program"))
    assert await process_table({}) is None

    failing = tmp_path / "failing"
    failing.write_text(
        f"#!{sys.executable}\nprint('1 1 /sbin/launchd')\nraise SystemExit(2)\n", encoding="utf-8"
    )
    failing.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(failing))
    assert await process_table({}) is None, "it ended badly: what it printed is not a table"

    slow = tmp_path / "slow"
    slow.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(120)\n", encoding="utf-8")
    slow.chmod(0o700)
    monkeypatch.setattr(account, "PS", str(slow))
    monkeypatch.setattr(account, "PS_SECONDS", 0.2)
    try:
        assert await asyncio.wait_for(process_table({}), 20) is None
        assert started_as(slow) == [], "killed, and collected: nothing of it is left"
    finally:
        for left in started_as(slow):
            os.kill(left, signal.SIGKILL)


async def test_what_names_the_folder_is_said_by_the_one_reading_of_a_command_line(
    tmp_path: Path, installed: Path
) -> None:
    """One predicate (decision 153): a process of that browser names the folder when the
    function that says whether the folder is held, and by what, does not answer «nothing» of
    its command line — the browser itself, what it started for itself. Not the collector of
    crashes, which names a folder inside it; not a browser on another folder. **And of that
    browser's group alone.**"""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)
    binary = made._executable()

    async def table() -> dict[int, tuple[int, str]]:
        return {
            11: (11, f"{binary} --user-data-dir={profile} --use-mock-keychain"),
            12: (11, f"/a/helper --type=renderer --user-data-dir={profile} --lang=it"),
            13: (11, f"/a/collector --database={profile}/Crashpad"),
            14: (11, f"{binary} --user-data-dir={profile}-of-another"),
            15: (11, "/sbin/launchd"),
            21: (21, f"/another/browser --user-data-dir={profile}"),
        }

    made._tabled = table
    assert await made._naming(profile, 11) == [11, 12]
    assert await made._naming(profile, 21) == [21]
    assert await made._naming(profile, 99) == [], "a group nothing is in names nothing"
    assert await made._group_of(12) == 11 and await made._group_of(404) is None


async def test_a_doubt_about_the_table_or_about_the_group_is_never_an_empty_folder(
    tmp_path: Path, installed: Path
) -> None:
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)

    async def somebody() -> dict[int, tuple[int, str]]:
        return {11: (11, "/sbin/launchd")}

    made._tabled = somebody
    assert await made._naming(profile, None) is None, "a group nobody could say is a doubt"

    async def nobody_says() -> None:
        return None

    made._tabled = nobody_says
    assert await made._naming(profile, 11) is None, "a table that was not given is a doubt"
    assert await made._group_of(11) is None


async def test_a_process_of_no_browser_whose_line_holds_the_words_of_a_folder_delays_no_close(
    tmp_path: Path, installed: Path
) -> None:
    """Why the group (measured on 2026-10-13, writing decision 153): the one reading counts a
    doubt — a command line that names a folder from where its process stands — as a process
    that names the folder. That is right of the one process a lock names. Read of every process
    of the user, it made **a shell whose own command line held the text of such an argument**
    hold every close of the machine until its grace. A process outside the browser's group is
    not read at all."""
    profile = tmp_path / "profile"
    profile.mkdir(mode=0o700)
    made = chrome(profile)
    a_doubt = "/bin/zsh -c grep -- --user-data-dir={profile} notes.txt"
    assert on_the_folder(a_doubt, profile, None) is not None, "the control: a doubt of the reading"

    async def table() -> dict[int, tuple[int, str]]:
        return {700: (700, a_doubt)}

    made._tabled = table
    assert await made._naming(profile, 11) == []


async def test_on_another_system_no_screen_is_asked_about(tmp_path: Path) -> None:
    browser = with_a_screen(tmp_path / "profile", nobody_may_ask, system="Linux")

    with pytest.raises(BrowserUnsupported):
        await browser.can_show()
    with pytest.raises(BrowserUnsupported):
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())
    assert not (tmp_path / "profile").exists()


async def test_a_stopping_ela_is_asked_nothing_about_a_window(tmp_path: Path) -> None:
    stopping = asyncio.Event()
    stopping.set()
    browser = with_a_screen(tmp_path / "profile", nobody_may_ask, stopping=stopping)

    with pytest.raises(BrowserStopped):
        await browser.can_show()
    with pytest.raises(BrowserStopped):
        await browser.open_shown(AN_ADDRESS, everywhere, FakeStop())
