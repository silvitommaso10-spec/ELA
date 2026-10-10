"""The browser of ELA's own, with Playwright (§19; M13.4, ADR 0052): the one module that imports it.

**Here because it starts processes** — Playwright's Node driver, and the Chromium it launches — and
ELA reaches the operating system in one place (rule 32, ADR 0028 §1): «the door, not the word»
(ADR 0029 §3). ``playwright`` is one of the names rule 32 looks for, and outside this folder it is a
violation.

**A mechanism, not a policy** (M13.4 form K). Every decision reaches this module as data: the
address, the function that says which navigations of the main frame may be sent, the selector, the
value, the closed environment, the deadline of a page nobody looks at. What stays here is what only
the engine can do, and the branches of it — the translation of the engine's errors into the port's,
the callback that stops a navigation, the deadline that closes — are proved by the real browser
(``tests/infrastructure/machine/test_browser.py``), not by the gate: this folder is outside it.

What every page gets, measured before it was decided (M13.4, «Le misure»):

* **a driver and a browser of its own**, started for the page and closed with it (M3: 226 ms cold);
  the profile is Playwright's temporary one — empty, and gone with the browser (form C);
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
  is handed to the driver, and the route lets no request through — so what can still reach a site
  does not depend on how long the closing of the pages takes. An opening looks at the stop again
  the instant its page is in the table, and closes it itself: the task that closes every page may
  have come and gone while the browser was starting (measured: a form was sent after the stop);
* no downloads, no service workers, no timeout of Playwright's — the tool's deadline is the one —,
  and **every request routed**, so that a navigation of the main frame the boundary refuses is
  aborted before it is sent; the document of the main frame is fetched by the route itself, without
  following redirects, because Playwright does not call a route for a redirect (measured).

**That document is fetched by the driver, not by the browser**: its certificate is checked by Node,
and Node reads its environment — ``NODE_TLS_REJECT_UNAUTHORIZED`` or ``NODE_EXTRA_CA_CERTS`` make an
invalid certificate pass (measured, ADR 0052 §14). The rest of the page is the browser's, with the
closed environment.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, TypeVar
from urllib.parse import urljoin
from uuid import uuid4

import playwright
from playwright.async_api import Browser as Chromium
from playwright.async_api import BrowserContext, Page, Playwright, Request, Route, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout

from ela.ports import (
    NAVIGATION,
    BrowserError,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    BrowserUnsupported,
    Field,
    Glanced,
    Opened,
    PageGone,
    SiteUnreachable,
    TaskStop,
)

__all__ = ["MISSING_EXECUTABLE", "PlaywrightBrowser", "shell_folder"]

MISSING_EXECUTABLE = "Executable doesn't exist"
"""What Playwright says when the browser the lock names was never installed (M2): the one message
of the engine this module reads, and a test with an empty browsers folder holds it."""

SHELL: Final = "chromium-headless-shell"
"""The name Playwright's registry gives the Chrome Headless Shell, in its ``browsers.json``."""


