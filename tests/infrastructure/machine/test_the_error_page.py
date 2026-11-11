"""The browser's own error page is not another site, **on the two real browsers** (M13.9b).

When a site takes a request and closes the connection, the browser shows a page of its own,
``chrome-error://chromewebdata/``, and its protocol carries the address it tried to reach — the
main frame's ``unreachableUrl`` (measured on 2026-11-02: 50 rounds of 50 on the two browsers, and
never on ``about:blank`` or a ``blob:``; ``docs/milestones/M13.9b.md``). The boundary is asked about
**that** address: inside, the site did not answer, at the address asked and with no status;
outside, the page is another site's.

**Every test builds its precondition** (CLAUDE.md): it waits for the main frame to commit the error
page — Playwright's ``framenavigated`` towards ``chrome-error://`` — before any use. Without it a
``POST`` that fails leaves the form's page to be read: the click returns before the error page is
there (measured on 2026-11-03, 10 rounds of 10), and a test would pass before the repair.

And ``landed`` **waits for the end of the navigation the click started** (answer 15 of the review at
``5808ae5``; the measure of that day: ``Page.frameStoppedLoading`` of the main frame says the end,
``Page.frameRequestedNavigation`` before the click returns says the start): the last two tests ask
it right after the click, with nothing awaited by the test.

Sites of this machine only, and nothing left on the machine.
"""

from __future__ import annotations

import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from ela.infrastructure.machine.account import AccountChrome
from ela.ports import LeftSite
from ela.testing.fakes import FakeStop
from tests.infrastructure.machine import test_the_boundary as bounds

served = bounds.served
nothing_left_behind = bounds.nothing_left_behind
profile = bounds.profile
browser = bounds.browser
with_the_profile = bounds.with_the_profile
only = bounds.only

ERROR_PAGE = "chrome-error://"
PAGE = """<p id="said">before</p>
<form action="login" method="post"><input name="acct"><input type="submit" value="go"></form>
<a id="dead" href="dead">dead</a>
<button id="word" onclick="document.querySelector('#said').textContent = 'after'">word</button>"""


