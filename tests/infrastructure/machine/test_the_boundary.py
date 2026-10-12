"""The boundary of the browser, **on the two real browsers** (M13.4f, ADR 0064).

Until M13.4f the gate fetched the first document of a navigation from the driver's process and
handed it to the page. Measured on 2026-10-12: it looked at **one** answer for each navigation,
so the second redirect of a chain left the boundary; it chose the cookies of a document beside
the browser, and answered by itself a question the browser asks another site; and no tool but
the login compared where the page **was** with the site of the question. The red tests of that
day are in ``test_what_the_gate_does_not_stop.py``, as they were written; here is the rest.

What these tests hold, with sites of this machine and never one of the world's:

* a request for a document of the main frame the boundary refuses **does not leave** — the hop
  of a redirect that keeps its ``POST``, a navigation in the history, a link that downloads;
* **of a page that is not the one ELA works on no document leaves**: not its navigation, not a
  link, not a form, not a frame written in it — however it was opened and however it was
  filled. What the first page has loaded in an empty page it opened **is a request of the first
  page**, and arrives as it would from its own document: the same cookies, nothing more;
* what leaves **is the browser's own**: the same names and the same values as with no gate at
  all, every frame of the page, and the question a browser asks another site first;
* **when in doubt nothing leaves**: a session that is not attached, an alert that tells nobody,
  a session that never answers, a judge that raises, a driver that dies, ELA's stop;
* **every use of a page asks the boundary where the page is**, before and after: what was read
  on a page that ended elsewhere is thrown away.

**A «nothing arrived» is asserted after an event** — what the gate decided of that request, kept
by :func:`judged` as it decides —, never after a time.

On every system the empty browser; on a Mac also the browser of the profile, each test with a
folder of its own under ``/tmp``, and nothing left on the machine.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from ela.domain import ExecutionStatus
from ela.infrastructure.machine import browser as adapter
from ela.infrastructure.machine.account import AccountChrome
from ela.infrastructure.machine.browser import PlaywrightBrowser, _descendants, _listed
from ela.permissions import BROWSER_ACT, BROWSER_READ
from ela.ports import BrowserFailed, BrowserStopped, Secret, SiteUnreachable
from ela.testing.fakes import FakeIdGenerator, FakeStop
from ela.tools.browser import (
    FAILED,
    LEFT_SITE,
    TIMEOUT,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
    boundary,
    origin_of,
)
from tests.browser_leftovers import running
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine.test_browser import CLOCK, Kept, Site, decision, site

served = shell.served
nothing_left_behind = shell.nothing_left_behind
profile = account.profile

ON_A_MAC = pytest.mark.skipif(
    account.SYSTEM != "Darwin", reason="the browser with the profile is Chrome for Testing on a Mac"
)
EMPTY, PROFILE = "the empty browser", "the browser of the profile"
ENVIRONMENT = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"}
HTML = [("Content-Type", "text/html; charset=utf-8")]
GIF = [("Content-Type", "image/gif")]
PIXEL = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)
LONG = 20.0
"""The bound of a wait for an event of a browser: past it the test fails, saying what it waited
for. Never the measure of anything."""


def empty(stopping: asyncio.Event | None = None, **more: str) -> PlaywrightBrowser:
    return PlaywrightBrowser(
        asyncio.Event() if stopping is None else stopping,
        environment={**ENVIRONMENT, **more},
        kept=Kept(),
        system=shell.SYSTEM,
    )


@pytest.fixture(params=[EMPTY, pytest.param(PROFILE, marks=ON_A_MAC)])
async def browser(request: pytest.FixtureRequest, profile: Path) -> AsyncIterator[Any]:
    """Each of the two browsers, closed by ELA's own closing whatever the test did."""
    made = empty() if request.param == EMPTY else account.chrome(profile)
    if not await made.installed():
        pytest.fail("the browser this test launches is not installed on this machine")
    yield made
    for page in list(made._pages):
        await made.close(page)


@pytest.fixture
async def with_the_profile(profile: Path) -> AsyncIterator[AccountChrome]:
    """The browser of the profile, for a test that is of it alone — closed like the other."""
    made = account.chrome(profile)
    yield made
    for page in list(made._pages):
        await made.close(page)


@pytest.fixture
def judged(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, bool]]:
    """What the gate decided of every request it was told of — its method, its address, and
    whether it leaves —, kept **as it decides**: a request the gate refused cannot leave after
    that, so this is the event a «nothing arrived» is asserted after."""
    seen: list[tuple[str, str, bool]] = []
    deciding = adapter._Gate._leaves

    async def kept(self: Any, event: dict[str, Any]) -> bool:
        leaves = await deciding(self, event)
        seen.append((event["request"]["method"], event["request"]["url"], leaves))
        return leaves

    monkeypatch.setattr(adapter._Gate, "_leaves", kept)
    return seen


async def until(look: Callable[[], Any], what: str) -> Any:
    """Wait for something a test can only see by looking, and say what it was if it never came."""
    deadline = asyncio.get_running_loop().time() + LONG
    while not (found := look()):
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"never happened within {LONG:g} s: {what}")
        await asyncio.sleep(0.02)
    return found


async def said_after(browser: Any, page: str, selector: str, waiting: str) -> str:
    """The text of an element once it is no longer what the page shows while it waits."""
    deadline = asyncio.get_running_loop().time() + LONG
    while (said := await browser.text(page, selector)) == waiting:
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"the page still said {waiting!r} after {LONG:g} s")
        await asyncio.sleep(0.02)
    return str(said)


async def decided(
    judged: list[tuple[str, str, bool]], address: str, *, leaves: bool
) -> tuple[str, str, bool]:
    """The gate's decision on the request for ``address``, once it is made."""

    def found() -> tuple[str, str, bool] | None:
        return next((one for one in judged if one[1].startswith(address)), None)

    one = await until(found, f"the gate was told of a request for {address}")
    assert one[2] is leaves, f"the gate {'let go' if one[2] else 'refused'} {one[0]} {one[1]}"
    return one


