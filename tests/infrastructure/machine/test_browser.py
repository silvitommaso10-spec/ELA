"""The real browser: Playwright and the Chrome Headless Shell of the lock (M13.4, ADR 0052).

What only a real browser can show, on pages served from inside the test on ``127.0.0.1`` — no
network, no site of anybody's. The origin of a site is the tool's dependency (form E), so the tool
and the verifier run here exactly as in production, with a local origin instead of ``https``:

* a read, and **a click sent is not a click that worked** (§20): the verifier waits for the text;
* the boundary: a navigation of the main frame off it **is not sent** — the other server counts —,
  and one it admits **is followed and read**: a redirect on the same site or to another declared
  one, and the ``303`` after a form;
* **no gesture** when the page is not the plan's — the page reports every event it sees;
* an empty profile for every page: a cookie does not pass;
* the stop, the deadline and the close, and **no process left** when the close returns;
* a cancellation (M13.4b): a tool cancelled after the opening, a close and an opening cancelled
  halfway — **no process left** once the adapter's own closings are done, awaited as tasks;
* ELA's stop, **whenever it is raised** (M13.4c): while the browser starts, at the last listening,
  at the gate, with a page open — from then on no navigation and no gesture leaves, and the site
  counts nothing. Each of those instants is built with an event, never with a time;
* what ELA's close waits for (M13.4e): after the stop the adapter is brought to rest, and **a
  browser that does not close is killed when the grace is over** — its driver stopped by a signal,
  the grace an event of the test's;
* a ``SIGINT`` to ELA's process group does not close the page (M5-bis).

**No sleep**: the pages answer to requests, and the deadline is an event. The one wait is the
negative case of the verifier — a text that never appears has no event —, bounded to a fifth of a
second. If the shell is not installed these tests **fail**, naming the command: a skip on the
system they cover is the debt of ADR 0047 §18.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import signal
import subprocess
import sys
import threading
from collections.abc import AsyncIterator, Coroutine, Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import playwright
import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from ela.domain import (
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.infrastructure.machine import PlaywrightBrowser
from ela.infrastructure.machine.browser import (
    _descendants,
    _gone,
    _listed,
    _temporary_profiles,
    shell_folder,
)
from ela.permissions import BROWSER_ACT, BROWSER_READ
from ela.ports import (
    NAVIGATION,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    BrowserUnsupported,
    PageGone,
    SiteUnreachable,
    ToolStopped,
)
from ela.testing.fakes import FakeClock, FakeIdGenerator, FakeStop
from ela.tools.browser import (
    ELEMENT_MISSING,
    LEFT_SITE,
    SECRET_FIELD,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
    boundary,
    origin_of,
)
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_TEXT_MATCHES,
    BrowserActVerifier,
    BrowserReadVerifier,
)

INSTALL = "uv run playwright install --only-shell chromium"
SYSTEM = platform.system()
"""The system these tests run on: the real browser is this machine's, and so is where its shell is.
Named here once and handed to the adapter, as the composition names it."""
CLOCK = FakeClock()
REPORTS = """
<script>
for (const kind of ["focus", "input", "change", "click"]) {
  document.addEventListener(kind, () => navigator.sendBeacon("/event", kind), true);
}
</script>
"""


class Site:
    """A web server of the test's, and what it received."""

    def __init__(self, pages: dict[str, tuple[int, dict[str, str], str]]) -> None:
        self.pages = pages
        self.requests: list[str] = []
        self.bodies: list[str] = []
        self.events: list[str] = []
        self.cookies: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                path = self.path
                if self.command == "POST" and path == "/event":
                    length = int(self.headers.get("Content-Length") or 0)
                    site.events.append(self.rfile.read(length).decode())
                    self.send_response(204)
                    self.end_headers()
                    return
                site.requests.append(f"{self.command} {path}")
                site.cookies.append(self.headers.get("Cookie") or "")
                if self.command == "POST":
                    length = int(self.headers.get("Content-Length") or 0)
                    body = self.rfile.read(length).decode()
                    site.bodies.append(body)
                    thanks = (200, {}, f"<p>Grazie {body.split('=', 1)[-1]}</p>")
                    page = site.pages.get(path, thanks)
                else:
                    page = site.pages.get(path.split("?")[0], (404, {}, "<p>nothing</p>"))
                status, headers, html = page
                data = html.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _answer  # noqa: N815
            do_POST = _answer  # noqa: N815

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def served() -> Iterator[list[Site]]:
    made: list[Site] = []
    yield made
    for site in made:
        site.close()


def site(served: list[Site], pages: dict[str, tuple[int, dict[str, str], str]]) -> Site:
    made = Site(pages)
    served.append(made)
    return made


class Kept:
    """The deadline of a page nobody looks at, as an event the test raises (form I)."""

    def __init__(self) -> None:
        self.due = asyncio.Event()

    async def __call__(self) -> None:
        await self.due.wait()


@pytest.fixture
async def browser() -> AsyncIterator[PlaywrightBrowser]:
    made = PlaywrightBrowser(
        asyncio.Event(),
        environment={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"},
        kept=Kept(),
        system=SYSTEM,
    )
    if not await made.installed():
        pytest.fail(f"the browser ELA uses is not installed on this machine: run `{INSTALL}`")
    yield made
    for page in list(made._pages):  # noqa: SLF001 — nothing is left running after a test
        await made.close(page)


def started() -> list[tuple[int, str]]:
    """What this worker has started and the kernel still knows — ``ps`` itself aside."""
    out = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True, check=True
    ).stdout
    children: dict[int, list[tuple[int, str]]] = {}
    for pid, (ppid, name) in _listed(out).items():
        children.setdefault(ppid, []).append((pid, name))
    found: list[tuple[int, str]] = []
    todo = [os.getpid()]
    while todo:
        for pid, name in children.get(todo.pop(), []):
            if name != "ps":
                found.append((pid, name))
                todo.append(pid)
    return found


def descendants() -> list[str]:
    """The same, by name."""
    return [name for _, name in started()]


