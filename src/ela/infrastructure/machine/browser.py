"""The browser of ELA's own, with Playwright (§19; M13.4, ADR 0052): the one module that imports it.

**Here because it starts processes** — Playwright's Node driver, and the Chromium it launches — and
ELA reaches the operating system in one place (rule 32, ADR 0028 §1): «the door, not the word»
(ADR 0029 §3). ``playwright`` is one of the names rule 32 looks for, and outside this folder it is a
violation.

**A mechanism, not a policy** (M13.4 form K). Every decision reaches this module as data: the
address, the function that says which navigations of the main frame may be sent, the selector, the
value, the closed environment, the deadline of a page nobody looks at. What stays here is what only
the engine can do, and the branches of it — the translation of the engine's errors into the port's,
the session that stops a request, the deadline that closes — are proved by the real browser
(``tests/infrastructure/machine/test_browser.py`` and ``test_the_boundary.py``), not by the
coverage gate: this folder is outside it.

What every page gets, measured before it was decided (M13.4, «Le misure»):

* **a driver and a browser of its own**, started for the page and closed with it (M3: 226 ms cold);
  the profile is Playwright's temporary one — empty, and gone with the browser (form C): the
  browser takes its folder away when it closes, and **the adapter takes it away when it had to
  kill the browser** (M13.4e) — a killed browser leaves it, with what the page had put in it;
* **the Chrome Headless Shell of the version the lock names** (``headless=True``), which opened no
  connection of its own in thirty seconds, where the full Chromium and the installed Chrome talked
  to Google (M4);
* **the closed environment** the composition computes (M6), and ``handle_sigint``,
  ``handle_sigterm`` and ``handle_sighup`` **off** (M5-bis): Playwright starts its driver in ELA's
  process group, and with its handlers on a Ctrl-C closes the browser before ELA decides anything.
  The stop is ELA's, through the event of ADR 0038 §11;
* **a closing that runs to its end whoever waits for it** (M13.4b): the three closings of a page,
  and the stop of a driver whose opening was cancelled while it started, run in tasks of the
  adapter's own, shielded and held until they end — a caller cancelled halfway gets its
  cancellation, and the processes still go. Measured: cancelled in the caller's task, a close left
  five processes outside the table, where not even ELA's stop found them;
* **ELA's stop, whenever it is raised** (M13.4c): from that moment no navigation and no gesture
  is handed to the driver, and the gate lets no request through — so what can still reach a site
  does not depend on how long the closing of the pages takes. An opening looks at the stop again
  the instant its page is in the table, and closes it itself: the task that closes every page may
  have come and gone while the browser was starting (measured: a form was sent after the stop);
* **what ELA's close waits for** (M13.4e): :meth:`PlaywrightBrowser.settle` waits for the task the
  stop wakes — which ends when no page, no closing and no opening of this adapter is in flight —
  and, past the grace the composition gives, **kills what the adapter started**: its drivers, read
  where Playwright keeps their process, and whatever they started. Measured: torn down with a call
  of Playwright's in flight, the loop never ends — the cancelled call waits for an answer the
  cancelled reader of the pipe does not deliver —, and ELA does not exit;
* no downloads, no service workers, no timeout of Playwright's — the tool's deadline is the one.

**The gate looks at the browser's requests, and makes none** (M13.4f, ADR 0064; :class:`_Gate`).
Until M13.4f it was a route of Playwright's that fetched the document of the main frame from the
driver's process and handed it to the page. Measured on 2026-10-12: it was called for one hop of a
chain of redirects, so the second left the boundary; the driver chose the cookies of that request
beside the browser, and answered by itself a question the browser asks another site; the site saw
a client that bore the browser's name without being it; and the certificate was judged by Node,
which reads its environment. Now a session of the browser's own protocol is told of **every
request of every page before it leaves**, and answers each: let go as it is, or made to fail.
Every request, every cookie and every certificate is the browser's. No route is left in this
folder, and a rule of the architecture holds it (rule 70).

**And every use of a page asks the boundary where the page is** (ADR 0064 §4): before the use,
which then does not take place, and once it is made, when what was read is thrown away —
:class:`~ela.ports.LeftSite`. A second look, behind the gate: what keeps a page from being
elsewhere is the gate, and this is what stops ELA if the gate has missed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
import signal
import weakref
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, TypeVar
from uuid import uuid4

import playwright
from playwright.async_api import Browser as Chromium
from playwright.async_api import (
    BrowserContext,
    CDPSession,
    Frame,
    Page,
    Playwright,
    Request,
    Response,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from ela.ports import (
    NAVIGATION,
    AnotherPage,
    BrowserError,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    BrowserUnsupported,
    Field,
    Glanced,
    LeftSite,
    Opened,
    PageGone,
    SiteUnreachable,
    TaskStop,
)

__all__ = ["MISSING_EXECUTABLE", "PlaywrightBrowser", "registry_folder", "shell_folder"]

MISSING_EXECUTABLE = "Executable doesn't exist"
"""What Playwright says when the browser the lock names was never installed (M2): the one message
of the engine this module reads, and a test with an empty browsers folder holds it."""

SHELL: Final = "chromium-headless-shell"
"""The name Playwright's registry gives the Chrome Headless Shell, in its ``browsers.json``."""