class Recording:
    """A site that answers any method, keeps what it received with its headers and its body, and
    can be told what to do before it answers."""

    def __init__(self, host: str = "127.0.0.1") -> None:
        self.pages: dict[tuple[str, str], tuple[int, list[tuple[str, str]], str | bytes]] = {}
        self.seen: list[tuple[str, list[tuple[str, str]], str]] = []
        self.before: Callable[[str], None] | None = None
        kept = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                path = self.path.split("?")[0]
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length).decode() if length else ""
                asked = f"{self.command} {self.path}"
                if path != "/favicon.ico":
                    kept.seen.append((asked, list(self.headers.items()), body))
                if kept.before is not None:
                    kept.before(asked)
                status, headers, page = kept.pages.get((self.command, path), (404, HTML, "no"))
                data = page if isinstance(page, bytes) else page.encode()
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_OPTIONS = _answer  # noqa: N815

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://{host}:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def requests(self) -> list[str]:
        return [asked for asked, _, _ in self.seen]

    def _one(self, asked: str) -> tuple[str, list[tuple[str, str]], str]:
        (found,) = [one for one in self.seen if one[0] == asked]
        return found

    def headers(self, asked: str) -> list[tuple[str, str]]:
        return self._one(asked)[1]

    def body(self, asked: str) -> str:
        return self._one(asked)[2]

    def cookies(self, asked: str) -> str:
        return next((value for name, value in self.headers(asked) if name == "Cookie"), "")

    async def arrived(self, asked: str) -> None:
        await until(lambda: asked in self.requests, f"the site received {asked}")

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def two(served: list[Site]) -> tuple[Recording, Recording]:
    """A site by its name and another by its address: two sites, for a browser. The first is
    the one inside the boundary of the tests that use them."""
    a, off = Recording("localhost"), Recording()
    served.extend([a, off])  # type: ignore[list-item] — closed with the others: they have ``close``
    return a, off


def only(*sites: Any) -> Callable[[str], bool]:
    return boundary(frozenset(one.origin for one in sites))


def everywhere(address: str) -> bool:
    return True


@asynccontextmanager
async def alone(made: Any, profile: Path) -> AsyncIterator[Any]:
    """A page of the same binary, launched with the options its adapter launches it with — on a
    folder prepared as the adapter prepares its own — and **with no gate at all**: the
    precondition of every «as the browser alone»."""
    async with async_playwright() as playwright:
        if isinstance(made, AccountChrome):
            other = account.chrome(profile.with_name("alone"))
            folder = await other._folder()
            await other._prepare(folder, driven=True)
            context = await playwright.chromium.launch_persistent_context(
                str(folder), **other._launch()
            )
            try:
                yield context.pages[0]
            finally:
                await context.close()
        else:
            launched = await playwright.chromium.launch(**made._launch())
            try:
                context = await launched.new_context(
                    accept_downloads=False, service_workers="block"
                )
                yield await context.new_page()
            finally:
                await launched.close()


# ----------------------------------------------------------------------------------------
# A document the boundary refuses does not leave: a kept POST, the history, a download
# ----------------------------------------------------------------------------------------

FORM = (
    '<form method="post" action="{}"><input name="chi" value="mario">'
    '<button id="go">B</button></form>'
)


@pytest.mark.parametrize("status", [307, 308])
async def test_a_redirect_that_keeps_the_post_is_followed_inside_and_refused_outside(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]], status: int
) -> None:
    """Decision 127. A redirect that keeps the method keeps the body: inside the boundary it
    arrives as the browser sends it; towards a site off the boundary neither the request nor
    what the form held leaves."""
    a, off = two(served)
    a.pages[("GET", "/in")] = (200, HTML, FORM.format("/send-in"))
    a.pages[("GET", "/out")] = (200, HTML, FORM.format("/send-out"))
    a.pages[("POST", "/send-in")] = (status, [("Location", "/taken")], "")
    a.pages[("POST", "/taken")] = (200, HTML, "<p>taken</p>")
    a.pages[("POST", "/send-out")] = (status, [("Location", off.origin + "/taken")], "")

    inside = await browser.open(a.origin + "/in", only(a), FakeStop())
    await browser.click(inside.page, "#go")
    arrived = await browser.text(inside.page, "p")
    await browser.close(inside.page)
    outside = await browser.open(a.origin + "/out", only(a), FakeStop())
    await browser.click(outside.page, "#go")
    method, _, _ = await decided(judged, off.origin + "/taken", leaves=False)

    assert arrived == "taken" and a.body("POST /taken") == "chi=mario"
    assert method == "POST", "the hop kept its method, and was judged with it"
    assert await browser.left(outside.page) == off.origin + "/taken"
    assert off.requests == [], "neither the request nor the body of the form left"


HISTORY = {
    ("GET", "/one"): (
        200,
        HTML,
        '<a id="next" href="/two">two</a><button id="fwd" onclick="history.forward()">f</button>',
    ),
    ("GET", "/two"): (200, HTML, '<button id="back" onclick="history.back()">b</button>'),
}


@pytest.mark.parametrize("towards", ["back", "forward"])
async def test_a_navigation_in_the_history_is_judged_like_any_other(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]], towards: str
) -> None:
    """Decision 127. The boundary of this test stops admitting an address the page has been at:
    going back to it, or forward to it, is a request for a document like any other."""
    a, _ = two(served)
    a.pages.update(HISTORY)
    closed: set[str] = set()
    opened = await browser.open(
        a.origin + "/one", lambda url: url.split("/", 3)[-1] not in closed, FakeStop()
    )
    await browser.click(opened.page, "#next")
    assert await browser.text(opened.page, "#back") == "b"
    click, refused = "#back", "one"
    if towards == "forward":
        await browser.click(opened.page, "#back")
        assert await browser.text(opened.page, "#fwd") == "f"
        click, refused = "#fwd", "two"
    before = list(a.requests)
    del judged[:]

    closed.add(refused)
    await browser.click(opened.page, click)
    await decided(judged, f"{a.origin}/{refused}", leaves=False)

    assert await browser.left(opened.page) == f"{a.origin}/{refused}"
    assert a.requests == before, "the way through the history was not sent"


async def test_a_link_that_downloads_from_another_site_sends_nothing_there(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]]
) -> None:
    """Decision 127: for the gate a download is a document of the main frame, like any other —
    refused off the boundary, and let go on the site, where the page stays what it was."""
    a, off = two(served)
    attached = [("Content-Type", "text/plain"), ("Content-Disposition", "attachment")]
    a.pages[("GET", "/")] = (200, HTML, f'<a id="go" download href="{off.origin}/file">x</a>')
    a.pages[("GET", "/own")] = (200, HTML, '<a id="go" href="/file">x</a><p>still here</p>')
    a.pages[("GET", "/file")] = (200, attached, "data")

    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await browser.click(opened.page, "#go")
    await decided(judged, off.origin + "/file", leaves=False)
    refused = await browser.left(opened.page)
    await browser.close(opened.page)
    own = await browser.open(a.origin + "/own", only(a), FakeStop())
    await browser.click(own.page, "#go")
    await a.arrived("GET /file")

    assert refused == off.origin + "/file" and off.requests == []
    assert await browser.text(own.page, "p") == "still here"


