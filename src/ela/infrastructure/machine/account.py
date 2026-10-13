"""ELA's own browser **with the profile that lasts**: Chrome for Testing of the lock's version, on
the folder the user declared (§19, §57; M13.9, ADR 0063).

Implements :class:`~ela.ports.AccountBrowser`. Everything the adapter of the empty browser does —
a driver and a browser per page, the gate that stops a navigation before it is sent, the stop of
ELA, the closing that runs to its end, the kill past the grace — is **inherited**, on this binary:
what changes is *which* browser a page gets, and what is done to the folder before it starts.

**The folder is read by this module and by nothing else in ELA.** It arrives from the composition;
no error raised here carries its path — **what the system says of it does not leave either**: an
``OSError`` names the path in its text, so it becomes an error of the browser that names its
type —, and no other module receives it.

What a page gets here that an empty one does not:

* **Chrome for Testing**, not the shell: the full browser of the lock's version — never the Chrome
  installed on the machine, whose profile ELA does not open, read, copy or list;
* **the sandbox on**, which Playwright turns off by default: a browser that opens pages of the web
  with the user's sessions in it does not run without;
* **the same folder every time**, checked before every launch — the user's own, open to nobody
  else, made by ELA ``0700`` if it is not there, never narrowed by ELA if it is found wider; and
  **below its top too**: ``Default``, where the browser keeps what ELA reads and rewrites, is a
  folder of its own and never a link to another;
* **one process at a time on it**: a launch on a folder found held is not attempted — it is the
  launch that can kill the first. Held by what this adapter has in flight, or by a process the
  folder's lock names **whose command line names the folder** (:func:`on_the_folder`): a lock
  whose pid went to another process holds nothing;
* **one profile of the browser's, by name**: every launch names ``Default``, the one ELA
  prepares — with no name the browser opens whichever was used last (measured);
* **the reports of a crash inside the folder, and gone before every launch**: this version has
  no argument that switches its collector off, and one that says where it writes (measured) —
  the folder's rules hold for what it writes, and what a crash left does not pass to the launch
  after;
* **the preferences rewritten before every launch**, over whatever the file says
  (:data:`PREFERENCES`): they — with the flags of :data:`LAUNCH_ARGUMENTS` —, and not the binary,
  are what keeps the browser away from a Google account and from saving passwords (measured);
* **no service worker left from before**: of a navigation a worker answers the gate is not told
  — the browser sends the request to the site all the same, beside its worker (measured with the
  gate of M13.4, and again with the one of M13.4f: ADR 0064 §6). The folder of the workers is
  removed before every launch ELA drives, and new ones are blocked;
* **no HAR, no tracing, no video**: the options of the launch are a closed set
  (:data:`LAUNCH_OPTIONS`).

**With a window or without** is the user's switch, read at each launch — **but for a page asked
with a window** (:meth:`AccountChrome.open_shown`, decision 143 of the review of 2026-10-13): the
one capability that signs in asks for it, because a site may refuse a browser that says it has no
window (measured on one site). That launch has a window whatever the switch says, and is not
made at all where the system did not say that this process is inside a session of the screen.

**The window** (:meth:`AccountChrome.window`) is the same binary on the same folder **with nothing
attached**: no driver, no pipe, no debugging port; its output goes nowhere; ELA keeps one thing of
it, the wait for its end. At ELA's stop it is told — ``SIGTERM``, to which it exits by itself,
writing its cookies —, waited for within the grace of the close, and then killed with its group.
**The user's command does the same to it, and nothing does it by itself**
(:meth:`AccountChrome.shut`): the red button of a window closes the window and leaves the browser
running.
**It is never left behind**: the launch is a task of the adapter's own, which runs to its end
whoever asked for it and went away, and which the close waits for before it calls the folder free.

**ELA does not disguise itself**: no user agent, no script injected in a page, nothing that touches
``navigator.webdriver``. A site that refuses a driven browser is told so by the outcome.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import shutil
import signal
import sqlite3
import stat
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

from playwright.async_api import Browser as Chromium
from playwright.async_api import BrowserContext, Page, Playwright
from playwright.async_api import Error as PlaywrightError

from ela.infrastructure.machine.browser import (
    TEMPORARY_PROFILE,
    PlaywrightBrowser,
    _Open,
    registry_folder,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    SHUT_KILLED,
    SHUT_QUIT,
    SHUT_TOLD,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserUnsupported,
    Field,
    Glanced,
    Landed,
    NoWindow,
    Opened,
    PageGone,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Secret,
    TaskStop,
)

__all__ = [
    "ANOTHER_PROGRAM",
    "ELA_S_BROWSER",
    "LAUNCH_ARGUMENTS",
    "LAUNCH_OPTIONS",
    "NAMED_PROFILE",
    "PREFERENCES",
    "PROFILE_MODE",
    "WINDOW_ARGUMENTS",
    "AccountChrome",
    "command_line",
    "linked_in",
    "lock_holder",
    "on_the_folder",
    "profiles_in",
    "reports_in",
    "saved_in",
    "with_preferences",
]

_LOG = logging.getLogger(__name__)

CHROME: Final = "chromium"
"""The name Playwright's registry and its channels give Chrome for Testing."""
EXECUTABLE: Final = (
    "chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)
SUPPORTED: Final = "Darwin"
"""The one system the browser with the profile runs on today (M13.9, «Out of scope»)."""
WINDOW_NAME: Final = "Google Chrome for Testing"
"""What the window is called when ELA says it killed it."""

PROFILE_MODE: Final = 0o700
PREFERENCES_MODE: Final = 0o600
PROFILE_VARIABLE: Final = "ELA_BROWSER_PROFILE_DIR"

PROFILE: Final = "Default"
"""The one profile of the browser's, among those its folder may come to hold, that ELA prepares
and uses: where the preferences are rewritten, the workers taken away, and every launch starts."""
MOCK_KEYCHAIN: Final = "--use-mock-keychain"
NO_SYNC: Final = "--disable-sync"
NO_SIGNIN: Final = "--allow-browser-signin=false"
NAMED_PROFILE: Final = f"--profile-directory={PROFILE}"
"""With no name the browser opens the profile that was used last (measured on 2026-10-11): a
second one the user added from the window, which nothing here prepared. Named, it is this one —
in the window and under the driver (decision 79)."""
LAUNCH_ARGUMENTS: Final = (MOCK_KEYCHAIN, NO_SYNC, NO_SIGNIN, NAMED_PROFILE)
"""What ELA adds to the arguments Playwright passes by itself, beside where the reports of a crash
go (:func:`reports_in`). The first two Playwright passes too, on this system and in this version
— written here so that they are ELA's own and not a default of somebody else's: **no launch
touches the keychain**, and none starts the browser's sync. The third switches the browser's own
sign-in off (measured: without it and the preferences the same binary registers a Google
account). The fourth names the profile."""
WINDOW_ARGUMENTS: Final = (
    MOCK_KEYCHAIN,
    "--no-first-run",
    "--no-default-browser-check",
    NO_SYNC,
    NO_SIGNIN,
    NAMED_PROFILE,
)
"""What the window receives, beside its folder, where the reports of a crash go and — if there is
one — an address: a closed list. Nothing in it attaches anything to the browser."""
REPORTS: Final = "Crashpad"
"""The folder of the browser's own collector of crashes, inside the folder of the profile."""
REPORTS_AT: Final = "--breakpad-dump-location"
"""The argument this version of the browser reads for where its collector writes (measured on
2026-10-11, decision 74). **None switches the collector off**: ``--disable-breakpad``, which
Playwright passes by itself, is not listened to on a Mac — the collector ran beside the browser
all the same, and a crash wrote a megabyte of the process's memory in a folder of the binary's
own, outside the profile. With this one the collector's folder is inside the folder of the
profile, and the folder's rules hold for what a crash leaves — **until the next launch, which
takes it away** (:func:`_prepared`, decision 90). **What the system itself writes of a crash is
not the browser's to move**: a report of its own, with no memory of the process in it (ADR 0063
§4)."""


def reports_in(profile: Path) -> str:
    """The argument that keeps the reports of a crash inside ``profile``: composed with the
    folder, like the one other argument of a launch that names it."""
    return f"{REPORTS_AT}={profile / REPORTS}"


LAUNCH_OPTIONS: Final = frozenset(
    {
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
    }
)
"""Every option of a launch, by name: a closed set. No ``record_har_path``, no
``record_video_dir``, no tracing, no ``user_agent``, no ``extra_http_headers``."""

PREFERENCES: Final[Mapping[str, Any]] = {
    "credentials_enable_service": False,
    "credentials_enable_autosignin": False,
    "profile": {"password_manager_leak_detection": False},
    "autofill": {"profile_enabled": False, "credit_card_enabled": False},
    "signin": {"allowed": False, "allowed_on_next_startup": False},
}
"""What the profile does not keep, written before **every** launch over what the file says: the
offer to save a password and the automatic sign-in; the comparison of passwords with a service of
Google's; the automatic filling and the remembered values of forms; the browser's own sign-in to a
Google account."""
PREFERENCES_FILE: Final = (PROFILE, "Preferences")
SERVICE_WORKERS: Final = (PROFILE, "Service Worker")
LOGINS: Final = (PROFILE, "Login Data")
LOCK: Final = "SingletonLock"
"""The link the browser leaves in its folder while it runs: ``<host>-<pid>``."""
FIRST_PID: Final = 1
"""The system's own first process: it answers for ever, and is nobody's browser. Nor is zero,
which asked of the kernel is «every process of my group»."""
LAST_PID: Final = 2**31 - 1
"""The largest number a process can have on any system ELA runs on: a larger one, asked of the
kernel, is an error of the question."""
PS: Final = "/bin/ps"
"""The system's own program that says what a process was started with."""
PS_SECONDS: Final = 5.0
"""How long that program may take: past it, what a process is has not been said."""
ELA_S_BROWSER: Final = "browser"
"""A process on the folder that is ELA's own binary: the one ``ela browser close`` may tell."""
ANOTHER_PROGRAM: Final = "another"
"""A process on the folder that is not ELA's binary, or that could not be read: it holds the
folder, and ELA signals nothing it cannot name."""
GONE_EVERY = 0.05
"""How often a browser ELA did not start, once told to quit, is asked of the kernel: it is no
child of ELA's, and nothing tells ELA when it ends. Counted inside the grace, never beyond it."""
GONE_TURNS: Final = 40
"""How many times a browser ELA did not start is looked for once it was killed, before ELA says
so: the kernel takes a killed process away at once, and its parent collects it when it will."""
DATA_DIR: Final = " --user-data-dir="
DRIVEN: Final = " --remote-debugging"
"""How a command line says something is attached to the browser — a driver's pipe, a port: a
browser somebody drives is a step of somebody's, not the browser a hand may be on."""
LOCAL_STATE: Final = "Local State"
LISTED: Final = ("profile", "info_cache")
"""Where the browser keeps its own list of the profiles of its folder: read as presence — how
many names —, never as what a profile is called or whose account it is."""
LINKED: Final = (
    ("account_info",),
    ("google", "services", "account_id"),
    ("google", "services", "consented_to_sync"),
)
"""Where the browser says it knows an account (measured, G4): one registered, a primary account,
a consent to sync. Read as presence, never as values — an account's id is the user's."""
ONE_TIME_CODE: Final = 'input[autocomplete~="one-time-code" i]:visible'
METHOD_OF: Final = """element => {
  const attribute = (node, name) => Element.prototype.getAttribute.call(node, name);
  const form = element.form;
  if (!form) return "";
  const submits = Element.prototype.matches.call(
    element, "button, input[type=submit i], input[type=image i]");
  const own = submits ? attribute(element, "formmethod") : null;
  const said = ((own !== null ? own : attribute(form, "method")) || "").toLowerCase();
  return said === "post" || said === "dialog" ? said : "get";
}"""
"""How the form of an element sends, read **from the attributes, through the prototype**: a form
answers ``form.method`` with a field of its own named ``method`` if it has one — and a form that
posts and has such a field would not be seen to post. A button that sends carries its own
``formmethod`` over the form's; anything that is not ``post`` or ``dialog`` is ``get``, which is
what a browser does with it."""


def with_preferences(found: object) -> dict[str, Any]:
    """:data:`PREFERENCES` written over what a profile already says: every other key stays as it
    was, and a file that did not hold an object is replaced."""
    merged: dict[str, Any] = dict(found) if isinstance(found, dict) else {}
    _over(merged, PREFERENCES)
    return merged


def _over(into: dict[str, Any], wanted: Mapping[str, Any]) -> None:
    for key, value in wanted.items():
        if isinstance(value, Mapping):
            inner = into.get(key)
            into[key] = dict(inner) if isinstance(inner, dict) else {}
            _over(into[key], value)
        else:
            into[key] = value


def _read(file: Path) -> object:
    """What a file of the profile holds as JSON, or ``None``: not there, or not JSON."""
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def linked_in(preferences: object) -> bool:
    """Whether what a profile's preferences say names a Google account (:data:`LINKED`)."""
    for path in LINKED:
        found: object = preferences
        for part in path:
            found = found.get(part) if isinstance(found, dict) else None
        if found:
            return True
    return False


def _own_folders(folder: Path) -> list[Path]:
    """The folders ``folder`` holds of its own. None, for a folder that is not there yet.

    :raises BrowserFailed: a folder that is there and cannot be listed — by the system's type,
        never its text, which names the path —, **or one that holds a link to a folder**: the
        browser would follow it, ELA reads nothing a link leads to, and what is there is then
        something ELA did not count — never «none»."""
    refused: str | None = None
    found: list[Path] = []
    linked = False
    try:
        with os.scandir(folder) as listed:
            for one in listed:
                if one.is_dir(follow_symlinks=False):
                    found.append(Path(one.path))
                elif one.is_symlink() and one.is_dir():
                    linked = True
    except FileNotFoundError:
        pass
    except OSError as error:
        refused = type(error).__name__
    if refused is not None:
        raise BrowserFailed(f"the profiles of ELA's browser cannot be listed ({refused})")
    if linked:
        raise BrowserFailed(
            "the passwords the browser saved cannot be counted: a profile of its folder is a "
            "link, and ELA reads nothing a link leads to"
        )
    return sorted(found)


def profiles_in(folder: Path) -> int:
    """How many profiles **the browser itself lists** in ``folder`` (:data:`LISTED`): not every
    folder that holds a ``Preferences`` — the browser keeps folders beside its profiles that are
    none, the one of its profile picker among them. ELA prepares and uses one, :data:`PROFILE`;
    a second is one the user added from inside the window (decision 79). No list yet — a folder
    never launched — is none.

    :raises BrowserFailed: a list that is there and cannot be read, or is a link. Never a
        number."""
    file = folder / LOCAL_STATE
    try:
        mode: int | None = file.lstat().st_mode
    except FileNotFoundError:
        return 0
    except OSError:
        mode = None
    listed: object = None
    if mode is not None and stat.S_ISREG(mode):
        listed = _read(file)
        for part in LISTED:
            listed = listed.get(part) if isinstance(listed, dict) else None
    if not isinstance(listed, dict):
        raise BrowserFailed("the profiles of ELA's browser cannot be listed")
    return len(listed)


def saved_in(folder: Path) -> int:
    """How many rows the browser's own password manager holds, **in every folder of its own the
    profile's folder holds**: counted, and nothing of a row is read. No file yet — a profile
    never launched — is none. Opened read-only and as it is on the disk, so a browser that is
    running is neither waited for nor disturbed.

    :raises BrowserFailed: a file that is there and cannot be counted — a link included, which
        is not read through. Never «none»."""
    name = LOGINS[1]
    total = 0
    uncounted = False
    for one in _own_folders(folder):
        file = one / name
        try:
            mode: int | None = file.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError:
            mode = None
        if mode is None or not stat.S_ISREG(mode):
            uncounted = True
            break
        total += _counted(file)
    if uncounted:
        raise BrowserFailed("the passwords the browser saved cannot be counted")
    return total


def _counted(file: Path) -> int:
    try:
        with contextlib.closing(
            sqlite3.connect(f"{file.as_uri()}?mode=ro&immutable=1", uri=True)
        ) as database:
            cursor = database.cursor()
            (count,) = cursor.execute("select count(*) from logins").fetchone()
    except sqlite3.Error:
        count = None
    if count is None:
        raise BrowserFailed("the passwords the browser saved cannot be counted")
    return int(count)


def lock_holder(profile: Path, alive: Callable[[int], bool]) -> int | None:
    """The process the folder's lock names, if ``alive`` knows it. A lock left by a process that
    is gone holds nothing (measured: the next launch starts).

    **Read by the pid, and not by the host** the lock names before it: a machine's own name
    changes with the network it is on — measured, a Mac that called itself by an address —, and a
    browser that is running under yesterday's name is running all the same. A lock that names a
    pid the kernel knows is held, whatever it calls the machine.

    **Only what can be the pid of a browser is asked of the kernel**: digits of ASCII, above
    :data:`FIRST_PID` and no larger than :data:`LAST_PID`. Anything else was not left by a browser
    that runs, and holds nothing."""
    try:
        named = os.readlink(profile / LOCK).rpartition("-")[2]
    except OSError:
        return None
    if not (named.isascii() and named.isdigit()):
        return None
    pid = int(named)
    if not FIRST_PID < pid <= LAST_PID:
        return None
    return pid if alive(pid) else None


def _same_place(value: str, profile: Path) -> bool:
    """Whether ``value`` — a path that begins at the root, as a process was given it — is the
    folder ``profile``, **however it is written**: with the slash a shell leaves at its end,
    through a link above it, in other capitals on a volume that ignores them. Asked of the
    system when both are there; compared as paths made plain when they are not."""
    if os.path.normpath(value) == os.path.normpath(profile):
        return True
    try:
        return os.path.samefile(value, profile)
    except OSError:
        return False


def on_the_folder(command: str | None, profile: Path, executable: Path | None) -> str | None:
    """What a process the folder's lock names is, read from its command line — **one function for
    the two that ask** (decisions 80 and 82): whether the folder is held, and whether ELA may
    tell that process to quit.

    ``None``: it does not name the folder — the lock is what a browser that was killed left, and
    its pid went to another process: nothing holds the folder. :data:`ELA_S_BROWSER`: ELA's own
    binary on this folder, the browser itself rather than one of its helpers, **with nothing
    attached to it** and the folder's name ending plainly. :data:`ANOTHER_PROGRAM`: anything
    else that names the folder, **and every doubt** — a command line that could not be read
    (``command`` is ``None``), a folder named from where that process stands, which ELA does not
    know. **A doubt holds the folder, and is told nothing.**

    The command line is the system's, its arguments joined by spaces: where the folder's name
    ends is tried at every space, and each try is compared with the folder as a place
    (:func:`_same_place`). It ends *plainly* when a switch follows it, or nothing: only then is
    the process told."""
    if command is None:
        return ANOTHER_PROGRAM
    padded = f"{command} "
    _, found, after = padded.partition(DATA_DIR)
    if not found:
        return None
    words = after.split(" ")[:-1]
    if not words or not words[0].startswith(os.sep):
        return ANOTHER_PROGRAM
    plainly: bool | None = None
    for end in range(1, len(words) + 1):
        if _same_place(" ".join(words[:end]), profile):
            plainly = end == len(words) or words[end].startswith("--")
            break
    if plainly is None:
        return None
    ours = executable is not None and command.startswith(f"{executable} --")
    if not (ours and plainly) or " --type=" in padded or DRIVEN in padded:
        return ANOTHER_PROGRAM
    return ELA_S_BROWSER


async def command_line(pid: int, environment: Mapping[str, str]) -> str | None:
    """What the system says process ``pid`` was started with: its arguments, joined by spaces.
    Empty for a process that is not there any more; ``None`` when the system could not be asked,
    or did not answer within :data:`PS_SECONDS` — never a guess.

    **The one launch this module makes to look at a process, and made only when a lock names
    one** (decision 82): the system's own program, at its absolute path, with the closed
    environment of the browser, its input the end of a file and its errors nowhere."""
    try:
        process = await asyncio.create_subprocess_exec(
            PS,
            "-ww",
            "-o",
            "command=",
            "-p",
            str(pid),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=dict(environment),
            start_new_session=True,
        )
    except OSError:
        return None
    printed: bytes | None = None
    try:
        printed, _ = await asyncio.wait_for(process.communicate(), PS_SECONDS)
    except TimeoutError:
        pass
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
    if printed is None:
        return None
    said = printed.decode("utf-8", "replace").strip()
    # The program ends with 1 and prints nothing for a process that is not there: that is an
    # answer. Anything else it could not say is not.
    return said if said or process.returncode == 1 else None


def _taken_away(place: Path) -> None:
    """What is at ``place`` is gone: a folder with what it holds, a file — and of a link the
    link, **never what it points at**: nothing is reached through it."""
    if place.is_symlink() or place.is_file():
        place.unlink(missing_ok=True)
    else:
        shutil.rmtree(place, ignore_errors=True)


def _prepared(profile: Path, *, driven: bool) -> None:
    """What is done to the folder before a launch: the preferences, always; **what a crash left,
    always** (decision 90) — a report is memory of the process that held the sessions, it serves
    nobody, and it does not pass to the launch after: the browser makes the folder of its
    collector again —; and before a launch Playwright drives, the service workers gone."""
    default = profile / PREFERENCES_FILE[0]
    default.mkdir(mode=PROFILE_MODE, exist_ok=True)
    file = profile.joinpath(*PREFERENCES_FILE)
    written = json.dumps(with_preferences(_read(file)))
    fresh = file.with_name(f"{file.name}.ela")
    # Whatever bears the name goes first — what a launch that was interrupted left, or a link —,
    # and the file is then made new, by this call and through no link: nothing a link leads to
    # is ever written.
    fresh.unlink(missing_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(fresh, flags, PREFERENCES_MODE)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(written)
    fresh.replace(file)
    _taken_away(profile / REPORTS)
    if driven:
        _taken_away(profile.joinpath(*SERVICE_WORKERS))


WEB: Final = frozenset({"https", "http"})
"""The schemes of an address of the web. *Which* address — ``https``, of a declared site — is
the caller's to say, as it is for a page: here it is that the window is started on an address,
and on nothing else."""


def _of_a_site(address: str) -> bool:
    """Whether ``address`` is the address of a site, and nothing beside it. What the window is
    started with is an argument of the binary: anything that is not an address of the web would
    be read as one of the browser's own — a debugging port, another folder — or would open what
    is not a site: a file, a page of the browser's settings."""
    if any(character.isspace() for character in address):
        return False
    try:
        parts = urlsplit(address)
        named = parts.username is not None or parts.password is not None
    except ValueError:
        return False
    return parts.scheme in WEB and bool(parts.hostname) and not named


def _seen(launching: asyncio.Future[None]) -> None:
    """A launch whose caller went away has nobody to raise its failure to: looked at here, so
    that it is not a warning of the loop's when the task is collected."""
    if not launching.cancelled():
        launching.exception()


async def _nobody_is_told(address: str | None, seconds: float) -> None:
    """Whoever builds this adapter without saying who is told that a window ended."""


async def _no_screen_was_said() -> bool:
    """Whoever builds this adapter without saying how the system answers «is this process inside
    a session of the screen»: it is not (fail-safe) — a page asked with a window is refused."""
    return False


class AccountChrome(PlaywrightBrowser):
    """The port :class:`~ela.ports.AccountBrowser`, with Playwright and Chrome for Testing.

    ``profile`` is the folder the user declared, ``None`` when nobody did. ``shown`` says, at
    each launch, whether the browser has a window — the user's switch, never a tool's. ``ended``
    is told when a window opened by :meth:`window` has ended: on which address it was opened, and
    how long it lasted. ``on_a_screen`` answers, each time it is asked, whether this process is
    inside a session of the screen: where it is not, no window can be had (decision 143).
    """

    def __init__(
        self,
        stopping: asyncio.Event,
        *,
        environment: Mapping[str, str],
        kept: Callable[[], Awaitable[None]],
        system: str,
        profile: Path | None,
        shown: Callable[[], bool],
        ended: Callable[[str | None, float], Awaitable[None]] = _nobody_is_told,
        on_a_screen: Callable[[], Awaitable[bool]] = _no_screen_was_said,
    ) -> None:
        super().__init__(stopping, environment=environment, kept=kept, system=system)
        self._profile = profile
        self._shown = shown
        self._ended = ended
        self._on_a_screen = on_a_screen
        self._with_a_window = False
        self._said_of: Callable[[int], Awaitable[str | None]] = self._asked
        self._was_told: set[int] = set()
        self._window: asyncio.subprocess.Process | None = None
        self._windowing = False
        self._launching: asyncio.Future[None] | None = None
        self._watched: asyncio.Task[None] | None = None

    # The binary -----------------------------------------------------------------------------

    def _executable(self) -> Path | None:
        """Chrome for Testing, where Playwright would launch it from: a look at a file."""
        if self._system != SUPPORTED:
            raise BrowserUnsupported(self._system)
        folder = registry_folder(CHROME, os.environ, self._system)
        assert folder is not None  # noqa: S101 — the registry knows the supported system
        return next((found for found in sorted(folder.glob(EXECUTABLE)) if found.is_file()), None)

    async def installed(self) -> bool:
        self._refuse_if_stopping()
        return self._executable() is not None

    def _launch(self) -> dict[str, Any]:
        profile = self._profile
        assert profile is not None  # noqa: S101 — a launch is on a folder found usable
        return {
            "channel": CHROME,
            "headless": not (self._with_a_window or self._shown()),
            "chromium_sandbox": True,
            "args": [*LAUNCH_ARGUMENTS, reports_in(profile)],
            "env": self._environment,
            "handle_sigint": False,
            "handle_sigterm": False,
            "handle_sighup": False,
            "accept_downloads": False,
            "service_workers": "block",
        }

    # The folder -----------------------------------------------------------------------------

    def _usable(self) -> Path:
        """The folder, fit to hold the user's sessions: made ``0700`` if it is not there, refused
        if it is found any other way. **ELA does not narrow it by itself**: a folder somebody
        widened was widened by somebody.

        **What the system says of it is a refusal of this adapter's**: a part of its path that is
        a file, a folder above it that cannot be written. An ``OSError`` names the path in its
        text — so what leaves names its type, and is raised once the handler of the system's is
        over, chained to nothing."""
        profile = self._profile
        if profile is None:
            raise ProfileUndeclared(
                f"{PROFILE_VARIABLE} is not set: write in the .env the absolute path of a folder "
                "for ELA's browser to keep your sessions in, and restart ELA"
            )
        refused: str | None = None
        try:
            self._checked(profile)
        except OSError as error:
            refused = type(error).__name__
        if refused is not None:
            raise ProfileUnsafe(
                f"the folder of {PROFILE_VARIABLE} cannot be looked at, or made ({refused})"
            )
        return profile

    def _checked(self, profile: Path) -> None:
        if profile.name.startswith(TEMPORARY_PROFILE):
            raise ProfileUnsafe(
                f"the folder of {PROFILE_VARIABLE} is named as the temporary profiles ELA takes "
                "away after it kills a browser: give it another name"
            )
        try:
            found = profile.lstat()
        except FileNotFoundError:
            with contextlib.suppress(FileExistsError):
                profile.mkdir(mode=PROFILE_MODE, parents=True)
                profile.chmod(PROFILE_MODE)
                return
            # Made between the look and the making — by a second opening that came at the same
            # time, or by anybody: looked at again like any folder found, and trusted for nothing.
            found = profile.lstat()
        if stat.S_ISLNK(found.st_mode) or not stat.S_ISDIR(found.st_mode):
            raise ProfileUnsafe(f"the folder of {PROFILE_VARIABLE} is a link, or is not a folder")
        if found.st_uid != os.getuid():
            raise ProfileUnsafe(f"the folder of {PROFILE_VARIABLE} belongs to another user")
        if stat.S_IMODE(found.st_mode) & ~PROFILE_MODE:
            raise ProfileUnsafe(
                f"the folder of {PROFILE_VARIABLE} is open to others than you (mode "
                f"{stat.S_IMODE(found.st_mode):04o}): ELA wants 0700 and does not narrow it by "
                "itself — chmod 700 it"
            )
        # Below the top: where the browser keeps what ELA counts, rewrites and takes away. A link
        # there would have ELA do all three to the folder it leads to.
        try:
            below = (profile / PREFERENCES_FILE[0]).lstat()
        except FileNotFoundError:
            return
        if stat.S_ISLNK(below.st_mode) or not stat.S_ISDIR(below.st_mode):
            raise ProfileUnsafe(
                f"`{PREFERENCES_FILE[0]}`, inside the folder of {PROFILE_VARIABLE}, is a link, or "
                "is not a folder: ELA reads and writes the profile of its own browser, and "
                "nothing a link leads to"
            )

    def _mine(self) -> str | None:
        """What this adapter itself has on the folder: a step of ELA's, or its window."""
        if self._pages or self._opening or self._closing:
            return PROFILE_STEP
        if self._windowing or self._window is not None:
            return PROFILE_WINDOW
        return None

    async def _asked(self, pid: int) -> str | None:
        closed = {name: str(value) for name, value in self._environment.items()}
        return await command_line(pid, closed)

    async def _named(self, profile: Path) -> tuple[int, str] | None:
        """The process the folder's lock names, and what it is (:func:`on_the_folder`) — or
        ``None``: no lock, one left by a process that is gone, or one whose pid went to a process
        that has nothing to do with the folder. **The system is asked what a process is only
        when a lock names one the kernel knows.**"""
        pid = lock_holder(profile, self._known)
        if pid is None:
            return None
        what = await self._what(pid, profile)
        return None if what is None else (pid, what)

    async def _what(self, pid: int, profile: Path) -> str | None:
        """What process ``pid`` is, on ``profile`` (:func:`on_the_folder`). **The system saying
        nothing is believed only of a process the kernel does not know any more**: its program
        ends the same way for a process that is gone and for every error of its own (measured),
        so «nothing» of a process that is still there is a doubt."""
        said = await self._said_of(pid)
        if said == "" and self._known(pid):
            said = None
        return on_the_folder(said, profile, self._executable())

    def _tell(self, pid: int) -> bool:
        """Whether ``pid`` is to be told now: **once, however many ask**. A browser has one
        chance to end by itself — measured on 2026-10-11: a second ``SIGTERM`` twenty
        milliseconds after the first killed it, where one alone let it end and write its
        cookies."""
        if pid in self._was_told:
            return False
        self._was_told.add(pid)
        return True

    async def _holder(self, profile: Path) -> str | None:
        """Who holds the folder now: derived, in this order — what this adapter has in flight,
        its window, and then the folder's own lock. Asking the system about the lock's process
        takes its time, so what this adapter has in flight is **looked at again after it**: no
        wait stands between the answer and whoever acts on it."""
        if self._mine() is None and await self._named(profile) is not None:
            return self._mine() or PROFILE_PROCESS
        return self._mine()

    async def _folder(self) -> Path:
        """The folder, fit to be used: asked of the disk at every call, and **only on the system
        this browser runs on** — anywhere else no use of it looks at a folder, or makes one."""
        if self._system != SUPPORTED:
            raise BrowserUnsupported(self._system)
        return await asyncio.to_thread(self._usable)

    async def _free(self) -> Path:
        """The folder, usable and held by nobody — or the error that says which it is not. No
        wait stands between the look this ends with and what the caller does next."""
        profile = await self._folder()
        holder = await self._holder(profile)
        if holder is not None:
            raise ProfileBusy(holder)
        return profile

    async def _prepare(self, profile: Path, *, driven: bool) -> None:
        """:func:`_prepared`, in a thread — and what the system says of a folder that cannot be
        written does not leave: its type, never its text, which names the path."""
        refused: str | None = None
        try:
            await asyncio.to_thread(_prepared, profile, driven=driven)
        except OSError as error:
            refused = type(error).__name__
        if refused is not None:
            raise BrowserFailed(
                f"the folder of {PROFILE_VARIABLE} could not be prepared for a launch ({refused})"
            )

    async def occupied(self) -> str | None:
        return await self._holder(await self._folder())

    async def linked(self) -> bool:
        profile = await self._folder()
        return linked_in(await asyncio.to_thread(_read, profile.joinpath(*PREFERENCES_FILE)))

    async def saved(self) -> int:
        return await asyncio.to_thread(saved_in, await self._folder())

    async def profiles(self) -> int:
        return await asyncio.to_thread(profiles_in, await self._folder())

    # A page ---------------------------------------------------------------------------------

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        self._refuse_if_stopping()
        await self._free()
        # From the look of ``_free`` to the count of this opening there is no wait: a second
        # opening that looks now finds this one.
        return await super().open(address, allowed, stop)

    async def can_show(self) -> bool:
        self._refuse_if_stopping()
        if self._system != SUPPORTED:
            raise BrowserUnsupported(self._system)
        return await self._on_a_screen()

    async def open_shown(
        self, address: str, allowed: Callable[[str], bool], stop: TaskStop
    ) -> Opened:
        """A page in a browser that has a window, whatever the switch says — and no page at all
        where no window can be had: asked first, before the folder is looked at."""
        if not await self.can_show():
            raise NoWindow(
                "the system did not say that ELA runs inside a session of the screen, and a "
                "page asked with a window is not opened without one"
            )
        await self._free()
        # From the look of ``_free`` to the count of this opening there is no wait, as in
        # ``open`` — so no other launch can read what this one is given: a second opening
        # that looks now finds this one, and is refused before it launches.
        self._with_a_window = True
        try:
            return await super().open(address, allowed, stop)
        finally:
            self._with_a_window = False

    async def _begun(self, playwright: Playwright) -> tuple[Chromium | None, BrowserContext]:
        profile = self._profile
        assert profile is not None  # noqa: S101 — ``open`` has just found it usable
        await self._prepare(profile, driven=True)
        context = await playwright.chromium.launch_persistent_context(
            str(profile), **self._launch()
        )
        return None, context

    async def _paged(self, context: BrowserContext) -> Page:
        """The page a browser on a profile opens with — one, and empty —, rather than a second
        one beside it."""
        return context.pages[0] if context.pages else await context.new_page()

    async def _looked(
        self, opened: _Open, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        glanced = await super()._looked(opened, selector, expect, seconds)
        asked = await opened.page.locator(ONE_TIME_CODE).count()
        return replace(glanced, second_factor=asked > 0)

    async def field(self, page: str, selector: str) -> Field:
        async def read(opened: _Open) -> Field:
            element = opened.page.locator(selector)
            declared = await element.get_attribute("type") or ""
            autocomplete = await element.get_attribute("autocomplete") or ""
            method = await element.evaluate(METHOD_OF)
            return Field(
                type=declared.lower(), autocomplete=autocomplete.lower(), method=str(method)
            )

        return await self._on(page, read)

    async def landed(self, page: str) -> Landed:
        """Where the page is once the document its last gesture led to is parsed, and the
        status of that document (decision 106). **The click has already waited for the
        navigation it started** — measured on 2026-10-12 with a site that takes its time: when
        it returns, the page is at the address the site's redirect led to —, so what is waited
        for here is the document itself, which the count of an element needs."""

        async def read(opened: _Open) -> Landed:
            await opened.page.wait_for_load_state("domcontentloaded")
            status = opened.documents[-1] if opened.documents else None
            return Landed(address=opened.page.url, status=status)

        return await self._on(page, read)

    async def fill_secret(self, page: str, selector: str, value: Secret) -> None:
        """Type what ``value`` holds. **The engine's own exception does not leave**, not even as
        the context of the one that does: its message names the call with what was typed
        (measured). What leaves is built from the engine's type, and raised once the handler of
        the engine's is over — so nothing is chained to it."""
        opened = self._page(page)
        # The one predicate, as around every use of a page (ADR 0064 §4): a secret is not typed
        # on a page that is not inside its boundary.
        self._within(opened)
        failed: BaseException | None = None
        try:
            await opened.page.locator(selector).fill(value.reveal())
        except PlaywrightError as error:
            if page not in self._pages and not self._stopping.is_set():
                failed = PageGone("the page was closed while ELA was using it")
            else:
                failed = self._translated(error)
        if failed is not None:
            raise failed
        self._within(opened, made=True)

    async def holds(self, page: str, selector: str, value: Secret) -> bool:
        """Whether the field holds what ``value`` holds: read from the page and compared here,
        where the secret is opened to be typed — the tool gets a yes or a no (decision 144).
        Compared whole, in a time that does not say where two values part."""

        async def read(opened: _Open) -> bool:
            written = await opened.page.locator(selector).input_value()
            return hmac.compare_digest(written.encode(), value.reveal().encode())

        return await self._on(page, read)

    async def close(self, page: str) -> None:
        """Close the page — **and return only when no closing of this adapter is in flight**
        (criterion 28): on a profile, whoever asks while another is already closing the page
        would otherwise be told «closed» with the browser still on the folder."""
        await super().close(page)
        while others := self._closing - {asyncio.current_task()}:
            await asyncio.wait(others)

    # The window -----------------------------------------------------------------------------

    async def window(self, address: str | None) -> None:
        self._refuse_if_stopping()
        if address is not None and not _of_a_site(address):
            raise BrowserFailed("the window opens on the address of a site, or on none")
        executable = self._executable()
        if executable is None:
            raise BrowserNotInstalled("the browser ELA uses is not installed")
        profile = await self._free()
        # From the look of ``_free`` to this there is no wait: a second window, or a page, that
        # looks now finds this one.
        self._windowing = True
        launching = asyncio.ensure_future(self._launched(executable, profile, address))
        launching.add_done_callback(_seen)
        self._launching = launching
        # Shielded: whoever asked may go away — a request dropped —, and the launch runs to its
        # end all the same. A process that exists is the adapter's from its first instant: it is
        # in the table, the folder is said held, and ELA's close finds it.
        await asyncio.shield(launching)

    async def _launched(self, executable: Path, profile: Path, address: str | None) -> None:
        """Start the window, and keep the wait for its end. A task of the adapter's own."""
        try:
            await self._prepare(profile, driven=False)
            self._refuse_if_stopping()
            try:
                process = await asyncio.create_subprocess_exec(
                    str(executable),
                    f"--user-data-dir={profile}",
                    reports_in(profile),
                    *WINDOW_ARGUMENTS,
                    *(() if address is None else (address,)),
                    stdin=asyncio.subprocess.DEVNULL,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    env={name: str(value) for name, value in self._environment.items()},
                    start_new_session=True,
                )
            except OSError as error:
                raise BrowserFailed(type(error).__name__) from None
            self._window = process
            self._watched = asyncio.create_task(self._waited(process, address))
        finally:
            self._windowing = False

    async def _waited(self, process: asyncio.subprocess.Process, address: str | None) -> None:
        """The one thing ELA keeps of the window: the wait for its end. At ELA's stop the window
        is **told** — ``SIGTERM``, to which the browser exits by itself —, and still waited for:
        what kills it, past the grace, is :meth:`settle`."""
        started = asyncio.get_running_loop().time()
        ended = asyncio.ensure_future(process.wait())
        stopped = asyncio.ensure_future(self._stopping.wait())
        try:
            await asyncio.wait({ended, stopped}, return_when=asyncio.FIRST_COMPLETED)
            if not ended.done():
                if self._tell(process.pid):
                    with contextlib.suppress(ProcessLookupError):
                        process.terminate()
                await ended
        finally:
            stopped.cancel()
            self._window = None
            self._was_told.discard(process.pid)
        try:
            await self._ended(address, asyncio.get_running_loop().time() - started)
        except Exception as error:
            # Whoever is told may fail — the audit, with a database that went away. Said here,
            # where it happened, by its type: kept in this task, it would be raised by ELA's
            # close hours later, in the place of the close.
            _LOG.error(
                "the end of a window of ELA's browser could not be told (%s)",
                type(error).__name__,
            )

    async def shut(self, grace: Callable[[], Awaitable[None]]) -> str | None:
        self._refuse_if_stopping()
        profile = await self._folder()
        launching = self._launching
        if launching is not None and not launching.done():
            # A window is being started: what is told is the window, once it is there.
            await asyncio.wait({launching})
        if self._pages or self._opening or self._closing:
            raise ProfileBusy(PROFILE_STEP)
        window, watched = self._window, self._watched
        if window is not None and watched is not None:
            self._refuse_if_stopping()
            return await self._end_window(window, watched, grace)
        named = await self._named(profile)
        # Asking the system took its time, and ELA may have begun to stop meanwhile: at its own
        # close ELA signals only what it started. No wait stands between this look and a signal.
        self._refuse_if_stopping()
        if named is None:
            return None
        pid, what = named
        if what != ELA_S_BROWSER:
            raise ProfileBusy(PROFILE_PROCESS)
        return await self._end_another(pid, profile, grace)

    async def _end_window(
        self,
        window: asyncio.subprocess.Process,
        watched: asyncio.Task[None],
        grace: Callable[[], Awaitable[None]],
    ) -> str:
        """The window ELA started: told as at ELA's stop — **once** —, waited for through the
        wait ELA keeps of it, which says its end to whoever is told, and killed with its group,
        which is ELA's own, once the grace is over. How it ended is read from the process: whoever
        asked a second time is answered the same."""
        if self._tell(window.pid):
            with contextlib.suppress(ProcessLookupError):
                window.terminate()
        over = asyncio.ensure_future(grace())
        try:
            await asyncio.wait({watched, over}, return_when=asyncio.FIRST_COMPLETED)
            if not watched.done():
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(window.pid, signal.SIGKILL)
                await asyncio.wait({watched})
            return SHUT_KILLED if window.returncode == -signal.SIGKILL else SHUT_QUIT
        finally:
            over.cancel()

    async def _end_another(
        self, pid: int, profile: Path, grace: Callable[[], Awaitable[None]]
    ) -> str:
        """A browser ELA did not start, which the system said is ELA's binary on this folder:
        told once; asked of the kernel until it is gone, the grace is over, or ELA stops; and
        then — **if the system still says that process is that browser** — killed by its pid.
        Never its group: a group ELA did not make is not ELA's to kill. What ELA cannot name any
        more it does not kill, **and does not call gone**: it was told, and that is all ELA
        knows."""
        if self._tell(pid):
            refused = False
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                refused = True
            if refused:
                # Another user's: not ELA's to signal, and never the system's error.
                self._was_told.discard(pid)
                raise ProfileBusy(PROFILE_PROCESS)
        over = asyncio.ensure_future(grace())
        stopped = asyncio.ensure_future(self._stopping.wait())
        try:
            while self._known(pid) and not over.done() and not stopped.done():
                await asyncio.wait(
                    {over, stopped}, timeout=GONE_EVERY, return_when=asyncio.FIRST_COMPLETED
                )
            if not self._known(pid):
                self._was_told.discard(pid)
                return SHUT_QUIT
            if stopped.done():
                return SHUT_TOLD
            # A pid is the system's to give again, and one that ended and is not collected still
            # answers: what **that process** is now is asked once more, right before it is
            # killed — of the process that was told, not of whatever the lock names by now.
            what = await self._what(pid, profile)
            if what is None:
                self._was_told.discard(pid)
                return SHUT_QUIT
            if what != ELA_S_BROWSER or self._stopping.is_set():
                return SHUT_TOLD
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                return SHUT_TOLD
            for _ in range(GONE_TURNS):
                if not self._known(pid):
                    break
                await asyncio.sleep(GONE_EVERY)
            self._was_told.discard(pid)
            return SHUT_KILLED
        finally:
            over.cancel()
            stopped.cancel()

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        """What ELA's close waits for, on the profile: the pages, as the empty browser's, **and
        the window** — told at the stop, waited for within the same grace, then killed with its
        group. When this returns nothing holds the folder."""
        if not self._stopping.is_set():
            raise RuntimeError(
                "a browser is settled after ELA's stop: the stop is what closes its pages"
            )
        counted: list[asyncio.Future[None]] = []

        def the_grace() -> asyncio.Future[None]:
            # One grace for the pages and the window, counted from the first that has to wait —
            # and not at all when neither does.
            if not counted:
                counted.append(asyncio.ensure_future(grace()))
            return asyncio.shield(counted[0])

        try:
            names = await super().settle(the_grace)
            launching = self._launching
            if launching is not None and not launching.done():
                # A window is being started: the folder is not free until that has ended, one way
                # or the other. The stop is raised, so what it starts is told at once — and is
                # waited for and killed below, like a window that was already there.
                await asyncio.wait({launching})
            window, watched = self._window, self._watched
            if watched is None:
                return names
            if not watched.done():
                await asyncio.wait({watched, the_grace()}, return_when=asyncio.FIRST_COMPLETED)
            if not watched.done() and window is not None:
                # «Not permitted» is what macOS answers for a group whose only process has ended
                # and is not collected yet (measured): a group with nothing left to kill, like
                # one that is not there.
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(window.pid, signal.SIGKILL)
                names = (*names, WINDOW_NAME)
            await asyncio.wait({watched})
            self._watched = None
            watched.result()
            return names
        finally:
            for waiting in counted:
                waiting.cancel()