PS: Final = "/bin/ps"
GONE_SECONDS: Final = 2.0
"""How long the kernel is asked whether what was killed is gone: a ``SIGKILL`` is not refused, and
what is left after it is an entry nobody has collected yet."""
LOOK_SECONDS: Final = 0.01
TEMPORARY_PROFILE: Final = "playwright_chromiumdev_profile-"
"""How Playwright names the folder of the profile it makes for a browser of one page."""
PROFILE_ARGUMENT: Final = re.compile(r"--user-data-dir=(.+?)(?= --|$)")
ALERT: Final[Mapping[str, Any]] = {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]}
"""What the gate asks the browser to be told of (ADR 0064 §2): **every request of every page**,
before it leaves. On the browser and not on a page: a page that was just opened has nothing to
turn on, and nobody has to get to it first."""
CHECK: Final = "http://127.0.0.1:9/ela-gate-check"
"""The address every page asks for before its first navigation (ADR 0064 §3): one the browser
itself refuses to open — the port is one it never connects to —, so that with the alert off no
request can reach anybody, not even on this machine. With the alert on the gate is told of it,
and that is how an opening knows the gate is there before the address of a site is asked for."""
PAGE: Final = "page"
"""What the browser calls a page among the things it announces; a frame that runs by itself is
an ``iframe``, and a worker has a name of its own."""
REFUSED: Final = "Aborted"
"""How a request the gate does not let go fails: as one somebody gave up — the page stays where
it is, and shows no error of the browser's in its place (measured)."""
DRIVER: Final = "node"
"""What a driver is called when ELA says it killed one: the binary Playwright starts it with. Said
by the adapter, which started it, and **not read from** ``ps``: a Linux kernel calls that process
by the name of its main thread — ``MainThread`` —, which names nothing to whoever reads the line
(seen on the ubuntu runner on 2026-10-10)."""


def shell_folder(environment: Mapping[str, str], system: str) -> Path | None:
    """The folder Playwright installs the shell of the lock's version into: :func:`registry_folder`
    for the shell."""
    return registry_folder(SHELL, environment, system)