# ----------------------------------------------------------------------------------------
# What leaves is the browser's own
# ----------------------------------------------------------------------------------------


async def test_what_a_site_receives_through_the_gate_is_what_the_browser_alone_sends(
    browser: Any, profile: Path, served: list[Site]
) -> None:
    """Criterion 6: the same names and the same values, for a document asked by address, for
    the ``POST`` of a form and for the page after its redirect — and for a first request the
    same order too. *The order of the hop of a redirect is declared different (ADR 0064 §7).*"""
    a, _ = two(served)
    a.pages[("GET", "/")] = (200, HTML, FORM.format("/send"))
    a.pages[("POST", "/send")] = (302, [("Location", "/done")], "")
    a.pages[("GET", "/done")] = (200, HTML, "<p>done</p>")
    walk = ["GET /", "POST /send", "GET /done"]

    async with alone(browser, profile) as page:
        await page.goto(a.origin + "/")
        await page.locator("#go").click()
        await page.get_by_text("done").wait_for(timeout=LONG * 1000)
    bare = {asked: a.headers(asked) for asked in walk}
    del a.seen[:]
    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await browser.click(opened.page, "#go")
    assert await browser.text(opened.page, "p") == "done"
    gated = {asked: a.headers(asked) for asked in walk}

    assert gated["GET /"] == bare["GET /"], "a first address: the same, in the same order"
    assert gated["POST /send"] == bare["POST /send"]
    assert sorted(gated["GET /done"]) == sorted(bare["GET /done"]), "a hop: names and values"


FRAMED = {
    "/": '<img src="/main.gif"><iframe src="/same"></iframe><iframe src="{off}/cross"></iframe>',
    "/same": '<img src="/same.gif"><iframe src="/same-nested"></iframe>',
    "/same-nested": '<img src="/same-nested.gif">',
    "/back": '<img src="/back.gif"><iframe src="/back-nested"></iframe>',
    "/back-nested": '<img src="/back-nested.gif">',
}
CROSSED = {
    "/cross": (
        '<img src="/cross.gif"><iframe src="/cross-nested"></iframe>'
        '<iframe src="{a}/back"></iframe>'
    ),
    "/cross-nested": '<img src="/cross-nested.gif">',
}


async def test_every_frame_of_the_page_loads_what_it_loads_with_no_gate(
    browser: Any, profile: Path, served: list[Site]
) -> None:
    """The gate is told of a request with its frame, and nothing of its page: a frame of another
    site, the frames inside it, and a frame of the first site inside those are all **the
    page's** — found in the tree of the page or in the tree of a frame that has one of its own
    —, and what they load leaves as it does from the browser alone. Nothing less, nothing more."""
    a, off = two(served)
    for pages, host in ((FRAMED, a), (CROSSED, off)):
        for path, html in pages.items():
            host.pages[("GET", path)] = (200, HTML, html.format(a=a.origin, off=off.origin))
            if path != "/":
                host.pages[("GET", f"{path}.gif")] = (200, GIF, PIXEL)
    a.pages[("GET", "/main.gif")] = (200, GIF, PIXEL)
    whole = 2 * (len(FRAMED) + len(CROSSED))

    def asked() -> list[str]:
        return sorted([f"A {one}" for one in a.requests] + [f"OFF {one}" for one in off.requests])

    async with alone(browser, profile) as page:
        await page.goto(a.origin + "/")
        await until(lambda: len(asked()) == whole, "the browser alone loaded every frame")
    bare = asked()
    del a.seen[:], off.seen[:]
    await browser.open(a.origin + "/", only(a), FakeStop())
    await until(lambda: len(asked()) >= whole, "every frame loaded through the gate")

    assert asked() == bare


def asking(served: list[Site]) -> tuple[Recording, Recording]:
    """Site A, whose page asks site B for something a browser asks permission for first; and B,
    which answers that question with a no."""
    a, b = two(served)
    b.pages[("OPTIONS", "/api")] = (403, HTML, "no")
    b.pages[("PUT", "/api")] = (200, HTML, "done")
    a.pages[("GET", "/")] = (
        200,
        HTML,
        "<p id='said'>asking</p><script>"
        f"fetch('{b.origin}/api', {{method: 'PUT', credentials: 'include', "
        "headers: {'X-Of-The-Page': '1'}, body: 'x'})"
        ".then(() => document.querySelector('#said').textContent = 'answered')"
        ".catch(() => document.querySelector('#said').textContent = 'refused');"
        "</script>",
    )
    return a, b


async def test_the_question_a_browser_asks_another_site_first_is_left_to_that_site(
    browser: Any, served: list[Site]
) -> None:
    """Criterion 5, and the fourth fact of ADR 0064: with a route of Playwright's the driver
    answered that question itself, with a yes, and the site received what it would have
    refused. The site receives the question, says no, and the request does not leave."""
    a, b = asking(served)

    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await b.arrived("OPTIONS /api")
    said = await said_after(browser, opened.page, "#said", "asking")

    assert said == "refused"
    assert b.requests == ["OPTIONS /api"], "the question arrived, and nothing after it"


# ----------------------------------------------------------------------------------------
# Of a page that is not the one ELA works on no document leaves
# ----------------------------------------------------------------------------------------

OPENS = {
    "a link that opens elsewhere": (
        '<a id="go" target="_blank" href="{off}/x?k=1">go</a>',
        ("GET", "{off}/x?k=1"),
    ),
    "window.open": (
        '<button id="go" onclick="window.open(\'{off}/x?k=1\')">go</button>',
        ("GET", "{off}/x?k=1"),
    ),
    "a form that sends elsewhere": (
        '<form method="post" target="_blank" action="{off}/x"><input name="a" value="b">'
        '<input id="go" type="submit" value="go"></form>',
        ("POST", "{off}/x"),
    ),
    "a link that opens elsewhere an address inside, which redirects off": (
        '<a id="go" target="_blank" href="/out">go</a>',
        ("GET", "{a}/out"),
    ),
}