def shell_folder(environment: Mapping[str, str], system: str) -> Path | None:
    """The folder Playwright installs the shell of the lock's version into — found as its registry
    finds it, never by launching anything (decision 2 of the review of 2026-09-30).

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
    (revision,) = [entry["revision"] for entry in browsers if entry["name"] == SHELL]
    return registry.absolute() / f"{SHELL.replace('-', '_')}-{revision}"


_T = TypeVar("_T")


@dataclass
class _Open:
    """One page, and everything that runs for it: closed together."""

    playwright: Playwright
    browser: Chromium
    context: BrowserContext
    page: Page
    refused: list[str]
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
        starting = asyncio.create_task(async_playwright().start())
        try:
            return await asyncio.shield(starting)
        except asyncio.CancelledError:
            self._carried(_stopped_once_started(starting))
            raise

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
                browser = await playwright.chromium.launch(**self._launch())
            except PlaywrightError as error:
                if MISSING_EXECUTABLE in str(error):
                    raise BrowserNotInstalled("the browser ELA uses is not installed") from None
                raise
            context = await browser.new_context(accept_downloads=False, service_workers="block")
            context.set_default_timeout(0)
            context.set_default_navigation_timeout(0)
            refused: list[str] = []

            async def gate(route: Route, request: Request) -> None:
                """Stop a navigation of the main frame the boundary refuses, before it is sent.

                **A redirect is looked at here, not left to the browser**: Playwright calls a route
                only for the first address of a navigation, and a server's redirect would be
                followed with no route in between — measured by the test of the real browser, and
                the reason for the second branch. So the document of the main frame is fetched here
                without following redirects; a redirect the boundary refuses is not followed, and
                one it admits is handed to the page, which follows it through this route again.
                """
                main = request.is_navigation_request() and request.frame.parent_frame is None
                if main and not allowed(request.url):
                    refused.append(request.url)
                    await route.abort()
                    return
                if self._stopping.is_set():
                    # ELA is stopping (M13.4c): nothing more leaves for a site — not a navigation
                    # asked for an instant before, not the redirect after a form. Looked at after
                    # the boundary and right before the request is let go: ``route.fetch`` writes
                    # to the driver in this same turn of the loop; ``route.continue_`` is handed
                    # over by Playwright one turn later, and a request let go here has left.
                    await route.abort()
                    return
                if not main:
                    await route.continue_()
                    return
                try:
                    response = await route.fetch(max_redirects=0)
                except PlaywrightError:
                    # A site that does not answer: the route is resolved all the same, or the
                    # navigation — which has no timeout of Playwright's — would wait for ever.
                    await route.abort("failed")
                    return
                location = response.headers.get("location")
                if 300 <= response.status < 400 and location:
                    target = urljoin(request.url, location)
                    if not allowed(target):
                        refused.append(target)
                        await route.abort()
                        return
                await route.fulfill(response=response)

            await context.route("**/*", gate)
            page = await context.new_page()
            self._pages[token] = _Open(playwright, browser, context, page, refused)
            # The last instant before the site sees anything (M6.3c, ADR 0054 §3): a stopped task
            # leaves here with ToolStopped, and the page and its browser are closed below.
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
                raise SiteUnreachable(type(error).__name__) from None
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

    def _page(self, page: str) -> _Open:
        """The page, to be used. **Not once ELA is stopping** (M13.4c): a page the stop has not
        closed yet is in the table still, and a gesture asked of it then would leave."""
        if self._stopping.is_set():
            raise BrowserStopped("ELA is stopping: the browser was closed")
        found = self._pages.get(page)
        if found is None:
            raise PageGone("no page of ELA's has this identifier any more")
        return found

    async def _on(self, page: str, action: Callable[[_Open], Awaitable[_T]]) -> _T:
        opened = self._page(page)
        try:
            return await action(opened)
        except PlaywrightError as error:
            if page not in self._pages and not self._stopping.is_set():
                raise PageGone("the page was closed while ELA was using it") from None
            raise self._translated(error) from None

    async def count(self, page: str, selector: str) -> int:
        return await self._on(page, lambda opened: opened.page.locator(selector).count())

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
        refused = self._page(page).refused
        return refused[-1] if refused else None

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
            return await self._on(page, lambda found: _look(found, selector, expect, seconds))
        finally:
            await self.close(page)

    async def close(self, page: str) -> None:
        opened = self._pages.pop(page, None)
        if opened is None:
            return
        if opened.kept is not None and opened.kept is not asyncio.current_task():
            opened.kept.cancel()
        await asyncio.shield(self._carried(_shut(opened)))


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
    return Glanced(text=text, shown=shown, left=opened.refused[-1] if opened.refused else None)


async def _shut(opened: _Open) -> None:
    """The three closings of a page, in their order: its context, its browser, its driver."""
    await _quietly(opened.context.close)
    await _quietly(opened.browser.close)
    await _quietly(opened.playwright.stop)


async def _stopped_once_started(starting: asyncio.Task[Playwright]) -> None:
    """Stop the driver an abandoned opening was starting, once its start has ended."""
    try:
        playwright = await starting
    except Exception:  # noqa: BLE001 — a start that failed started nothing to stop
        return
    await _quietly(playwright.stop)


async def _quietly(close: Callable[[], Awaitable[None]]) -> None:
    """Close something that may be closed already: a driver that died took its browser with it
    (M5), and what cannot be closed any more is closed."""
    with contextlib.suppress(Exception):  # noqa: BLE001 — whatever it raises, it is not running
        await close()