def drivers() -> list[int]:
    """The drivers this worker has started: **its own children**, by pid. Not found by a name —
    ``node`` is what macOS calls the process; a Linux kernel calls it by the name of its main
    thread, ``MainThread``, and a test that looked for ``node`` passed on one runner and failed on
    the other (the CI of 2026-10-10)."""
    out = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True, check=True
    ).stdout
    mine = os.getpid()
    return sorted(
        pid for pid, (parent, name) in _listed(out).items() if parent == mine and name != "ps"
    )


@pytest.fixture
async def nothing_left_behind() -> AsyncIterator[None]:
    """A browser a test leaves that nobody holds is not left to the next test — nor to the loop,
    which at its end cancels every task and then waits for ever for a call of Playwright's that
    was in flight (measured, 2026-10-10: ``asyncio.run`` does not return). Killed here, by pid:
    the test that left it has failed on its own assertion already, and this asserts nothing.

    **An ``async`` fixture on purpose**: it is torn down inside the loop, so before the loop
    itself — a plain one is torn down after it in every test that asks for no other fixture of the
    loop's, which is where a red test hung instead of failing (the review of the repair)."""
    yield
    left = started()
    for pid, _ in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:  # gone on its own in between
            continue
    others = asyncio.all_tasks() - {asyncio.current_task()}
    closing = [
        task
        for task in others
        if getattr(task.get_coro(), "__name__", "") in CLOSINGS_OF_THE_ADAPTER
    ]
    if left or closing:
        # Only after a test that failed: either it left a process, killed above, or it returned
        # while a closing of the adapter's was still in flight — its processes dead already. The
        # calls that were in flight fail on a closed pipe: they are given the loop before it is
        # torn down, and what waits for ever — the task the stop wakes — is what the bound is for.
        await asyncio.wait(others, timeout=2)


CLOSINGS_OF_THE_ADAPTER = frozenset({"_shut", "_dropped", "_stopped_once_started"})
"""The coroutines of the adapter that hold a call of Playwright's while they close something."""


def decision(capability: str) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def browsing(*sites: Site) -> Browsing:
    """The tool's view of the test's servers: each a declared site, with a local origin."""
    names = {f"sito{index}.example": made.origin for index, made in enumerate(sites)}
    return Browsing(sites=tuple(names), origin=lambda name: names[name])


# ----------------------------------------------------------------------------------------
# A read, an action, and a click that did nothing
# ----------------------------------------------------------------------------------------