def registry_folder(name: str, environment: Mapping[str, str], system: str) -> Path | None:
    """The folder Playwright installs the browser ``name`` of the lock's version into — found as
    its registry finds it, never by launching anything (decision 2 of the review of 2026-09-30).

    ``PLAYWRIGHT_BROWSERS_PATH`` first — ``0`` for the folder inside the package, anything else a
    folder of its own —, then the cache folder of ``system``, named as ``platform.system()`` names
    it: the two systems the Core runs on, and ``None`` on any other — where ELA does not know where
    to look, which is not «not installed» (review of the summary, 2026-09-30, decision 1). The
    revision is the one of the ``browsers.json`` Playwright ships. The day Playwright moves the
    shell, the test of the real browser that asks Playwright where it launches from fails.
    """
    package = Path(playwright.__file__).parent / "driver" / "package"
    declared = environment.get("PLAYWRIGHT_BROWSERS_PATH")
    if declared == "0":
        registry = package / ".local-browsers"
    elif declared:
        registry = Path(declared)
    elif system == "Darwin":
        registry = Path.home() / "Library" / "Caches" / "ms-playwright"
    elif system == "Linux":
        registry = (
            Path(environment.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"
        )
    else:
        return None
    browsers = json.loads((package / "browsers.json").read_text(encoding="utf-8"))["browsers"]
    (revision,) = [entry["revision"] for entry in browsers if entry["name"] == name]
    return registry.absolute() / f"{name.replace('-', '_')}-{revision}"


_T = TypeVar("_T")


@dataclass
class _Open:
    """One page, and everything that runs for it: closed together."""

    playwright: Playwright
    browser: Chromium | None
    """``None`` for a context that **is** its browser — the one of a profile that lasts (M13.9):
    closing it closes the browser."""
    context: BrowserContext
    page: Page
    refused: list[str]
    gate: _Gate
    allowed: Callable[[str], bool]
    """The boundary of the page: the function its tool handed to :meth:`PlaywrightBrowser.open`,
    asked by the gate about a request and by every use of the page about where the page is."""
    documents: list[int | None] = field(default_factory=list)
    """The status of every document the main frame asked for, in the order they were asked: the
    last is the page's own, and ``None`` for one that never came (M13.9, decision 106)."""
    kept: asyncio.Task[None] | None = None
    looking: bool = False
    tasks: set[asyncio.Task[None]] = field(default_factory=set)


class PlaywrightBrowser:
    """The port :class:`~ela.ports.Browser`, with Playwright and the Chrome Headless Shell.

    ``stopping`` is ELA's stop signal (ADR 0038 §11): when it is raised every page is closed, and
    what was running raises :class:`~ela.ports.BrowserStopped` — and **from then on nothing is
    started or sent**, whenever it was raised (M13.4c). ``environment`` is what the browser
    receives, and nothing else (M6). ``kept`` is how long a page handed to the verifier may wait for
    its look — a function the composition gives, awaited once per page kept.
    """

    def __init__(
        self,
        stopping: asyncio.Event,
        *,
        environment: Mapping[str, str],
        kept: Callable[[], Awaitable[None]],
        system: str,
    ) -> None:
        self._stopping = stopping
        self._system = system
        self._environment: dict[str, str | float | bool] = dict(environment)
        self._kept = kept
        self._pages: dict[str, _Open] = {}
        self._watching: asyncio.Task[None] | None = None
        self._closing: set[asyncio.Task[None]] = set()
        self._opening = 0
        self._settled = asyncio.Event()
        self._settled.set()
        self._drivers: weakref.WeakSet[Any] = weakref.WeakSet()
        # The question the kill asks the kernel of what it killed — «is it still there?».
        self._known: Callable[[int], bool] = _alive

    def _launch(self) -> dict[str, Any]:
        return {
            "headless": True,
            "env": self._environment,
            "handle_sigint": False,
            "handle_sigterm": False,
            "handle_sighup": False,
        }

    def _refuse_if_stopping(self) -> None:
        if self._stopping.is_set():
            raise BrowserStopped("ELA is stopping: no browser is started")

    def _watch(self) -> None:
        """Close every page the moment the stop signal is raised: once per browser adapter."""
        if self._watching is None or self._watching.done():
            self._watching = asyncio.create_task(self._close_all_on_stop())

    async def _close_all_on_stop(self) -> None:
        """Close every page once the stop is raised, and **do not end while anything of this
        adapter is still running** (M13.4b, decision 26): the pages in the table; the closings
        nobody waits for any more, because their caller was cancelled; and what an opening that
        was in flight when the stop was raised will close when it gets to look at the stop — it
        puts nothing in the table and no closing in the set until then, so the stop waits for it.
        No opening begins after the stop, so this ends."""
        await self._stopping.wait()
        while self._pages or self._closing or self._opening:
            for page in list(self._pages):
                await self.close(page)
            if self._closing:
                await asyncio.wait(self._closing)
            await self._settled.wait()

    def _carried(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """Run a closing in a task of the adapter's own, held until it ends (M13.4b): whoever
        waits for it may be cancelled — and cancelled again while it waits —, and what was
        running is closed all the same."""
        task = asyncio.create_task(work)
        self._closing.add(task)
        task.add_done_callback(self._closing.discard)
        return task

    async def _driver(self) -> Playwright:
        """Playwright's driver, started in a task of its own (M13.4b). An opening cancelled while
        the driver starts has nothing in its hands to stop — the process is nobody's yet —, so the
        start is left to end, and what it started is stopped then."""
        manager = async_playwright()
        self._drivers.add(manager)
        starting = asyncio.create_task(manager.start())
        try:
            playwright = await asyncio.shield(starting)
        except asyncio.CancelledError:
            self._carried(_stopped_once_started(starting))
            raise
        if _process_of(manager) is None:
            # Where Playwright keeps the process of its driver is the one thing of its insides,
            # beside a message, this adapter reads (M13.4e): without it ELA's close could not kill
            # what was started here — so nothing is started.
            await _quietly(playwright.stop)
            raise BrowserFailed("the process of the browser's driver cannot be read")
        return playwright

    def _driver_pids(self) -> list[int]:
        """The drivers this adapter started that have not ended, by pid."""
        return sorted(process.pid for process in self._running_drivers())

    def _running_drivers(self) -> list[asyncio.subprocess.Process]:
        found = (_process_of(manager) for manager in list(self._drivers))
        return [process for process in found if process is not None and process.returncode is None]

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        """What ELA's close waits for (M13.4e) — the composition's contract, beside the port:
        after the stop, nothing of this adapter runs when this returns. Past ``grace`` what the
        adapter started is killed, and named."""
        if not self._stopping.is_set():
            raise RuntimeError(
                "a browser is settled after ELA's stop: the stop is what closes its pages"
            )
        watching = self._watching
        if watching is None or watching.done():
            return ()
        waited = asyncio.ensure_future(grace())
        try:
            await asyncio.wait({watching, waited}, return_when=asyncio.FIRST_COMPLETED)
            if watching.done():
                return ()
            # The grace is over and something of this adapter is still in flight: a browser that
            # was told to close — the stop is the telling — and did not. Never SIGTERM first (the
            # form of ADR 0060 §7). With the pipes closed every call of Playwright's in flight
            # fails, so the task the stop woke ends, and is waited for.
            killed = await self._kill()
            await watching
            return killed
        finally:
            waited.cancel()

    async def _kill(self) -> tuple[str, ...]:
        """``SIGKILL`` to every driver this adapter started and to whatever each of them started,
        and their names. Returns when the kernel knows none of them: a driver is ELA's child and
        its end is an event; a browser is its driver's, and is asked of the kernel."""
        drivers = self._running_drivers()
        table = await _processes()
        doomed: list[tuple[int, str]] = []
        for driver in drivers:
            doomed.extend(_descendants(driver.pid, table))
            doomed.append((driver.pid, DRIVER))
        # Read before the kill, from the browsers' own arguments: where each keeps its profile. A
        # browser that closes takes that folder away; one that is killed leaves it.
        profiles = await _profiles([pid for pid, _ in doomed])
        for pid, _ in doomed:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        for driver in drivers:
            await driver.wait()
        # Only once the kernel has none of what was killed is its profile taken away: a browser
        # killed a moment ago may still be writing in it (decision 58 — held by a test that asks
        # the question itself).
        await _gone([pid for pid, _ in doomed], self._known)
        for folder in profiles:
            if folder.is_dir() and not folder.is_symlink():
                await asyncio.to_thread(shutil.rmtree, folder, True)
        return tuple(name for _, name in doomed)

    async def _dropped(self, token: str, playwright: Playwright) -> None:
        """What an opening started and will not hand over: the page, if it reached the table, and
        the driver in any case."""
        await self.close(token)
        await _quietly(playwright.stop)

    def _translated(self, error: BaseException) -> BaseException:
        if isinstance(error, BrowserError):
            return error
        if self._stopping.is_set():
            return BrowserStopped("ELA is stopping: the browser was closed")
        if isinstance(error, PlaywrightError):
            return BrowserFailed(type(error).__name__)
        return error

    async def installed(self) -> bool:
        """Whether the shell's executable is where Playwright would launch it from: a look at a
        file, and nothing started — the launch that does the work says the rest."""
        self._refuse_if_stopping()
        folder = shell_folder(os.environ, self._system)
        if folder is None:
            raise BrowserUnsupported(self._system)
        return any(
            found.is_file()
            for found in folder.glob("chrome-headless-shell-*/chrome-headless-shell")
        )

    async def open(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        self._refuse_if_stopping()
        self._watch()
        # In flight from here to its end, whatever the end: the stop does not call itself done
        # with the browser while an opening may still have something to close (decision 26).
        self._opening += 1
        self._settled.clear()
        try:
            return await self._opened(address, allowed, stop)
        finally:
            self._opening -= 1
            if not self._opening:
                self._settled.set()

    async def _opened(self, address: str, allowed: Callable[[str], bool], stop: TaskStop) -> Opened:
        playwright = await self._driver()
        token = uuid4().hex
        try:
            try:
                browser, context = await self._begun(playwright)
            except PlaywrightError as error:
                if MISSING_EXECUTABLE in str(error):
                    raise BrowserNotInstalled("the browser ELA uses is not installed") from None
                raise
            context.set_default_timeout(0)
            context.set_default_navigation_timeout(0)
            refused: list[str] = []
            page = await self._paged(context)
            try:
                gate = await self._gated(context, page, allowed, refused)
            except BrowserError:
                raise
            except Exception as error:
                if self._stopping.is_set():
                    raise  # said below as what it is: ELA was stopping
                # Whatever it was, the gate is not there: nothing is asked of any site, and the
                # step says which part of the browser failed.
                raise BrowserFailed(
                    f"the gate of the browser could not be turned on ({type(error).__name__})"
                ) from None
            await self._proved(page, gate)
            documents: list[int | None] = []
            page.on("request", lambda request: _asked(documents, request, page))
            page.on("response", lambda response: _answered(documents, response, page))
            self._pages[token] = _Open(
                playwright, browser, context, page, refused, gate, allowed, documents
            )
            # The last instant before the site sees anything (M6.3c, ADR 0054 §3): a stopped task
            # leaves here with ToolStopped, and the page and its browser are closed below. **No
            # use of the page stands between the check of the gate and this navigation**
            # (ADR 0064 §3).
            stop.listen(NAVIGATION)
            # And ELA's own stop, looked at again now that the page is in the table (M13.4c): a
            # stop raised while the browser was starting woke the task that closes every page
            # before this page was there to be closed. Whoever puts a page in the table after the
            # stop closes it — below. No wait stands between this look and the navigation.
            self._refuse_if_stopping()
            try:
                response = await page.goto(address, wait_until="load")
            except PlaywrightError as error:
                if refused:
                    return Opened(page=token, status=None, address=page.url, left=refused[0])
                if self._stopping.is_set():
                    raise
                if gate.broken:
                    raise BrowserFailed(UNJUDGED) from None
                raise SiteUnreachable(type(error).__name__) from None
            # The page that was opened is asked where it is, like every use of it after
            # (ADR 0064 §4): what this returns — its address, the status of its document — is
            # said of a page inside the boundary, or not said.
            self._within(self._pages[token])
            return Opened(
                page=token,
                status=None if response is None else response.status,
                address=page.url,
                left=refused[0] if refused else None,
            )
        except asyncio.CancelledError:
            # The tool's deadline, or a cancelled run: close what was started, and let the
            # cancellation be what it is — turned into anything else, the deadline would not fire.
            await asyncio.shield(self._carried(self._dropped(token, playwright)))
            raise
        except Exception as error:
            await asyncio.shield(self._carried(self._dropped(token, playwright)))
            raise self._translated(error) from None

    async def _begun(self, playwright: Playwright) -> tuple[Chromium | None, BrowserContext]:
        """The browser of one page and its context: the shell, launched, and an empty context of
        its own. The seam of the adapter of the profile (M13.9), which launches another binary on
        a folder that lasts."""
        browser = await playwright.chromium.launch(**self._launch())
        context = await browser.new_context(accept_downloads=False, service_workers="block")
        return browser, context

    async def _paged(self, context: BrowserContext) -> Page:
        """The page of a context that has none yet."""
        return await context.new_page()

    async def _attached(self, context: BrowserContext) -> CDPSession:
        """A session of the browser's own, beside Playwright's: where the gate is told of every
        request. Not a page's: a page that is opened later would have none."""
        browser = context.browser
        if browser is None:
            raise BrowserFailed("the browser of the page cannot be reached: no gate, no page")
        return await browser.new_browser_cdp_session()

    async def _gated(
        self,
        context: BrowserContext,
        page: Page,
        allowed: Callable[[str], bool],
        refused: list[str],
    ) -> _Gate:
        """The gate of ``page``, turned on: from here every request of every page of this
        browser waits for it."""
        session = await self._attached(context)
        own = await context.new_cdp_session(page)
        main = _frames_in((await own.send("Page.getFrameTree"))["frameTree"])[0]
        gate = _Gate(session, own, context, page, main, allowed, self._stopping, refused)
        await gate.on()
        return gate

    async def _proved(self, page: Page, gate: _Gate) -> None:
        """Ask for :data:`CHECK`, which the browser itself would refuse, and see that the gate
        was told of it (ADR 0064 §3): a gate that is told of nothing would be told of nothing of
        the site either, and the opening fails closed before any address of the site is asked
        for. With the alert on and nobody told, the request stays paused and this does not
        return: the tool's own time ends the step, and the page is closed like any other."""
        gate.proving = True
        try:
            with contextlib.suppress(PlaywrightError):
                await page.goto(CHECK, wait_until="commit")
        finally:
            gate.proving = False
        if not gate.checked:
            raise BrowserFailed(
                "the gate of the browser is not told of its requests: no address was asked for"
            )

    async def _looked(
        self, opened: _Open, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        """The verifier's one look: what this browser says of a page."""
        return await _look(opened, selector, expect, seconds)

    def _page(self, page: str) -> _Open:
        """The page, to be used. **Not once ELA is stopping** (M13.4c): a page the stop has not
        closed yet is in the table still, and a gesture asked of it then would leave."""
        if self._stopping.is_set():
            raise BrowserStopped("ELA is stopping: the browser was closed")
        found = self._pages.get(page)
        if found is None:
            raise PageGone("no page of ELA's has this identifier any more")
        return found

    def _within(self, opened: _Open, *, made: bool = False) -> None:
        """**The one predicate** (ADR 0064 §4): the boundary of the page, asked where the page is.
        Before a use, which then does not take place; and once it is made — ``made`` —, when what
        was read is thrown away. A gate whose judge raised has let nothing go, and says so here
        — **before a use, never after one**: a gesture whose own request the judge raised on was
        made, returns as made, and it is the next use that says the browser failed, with that
        gesture counted."""
        if opened.gate.broken and not made:
            raise BrowserFailed(UNJUDGED)
        address = _where(opened.page)
        if not opened.allowed(address):
            raise LeftSite(address, made=made)

    async def _on(self, page: str, action: Callable[[_Open], Awaitable[_T]]) -> _T:
        """A use of a page: the predicate, the use, the predicate again."""
        opened = self._page(page)
        self._within(opened)
        try:
            done = await action(opened)
        except PlaywrightError as error:
            if page not in self._pages and not self._stopping.is_set():
                raise PageGone("the page was closed while ELA was using it") from None
            raise self._translated(error) from None
        self._within(opened, made=True)
        return done

    async def count(self, page: str, selector: str) -> int:
        return await self._on(page, lambda opened: opened.page.locator(selector).count())

    async def appeared(self, page: str, selector: str) -> int:
        """The engine's own wait, **strict**, on the selector itself (M13.10, measures (a) and (g)
        of its SPEC): it ends when the selector finds one visible element, and raises at once when
        it finds several — then the count says how many. It looks at the page at intervals of its
        own, up to half a second: an element is seen at most about half a second after it is
        there. No timeout here: the tool's time is the one."""

        async def wait(opened: _Open) -> int:
            element = opened.page.locator(selector)
            try:
                await element.wait_for(state="visible", timeout=0)
            except PlaywrightError:
                found = await element.count()
                if found > 1:
                    return found
                raise
            return await element.count()

        return await self._on(page, wait)

    async def field(self, page: str, selector: str) -> Field:
        async def read(opened: _Open) -> Field:
            element = opened.page.locator(selector)
            declared = await element.get_attribute("type") or ""
            autocomplete = await element.get_attribute("autocomplete") or ""
            return Field(type=declared.lower(), autocomplete=autocomplete.lower())

        return await self._on(page, read)

    async def fill(self, page: str, selector: str, value: str) -> None:
        await self._on(page, lambda opened: opened.page.locator(selector).fill(value))

    async def click(self, page: str, selector: str) -> None:
        await self._on(page, lambda opened: opened.page.locator(selector).click())

    async def text(self, page: str, selector: str | None) -> str:
        return await self._on(
            page, lambda opened: opened.page.locator(selector or "body").inner_text()
        )

    async def title(self, page: str) -> str:
        return await self._on(page, lambda opened: opened.page.title())

    async def left(self, page: str) -> str | None:
        opened = self._page(page)
        self._within(opened)
        return opened.refused[-1] if opened.refused else None

    async def another(self, page: str) -> AnotherPage | None:
        opened = self._pages.get(page)
        return None if opened is None else opened.gate.another

    async def keep(self, page: str) -> None:
        opened = self._pages.get(page)
        if opened is not None:
            opened.kept = asyncio.create_task(self._expire(page))

    async def _expire(self, page: str) -> None:
        """The last defence: a page handed to the verifier and never looked at is closed."""
        await self._kept()
        opened = self._pages.get(page)
        if opened is not None and not opened.looking:
            await self.close(page)

    async def glance(
        self, page: str, *, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        opened = self._page(page)
        opened.looking = True
        if opened.kept is not None:
            opened.kept.cancel()
        try:
            return await self._on(
                page, lambda found: self._looked(found, selector, expect, seconds)
            )
        finally:
            await self.close(page)

    async def close(self, page: str) -> None:
        opened = self._pages.pop(page, None)
        if opened is None:
            return
        if opened.kept is not None and opened.kept is not asyncio.current_task():
            opened.kept.cancel()
        await asyncio.shield(self._carried(_shut(opened)))


UNJUDGED: Final = "the boundary could not be asked about a request of the page: nothing was sent"
"""What a step says when whoever judges a request raised: the request was made to fail."""


def _where(page: Page) -> str:
    """Where the page is: the address of its main frame **as this adapter knows it** — the last
    the driver told it, with no call more. It can be an instant behind the browser, and the
    page can move between this and the use: it is the second look (ADR 0064 §4)."""
    return page.url


def _frames_in(tree: Mapping[str, Any]) -> list[str]:
    """The ids of the frames of a tree as the browser gives it, the root first."""
    found = [str(tree["frame"]["id"])]
    for child in tree.get("childFrames", ()):
        found.extend(_frames_in(child))
    return found


class _Gate:
    """The gate of one page (M13.4f, ADR 0064 §2): **it looks, and makes no request**.

    A session of the browser's own protocol, beside Playwright's, asks to be told of every
    request of every page before it leaves (:data:`ALERT`), and answers each one:

    * **a document of the main frame of the page ELA works on** — the first address of a
      navigation or the hop of a redirect, whatever its method, a link that downloads too — is
      judged by the boundary: refused, it fails here and its address is kept; admitted, it
      leaves **as the browser made it**;
    * **everything else that page loads**, and the documents of the frames inside it, leave:
      the boundary is not what a page may load;
    * **a request whose frame is no frame of that page fails**, whatever it is: another page's,
      a shared worker's, a service worker's. ELA works on one page, and nobody would look at
      another. The session is told of a request with its frame and nothing of its page: a frame
      is the page's when the tree of the page has it, or the tree of a frame that has a session
      of its own — the frames inside a frame of another site are only there (measured) —,
      **and a frame that is found nowhere is refused**. What a dedicated worker of the page
      asks for is told with the frame of the page, and leaves (measured);
    * **what the browser has announced as something else is refused without asking the page**:
      a page, a worker. The browser says so before that thing makes its first request
      (measured), and the page cannot always be asked — while a worker answers a navigation
      of the page, the page's own session answers nothing, and a gate that waited for it
      would wait for the navigation that waits for the worker that waits for the gate
      (measured: a test stopped there);
    * **from ELA's stop on, every request fails** (M13.4c) — looked at last, right before a
      request would be let go;
    * **whoever judges raises, and the request fails**: in doubt nothing leaves, and the next
      use of the page says the browser failed.

    The alert is never turned off and the session is never let go of while the browser lives:
    a request that is paused leaves when its alert goes (measured). When the driver dies the
    browser dies with it, and what was paused never left.

    **What it does not do**, and why (ADR 0064 §5): what the first page has loaded in an empty
    page it opened is told to this session with the frame of the first page — it is the first
    page that loads it, as it would in its own document —, and leaves like everything a page
    loads. Every document of that other page has a frame of its own, and fails.
    """

    def __init__(
        self,
        session: CDPSession,
        own: CDPSession,
        context: BrowserContext,
        page: Page,
        main: str,
        allowed: Callable[[str], bool],
        stopping: asyncio.Event,
        refused: list[str],
    ) -> None:
        self._session = session
        self._own = own
        self._context = context
        self._page = page
        self._target = main
        """The id the browser knows the page by: that of its main frame when the page was made."""
        self._main = main
        self._allowed = allowed
        self._stopping = stopping
        self.refused = refused
        self.another: AnotherPage | None = None
        """The page the first page opened, once the browser has said so — before anything
        written in it is asked for (measured) —, with its first request once it has made one."""
        self.proving = False
        """Whether the opening is asking for :data:`CHECK` now: only then is that address the
        check, and not something a page asks for — which the boundary judges like the rest."""
        self.checked = False
        self.broken = False
        self._strangers: dict[str, str] = {}
        """What the browser announced that is not this page and is no frame — another page, a
        worker —, with what kind of thing it said it was. A request that names one of them as
        its frame is nobody's of this page."""
        self._inside: set[str] = set()
        self._of_frames: dict[Frame, CDPSession] = {}
        self._judging: set[asyncio.Task[None]] = set()
        session.on("Fetch.requestPaused", self._told)
        session.on("Target.targetCreated", self._born)

    async def on(self) -> None:
        """Ask to be told of every page that is opened, and of every request."""
        await self._session.send("Target.setDiscoverTargets", {"discover": True})
        await self._session.send("Fetch.enable", dict(ALERT))

    def _born(self, event: Mapping[str, Any]) -> None:
        """The browser announces something: a page, a worker, a frame that runs by itself.

        A page the page ELA works on opened is said, even if it never asks for anything. And
        whatever is not this page and not a frame is kept as a stranger — a frame is not one:
        a frame of another site inside the page is announced too, and is the page's."""
        born = event.get("targetInfo", {})
        kind, target = born.get("type"), str(born.get("targetId", ""))
        if kind == PAGE and born.get("openerId") == self._target:
            self.another = self.another or AnotherPage(method=None, address=None)
        if target != self._target and kind != "iframe":
            self._strangers[target] = str(kind)

    def _told(self, event: Mapping[str, Any]) -> None:
        """A request is paused, and waits for this gate: answered in a task of the gate's own,
        held until it ends."""
        judging = asyncio.ensure_future(self._answered(event))
        self._judging.add(judging)
        judging.add_done_callback(self._judging.discard)

    async def _answered(self, event: Mapping[str, Any]) -> None:
        try:
            leaves = await self._leaves(event)
        except Exception:  # noqa: BLE001 — whoever judges could not say: in doubt it stays
            self.broken = True
            leaves = False
        # ELA's stop, looked at last (M13.4c): the answer is written to the driver in this same
        # turn of the loop, so a request let go here is one the stop had not reached.
        if leaves and self._stopping.is_set():
            leaves = False
        answer: dict[str, Any] = {"requestId": event["requestId"]}
        if not leaves:
            answer["errorReason"] = REFUSED
        # A request that is gone by now — its page closed, its frame gone elsewhere — cannot be
        # answered, and has not left: the browser says so, and that is not a failure.
        with contextlib.suppress(PlaywrightError):
            await self._session.send(
                "Fetch.continueRequest" if leaves else "Fetch.failRequest", answer
            )

    async def _leaves(self, event: Mapping[str, Any]) -> bool:
        """Whether the request the gate was told of may leave."""
        request = event["request"]
        address = str(request["url"])
        if self.proving and address == CHECK:
            self.checked = True
            return False
        if self._stopping.is_set():
            return False
        frame = str(event.get("frameId", ""))
        if frame in self._strangers or not await self._of_the_page(frame):
            # The first thing the page that was opened asked for — its own request or a frame's
            # written in it, never a worker's, which is no page.
            of_a_page = self._strangers.get(frame, PAGE) == PAGE
            if self.another is not None and self.another.address is None and of_a_page:
                self.another = AnotherPage(method=str(request["method"]), address=address)
            return False
        of_the_main_frame = frame == self._main and event.get("resourceType") == "Document"
        if of_the_main_frame and not self._allowed(address):
            self.refused.append(address)
            return False
        return True

    async def _of_the_page(self, frame: str) -> bool:
        """Whether ``frame`` is a frame of the page ELA works on. Asked of the browser only for
        a frame not seen before; whatever cannot be asked is not the page's."""
        if frame == self._main or frame in self._inside:
            return True
        try:
            tree = _frames_in((await self._own.send("Page.getFrameTree"))["frameTree"])
        except PlaywrightError:
            return False
        self._main = tree[0]
        self._inside.update(tree)
        for one in self._page.frames:
            if frame in self._inside:
                break
            if one is self._page.main_frame:
                continue
            try:
                self._inside.update(await self._frames_under(one))
            except PlaywrightError:
                # A frame with no session of its own is in the tree of the one above it; one
                # that is gone has no request to make.
                continue
        return frame in self._inside

    async def _frames_under(self, frame: Frame) -> list[str]:
        """The frames in the tree of a frame that has a session of its own. The session is kept
        for the next time — and made again when it answers no more: a frame that went to
        another site has another one."""
        kept = self._of_frames.pop(frame, None)
        if kept is not None:
            with contextlib.suppress(PlaywrightError):
                found = _frames_in((await kept.send("Page.getFrameTree"))["frameTree"])
                self._of_frames[frame] = kept
                return found
        session = await self._context.new_cdp_session(frame)
        found = _frames_in((await session.send("Page.getFrameTree"))["frameTree"])
        self._of_frames[frame] = session
        return found


def _of_the_page(request: Request, page: Page) -> bool:
    """Whether ``request`` asks for **a document of the main frame** — and not for anything else
    the page loads: an image, a script, the document of a frame inside it."""
    return request.is_navigation_request() and request.frame is page.main_frame


def _asked(documents: list[int | None], request: Request, page: Page) -> None:
    """A document of the main frame was asked for: it has no status until it comes (M13.9,
    decision 106). The one of the page before it is not its own — a site that takes a login and
    answers nothing would be told with the ``200`` of its form."""
    if _of_the_page(request, page):
        documents.append(None)


def _answered(documents: list[int | None], response: Response, page: Page) -> None:
    """A document of the main frame came: a redirect's, and then the page's own."""
    if not _of_the_page(response.request, page):
        return
    if documents and documents[-1] is None:
        documents[-1] = response.status
    else:
        documents.append(response.status)


async def _look(opened: _Open, selector: str | None, expect: str | None, seconds: float) -> Glanced:
    """What the verifier asked about, on the page as it is now."""
    text: str | None = None
    if selector is not None or expect is None:
        element = opened.page.locator(selector or "body")
        if await element.count() == 1:
            text = await element.inner_text()
    shown: bool | None = None
    if expect is not None:
        try:
            await opened.page.get_by_text(expect).first.wait_for(
                state="visible", timeout=seconds * 1000
            )
            shown = True
        except PlaywrightTimeout:
            shown = False
    return Glanced(
        text=text,
        shown=shown,
        left=opened.refused[-1] if opened.refused else None,
        another=opened.gate.another,
    )


async def _shut(opened: _Open) -> None:
    """The three closings of a page, in their order: its context, its browser, its driver."""
    await _quietly(opened.context.close)
    if opened.browser is not None:
        await _quietly(opened.browser.close)
    await _quietly(opened.playwright.stop)


async def _stopped_once_started(starting: asyncio.Task[Playwright]) -> None:
    """Stop the driver an abandoned opening was starting, once its start has ended."""
    try:
        playwright = await starting
    except Exception:  # noqa: BLE001 — a start that failed started nothing to stop
        return
    await _quietly(playwright.stop)


def _process_of(manager: object) -> asyncio.subprocess.Process | None:
    """The process of a driver, read where Playwright keeps it (pinned in the lock) — the manager
    of ``async_playwright()``, its connection, its transport. ``None`` before the driver is
    started, and the day Playwright keeps it elsewhere: a test of the real browser holds it."""
    connection = getattr(manager, "_connection", None)
    process = getattr(getattr(connection, "_transport", None), "_proc", None)
    return process if isinstance(process, asyncio.subprocess.Process) else None


async def _processes() -> dict[int, tuple[int, str]]:
    """Every process the kernel knows — its parent and its name —, as ``ps`` says it. Empty when
    ``ps`` cannot be asked: then a driver is killed alone, and its browser goes with its pipe."""
    try:
        asking = await asyncio.create_subprocess_exec(
            PS,
            "-A",
            "-o",
            "pid=,ppid=,comm=",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return {}
    said, _ = await asking.communicate()
    return _listed(said.decode(errors="replace"))


def _listed(said: str) -> dict[int, tuple[int, str]]:
    """What ``ps -o pid=,ppid=,comm=`` printed, by pid: the parent, and the name without its path.
    A line that is not «pid, parent, name» is not a process this can place: left out, and never an
    error in the middle of ELA's close."""
    table: dict[int, tuple[int, str]] = {}
    # Split where ``ps`` ends a line and nowhere else: a name is whatever its process says it is,
    # and one that carried a line separator of Unicode's would otherwise write a row of its own —
    # a process that is nobody's, listed as started by a driver, and killed with it.
    for line in said.split("\n"):
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2].rsplit("/", 1)[-1])
    return table


def _descendants(of: int, table: Mapping[int, tuple[int, str]]) -> list[tuple[int, str]]:
    """What ``of`` started, and what that started: pids and names, the nearest first. Each once,
    and never ``of`` itself: a table that loops — which a kernel does not say — is walked once."""
    found: list[tuple[int, str]] = []
    seen = {of}
    todo = [of]
    while todo:
        parent = todo.pop()
        for pid, (above, name) in table.items():
            if above == parent and pid not in seen:
                seen.add(pid)
                found.append((pid, name))
                todo.append(pid)
    return found


async def _profiles(pids: Sequence[int]) -> list[Path]:
    """The temporary profiles of the browsers among ``pids``, read from their own arguments."""
    if not pids:
        return []
    try:
        asking = await asyncio.create_subprocess_exec(
            PS,
            "-ww",
            "-o",
            "args=",
            "-p",
            ",".join(str(pid) for pid in pids),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        return []
    said, _ = await asking.communicate()
    return _temporary_profiles(said.decode(errors="replace"))


def _temporary_profiles(said: str) -> list[Path]:
    """The folders ``--user-data-dir=`` names in what ``ps -o args=`` printed, **kept only if they
    are Playwright's temporary profiles** — an absolute path whose last part begins as Playwright
    names them. What is taken away after a kill is never a folder somebody chose."""
    named = {Path(folder) for line in said.split("\n") for folder in PROFILE_ARGUMENT.findall(line)}
    return sorted(
        folder
        for folder in named
        if folder.is_absolute() and folder.name.startswith(TEMPORARY_PROFILE)
    )


async def _gone(pids: list[int], known: Callable[[int], bool]) -> None:
    """Wait until the kernel knows none of ``pids`` — ``known`` is the question —, asked every
    :data:`LOOK_SECONDS` and for no longer than :data:`GONE_SECONDS`: a deadline on the loop's
    clock, as the launcher's."""
    deadline = asyncio.get_running_loop().time() + GONE_SECONDS
    left = list(pids)
    while left:
        left = [pid for pid in left if known(pid)]
        if not left or asyncio.get_running_loop().time() >= deadline:
            return
        await asyncio.sleep(LOOK_SECONDS)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _quietly(close: Callable[[], Awaitable[None]]) -> None:
    """Close something that may be closed already: a driver that died took its browser with it
    (M5), and what cannot be closed any more is closed."""
    with contextlib.suppress(Exception):  # noqa: BLE001 — whatever it raises, it is not running
        await close()