class Silent:
    """A site of this machine: ``/`` is a page with a form and a link; ``POST /login`` and
    ``GET /dead`` take the request and close the connection — the browser shows its own page.
    **The form's page is ``/`` and the form goes to ``/login``**: a read of the form's page and a
    read of the address asked are two answers, not one."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                path = self.path.split("?")[0]
                if path == "/favicon.ico":
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                site.requests.append(f"{self.command} {path}")
                if self.command == "POST" or path == "/dead":
                    if self.command == "POST":
                        self.rfile.read(int(self.headers.get("Content-Length") or 0))
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                data = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

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


def silent(served: list[Any]) -> Silent:
    made = Silent()
    served.append(made)
    return made


async def clicked_onto_the_error_page(browser: Any, token: str, selector: str) -> None:
    """The click, and **the error page committed**, awaited as the event it is."""
    page = browser._pages[token].page
    async with page.expect_event(
        "framenavigated",
        predicate=lambda frame: frame == page.main_frame and frame.url.startswith(ERROR_PAGE),
        timeout=bounds.LONG * 1000,
    ):
        await browser.click(token, selector)


async def test_the_browser_s_page_for_an_address_inside_is_where_the_site_did_not_answer(
    browser: Any, served: list[Any]
) -> None:
    web = silent(served)
    opened = await browser.open(web.origin + "/", only(web), FakeStop())

    await clicked_onto_the_error_page(browser, opened.page, "#dead")
    found = await browser.count(opened.page, "#said")
    where = await browser.where(opened.page)
    unanswered = await browser.unanswered(opened.page)

    assert found == 0, "the page is the browser's own, not the site's"
    assert (where, unanswered) == (web.origin + "/dead", web.origin + "/dead")
    assert web.requests[:2] == ["GET /", "GET /dead"]


async def test_the_browser_s_page_for_an_address_outside_is_another_site_s_by_that_address(
    browser: Any, served: list[Any]
) -> None:
    """Taken back with the boundary of another site — the one way, with the gate on, the browser
    shows its page for an address outside the boundary (measured: a refusal of the gate makes
    none) —, the page is outside, and said by the address the browser tried."""
    web, other = silent(served), silent(served)
    opened = await browser.open(web.origin + "/", only(web), FakeStop())
    await clicked_onto_the_error_page(browser, opened.page, "#dead")
    await browser.hold(opened.page)

    with pytest.raises(LeftSite) as found:
        await browser.resume(opened.page, only(other))

    assert found.value.address == web.origin + "/dead"


async def test_a_page_that_answered_is_not_the_browser_s(browser: Any, served: list[Any]) -> None:
    web = silent(served)
    opened = await browser.open(web.origin + "/", only(web), FakeStop())

    assert await browser.unanswered(opened.page) is None


async def test_a_login_the_site_does_not_answer_lands_where_it_was_asked_with_no_status(
    with_the_profile: AccountChrome, served: list[Any]
) -> None:
    """The case of M13.9's test, with the boundary of the site's origin, as in production."""
    web = silent(served)
    opened = await with_the_profile.open(web.origin + "/", only(web), FakeStop())
    await with_the_profile.fill(opened.page, "input[name=acct]", "someone")

    await clicked_onto_the_error_page(with_the_profile, opened.page, "input[type=submit]")
    landed = await bounded(with_the_profile.landed(opened.page), "the end of a navigation")

    assert (landed.address, landed.status) == (web.origin + "/login", None)
    assert landed.unanswered == web.origin + "/login"


async def test_landed_waits_for_the_end_of_the_navigation_the_click_started(
    with_the_profile: AccountChrome, served: list[Any]
) -> None:
    """Answer 15: asked **right after the click**, with nothing awaited by the test, ``landed``
    says the page the navigation ended on — the browser's own, for the address of the ``POST`` —,
    and not the form's page, which is ``/``."""
    web = silent(served)
    opened = await with_the_profile.open(web.origin + "/", only(web), FakeStop())
    await with_the_profile.fill(opened.page, "input[name=acct]", "someone")

    await with_the_profile.click(opened.page, "input[type=submit]")
    landed = await bounded(with_the_profile.landed(opened.page), "the end of a navigation")

    assert (landed.address, landed.status, landed.unanswered) == (
        web.origin + "/login",
        None,
        web.origin + "/login",
    )


async def test_landed_after_a_click_that_starts_no_navigation_waits_for_nothing(
    with_the_profile: AccountChrome, served: list[Any]
) -> None:
    web = silent(served)
    opened = await with_the_profile.open(web.origin + "/", only(web), FakeStop())

    await with_the_profile.click(opened.page, "#word")
    landed = await bounded(with_the_profile.landed(opened.page), "nothing, after no navigation")

    assert (landed.address, landed.status, landed.unanswered) == (web.origin + "/", 200, None)


async def test_the_look_says_the_page_is_the_browser_s_and_for_which_address(
    browser: Any, served: list[Any]
) -> None:
    """The verifier's look on the browser's own page, inside the boundary (answer 16): what it
    read is the browser's, and it says so — found by a mutant that dropped it and lived."""
    web = silent(served)
    opened = await browser.open(web.origin + "/", only(web), FakeStop())
    await clicked_onto_the_error_page(browser, opened.page, "#dead")

    glanced = await browser.glance(opened.page, selector=None, expect=None, seconds=0)

    assert glanced.unanswered == web.origin + "/dead"
    assert glanced.status is None


async def bounded(awaited: Any, what: str) -> Any:
    """``landed`` with a bound: past it the test fails saying what ``landed`` waited for, instead
    of holding the suite — found by a mutant whose end of navigation was never heard, which held
    the run until it was interrupted. Never the measure of anything."""
    try:
        async with asyncio.timeout(bounds.LONG):
            return await awaited
    except TimeoutError:
        pytest.fail(f"landed waited {bounds.LONG:g} s for {what}")
