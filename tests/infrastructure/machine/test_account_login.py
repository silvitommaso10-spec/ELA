"""The shape of a real login, through the gate, **on the real Chrome for Testing** (M13.9,
decision 105a).

Until the proof of 2026-10-12 the suite held the two halves apart: a cookie given on a ``200``
and found by the next launch, and a form sent with ``POST`` and answered with a ``303`` that
carried no cookie. A site that signs somebody in does both at once, and the login of the proof
did not get in. Here is the whole of it, on a site of the test's:

* a form sent with ``POST``;
* answered with **a redirect that carries the cookie of the access**, with the attributes such
  a cookie has — ``Secure``, ``HttpOnly``, an end, ``SameSite``;
* and a page after the redirect that shows the text awaited **only if that cookie came back**;
* then **a second launch**, which finds it.

**The site is on the loopback, like every site of these tests**, and that is what lets its
cookie be ``Secure`` with no TLS: a browser keeps such a cookie from a page served in the clear
only when the machine is talking to itself. Measured on 2026-10-12 under both of its names,
``localhost`` and ``127.0.0.1``: the three tests say the same.

**The first test is the precondition of the others** (ADR 0031 §6): the same site and the same
browser with no gate at all. A site of the test's that the browser alone could not sign in to
would make the tests of the gate say nothing.

Reserved to a Mac with Chrome for Testing, like ``test_account_browser.py``, whose fixtures
these are: a folder of its own under ``/tmp`` for every test, and nothing left on the machine.
"""

from __future__ import annotations

import threading
import time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import pytest
from playwright.async_api import async_playwright

from ela.ports import Secret
from ela.testing.fakes import FakeStop
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine.test_account_browser import chrome, everywhere

served = account.served
nothing_left_behind = account.nothing_left_behind
profile = account.profile

pytestmark = account.pytestmark

USER = "mario"
WORD = "-".join(("the", "word", "of", "the", "test"))
ACCESS = f"user={USER}&0123456789abcdef"
"""The cookie of the access, as a site writes one: a name, and a value nobody could guess."""
FORM = """
<form action="login" method="post">
  <input type="hidden" name="goto" value="home">
  <input type="text" name="acct">
  <input type="password" name="pw">
  <input type="submit" value="login">
</form>
"""
INSIDE = f'<a href="user">{USER}</a> | <a href="logout">logout</a>'
OUTSIDE = '<a href="login">login</a>'
IN = "logout"
STILL_ARRIVING = 0.5
"""How long the second half of a page is held back: long beside the instant a click returns in,
which is when its address is the page's already."""
"""What only a page from inside shows: it is in neither the form nor the page of who is out."""


class LoginSite:
    """A site that signs in as a real one does, and what it received.

    ``POST /login`` with the right two values answers ``302`` to ``home`` — a relative address,
    as sites write it — with the cookie of the access; with anything else it answers ``401`` and
    the form again — or, made with ``back``, with a redirect to ``again``, where the form is
    served **in two halves with a pause between them**: a site that sends who failed back to its
    form, on a connection that is slow. ``/home`` shows :data:`INSIDE` to a request that carries
    that cookie, and :data:`OUTSIDE` to any other.
    """

    def __init__(self, *, back: bool = False) -> None:
        self.requests: list[str] = []
        self.cookies: list[str] = []
        self.back = back
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _page(self, status: int, html: str, headers: dict[str, str] | None = None) -> None:
                data = html.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _in_two_halves(self, first: str, then: str) -> None:
                """A page that is still arriving when its address is already the page's: its
                beginning, a pause, and only then the rest."""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(first.encode()) + len(then.encode())))
                self.end_headers()
                self.wfile.write(first.encode())
                self.wfile.flush()
                time.sleep(STILL_ARRIVING)
                self.wfile.write(then.encode())

            def _answer(self) -> None:
                path = self.path.split("?")[0]
                if path == "/favicon.ico":
                    self._page(404, "")
                    return
                carried = self.headers.get("Cookie") or ""
                site.requests.append(f"{self.command} {path}")
                site.cookies.append(carried)
                if self.command == "POST" and path == "/login":
                    length = int(self.headers.get("Content-Length") or 0)
                    sent = parse_qs(self.rfile.read(length).decode())
                    if sent.get("acct") == [USER] and sent.get("pw") == [WORD]:
                        ends = formatdate(time.time() + 30 * 24 * 3600, usegmt=True)
                        cookie = f"{ACCESS}; Expires={ends}; Path=/; Secure; HttpOnly; SameSite=Lax"
                        self._page(302, "", {"Location": "home", "Set-Cookie": cookie})
                    elif site.back:
                        self._page(302, "", {"Location": "again"})
                    else:
                        self._page(401, "<p>Bad login.</p>" + FORM)
                elif path == "/again":
                    self._in_two_halves("<p>Bad login.</p>" + " " * 4096, FORM)
                elif path == "/login":
                    self._page(200, FORM)
                elif path == "/home":
                    self._page(200, INSIDE if ACCESS in carried.split("; ") else OUTSIDE)
                else:
                    self._page(404, "<p>nothing</p>")

            do_GET = _answer  # noqa: N815
            do_POST = _answer  # noqa: N815

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://localhost:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def login_site(served: list[account.Site], *, back: bool = False) -> LoginSite:
    made = LoginSite(back=back)
    served.append(made)  # type: ignore[arg-type] — closed with the others: it has ``close``
    return made