async def test_a_page_is_read_and_the_verifier_reads_it_again(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<title>Prova</title><h1>Pagina di prova</h1>")})
    arguments = {"site": "sito0.example", "path": "/", "selector": "h1", "purpose": "x"}

    result = await BrowserReadTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ), arguments, FakeStop()
    )
    failures = await BrowserReadVerifier(browser, 5.0).verify(
        [BROWSER_TEXT_MATCHES], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert result.output["text"] == "Pagina di prova"
    assert result.output["title"] == "Prova"
    assert result.output["status"] == 200
    assert failures == ()
    assert descendants() == [], "the look released the page, and its browser with it"


FORM = (
    '<form method="post" action="/grazie"><input id="nome" name="nome">'
    '<button id="invia">Invia</button></form>' + REPORTS
)


async def test_a_click_that_worked_is_verified_by_the_page(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, FORM)})
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ELA"]],
        "click": "#invia",
        "expect_text": "Grazie ELA",
        "purpose": "x",
    }

    result = await BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )
    failures = await BrowserActVerifier(browser, 5.0).verify(
        [BROWSER_EXPECT_VISIBLE], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["gestures"] == 2
    assert "POST /grazie" in web.requests
    assert failures == ()
    assert web.events, "the page reports what it sees: the control of the next tests"


async def test_a_click_that_did_nothing_is_not_a_click_that_worked(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """§20. The only wait of the file: a text that never appears has no event, and the verifier
    is given a fifth of a second."""
    web = site(served, {"/": (200, {}, '<button id="invia" type="button">Invia</button>')})
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [],
        "click": "#invia",
        "expect_text": "Grazie",
        "purpose": "x",
    }

    result = await BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )
    (failure,) = await BrowserActVerifier(browser, 0.2).verify(
        [BROWSER_EXPECT_VISIBLE], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED
    assert failure.code == BROWSER_EXPECT_MISSING


# ----------------------------------------------------------------------------------------
# The boundary: a redirect it admits is followed and read
# ----------------------------------------------------------------------------------------


async def test_a_read_follows_a_redirect_on_the_same_site_and_reads_where_it_lands(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """Review of 2026-09-30, 1c: the document is fetched by the route without following redirects
    (ADR 0052 §6), so a redirect the boundary admits must still be followed — otherwise «follows
    only the admitted ones» and «follows none» look the same from the tests of the refusal."""
    web = site(
        served,
        {
            "/": (302, {"Location": "/dopo"}, ""),
            "/dopo": (200, {}, "<title>Dopo</title><h1>Arrivato</h1>"),
        },
    )
    arguments = {"site": "sito0.example", "path": "/", "selector": "h1", "purpose": "x"}

    result = await BrowserReadTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ), arguments, FakeStop()
    )
    failures = await BrowserReadVerifier(browser, 5.0).verify(
        [BROWSER_TEXT_MATCHES], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["address"] == web.origin + "/dopo"
    assert result.output["text"] == "Arrivato"
    assert web.requests == ["GET /", "GET /dopo"]
    assert failures == ()


async def test_a_read_follows_a_redirect_to_another_declared_site(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """The boundary of a read is every declared site (ADR 0052 §6)."""
    other = site(served, {"/altro": (200, {}, "<title>Altro</title><h1>Sull'altro sito</h1>")})
    web = site(served, {"/": (302, {"Location": other.origin + "/altro"}, "")})
    arguments = {"site": "sito0.example", "path": "/", "selector": "h1", "purpose": "x"}

    result = await BrowserReadTool(browsing(web, other), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ), arguments, FakeStop()
    )
    failures = await BrowserReadVerifier(browser, 5.0).verify(
        [BROWSER_TEXT_MATCHES], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["address"] == other.origin + "/altro"
    assert result.output["text"] == "Sull'altro sito"
    assert (web.requests, other.requests) == (["GET /"], ["GET /altro"])
    assert failures == ()


async def test_an_action_follows_a_redirect_on_its_site_to_the_form(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(served, {"/": (302, {"Location": "/modulo"}, ""), "/modulo": (200, {}, FORM)})
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ELA"]],
        "click": "#invia",
        "expect_text": "Grazie ELA",
        "purpose": "x",
    }

    result = await BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )
    failures = await BrowserActVerifier(browser, 5.0).verify(
        [BROWSER_EXPECT_VISIBLE], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["gestures"] == 2
    assert web.requests == ["GET /", "GET /modulo", "POST /grazie"]
    assert failures == ()


async def test_a_form_answered_with_a_303_is_followed_to_its_page(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """Post/Redirect/Get: the POST goes through the route like any navigation — the route fetches
    it with its body —, and the ``303`` it answers is followed with a ``GET``, on the same site."""
    web = site(
        served,
        {
            "/": (200, {}, FORM.replace('action="/grazie"', 'action="/invia"')),
            "/invia": (303, {"Location": "/ricevuto"}, ""),
            "/ricevuto": (200, {}, "<p>Modulo ricevuto</p>"),
        },
    )
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ELA"]],
        "click": "#invia",
        "expect_text": "Modulo ricevuto",
        "purpose": "x",
    }

    result = await BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )
    failures = await BrowserActVerifier(browser, 5.0).verify(
        [BROWSER_EXPECT_VISIBLE], arguments, result
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert web.requests == ["GET /", "POST /invia", "GET /ricevuto"]
    assert web.bodies == ["nome=ELA"], "sent once, with its body"
    assert failures == ()


# ----------------------------------------------------------------------------------------
# The boundary: a navigation off it is not sent
# ----------------------------------------------------------------------------------------


async def test_a_redirect_off_the_boundary_is_not_followed_and_nothing_reaches_the_other(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    other = site(served, {"/": (200, {}, "<p>altrove</p>")})
    web = site(served, {"/": (302, {"Location": other.origin + "/?chiave=segreta"}, "")})

    opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())

    assert opened.left is not None and origin_of(opened.left) == other.origin
    assert other.requests == [], "the request was never sent"
    await browser.close(opened.page)


async def test_a_form_that_sends_to_another_site_is_not_sent(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """Decision 13: an action acts on the site of the question and no other."""
    other = site(served, {})
    web = site(
        served,
        {
            "/": (
                200,
                {},
                f'<form method="post" action="{other.origin}/x"><button id="b">B</button></form>',
            )
        },
    )
    names = browsing(web, other)
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [],
        "click": "#b",
        "expect_text": "ok",
        "purpose": "x",
    }

    result = await BrowserActTool(names, browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )

    assert result.error is not None and result.error.code == LEFT_SITE
    assert other.requests == []


# ----------------------------------------------------------------------------------------
# No gesture when the page is not the plan's (criterion 7)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("page", "code"),
    [
        ('<input id="nome"><button id="invia">Invia</button>', ELEMENT_MISSING),
        ('<input id="nome" type="password"><button id="altro">Invia</button>', SECRET_FIELD),
        (
            '<input id="nome" autocomplete="cc-number"><button id="altro">Invia</button>',
            SECRET_FIELD,
        ),
    ],
)
async def test_nothing_is_touched_when_the_page_is_not_the_plan_s(
    browser: PlaywrightBrowser, served: list[Site], page: str, code: str
) -> None:
    """The wrong element **last**, after the field: a check made element by element would fill the
    field before finding out, and the page would report it."""
    web = site(served, {"/": (200, {}, page + REPORTS)})
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ELA"]],
        "click": "#manca" if code == ELEMENT_MISSING else "#altro",
        "expect_text": "ok",
        "purpose": "x",
    }

    result = await BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), arguments, FakeStop()
    )

    assert result.error is not None and result.error.code == code
    assert web.events == []
    assert [line for line in web.requests if line.startswith("POST")] == []


# ----------------------------------------------------------------------------------------
# An empty profile for every page
# ----------------------------------------------------------------------------------------


