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
* a ``SIGINT`` to ELA's process group does not close the page (M5-bis).

**No sleep**: the pages answer to requests, and the deadline is an event. The one wait is the
negative case of the verifier — a text that never appears has no event —, bounded to a fifth of a
second. If the shell is not installed these tests **fail**, naming the command: a skip on the
system they cover is the debt of ADR 0047 §18.
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import threading
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ela.domain import (
    DecisionId,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.infrastructure.machine import PlaywrightBrowser
from ela.permissions import BROWSER_ACT, BROWSER_READ
from ela.ports import BrowserNotInstalled, BrowserStopped, PageGone, SiteUnreachable
from ela.testing.fakes import FakeClock, FakeIdGenerator
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
    )
    if not await made.installed():
        pytest.fail(f"the browser ELA uses is not installed on this machine: run `{INSTALL}`")
    yield made
    for page in list(made._pages):  # noqa: SLF001 — nothing is left running after a test
        await made.close(page)


def descendants() -> list[str]:
    """What this worker has started and the kernel still knows, by name — ``ps`` itself aside."""
    out = subprocess.run(
        ["/bin/ps", "-A", "-o", "pid=,ppid=,comm="], capture_output=True, text=True, check=True
    ).stdout
    rows = [line.split(None, 2) for line in out.splitlines()]
    children: dict[int, list[tuple[int, str]]] = {}
    for pid, ppid, name in ((int(a), int(b), c) for a, b, c in rows):
        children.setdefault(ppid, []).append((pid, name.rsplit("/", 1)[-1]))
    found: list[str] = []
    todo = [os.getpid()]
    while todo:
        for pid, name in children.get(todo.pop(), []):
            if name != "ps":
                found.append(name)
                todo.append(pid)
    return found


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
        decision(BROWSER_READ), arguments
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
        decision(BROWSER_ACT), arguments
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
        decision(BROWSER_ACT), arguments
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
        decision(BROWSER_READ), arguments
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
        decision(BROWSER_READ), arguments
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
        decision(BROWSER_ACT), arguments
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
        decision(BROWSER_ACT), arguments
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

    opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})))

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
        decision(BROWSER_ACT), arguments
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
        decision(BROWSER_ACT), arguments
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

    first = await browser.open(web.origin + "/set", allowed)
    await browser.close(first.page)
    second = await browser.open(web.origin + "/check", allowed)
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
        await browser.open(address, lambda url: True)

    assert descendants() == []


async def test_a_page_closed_leaves_no_process_when_the_close_returns(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opened = await browser.open(web.origin + "/", lambda url: True)
    assert descendants(), "a driver and a browser run while the page is open"

    await browser.close(opened.page)

    assert descendants() == []
    with pytest.raises(PageGone):
        await browser.text(opened.page, None)


async def test_the_stop_signal_closes_every_page_and_stops_what_runs(served: list[Site]) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = PlaywrightBrowser(stopping, environment={}, kept=Kept())
    opened = await browser.open(web.origin + "/", lambda url: True)
    watching = browser._watching  # noqa: SLF001 — the task the signal wakes
    assert watching is not None

    stopping.set()
    await watching

    assert descendants() == []
    with pytest.raises(BrowserStopped):
        await browser.text(opened.page, None)
    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", lambda url: True)


async def test_a_page_handed_over_and_never_looked_at_is_closed_at_its_deadline(
    served: list[Site],
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    kept = Kept()
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=kept)
    opened = await browser.open(web.origin + "/", lambda url: True)
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
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=Kept())

    assert await browser.installed() is False
    with pytest.raises(BrowserNotInstalled):
        await browser.open("http://127.0.0.1:9/", lambda url: True)
    assert descendants() == []


# ----------------------------------------------------------------------------------------
# A Ctrl-C to ELA's process group does not close the page (M5-bis)
# ----------------------------------------------------------------------------------------

HOLDER = r"""
import asyncio, signal, sys
from ela.infrastructure.machine import PlaywrightBrowser

async def main() -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # uvicorn keeps serving what is in flight
    browser = PlaywrightBrowser(asyncio.Event(), environment={}, kept=asyncio.Event().wait)
    opened = await browser.open(sys.argv[1], lambda url: True)
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
