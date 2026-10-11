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
  launch that can kill the first;
* **the preferences rewritten before every launch**, over whatever the file says
  (:data:`PREFERENCES`): they — with the flags of :data:`LAUNCH_ARGUMENTS` —, and not the binary,
  are what keeps the browser away from a Google account and from saving passwords (measured);
* **no service worker left from before**: the gate is a route of Playwright's, and a worker
  registered in the profile answers without the route being called (measured). The folder of the
  workers is removed before every launch here, and new ones are blocked;
* **no HAR, no tracing, no video**: the options of the launch are a closed set
  (:data:`LAUNCH_OPTIONS`).

**The window** (:meth:`AccountChrome.window`) is the same binary on the same folder **with nothing
attached**: no driver, no pipe, no debugging port; its output goes nowhere; ELA keeps one thing of
it, the wait for its end. At ELA's stop it is told — ``SIGTERM``, to which it exits by itself,
writing its cookies —, waited for within the grace of the close, and then killed with its group.
**It is never left behind**: the launch is a task of the adapter's own, which runs to its end
whoever asked for it and went away, and which the close waits for before it calls the folder free.

**ELA does not disguise itself**: no user agent, no script injected in a page, nothing that touches
``navigator.webdriver``. A site that refuses a driven browser is told so by the outcome.
"""

from __future__ import annotations

import asyncio
import contextlib
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
    BrowserFailed,
    BrowserNotInstalled,
    BrowserUnsupported,
    Field,
    Glanced,
    Opened,
    PageGone,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Secret,
    TaskStop,
)

__all__ = [
    "LAUNCH_ARGUMENTS",
    "LAUNCH_OPTIONS",
    "PREFERENCES",
    "PROFILE_MODE",
    "WINDOW_ARGUMENTS",
    "AccountChrome",
    "linked_in",
    "lock_holder",
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

MOCK_KEYCHAIN: Final = "--use-mock-keychain"
NO_SYNC: Final = "--disable-sync"
NO_SIGNIN: Final = "--allow-browser-signin=false"
LAUNCH_ARGUMENTS: Final = (MOCK_KEYCHAIN, NO_SYNC, NO_SIGNIN)
"""What ELA adds to the arguments Playwright passes by itself. The first two Playwright passes
too, on this system and in this version — written here so that they are ELA's own and not a
default of somebody else's: **no launch touches the keychain**, and none starts the browser's
sync. The third switches the browser's own sign-in off (measured: without it and the preferences
the same binary registers a Google account)."""
WINDOW_ARGUMENTS: Final = (
    MOCK_KEYCHAIN,
    "--no-first-run",
    "--no-default-browser-check",
    NO_SYNC,
    NO_SIGNIN,
)
"""What the window receives, beside its folder and — if there is one — an address: a closed list.
Nothing in it attaches anything to the browser."""
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
PREFERENCES_FILE: Final = ("Default", "Preferences")
SERVICE_WORKERS: Final = ("Default", "Service Worker")
LOGINS: Final = ("Default", "Login Data")
LOCK: Final = "SingletonLock"
"""The link the browser leaves in its folder while it runs: ``<host>-<pid>``."""
FIRST_PID: Final = 1
"""The system's own first process: it answers for ever, and is nobody's browser. Nor is zero,
which asked of the kernel is «every process of my group»."""
LAST_PID: Final = 2**31 - 1
"""The largest number a process can have on any system ELA runs on: a larger one, asked of the
kernel, is an error of the question."""
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


def saved_in(profile: Path) -> int:
    """How many rows the browser's own password manager holds: counted, and nothing of a row is
    read. No file yet — a profile never launched — is none. Opened read-only and as it is on the
    disk, so a browser that is running is neither waited for nor disturbed.

    :raises BrowserFailed: a file that is there and cannot be counted. Never «none»."""
    file = profile.joinpath(*LOGINS)
    if not file.is_file():
        return 0
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


def _prepared(profile: Path, *, driven: bool) -> None:
    """What is done to the folder before a launch: the preferences, always; and before a launch
    Playwright drives, the service workers gone."""
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
    workers = profile.joinpath(*SERVICE_WORKERS)
    if driven and workers.is_symlink():
        workers.unlink()  # the link, never what it points at: no worker is reached through it
    elif driven:
        shutil.rmtree(workers, ignore_errors=True)


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


class AccountChrome(PlaywrightBrowser):
    """The port :class:`~ela.ports.AccountBrowser`, with Playwright and Chrome for Testing.

    ``profile`` is the folder the user declared, ``None`` when nobody did. ``shown`` says, at
    each launch, whether the browser has a window — the user's switch, never a tool's. ``ended``
    is told when a window opened by :meth:`window` has ended: on which address it was opened, and
    how long it lasted.
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
    ) -> None:
        super().__init__(stopping, environment=environment, kept=kept, system=system)
        self._profile = profile
        self._shown = shown
        self._ended = ended
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
        return {
            "channel": CHROME,
            "headless": not self._shown(),
            "chromium_sandbox": True,
            "args": list(LAUNCH_ARGUMENTS),
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

    def _holder(self, profile: Path) -> str | None:
        """Who holds the folder now: derived, in this order — what this adapter has in flight,
        its window, and then the folder's own lock."""
        if self._pages or self._opening or self._closing:
            return PROFILE_STEP
        if self._windowing or self._window is not None:
            return PROFILE_WINDOW
        return PROFILE_PROCESS if lock_holder(profile, self._known) is not None else None

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
        holder = self._holder(profile)
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
        return self._holder(await self._folder())

    async def linked(self) -> bool:
        profile = await self._folder()
        return linked_in(await asyncio.to_thread(_read, profile.joinpath(*PREFERENCES_FILE)))

    async def saved(self) -> int:
        return await asyncio.to_thread(saved_in, await self._folder())

    # A page ---------------------------------------------------------------------------------

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        self._refuse_if_stopping()
        await self._free()
        # From the look of ``_free`` to the count of this opening there is no wait: a second
        # opening that looks now finds this one.
        return await super().open(address, allowed, stop)

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

    async def fill_secret(self, page: str, selector: str, value: Secret) -> None:
        """Type what ``value`` holds. **The engine's own exception does not leave**, not even as
        the context of the one that does: its message names the call with what was typed
        (measured). What leaves is built from the engine's type, and raised once the handler of
        the engine's is over — so nothing is chained to it."""
        opened = self._page(page)
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
                with contextlib.suppress(ProcessLookupError):
                    process.terminate()
                await ended
        finally:
            stopped.cancel()
            self._window = None
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