async def another(browser: Any, page: str, *, asked: bool = True) -> Any:
    """What the adapter says of the page the first page opened — once it asked for something,
    when ``asked``: the refusal of its first request is the event."""

    async def looked() -> Any:
        found = await browser.another(page)
        return found if found is not None and (found.address is not None or not asked) else None

    deadline = asyncio.get_running_loop().time() + LONG
    while (found := await looked()) is None:
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail("the adapter never said that the page had opened another")
        await asyncio.sleep(0.02)
    return found


@pytest.mark.parametrize("way", sorted(OPENS))
async def test_a_page_opened_by_a_page_sends_nothing_and_the_adapter_says_it_was_opened(
    browser: Any, served: list[Site], way: str
) -> None:
    """Criterion 7. ELA works on one page: another one nobody would look at. **The alert is on
    the browser and not on a page**, so nobody has to turn it on for a page that was just
    opened — measured 250 times for each way on each browser. Not even an address inside the
    boundary is asked for from that page; and the first page is what it was."""
    a, off = two(served)
    html, (method, address) = OPENS[way]
    a.pages[("GET", "/")] = (200, HTML, html.format(off=off.origin) + "<p>first</p>")
    a.pages[("GET", "/out")] = (302, [("Location", off.origin + "/x?k=1")], "")

    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await browser.click(opened.page, "#go")
    found = await another(browser, opened.page)

    assert (found.method, found.address) == (method, address.format(a=a.origin, off=off.origin))
    assert off.requests == [], "the page that was opened sent nothing to the other site"
    assert a.requests == ["GET /"], "nor to this one: it is not the page ELA works on"
    assert await browser.text(opened.page, "p") == "first"


FILLINGS = {
    "loads": "<img src={off}/w.gif><iframe src={off}/frame></iframe>",
    "image": "<img src={off}/w.gif>",
    "navigates": "<script>location = '{off}/nav?k=1'</script>",
    "sends": (
        "<form method=post action={off}/post><input name=a value=b></form>"
        "<script>document.forms[0].submit()</script>"
    ),
}
FIRST = """
<h1 id="first">first</h1>
<script>
const CONTENT = %s;
let opened = null;
function written(what) { const w = window.open('about:blank'); w.document.write(CONTENT[what]); }
function javascript(what) { window.open('javascript:' + JSON.stringify(CONTENT[what])); }
function inside() { opened = window.open('/inside'); }
function rewritten(what) {
  opened.document.open(); opened.document.write(CONTENT[what]); opened.document.close();
}
function blob(what) {
  window.open(URL.createObjectURL(new Blob([CONTENT[what]], {type: 'text/html'})));
}
function own() { const i = new Image(); i.src = '%s/own.gif'; document.body.append(i); }
</script>
<button id="own" onclick="own()">own</button><button id="inside" onclick="inside()">i</button>
"""
THE_FIRST_PAGE_S = ("written", "javascript", "rewritten")
"""The ways to fill a page in which what is put there is loaded **by the first page**: an empty
page written by the first, one opened with ``javascript:``, one opened on an address inside the
boundary — which never loads: its request is another page's — and then rewritten."""


def filling(a: Recording, off: Recording) -> None:
    """Site A, whose first page can open a page and fill it in each of the ways, with each of
    the contents; and what the site off the boundary would answer."""
    contents = {name: html.format(off=off.origin) for name, html in FILLINGS.items()}
    buttons = "".join(
        f'<button id="{way}-{what}" onclick="{way}(\'{what}\')">x</button>'
        for way in (*THE_FIRST_PAGE_S, "blob")
        for what in FILLINGS
    )
    script = FIRST % (json.dumps(contents).replace("</", "<\\/"), off.origin)
    a.pages[("GET", "/")] = (200, HTML, script + buttons)
    a.pages[("GET", "/inside")] = (200, HTML, "<p>inside</p>")
    for name in ("own.gif", "w.gif"):
        off.pages[("GET", f"/{name}")] = (200, GIF, PIXEL)
    for name in ("frame", "nav"):
        off.pages[("GET", f"/{name}")] = (200, HTML, "<p>elsewhere</p>")
    off.pages[("POST", "/post")] = (200, HTML, "<p>elsewhere</p>")


async def fill(
    browser: Any, page: str, judged: list[tuple[str, str, bool]], a: Recording, way: str, what: str
) -> None:
    """Have the first page open a page and fill it. The page that is rewritten is opened on an
    address inside the boundary first, and rewritten **once the gate has refused that request**
    — an event, where the page's own script would have to wait a time."""
    if way == "rewritten":
        await browser.click(page, "#inside")
        await decided(judged, a.origin + "/inside", leaves=False)
    await browser.click(page, f"#{way}-{what}")


@pytest.mark.parametrize("way", THE_FIRST_PAGE_S)
async def test_what_the_first_page_loads_in_a_page_it_opened_arrives_as_from_its_own_document(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]], way: str
) -> None:
    """Decisions 133 and 134 — the two halves. What the first page has loaded in a page it
    opened is, for the browser, **a request of the first page**: it leaves, as everything a page
    loads does. **The precondition is the control**: the same image asked by the first page's
    own document, which arrives with the one cookie that travels between sites. What is put in
    the other page arrives the same way, with the same cookies — nothing more than the page can
    already do —; and the frame written beside it, a document of that page, does not leave."""
    a, off = two(served)
    filling(a, off)
    given = [
        ("Set-Cookie", "lax=1; Max-Age=3600; Path=/"),
        ("Set-Cookie", "none=1; Max-Age=3600; Path=/; SameSite=None; Secure"),
    ]
    off.pages[("GET", "/set")] = (200, [*HTML, *given], f'<a id="to" href="{a.origin}/">to</a>')
    admitted = {a.origin, off.origin}
    opened = await browser.open(
        off.origin + "/set", lambda url: origin_of(url) in admitted, FakeStop()
    )
    await browser.click(opened.page, "#to")
    assert await browser.text(opened.page, "#first") == "first"
    admitted.discard(off.origin)

    await browser.click(opened.page, "#own")
    await off.arrived("GET /own.gif")
    await fill(browser, opened.page, judged, a, way, "loads")
    await off.arrived("GET /w.gif")
    await decided(judged, off.origin + "/frame", leaves=False)

    own, put = off.cookies("GET /own.gif"), off.cookies("GET /w.gif")
    assert own == "none=1", "the control: what the first page's own document sends, and no more"
    assert put == own, "what was put in the other page arrives as from the first page's document"
    assert off.requests == ["GET /set", "GET /own.gif", "GET /w.gif"], "and no document of it"
    assert await browser.another(opened.page) is not None, "and the adapter says a page was opened"