async def test_a_cookie_does_not_pass_from_one_page_to_the_next(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(
        served,
        {
            "/set": (200, {"Set-Cookie": "sessione=aperta; Path=/"}, "<p>set</p>"),
            "/check": (200, {}, "<p>check</p>"),
        },
    )
    allowed = boundary(frozenset({web.origin}))

    first = await browser.open(web.origin + "/set", allowed, FakeStop())
    await browser.close(first.page)
    second = await browser.open(web.origin + "/check", allowed, FakeStop())
    await browser.close(second.page)

    assert web.cookies == ["", ""]


# ----------------------------------------------------------------------------------------
# What the adapter reports, and what it leaves behind
# ----------------------------------------------------------------------------------------


async def test_a_site_that_does_not_answer_is_unreachable_and_leaves_nothing(
    browser: PlaywrightBrowser,
) -> None:
    closed = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    address = f"http://127.0.0.1:{closed.server_address[1]}/"
    closed.server_close()

    with pytest.raises(SiteUnreachable):
        await browser.open(address, lambda url: True, FakeStop())

    assert descendants() == []


async def test_a_page_closed_leaves_no_process_when_the_close_returns(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opened = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    assert descendants(), "a driver and a browser run while the page is open"

    await browser.close(opened.page)

    assert descendants() == []
    with pytest.raises(PageGone):
        await browser.text(opened.page, None)


async def test_the_stop_signal_closes_every_page_and_stops_what_runs(served: list[Site]) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = PlaywrightBrowser(stopping, environment={}, kept=Kept(), system=SYSTEM)
    opened = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    watching = browser._watching  # noqa: SLF001 — the task the signal wakes
    assert watching is not None

    stopping.set()
    await watching

    assert descendants() == []
    with pytest.raises(BrowserStopped):
        await browser.text(opened.page, None)
    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", lambda url: True, FakeStop())


# ----------------------------------------------------------------------------------------
# From the moment ELA's stop is raised nothing leaves, whenever that moment is (M13.4c)
# ----------------------------------------------------------------------------------------


class RaisedRightAfterTheFirstLook(asyncio.Event):
    """ELA's stop, raised by itself the instant after somebody first looks at it.

    The window of the defect, built as an event and not as a time: ``open`` looks at the stop
    once, at its beginning, and then starts a driver, a browser, a context and a page before that
    page is in the adapter's table. A stop raised in between found the table empty — the task that
    closes every page woke, closed nothing and ended — and the page came after it. Measured on
    2026-10-10 at 20, 80, 150 and 220 ms: each time ``open`` returned a page, and a form was sent.
    """

    def __init__(self) -> None:
        super().__init__()
        self._looked = False

    def is_set(self) -> bool:
        seen = super().is_set()
        if not self._looked:
            self._looked = True
            self.set()
        return seen


class RaisesTheStopOfElaWhenListenedTo(FakeStop):
    """A task's stop that is not raised — and, the instant the adapter listens to it, raises
    **ELA's**: the last instant before the site sees anything."""

    def __init__(self, stopping: asyncio.Event) -> None:
        super().__init__()
        self._stopping = stopping

    def listen(self, where: str) -> None:
        super().listen(where)
        self._stopping.set()


def stoppable(stopping: asyncio.Event) -> PlaywrightBrowser:
    return PlaywrightBrowser(stopping, environment={}, kept=Kept(), system=SYSTEM)


async def test_a_stop_of_ela_raised_while_the_browser_starts_opens_no_page_and_sends_nothing(
    served: list[Site], nothing_left_behind: None
) -> None:
    """Whoever puts a page in the table after the stop closes it: nobody else will. No waiting for
    the task that closes every page — it may have come and gone already."""
    web = site(served, {"/": (200, {}, FORM)})
    browser = stoppable(RaisedRightAfterTheFirstLook())
    at_the_gate: list[str] = []

    def admitted(address: str) -> bool:
        at_the_gate.append(address)
        return True

    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", admitted, FakeStop())

    assert at_the_gate == [], (
        "the navigation was handed to the driver after the stop: it is the gate that stopped it, "
        "not the opening"
    )
    assert web.requests == [], "the site saw a navigation after ELA had begun to stop"
    assert descendants() == []


async def test_what_an_opening_closes_after_the_stop_is_closed_before_the_stop_is_done(
    served: list[Site], nothing_left_behind: None
) -> None:
    """Decision 26, at the instant it is hardest: the stop is raised while the browser starts, so
    the task that closes every page finds nothing yet; the opening then closes what it started —
    and its caller is cancelled right there, so that closing is nobody's to wait for. The stop is
    not done with the browser until it has ended."""
    web = site(served, {"/": (200, {}, FORM)})
    browser = stoppable(RaisedRightAfterTheFirstLook())
    born = asyncio.Event()
    carrying = browser._carried  # noqa: SLF001 — where the adapter takes a closing as its own

    def carried(work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        born.set()
        return carrying(work)

    browser._carried = carried  # type: ignore[method-assign]  # noqa: SLF001
    opening = asyncio.create_task(browser.open(web.origin + "/", lambda url: True, FakeStop()))
    await born.wait()
    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening
    watching = browser._watching  # noqa: SLF001 — the task the signal wakes
    assert watching is not None

    await watching

    assert browser._closing == set()  # noqa: SLF001
    assert descendants() == []


async def test_a_stop_of_ela_raised_at_the_last_listening_sends_nothing(
    served: list[Site], nothing_left_behind: None
) -> None:
    web = site(served, {"/": (200, {}, FORM)})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    stop = RaisesTheStopOfElaWhenListenedTo(stopping)

    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", lambda url: True, stop)

    assert stop.listened == [NAVIGATION]
    assert web.requests == []
    assert descendants() == []


async def test_a_stop_of_ela_raised_while_a_navigation_is_at_the_gate_lets_nothing_through(
    served: list[Site], nothing_left_behind: None
) -> None:
    """The navigation had left the page and was at the adapter's route when ELA began to stop:
    the boundary admits it, and the gate does not send it."""
    web = site(served, {"/": (200, {}, FORM)})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    asked: list[str] = []

    def admitted_while_ela_stops(address: str) -> bool:
        asked.append(address)
        stopping.set()
        return True

    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", admitted_while_ela_stops, FakeStop())

    assert asked == [web.origin + "/"], "the navigation did reach the gate"
    assert web.requests == []


async def test_after_the_stop_of_ela_no_gesture_reaches_a_page_that_is_still_open(
    served: list[Site], nothing_left_behind: None
) -> None:
    """The stop is raised and, in the same turn of the loop — before the task that closes every
    page has run —, a fill and a click are asked of a page that is still in the table.

    **What is asserted is what the adapter hands to the driver**, read where every gesture of the
    adapter passes — ``page.locator`` —, because what reaches the site cannot tell: the task that
    closes the page gets there before the driver, and the gate lets nothing through anyway. The
    day a gesture stops passing through ``locator`` the control before the stop fails."""
    web = site(served, {"/": (200, {}, FORM)})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    opened = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    before = list(web.requests)
    page = browser._pages[opened.page].page  # noqa: SLF001 — the page as the driver holds it
    handed: list[str] = []
    locating = page.locator

    def handed_to_the_driver(selector: str) -> object:
        handed.append(selector)
        return locating(selector)

    page.locator = handed_to_the_driver  # type: ignore[method-assign, assignment]
    assert await browser.count(opened.page, "#nome") == 1
    assert handed == ["#nome"], "the control: before the stop, what the adapter asks is seen here"

    stopping.set()
    with pytest.raises(BrowserStopped):
        await browser.fill(opened.page, "#nome", "ELA")
    with pytest.raises(BrowserStopped):
        await browser.click(opened.page, "#invia")
    watching = browser._watching  # noqa: SLF001 — the task the signal wakes
    assert watching is not None
    await watching

    assert handed == ["#nome"], "a gesture was handed to the driver after ELA had begun to stop"
    assert web.requests == before
    assert descendants() == []


async def test_a_stopped_task_leaves_before_the_navigation_and_the_site_sees_nothing(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """The adapter's own listening (M6.3c, ADR 0054 §3): the page is made, the stop is heard
    before ``goto``, and the request never leaves — the site counts no request, and the browser
    started for the page is gone when ``open`` raises."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stop = FakeStop(stopped=True)

    with pytest.raises(ToolStopped) as caught:
        await browser.open(web.origin + "/", lambda url: True, stop)

    assert caught.value.where == NAVIGATION
    assert stop.listened == [NAVIGATION]
    assert web.requests == []
    assert descendants() == []


async def test_a_task_stopped_right_after_the_navigation_is_listened_to_reads_the_page(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """The other side: past the listening the request leaves, and the page is the site's."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stop = FakeStop(after=NAVIGATION)

    opened = await browser.open(web.origin + "/", lambda url: True, stop)

    assert stop.is_set()
    assert opened.status == 200
    assert web.requests == ["GET /"]
    await browser.close(opened.page)


# ----------------------------------------------------------------------------------------
# A cancellation leaves no browser nobody holds (M13.4b)
# ----------------------------------------------------------------------------------------


async def closings(browser: PlaywrightBrowser) -> None:
    """Wait for what the adapter is still closing: its own tasks, never a time (ADR 0006 §13)."""
    await asyncio.gather(*list(browser._closing))  # noqa: SLF001 — the closings it carries


NOT_YET = (
    '<form method="post" action="/grazie"><input id="nome" name="nome" disabled>'
    '<button id="invia">Invia</button></form>'
)
"""A form whose field cannot be written yet: Playwright's ``fill`` waits for it, and that wait is
what «a gesture in flight» is here — a fact of the page, not a time."""


async def test_a_tool_cancelled_after_the_opening_leaves_no_process_when_the_cancellation_is_back(
    browser: PlaywrightBrowser, served: list[Site], nothing_left_behind: None
) -> None:
    """The page was open, a gesture was in flight, and the task was cancelled: when the
    cancellation is back in the caller's hands the kernel knows no process of that page.

    «In flight» is built by the order of things and not by the page: the cancellation is given in
    the same turn of the loop in which the fill was handed to the driver, before any answer can
    come back. The field is ``disabled`` so that the fill would wait for as long as nobody cancels
    it — it keeps the test from depending on how fast a fill is, and is not what builds it."""
    web = site(served, {"/": (200, {}, NOT_YET)})
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ELA"]],
        "click": "#invia",
        "expect_text": "Grazie ELA",
        "purpose": "x",
    }
    reached = asyncio.Event()
    filling = browser.fill

    async def in_flight(page: str, selector: str, value: str) -> None:
        reached.set()
        await filling(page, selector, value)

    browser.fill = in_flight  # type: ignore[method-assign]
    tool = BrowserActTool(browsing(web), browser, CLOCK, FakeIdGenerator())
    running = asyncio.create_task(tool.execute(decision(BROWSER_ACT), arguments, FakeStop()))
    await reached.wait()
    assert descendants(), "a driver and a browser run while the fill waits"

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running

    assert descendants() == []
    assert web.requests == ["GET /"], "nothing was sent"


async def test_a_close_cancelled_halfway_still_runs_to_its_end(
    browser: PlaywrightBrowser, served: list[Site], nothing_left_behind: None
) -> None:
    """``close`` takes the page out of the table and then waits for three closings: cancelled
    there, it used to leave the browser running where nothing would find it again — not even
    ELA's stop. The closing is the adapter's, and ends whoever was waiting for it."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opened = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    closing = asyncio.create_task(browser.close(opened.page))
    await asyncio.sleep(0)  # one turn of the loop: the close has begun, and is waiting

    closing.cancel()
    with pytest.raises(asyncio.CancelledError):
        await closing
    await closings(browser)

    assert descendants() == []


async def test_an_opening_cancelled_while_the_driver_starts_leaves_no_driver(
    browser: PlaywrightBrowser, served: list[Site], nothing_left_behind: None
) -> None:
    """The driver is started before anything can close it: an opening cancelled in its first turn
    used to leave a ``node`` nobody held, which outlived ELA's stop (measured at every delay up to
    140 ms). What was started is stopped when its start ends."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opening = asyncio.create_task(browser.open(web.origin + "/", lambda url: True, FakeStop()))
    await asyncio.sleep(0)  # one turn of the loop: the opening has begun to start its driver

    opening.cancel()
    with pytest.raises(asyncio.CancelledError):
        await opening
    await closings(browser)

    assert descendants() == []
    assert web.requests == []


async def test_after_the_stop_of_ela_no_closing_is_left_running(
    served: list[Site], nothing_left_behind: None
) -> None:
    """Decision 26: a closing nobody waits for any more — its caller was cancelled — is still
    carried to its end before the stop is done with the browser.

    **One page, and no other**: with a second one the stop would wait for that page's closing,
    and the orphan would end by itself in the meantime — green for whoever comes first (the review
    of the repair measured it: 24 rounds in 26 without the wait this asserts)."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = PlaywrightBrowser(stopping, environment={}, kept=Kept(), system=SYSTEM)
    only = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    watching = browser._watching  # noqa: SLF001 — the task the signal wakes
    assert watching is not None
    orphan = asyncio.create_task(browser.close(only.page))
    await asyncio.sleep(0)
    orphan.cancel()
    with pytest.raises(asyncio.CancelledError):
        await orphan

    stopping.set()
    await watching

    assert browser._closing == set()  # noqa: SLF001
    assert descendants() == []


# ----------------------------------------------------------------------------------------
# What ELA's close waits for: nothing of the adapter runs when it returns (M13.4e)
# ----------------------------------------------------------------------------------------


class Grace:
    """How long ELA's close waits for the browser, as an event the test raises — never a time.
    ``asked`` is set when the adapter starts to wait: the browser has not closed by itself."""

    def __init__(self) -> None:
        self.asked = asyncio.Event()
        self.over = asyncio.Event()
        self.dropped = False

    async def __call__(self) -> None:
        self.asked.set()
        try:
            await self.over.wait()
        except asyncio.CancelledError:
            self.dropped = True
            raise


def known(pid: int) -> bool:
    """Whether the kernel still has ``pid`` in its table — running, stopped, or ended and not yet
    collected. What ``settle`` promises of what it killed is that it is not."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def profile_of(pids: list[int]) -> Path:
    """The temporary profile of a browser, read from its own arguments: the folder Playwright
    makes for it and takes away when the browser closes."""
    said = subprocess.run(
        ["/bin/ps", "-ww", "-o", "args=", "-p", ",".join(map(str, pids))],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (folder,) = set(re.findall(r"--user-data-dir=(\S+)", said))
    return Path(folder)


async def test_settled_after_the_stop_nothing_of_the_adapter_runs_and_nothing_was_killed(
    served: list[Site], nothing_left_behind: None
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    await browser.open(web.origin + "/", lambda url: True, FakeStop())
    await browser.open(web.origin + "/", lambda url: True, FakeStop())
    grace = Grace()

    stopping.set()
    killed = await browser.settle(grace)
    await asyncio.sleep(0)

    assert killed == ()
    assert descendants() == []
    assert browser._pages == {} and browser._closing == set()  # noqa: SLF001
    assert grace.asked.is_set() and grace.dropped, "the grace nobody needed is not left waiting"


@pytest.mark.parametrize("frozen", ["the driver", "the browser", "the driver and the browser"])
async def test_a_browser_that_does_not_close_is_killed_when_the_grace_is_over(
    frozen: str, served: list[Site], nothing_left_behind: None
) -> None:
    """A browser that does not close, built with an event: a ``SIGSTOP``. To its driver, and the
    closing ELA's stop begins is a call of Playwright's that never comes back. **To the browser
    itself**, and nothing but a kill of its own takes it away — a browser whose driver dies goes
    with its pipe, but not one that is stopped (the review of the repair: with only the driver
    frozen this was green without killing the browser at all).

    When the grace — an event too — is over, what the adapter started is killed and named; **the
    kernel knows none of it any more** when ``settle`` returns — the driver is this process's
    child, and nobody else would collect it —; and the temporary profile, which a browser takes
    away when it closes and a killed one leaves, is taken away by the adapter."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    await browser.open(web.origin + "/", lambda url: True, FakeStop())
    before = started()
    (driver,) = drivers()
    theirs = [pid for pid, _ in before if pid != driver]
    profile = profile_of(theirs)
    assert profile.is_dir() and profile.name.startswith("playwright_chromiumdev_profile-")
    for pid in [driver] * ("driver" in frozen) + theirs * ("browser" in frozen):
        os.kill(pid, signal.SIGSTOP)
    grace = Grace()

    try:
        stopping.set()
        settling = asyncio.create_task(browser.settle(grace))
        await grace.asked.wait()
        assert not settling.done(), "the browser has not closed, and nothing has been killed yet"
        assert all(known(pid) for pid, _ in before)
        grace.over.set()
        async with asyncio.timeout(30):  # the test's guard: an adapter that kills nothing fails
            killed = await settling

        assert killed.count("node") == 1, "the driver, called by the adapter what it is everywhere"
        assert len(killed) == 1 + len(theirs), "and every process the driver had started"
        assert all("/" not in name for name in killed), "names, never a path"
        assert [name for pid, name in before if known(pid)] == []
        assert not profile.exists(), "a killed browser leaves its profile: the adapter removes it"
        assert browser._pages == {} and browser._closing == set()  # noqa: SLF001
        watching = browser._watching  # noqa: SLF001 — the task the stop wakes
        assert watching is not None and watching.done()
    finally:
        # Only after a red run: a stopped browser whose driver was killed is nobody's descendant
        # any more — ``nothing_left_behind`` cannot see it — and stays stopped for ever (found on
        # this machine, 2026-10-10). Killed here by the pids this test froze, and nothing else.
        for pid, _ in before:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:  # the green run: the adapter has killed it already
                continue


async def test_settled_returns_only_when_the_task_the_stop_woke_has_ended(
    served: list[Site], nothing_left_behind: None
) -> None:
    """After the kill the pipes are closed and every call in flight fails — but only once the loop
    has run: ``settle`` waits for the task the stop woke, and does not return on having killed.
    Here the kill is the test's, and gives the loop to nobody: what is asserted is not held by how
    long the real one happens to take (the review of the repair)."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    await browser.open(web.origin + "/", lambda url: True, FakeStop())
    (driver,) = drivers()
    os.kill(driver, signal.SIGSTOP)

    async def killed_without_a_wait() -> tuple[str, ...]:
        for pid, _ in started():
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:  # gone on its own once its parent was killed
                continue
        return ("node",)

    browser._kill = killed_without_a_wait  # type: ignore[method-assign]  # noqa: SLF001
    grace = Grace()

    stopping.set()
    settling = asyncio.create_task(browser.settle(grace))
    await grace.asked.wait()
    grace.over.set()
    async with asyncio.timeout(30):
        assert await settling == ("node",)

    watching = browser._watching  # noqa: SLF001 — the task the stop wakes
    assert watching is not None and watching.done()
    assert browser._pages == {} and browser._closing == set()  # noqa: SLF001


async def test_a_browser_is_not_settled_before_the_stop() -> None:
    """The task that closes every page wakes on the stop: waiting for it without the stop would be
    waiting out the grace for nothing, and then killing a browser nobody had asked to close."""
    browser = stoppable(asyncio.Event())

    with pytest.raises(RuntimeError, match="after ELA's stop"):
        await browser.settle(Grace())


async def test_a_browser_that_never_opened_a_page_is_settled_at_once_and_starts_nothing() -> None:
    stopping = asyncio.Event()
    browser = stoppable(stopping)
    grace = Grace()

    stopping.set()
    killed = await browser.settle(grace)

    assert killed == ()
    assert not grace.asked.is_set()
    assert descendants() == []


async def test_the_process_of_a_driver_is_read_where_playwright_keeps_it(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    """The second private fact of the engine the adapter reads (the first is the message of a
    missing executable): where Playwright keeps the process of its driver. The day it moves, this
    fails — and an adapter that could not read it would have nothing to kill."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    assert browser._driver_pids() == []  # noqa: SLF001

    await browser.open(web.origin + "/", lambda url: True, FakeStop())

    assert drivers(), "the control: this worker has started a driver"
    assert browser._driver_pids() == drivers()  # noqa: SLF001


def test_what_ps_says_is_read_by_parent_and_a_line_it_cannot_place_is_left_out() -> None:
    """What the adapter kills past the grace is found here: a driver's own tree and nothing beside
    it. The names are the two a kernel gives — a path on macOS, of which the last part is kept;
    fifteen characters on Linux, where the driver is called by its main thread —, and a line that
    is not a process is skipped instead of breaking ELA's close."""
    said = (
        "  100     1 /usr/sbin/somebody-else\n"
        "  200    50 MainThread\n"
        "  201   200 /cache/chrome-headless-shell\n"
        "  202   201 chrome-headless\n"
        "  203   201 Google Chrome Helper (Renderer)\n"
        "  300     1 chrome-headless\n"
        "garbage\n"
        "  400   not-a-pid name\n"
    )

    table = _listed(said)

    assert table[201] == (200, "chrome-headless-shell")
    assert table[203] == (201, "Google Chrome Helper (Renderer)")
    assert sorted(table) == [100, 200, 201, 202, 203, 300]
    assert sorted(pid for pid, _ in _descendants(200, table)) == [201, 202, 203]
    assert _descendants(100, table) == [], "what somebody else started is nobody's to kill here"


def test_the_name_of_a_process_cannot_write_a_row_of_the_table_the_adapter_kills_from() -> None:
    """A name is whatever its process says it is, and ``ps`` prints it as it is — a line separator
    of Unicode included. Read line by line as Python reads lines, a process called
    ``x<U+2028>999 200 y`` would add a row: a process that is nobody's, listed as started by a
    driver, and killed with it (the review of the repair, measured). The table is split where
    ``ps`` ends its lines and nowhere else."""
    said = (
        "  200    50 MainThread\n"
        "  201   200 x\u2028999 200 injected\n"
        "  202   200 y\u2029998 200 z\n"
    )

    table = _listed(said)

    assert sorted(table) == [200, 201, 202]
    assert [pid for pid, _ in _descendants(200, table)] == [201, 202]


async def test_what_was_killed_is_waited_for_until_the_kernel_knows_it_no_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process that was killed and that nobody has collected is still in the kernel's table:
    built here with a child of the test's own, killed and not waited for. The adapter's wait does
    not end while it is there, and ends once it is collected — an event, the collecting. And it
    has a deadline of its own: with none left it returns, with the process still there."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
    try:
        child.kill()
        waiting = asyncio.create_task(_gone([child.pid]))
        for _ in range(5):
            await asyncio.sleep(0)
        assert known(child.pid) and not waiting.done()

        monkeypatch.setattr("ela.infrastructure.machine.browser.GONE_SECONDS", 0.0)
        await _gone([child.pid])
        assert known(child.pid), "the deadline, not the collecting, ended this wait"
    finally:
        child.wait()
    await waiting
    assert not known(child.pid)


def test_only_a_temporary_profile_of_playwright_s_is_taken_away_after_a_kill() -> None:
    """What the adapter removes after it killed a browser is read from the browser's own
    arguments, and kept only if it is the folder Playwright makes for a browser of one page: not a
    profile somebody chose, not a relative path, and a path with a space in it whole."""
    said = (
        "/cache/chrome-headless-shell --no-sandbox "
        "--user-data-dir=/tmp/playwright_chromiumdev_profile-una --remote-debugging-pipe\n"
        "/cache/chrome-headless-shell --type=renderer "
        "--user-data-dir=/tmp/playwright_chromiumdev_profile-una --lang=en-US\n"
        "/cache/chrome --user-data-dir=/Users/you/Library/A profile --flag\n"
        "/cache/chrome --user-data-dir=playwright_chromiumdev_profile-relative\n"
        "/cache/chrome --user-data-dir=/var/a b/playwright_chromiumdev_profile-due parti --x\n"
    )

    assert _temporary_profiles(said) == [
        Path("/tmp/playwright_chromiumdev_profile-una"),
        Path("/var/a b/playwright_chromiumdev_profile-due parti"),
    ]


def test_a_table_that_loops_is_walked_once() -> None:
    """A parent that is its own grandchild is not something a kernel says, and is not something
    the loop of ELA's close may hang on."""

    class Looked(dict[int, tuple[int, str]]):
        """The table, counting how often it is gone through: the test's guard. A walk that never
        ends is stopped here, by the table itself — nothing else can stop a loop that waits for
        nothing, and left alone it would fill the memory of whoever ran the suite."""

        looks = 0

        def items(self) -> Any:
            self.looks += 1
            if self.looks > len(self):
                # Raised, not asserted: an ``assert`` here is rewritten to describe ``self``, and
                # describing a table goes through it again.
                raise AssertionError("the walk of a table that loops did not end")
            return super().items()

    table = Looked({1: (2, "a"), 2: (1, "b"), 3: (2, "c")})

    assert sorted(_descendants(1, table)) == [(2, "b"), (3, "c")]


async def test_an_adapter_that_cannot_read_the_process_of_its_driver_opens_nothing(
    browser: PlaywrightBrowser, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative of the fact above: the day the process is not where it is read, an opening
    fails and says so, and stops the driver it had started — an adapter that could not kill what
    it starts does not start it."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    monkeypatch.setattr("ela.infrastructure.machine.browser._process_of", lambda manager: None)

    with pytest.raises(BrowserFailed, match="the process of the browser's driver cannot be read"):
        await browser.open(web.origin + "/", lambda url: True, FakeStop())

    assert web.requests == []
    assert descendants() == []


async def test_a_page_handed_over_and_never_looked_at_is_closed_at_its_deadline(
    served: list[Site],
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    kept = Kept()
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=kept, system=SYSTEM)
    opened = await browser.open(web.origin + "/", lambda url: True, FakeStop())
    await browser.keep(opened.page)
    deadline = browser._pages[opened.page].kept  # noqa: SLF001 — the task the deadline wakes
    assert deadline is not None

    kept.due.set()
    await deadline

    assert descendants() == []
    with pytest.raises(PageGone):
        await browser.glance(opened.page, selector=None, expect=None, seconds=1.0)


async def test_a_missing_browser_is_said_before_any_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "nessun-browser"))
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=Kept(), system=SYSTEM)

    assert await browser.installed() is False
    with pytest.raises(BrowserNotInstalled):
        await browser.open("http://127.0.0.1:9/", lambda url: True, FakeStop())
    assert descendants() == []


async def test_whether_the_shell_is_there_is_read_where_playwright_launches_it_starting_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 2 of the review of 2026-09-30: before the question, «the shell is installed» is
    known from the executable, without launching the browser. **The place is Playwright's**: with an
    empty folder of browsers Playwright names it in its own error, and an empty file put there makes
    the answer «installed» — an empty file cannot be started, so the answer was read, not launched.
    The day Playwright moves the shell, this test fails instead of ELA saying «not installed»."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    async with async_playwright() as playwright:
        with pytest.raises(PlaywrightError) as missing:
            await playwright.chromium.launch(headless=True)
    (named,) = re.findall(r"Executable doesn't exist at (\S+)", str(missing.value))
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=Kept(), system=SYSTEM)
    assert await browser.installed() is False

    Path(named).parent.mkdir(parents=True)
    Path(named).touch()

    assert await browser.installed() is True
    assert descendants() == []


async def test_on_a_system_whose_shell_it_cannot_place_it_says_it_did_not_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review of the summary, 2026-09-30, decision 1: the system is handed to the adapter by the
    composition, and here by the test — never read from the machine the suite runs on.

    **Nor is the folder of browsers**: the system places the shell only where nobody declared a
    folder, so the test takes the declaration away (M14.1). A machine that sets
    ``PLAYWRIGHT_BROWSERS_PATH`` — the container of the session of 2026-10-06 does — has said where
    to look, on any system, and the test below holds that half."""
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=Kept(), system="Plan 9")

    with pytest.raises(BrowserUnsupported) as unsupported:
        await browser.installed()

    assert "Plan 9" in str(unsupported.value)
    assert descendants() == []


@pytest.mark.parametrize("declared", ["a folder", "0"])
async def test_on_any_system_a_declared_folder_of_browsers_is_where_it_looks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, declared: str
) -> None:
    """The other half (M14.1, measured on 2026-10-06): Playwright's driver reads
    ``PLAYWRIGHT_BROWSERS_PATH`` from **ELA's process environment** — the client copies
    ``os.environ`` into the driver it starts, and the ``env`` of the launch is the browser's, not
    the driver's: declared only there, the shell installed in that folder is not found. So
    ``installed()`` reads the process environment, and a declared folder is the place to look
    whatever the system. Both values: a folder of its own, and ``0``, the folder inside the
    package — here a package of the test's, so that nothing is written into the installed one."""
    if declared == "0":
        package = tmp_path / "playwright" / "driver" / "package"
        package.mkdir(parents=True)
        installed = Path(playwright.__file__).parent / "driver" / "package" / "browsers.json"
        (package / "browsers.json").write_bytes(installed.read_bytes())
        monkeypatch.setattr(playwright, "__file__", str(tmp_path / "playwright" / "__init__.py"))
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "0")
    else:
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "browsers"))
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=Kept(), system="Plan 9")
    folder = shell_folder(os.environ, "Plan 9")
    assert folder is not None and folder.is_relative_to(tmp_path)

    assert await browser.installed() is False
    shell = folder / "chrome-headless-shell-plan9" / "chrome-headless-shell"
    shell.parent.mkdir(parents=True)
    shell.touch()

    assert await browser.installed() is True
    assert descendants() == []