async def test_the_site_of_these_tests_signs_in_the_browser_alone_with_no_gate(
    profile: Path, served: list[account.Site]
) -> None:
    """The precondition: the browser of the profile, launched as the adapter launches it and
    with no route at all, signs in to this site and is still in at the next launch."""
    web = login_site(served)
    profile.mkdir(mode=0o700)
    options = chrome(profile)._launch()

    async with async_playwright() as playwright:
        first = await playwright.chromium.launch_persistent_context(str(profile), **options)
        page = first.pages[0] if first.pages else await first.new_page()
        await page.goto(web.origin + "/login")
        await page.locator("input[name=acct]").fill(USER)
        await page.locator("input[name=pw]").fill(WORD)
        await page.locator("input[type=submit]").click()
        await page.get_by_text(IN).first.wait_for(state="visible", timeout=10_000)
        await first.close()
        second = await playwright.chromium.launch_persistent_context(str(profile), **options)
        page = second.pages[0] if second.pages else await second.new_page()
        await page.goto(web.origin + "/home")
        shown = await page.locator("body").inner_text()
        await second.close()

    assert IN in shown
    assert web.requests == ["GET /login", "POST /login", "GET /home", "GET /home"]
    assert web.cookies == ["", "", ACCESS, ACCESS]


@pytest.mark.parametrize("shown", [False, True], ids=["without a window", "with a window"])
async def test_a_login_as_a_site_does_it_passes_the_gate_and_the_next_launch_is_still_in(
    profile: Path, served: list[account.Site], shown: bool
) -> None:
    """Decision 105a. The form is sent, the redirect carries the cookie of the access, the page
    after it shows what only who is in sees — and the cookie is in the folder for the next
    launch, which a login exists for."""
    web = login_site(served)
    browser = chrome(profile, shown=lambda: shown)

    opened = await browser.open(web.origin + "/login", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "input[name=acct]", Secret(USER))
    await browser.fill_secret(opened.page, "input[name=pw]", Secret(WORD))
    await browser.click(opened.page, "input[type=submit]")
    glanced = await browser.glance(opened.page, selector=None, expect=IN, seconds=10)
    again = await browser.open(web.origin + "/home", everywhere, FakeStop())
    after = await browser.text(again.page, None)
    await browser.close(again.page)

    assert web.requests == ["GET /login", "POST /login", "GET /home", "GET /home"]
    assert web.cookies[2] == ACCESS, "the page after the redirect was asked for with the cookie"
    assert glanced.shown is True, "and showed what only who is in sees"
    assert web.cookies[3] == ACCESS, "the next launch found the cookie in the folder"
    assert IN in after


async def test_the_browser_says_where_a_login_ended_and_the_status_of_its_document(
    profile: Path, served: list[account.Site]
) -> None:
    """Decision 106, on the real browser: after the click the page is asked where it is **once
    the document the click led to is there** — an event of the page, with no time of its own —,
    and the status of that document is the last one the main frame was given: the redirect's is
    not it. A login the site refuses ends on its form, which still has its password field."""
    web = login_site(served)
    browser = chrome(profile)

    opened = await browser.open(web.origin + "/login?from=the-test", everywhere, FakeStop())
    before = await browser.landed(opened.page)
    await browser.fill_secret(opened.page, "input[name=acct]", Secret(USER))
    await browser.fill_secret(opened.page, "input[name=pw]", Secret("not the word"))
    await browser.click(opened.page, "input[type=submit]")
    refused = await browser.landed(opened.page)
    left = await browser.count(opened.page, "input[name=pw]")
    await browser.fill_secret(opened.page, "input[name=acct]", Secret(USER))
    await browser.fill_secret(opened.page, "input[name=pw]", Secret(WORD))
    await browser.click(opened.page, "input[type=submit]")
    inside = await browser.landed(opened.page)
    gone = await browser.count(opened.page, "input[name=pw]")
    await browser.close(opened.page)

    assert (before.address, before.status) == (web.origin + "/login?from=the-test", 200)
    assert (refused.address, refused.status, left) == (web.origin + "/login", 401, 1), (
        "the status of the page the site answered with, not the one the form was opened with"
    )
    assert (inside.address, inside.status, gone) == (web.origin + "/home", 200, 0), (
        "the 302 of the redirect is not the status of the page it led to"
    )


async def test_a_page_that_is_still_arriving_is_waited_for_before_it_is_asked_about(
    profile: Path, served: list[account.Site]
) -> None:
    """A site that sends a refused login **back to its form with a redirect**: the page after a
    redirect is asked for by the browser itself, and its address is the page's as soon as its
    first bytes are there. Asked then, the page has no password field yet — and the result
    would say the form was gone, which is what a login that worked looks like. What is waited
    for is the document: an event of the page, not a time."""
    web = login_site(served, back=True)
    browser = chrome(profile)

    opened = await browser.open(web.origin + "/login", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "input[name=acct]", Secret(USER))
    await browser.fill_secret(opened.page, "input[name=pw]", Secret("not the word"))
    await browser.click(opened.page, "input[type=submit]")
    refused = await browser.landed(opened.page)
    left = await browser.count(opened.page, "input[name=pw]")
    await browser.close(opened.page)

    assert web.requests == ["GET /login", "POST /login", "GET /again"]
    assert (refused.address, refused.status) == (web.origin + "/again", 200)
    assert left == 1, "the form is there: the second half of the page was waited for"