@pytest.mark.parametrize("what", ["navigates", "sends"])
@pytest.mark.parametrize("way", [*THE_FIRST_PAGE_S, "blob"])
async def test_no_document_of_a_page_that_was_opened_leaves_however_it_was_filled(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]], way: str, what: str
) -> None:
    """Decisions 133 and 135: not its navigation and not a form — the requests that would carry
    there every cookie a navigation carries —, for a page opened empty and written, opened with
    ``javascript:``, opened inside the boundary and rewritten, or opened on a ``blob:``."""
    a, off = two(served)
    filling(a, off)
    asked = ("GET", "/nav") if what == "navigates" else ("POST", "/post")

    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await fill(browser, opened.page, judged, a, way, what)
    method, _, _ = await decided(judged, off.origin + asked[1], leaves=False)

    assert method == asked[0]
    assert off.requests == []


async def test_of_a_page_opened_on_a_blob_not_even_an_image_leaves(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]]
) -> None:
    """Decision 135. A page opened on a ``blob:`` the first page made is a document of its own:
    what it loads is told to the gate with **its** frame, which is no frame of the page ELA
    works on — and a frame that is found nowhere in the page is refused."""
    a, off = two(served)
    filling(a, off)

    opened = await browser.open(a.origin + "/", only(a), FakeStop())
    await fill(browser, opened.page, judged, a, "blob", "image")
    await decided(judged, off.origin + "/w.gif", leaves=False)

    assert off.requests == []


async def test_a_read_of_a_page_that_opens_another_by_itself_succeeds_and_says_so(
    browser: Any, served: list[Site]
) -> None:
    """Decision 123: a step does not fail because a page tried to open another — a site that
    opens a window by itself would fail a read that worked. But the result says it, with the
    origin alone, or that the page had asked for nothing yet."""
    from ela.tools.browser import ANOTHER_PAGE, ASKED_FOR_NOTHING

    a, off = two(served)
    a.pages[("GET", "/")] = (
        200,
        HTML,
        f"<h1>Letto</h1><script>window.open('{off.origin}/x?k=1')</script>",
    )
    names = {"sito.example": a.origin}
    tool = BrowserReadTool(
        Browsing(sites=("sito.example",), origin=lambda name: names[name]),
        browser,
        CLOCK,
        FakeIdGenerator(),
    )
    arguments = {"site": "sito.example", "path": "/", "selector": "h1", "purpose": "x"}

    result = await tool.execute(decision(BROWSER_READ), arguments, FakeStop())
    found = await another(browser, str(result.output["page"]))

    assert result.status is ExecutionStatus.SUCCEEDED and result.output["text"] == "Letto"
    assert result.output[ANOTHER_PAGE] in {off.origin, ASKED_FOR_NOTHING}
    assert "k=1" not in str(result.output), "the origin, and nothing else of that address"
    assert found.address == off.origin + "/x?k=1" and off.requests == []