# ----------------------------------------------------------------------------------------
# A Ctrl-C to ELA's process group does not close the page (M5-bis)
# ----------------------------------------------------------------------------------------

HOLDER = r"""
import asyncio, platform, signal, sys
from ela.infrastructure.machine import PlaywrightBrowser
from ela.testing.fakes import FakeStop

async def main() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # uvicorn keeps serving what is in flight
    browser = PlaywrightBrowser(
        asyncio.Event(), environment={}, kept=asyncio.Event().wait, system=platform.system()
    )
    opened = await browser.open(sys.argv[1], lambda url: True, FakeStop())
    print("ready", flush=True)
    await asyncio.get_running_loop().run_in_executor(None, sys.stdin.readline)
    try:
        print("usable" if await browser.title(opened.page) is not None else "none", flush=True)
    except Exception as error:
        print(type(error).__name__, flush=True)
    await browser.close(opened.page)

asyncio.run(main())
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a process group and SIGINT are POSIX's")
def test_a_sigint_to_the_process_group_does_not_close_the_page(served: list[Site]) -> None:
    web = site(served, {"/": (200, {}, "<title>t</title>")})
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, web.origin + "/"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    assert holder.stdin is not None and holder.stdout is not None
    try:
        assert holder.stdout.readline().strip() == "ready"
        os.killpg(holder.pid, signal.SIGINT)
        holder.stdin.write("look\n")
        holder.stdin.flush()
        assert holder.stdout.readline().strip() == "usable"
    finally:
        holder.wait(timeout=60)