@ON_A_MAC
async def test_the_pages_of_the_browser_itself_ask_nothing_and_are_nobody_s_other_page(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    """Decision 127. The browser of the profile has pages of its own that nobody opened: a step
    works beside them, and the adapter does not take them for a page the first page opened."""
    a, off = two(served)
    a.pages[("GET", "/")] = (200, HTML, "<p>Ciao</p>")
    made = with_the_profile

    opened = await made.open(a.origin + "/", only(a), FakeStop())
    said = await made.text(opened.page, "p")
    stopped = await made.another(opened.page)
    await made.close(opened.page)

    assert said == "Ciao" and stopped is None
    assert a.requests == ["GET /"] and off.requests == []


@ON_A_MAC
async def test_a_worker_cannot_be_registered_through_the_gate(
    with_the_profile: AccountChrome,
    served: list[Site],
    judged: list[tuple[str, str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Found with the tests of M13.9 (decision 136): even from a launch that lets workers be —
    which no launch ELA drives is —, the request for the script of a worker has no frame of the
    page, and the gate refuses it. The site is never asked for the script."""
    web = account.worker_site(served)
    made = with_the_profile
    launch = made._launch
    monkeypatch.setattr(made, "_launch", lambda: {**launch(), "service_workers": "allow"})

    opened = await made.open(web.origin + "/register", only(web), FakeStop())
    await decided(judged, web.origin + "/worker.js", leaves=False)

    assert await made.text(opened.page, "#state") == "registering"
    assert "GET /worker.js" not in web.requests


WORKERS = {
    "dedicated": "new Worker('/w.js').onmessage = (e) => said(e.data);",
    "shared": (
        "const w = new SharedWorker('/shared.js'); w.port.onmessage = (e) => said(e.data); "
        "w.port.start();"
    ),
}
SAYS = (
    "<p id='s'>waiting</p><script>const said = (text) => "
    "document.querySelector('#s').textContent = text; %s</script>"
)
SCRIPT = {"Content-Type": "text/javascript"}
ASKS = "fetch('/asked').then(() => %s('done'), () => %s('failed'));"


@pytest.mark.parametrize(("worker", "says"), [("dedicated", "done"), ("shared", "failed")])
async def test_what_a_worker_of_the_page_asks_for_leaves_when_it_has_the_frame_of_the_page(
    browser: Any, served: list[Site], worker: str, says: str
) -> None:
    """What a **dedicated** worker of the page asks for — its script, what it imports, what it
    fetches — is told to the gate with the frame of the page, and leaves like everything the
    page loads. A **shared** worker asks with a frame of its own, which is no frame of the
    page: its script is the page's request and leaves, what it then asks for is refused —
    declared (ADR 0064 §7), and held here so that the day it changes somebody sees it."""
    web = site(
        served,
        {
            "/": (200, {}, SAYS % WORKERS[worker]),
            "/w.js": (
                200,
                SCRIPT,
                "importScripts('/imported.js'); " + ASKS % (("postMessage",) * 2),
            ),
            "/imported.js": (200, SCRIPT, "1;"),
            "/shared.js": (
                200,
                SCRIPT,
                "onconnect = (e) => { const tell = (text) => e.ports[0].postMessage(text); "
                + ASKS % (("tell",) * 2)
                + " };",
            ),
            "/asked": (200, {}, "x"),
        },
    )

    opened = await browser.open(web.origin + "/", only(web), FakeStop())
    said = await said_after(browser, opened.page, "#s", "waiting")

    assert said == says
    expected = {
        "dedicated": ["GET /", "GET /w.js", "GET /imported.js", "GET /asked"],
        "shared": ["GET /", "GET /shared.js"],
    }
    assert web.requests == expected[worker]


ASKING_WORKER = """
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (new URL(event.request.url).pathname === "/page") {
    const html = {headers: {"Content-Type": "text/html"}};
    event.respondWith(
      fetch("%s/asked", {mode: "no-cors"}).catch(() => null)
        .then(() => new Response("<p>from the worker</p>", html)));
  }
});
"""


@ON_A_MAC
async def test_what_a_worker_left_in_the_profile_asks_of_another_site_does_not_leave(
    with_the_profile: AccountChrome,
    served: list[Site],
    judged: list[tuple[str, str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Decision 136, the negative case, built: the profile launched **without** what ELA does
    to it — its workers not taken away, and not blocked. A worker is in charge of the page —
    the request for the other site is one only the worker makes —, and of the navigation it
    was handed the gate was not told: that is why the workers are taken away. What the worker
    asks of another site by itself has no frame of the page, and is refused like every request
    that is not the page's.

    *Not asserted: whose answer the page shows.* The browser sends the navigation to the site
    beside its worker and takes whichever answers first (measured: the worker's when it
    answers at once, the site's when the worker first waits for a request of its own)."""
    from ela.infrastructure.machine import account as profiled

    off = site(served, {"/asked": (200, {}, "x")})
    script = {"Content-Type": "text/javascript"}
    web = site(
        served,
        {
            "/register": (200, {}, account.REGISTERS),
            "/worker.js": (200, script, ASKING_WORKER % off.origin),
            "/page": (200, {}, "<p>from the network</p>"),
        },
    )
    made = with_the_profile
    await account.planted(made, web)
    launch = made._launch
    monkeypatch.setattr(made, "_launch", lambda: {**launch(), "service_workers": "allow"})
    monkeypatch.setattr(profiled, "_prepared", lambda profile, *, driven: None)

    # The guard of a test that once stopped here: the gate asked the page for its frames while
    # the page waited for its worker, which waited for the gate. A worker is refused by what
    # the browser announced of it, and the page is not asked.
    async with asyncio.timeout(LONG):
        opened = await made.open(web.origin + "/page", only(web), FakeStop())
    await decided(judged, off.origin + "/asked", leaves=False)
    await made.close(opened.page)

    assert [one for one in judged if one[1] == web.origin + "/page"] == []
    assert off.requests == []


# ----------------------------------------------------------------------------------------
# When in doubt nothing leaves
# ----------------------------------------------------------------------------------------


async def test_a_session_that_does_not_attach_opens_nothing(
    browser: Any, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})

    async def refused(context: Any) -> Any:
        raise RuntimeError("no session of the browser, for this test")

    monkeypatch.setattr(browser, "_attached", refused)

    with pytest.raises(BrowserFailed):
        await browser.open(web.origin + "/", only(web), FakeStop())

    assert web.requests == [] and browser._pages == {}


async def test_an_alert_that_tells_the_session_of_nothing_is_found_before_the_first_address(
    browser: Any, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 124. Before the first navigation the adapter asks for an address the browser
    itself refuses to open: with an alert that is on for nothing the session is not told of it,
    the opening fails closed, and the address of the site is never asked for."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    nothing = {"patterns": [{"urlPattern": "http://nowhere.invalid/*", "requestStage": "Request"}]}
    monkeypatch.setattr(adapter, "ALERT", nothing)

    with pytest.raises(BrowserFailed):
        await browser.open(web.origin + "/", only(web), FakeStop())

    assert web.requests == [] and browser._pages == {}


async def never(*anything: Any) -> Any:
    await asyncio.Event().wait()


@pytest.mark.parametrize("silent", ["never comes", "is told and never answers"])
async def test_a_session_that_never_answers_ends_the_step_in_its_time_and_leaves_nothing(
    browser: Any, served: list[Site], monkeypatch: pytest.MonkeyPatch, silent: str
) -> None:
    """Decision 128: no wait of the gate is without an end. The session never comes, or it is
    told of the request and never answers: the step ends at the tool's time, failed, the site
    received nothing, and the fixture of this module finds neither a process nor a folder."""
    web = site(served, {"/": (200, {}, "<h1>x</h1>")})
    if silent == "never comes":
        monkeypatch.setattr(browser, "_attached", never)
    else:
        monkeypatch.setattr(adapter._Gate, "_told", lambda self, event: None)
    names = {"sito.example": web.origin}
    tool = BrowserReadTool(
        Browsing(sites=("sito.example",), origin=lambda name: names[name], timeout_seconds=2),
        browser,
        CLOCK,
        FakeIdGenerator(),
    )

    async with asyncio.timeout(60):
        result = await tool.execute(
            decision(BROWSER_READ),
            {"site": "sito.example", "path": "/", "purpose": "x"},
            FakeStop(),
        )

    assert result.error is not None and result.error.code == TIMEOUT
    assert web.requests == [] and browser._pages == {}
    await shell.closings(browser)
    assert shell.descendants() == [], "what the opening had started is closed, not left"


async def test_a_judge_that_raises_lets_nothing_leave_and_the_step_says_the_browser_failed(
    browser: Any, served: list[Site], judged: list[tuple[str, str, bool]]
) -> None:
    """Criterion 9. The boundary of this test raises when it is asked about the other site:
    the request is made to fail instead of being left where it is, and the next use of the
    page says that the browser failed — not that a text is missing."""
    other = site(served, {"/": (200, {}, "<p>altrove</p>")})
    web = site(served, {"/": (200, {}, f'<a id="go" href="{other.origin}/">go</a>')})
    names = {"sito.example": web.origin}

    def allowed(address: str) -> bool:
        if address.startswith(other.origin):
            raise RuntimeError("the boundary of this test cannot say")
        return True

    opened = await browser.open(web.origin + "/", allowed, FakeStop())
    with pytest.raises(BrowserFailed):
        await browser.click(opened.page, "#go")
        await decided(judged, other.origin + "/", leaves=False)
        await browser.title(opened.page)
    await browser.close(opened.page)
    tool = BrowserActTool(
        Browsing(sites=("sito.example",), origin=lambda name: names[name]),
        browser,
        CLOCK,
        FakeIdGenerator(),
    )
    tool._gestures = lambda arguments, site, address: _raising(  # type: ignore[method-assign]
        BrowserActTool._gestures(tool, arguments, site, address), allowed
    )
    result = await tool.execute(
        decision(BROWSER_ACT),
        {
            "site": "sito.example",
            "path": "/",
            "fill": [],
            "click": "#go",
            "expect_text": "x",
            "purpose": "x",
        },
        FakeStop(),
    )

    assert result.error is not None and result.error.code == FAILED
    assert other.requests == [], "in doubt the request did not leave"


def _raising(call: Any, allowed: Callable[[str], bool]) -> Any:
    """The call a tool would make, with the boundary of the test in the place of its own."""
    from dataclasses import replace

    return replace(call, allowed=allowed)


async def test_from_ela_s_stop_on_not_even_the_hop_of_a_redirect_leaves(
    served: list[Site],
) -> None:
    """Criterion 10. The boundary of this test raises ELA's stop the instant it is asked about
    the hop: the gate is told of the hop of a redirect as of a first address, looks at the stop
    again right before it would let the request go, and does not."""
    web = site(served, {"/": (302, {"Location": "/dopo"}, ""), "/dopo": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    made = empty(stopping)
    asked: list[str] = []

    def admitted_while_ela_stops(address: str) -> bool:
        asked.append(address)
        if address.endswith("/dopo"):
            stopping.set()
        return True

    with pytest.raises(BrowserStopped):
        await made.open(web.origin + "/", admitted_while_ela_stops, FakeStop())
    watching = made._watching
    assert watching is not None
    await watching

    assert asked == [web.origin + "/", web.origin + "/dopo"], "the hop did reach the gate"
    assert web.requests == ["GET /"], "and was not sent"


PAUSED = r"""
import asyncio, platform, sys
from ela.infrastructure.machine import PlaywrightBrowser
from ela.infrastructure.machine import browser as adapter
from ela.testing.fakes import FakeStop

async def main() -> None:
    inside, outside = sys.argv[1], sys.argv[2]
    told = adapter._Gate._told

    def deaf(self, event):
        if event["request"]["url"].startswith(outside):
            print("paused", flush=True)  # told of it, and never answering: a judge that died
            return
        told(self, event)

    adapter._Gate._told = deaf
    browser = PlaywrightBrowser(
        asyncio.Event(), environment={}, kept=asyncio.Event().wait, system=platform.system()
    )
    opened = await browser.open(inside + "/", lambda url: True, FakeStop())
    print(" ".join(str(pid) for pid in browser._driver_pids()), flush=True)
    await browser.click(opened.page, "#go")

asyncio.run(asyncio.wait_for(main(), 90))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="a signal nobody can refuse is POSIX's")
def test_a_driver_that_dies_with_a_request_paused_lets_it_never_leave(served: list[Site]) -> None:
    """Criterion 9. In a process of its own, as the test of the signals has one: the request for
    the other site is paused and nobody answers; the driver is killed. The browser dies with
    its driver — the event —, and the site has received nothing."""
    other = site(served, {"/": (200, {}, "<p>altrove</p>")})
    web = site(served, {"/": (200, {}, f'<a id="go" href="{other.origin}/?k=1">go</a>')})
    holder = subprocess.Popen(
        [sys.executable, "-c", PAUSED, web.origin, other.origin],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    assert holder.stdout is not None
    try:
        drivers = [int(pid) for pid in holder.stdout.readline().split()]
        assert drivers, "the holder opened no page"
        table = _listed(
            subprocess.run(
                ["/bin/ps", "-A", "-o", "pid=,ppid=,comm="],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
        under = [pid for driver in drivers for pid, _ in _descendants(driver, table)]
        assert under, "the driver had started a browser"
        assert holder.stdout.readline().strip() == "paused"

        for pid in drivers:
            os.kill(pid, signal.SIGKILL)
        deadline = time.monotonic() + LONG
        while any(running(pid) for pid in under) and time.monotonic() < deadline:
            time.sleep(0.05)

        assert not [pid for pid in under if running(pid)], "the browser outlived its driver"
    finally:
        holder.wait(timeout=120)
    assert other.requests == [], "the request that was paused never left"


# ----------------------------------------------------------------------------------------
# Every use of a page asks the boundary where the page is
# ----------------------------------------------------------------------------------------


class Changing:
    """A boundary that stops admitting anything when the test says, or at its n-th question: the
    page is where it was, and it is not inside any more. With a gate that holds, a page does
    not end off the boundary by itself: the precondition of the predicate is built so."""

    def __init__(self) -> None:
        self.closed = False
        self.asked = 0
        self.closes_at: int | None = None

    def __call__(self, address: str) -> bool:
        self.asked += 1
        if self.closes_at is not None and self.asked >= self.closes_at:
            self.closed = True
        return not self.closed


USES: dict[str, Callable[[Any, str], Awaitable[Any]]] = {
    "count": lambda b, p: b.count(p, "#f"),
    "field": lambda b, p: b.field(p, "#f"),
    "fill": lambda b, p: b.fill(p, "#f", "x"),
    "click": lambda b, p: b.click(p, "#go"),
    "text": lambda b, p: b.text(p, None),
    "title": lambda b, p: b.title(p),
    "left": lambda b, p: b.left(p),
    "glance": lambda b, p: b.glance(p, selector=None, expect="x", seconds=1),
}
USED = shell.REPORTS + '<title>t</title><input id="f"><button id="go">go</button><p>x</p>'


OF_THE_PROFILE_ALONE = {"fill_secret", "landed"}
"""The uses of a page only the browser of the profile has: walked in a test of their own."""


def test_every_use_of_a_page_the_port_has_is_walked_here_on_the_real_browser() -> None:
    """The members that use a page are found by the port's signatures, never listed
    (``tests/architecture``): a member added to the port without its walk here is red."""
    from ela.ports import AccountBrowser, Browser
    from tests.architecture.test_every_use_of_a_page_asks_the_boundary import uses

    assert set(USES) == set(uses(Browser))
    assert set(USES) | OF_THE_PROFILE_ALONE == set(uses(AccountBrowser))


@pytest.mark.parametrize("use", sorted(USES))
async def test_no_use_of_a_page_that_is_not_inside_the_boundary_takes_place(
    browser: Any, served: list[Site], use: str
) -> None:
    from ela.ports import LeftSite

    web = site(served, {"/": (200, {}, USED)})
    allowed = Changing()
    opened = await browser.open(web.origin + "/", allowed, FakeStop())
    allowed.closed = True

    with pytest.raises(LeftSite) as refused:
        await USES[use](browser, opened.page)

    assert refused.value.address == web.origin + "/"
    assert web.origin not in str(refused.value), "the sentence of the error names no address"
    assert web.events == [], "nothing was typed and nothing was clicked"


@pytest.mark.parametrize("use", ["text", "title", "count", "glance"])
async def test_what_was_read_on_a_page_that_ended_elsewhere_meanwhile_is_thrown_away(
    browser: Any, served: list[Site], use: str
) -> None:
    """Decision 122. The boundary of this test admits the page when the use begins and not when
    it ends: what was read is in nobody's hands — and a look releases the page all the same."""
    from ela.ports import LeftSite

    web = site(served, {"/": (200, {}, USED)})
    allowed = Changing()
    opened = await browser.open(web.origin + "/", allowed, FakeStop())
    allowed.closes_at = allowed.asked + 2

    with pytest.raises(LeftSite):
        await USES[use](browser, opened.page)

    assert allowed.asked == allowed.closes_at, "asked once before the use, and once after it"
    assert use != "glance" or opened.page not in browser._pages


@ON_A_MAC
async def test_a_secret_is_not_typed_and_a_landing_is_not_told_on_a_page_outside_the_boundary(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    from ela.ports import LeftSite

    web = site(served, {"/": (200, {}, shell.REPORTS + '<input id="f" type="password">')})
    made = with_the_profile
    allowed = Changing()
    opened = await made.open(web.origin + "/", allowed, FakeStop())
    allowed.closed = True

    with pytest.raises(LeftSite):
        await made.fill_secret(
            opened.page, "#f", Secret("-".join(("a", "word", "of", "the", "test")))
        )
    with pytest.raises(LeftSite):
        await made.landed(opened.page)
    await made.close(opened.page)

    assert web.events == []


@ON_A_MAC
async def test_a_secret_typed_on_a_page_that_ends_elsewhere_meanwhile_is_said_as_typed(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    """The boundary admits the page when the typing begins and not when it ends: the gesture
    happened, and the error says so — a tool counts it as made, and does not report that
    nothing was typed."""
    from ela.ports import LeftSite

    web = site(served, {"/": (200, {}, shell.REPORTS + '<input id="f" type="password">')})
    made = with_the_profile
    allowed = Changing()
    opened = await made.open(web.origin + "/", allowed, FakeStop())
    allowed.closes_at = allowed.asked + 2

    with pytest.raises(LeftSite) as typed:
        await made.fill_secret(
            opened.page, "#f", Secret("-".join(("a", "word", "of", "the", "test")))
        )

    assert typed.value.made is True


async def test_a_tool_on_a_page_that_is_elsewhere_reads_nothing_and_says_where_by_its_origin(
    browser: Any, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 3, with the real browser and the real tools: the page is found elsewhere at
    the tool's first use of it. Nothing of the page is in the result, nothing was typed."""
    web = site(served, {"/": (200, {}, "<h1>secret of the page</h1>" + USED)})
    monkeypatch.setattr(adapter, "_where", lambda page: "https://altro.example/x?k=1")
    names = {"sito.example": web.origin}
    browsing = Browsing(sites=("sito.example",), origin=lambda name: names[name])
    reading = {"site": "sito.example", "path": "/", "selector": "h1", "purpose": "x"}
    acting = {
        "site": "sito.example",
        "path": "/",
        "fill": [["#f", "what the plan writes"]],
        "click": "#go",
        "expect_text": "x",
        "purpose": "x",
    }

    read = await BrowserReadTool(browsing, browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_READ), reading, FakeStop()
    )
    act = await BrowserActTool(browsing, browser, CLOCK, FakeIdGenerator()).execute(
        decision(BROWSER_ACT), acting, FakeStop()
    )

    for result in (read, act):
        assert result.error is not None and result.error.code == LEFT_SITE
        assert "https://altro.example" in result.error.message
        assert "k=1" not in result.error.message and "secret of the page" not in str(result)
    assert web.events == [] and browser._pages == {}


# ----------------------------------------------------------------------------------------
# A certificate the browser does not accept
# ----------------------------------------------------------------------------------------

OPENSSL = shutil.which("openssl")


@pytest.mark.skipif(OPENSSL is None, reason="the certificate of this test is made with openssl")
async def test_a_certificate_the_browser_does_not_accept_opens_no_page_whatever_the_driver_reads(
    served: list[Site], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Criterion 13, and ADR 0052 §14 revised: every certificate is judged by the browser. The
    variables that tell the driver to trust a certificate — in the environment of the process
    that starts it, which is ELA's — changed what the gate of before accepted: the driver
    fetched the document. They change nothing now.

    **The precondition is built**: the site does answer whoever trusts its certificate — so a
    page that does not open is the browser's refusal, and not a site that is not there."""
    key, cert = tmp_path / "key.pem", tmp_path / "cert.pem"
    assert OPENSSL is not None
    subprocess.run(
        [OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1"]
        + ["-subj", "/CN=localhost", "-keyout", str(key), "-out", str(cert)],
        check=True,
        capture_output=True,
    )
    web = site(served, {"/": (200, {}, "<p>behind a certificate nobody signed</p>")})
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    web.server.socket = context.wrap_socket(web.server.socket, server_side=True)
    address = web.origin.replace("http://127.0.0.1", "https://localhost") + "/"
    trusting = ssl.create_default_context(cafile=str(cert))
    trusting.check_hostname = False
    answered = await asyncio.to_thread(
        lambda: urllib.request.urlopen(address, context=trusting, timeout=LONG).status
    )
    assert answered == 200 and web.requests == ["GET /"]
    monkeypatch.setenv("NODE_TLS_REJECT_UNAUTHORIZED", "0")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", str(cert))
    made = empty()

    try:
        with pytest.raises(SiteUnreachable):
            await made.open(address, everywhere, FakeStop())
        assert web.requests == ["GET /"], "the request of the control, and none of the browser's"
        assert made._pages == {}
    finally:
        for page in list(made._pages):
            await made.close(page)
