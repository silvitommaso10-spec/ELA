"""What the gate of M13.4 did not stop — the red tests of 2026-10-12, **as they were written**
(M13.9, decision 105b; in the tree since M13.4f, decision 110).

Found while measuring what a site sees, and parked then outside the suite: the repair was of the
gate of M13.4, with its own letter and its own ADR. They are the red commit M13.4f starts from —
their bodies untouched, this head rewritten —, and ``test_the_boundary.py`` holds the rest.

1. **A chain of redirects was looked at once.** The gate fetched the first document of a
   navigation and handed an admitted redirect to the page; the request after it was the browser's
   own, and no route was called for it. A second redirect that left the boundary was followed:
   the request reached the other site, with what its address carries and with the cookies the
   profile holds for it.
2. **The cookies of a document were chosen twice, by two programs.** When the browser would send
   none — a form sent across sites, where ``SameSite`` says no — the driver that fetched the
   document added every cookie it held for that address.
3. **No tool looked at where the page was**, but the login when it opened its page: a read
   returned the text of the page of a site nobody declared, and an action typed on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from ela.infrastructure.machine.browser import PlaywrightBrowser
from ela.testing.fakes import FakeStop, FakeTaskPages
from ela.tools.browser import boundary
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine.test_browser import Site, site

served = shell.served
nothing_left_behind = shell.nothing_left_behind
browser = shell.browser
profile = account.profile

ON_A_MAC = pytest.mark.skipif(
    account.SYSTEM != "Darwin", reason="the browser with the profile is Chrome for Testing on a Mac"
)


def chained(served: list[Site]) -> tuple[Site, Site]:
    """A site whose first address redirects on the site, and from there off the boundary."""
    other = site(served, {"/": (200, {}, "<p>altrove</p>")})
    web = site(
        served,
        {
            "/": (302, {"Location": "/hop"}, ""),
            "/hop": (302, {"Location": other.origin + "/?chiave=segreta"}, ""),
        },
    )
    return web, other


async def test_the_second_redirect_of_a_chain_off_the_boundary_is_not_followed(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    web, other = chained(served)

    opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
    await browser.close(opened.page)

    assert other.requests == [], "the request was never sent"
    assert opened.left is not None, "and the step says where the page tried to go"


@ON_A_MAC
async def test_with_the_profile_the_second_redirect_off_the_boundary_is_not_followed(
    profile: Path, served: list[Site]
) -> None:
    web, other = chained(served)
    made = account.chrome(profile)

    opened = await made.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
    await made.close(opened.page)

    assert other.requests == [], "the request was never sent"
    assert opened.left is not None


CROSS = """
<form method="post" action="{there}/send"><input name="x" value="1">
<input id="post" type="submit" value="send"></form>
"""
GIVEN = {"Set-Cookie": "strict=1; Max-Age=3600; Path=/; SameSite=Strict"}


def two_sites(served: list[Site]) -> tuple[Site, Site]:
    """Two sites for a browser: one by its name, one by its address. The second gives a cookie
    that is not to travel with a request another site started."""
    there = site(served, {"/set": (200, GIVEN, "<p>set</p>"), "/send": (200, {}, "<p>sent</p>")})
    here = site(served, {"/": (200, {}, CROSS.format(there=there.origin))})
    here.origin = here.origin.replace("127.0.0.1", "localhost")
    return here, there


def carried(there: Site) -> str:
    """The cookies the form arrived with: of the one ``POST`` the site received."""
    (sent,) = [at for at, asked in enumerate(there.requests) if asked == "POST /send"]
    return there.cookies[sent]


@ON_A_MAC
async def test_the_browser_alone_sends_no_strict_cookie_with_a_form_from_another_site(
    profile: Path, served: list[Site]
) -> None:
    """The precondition of the next test: what the browser does with no gate."""
    here, there = two_sites(served)
    profile.mkdir(mode=0o700)
    options = account.chrome(profile)._launch()

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(str(profile), **options)
        page = context.pages[0]
        await page.goto(there.origin + "/set")
        await page.goto(here.origin + "/")
        await page.locator("#post").click()
        await page.get_by_text("sent").wait_for(state="visible", timeout=10_000)
        await context.close()

    assert carried(there) == "", "a form another site sent carries no cookie that says Strict"


@ON_A_MAC
async def test_through_the_gate_a_form_from_another_site_carries_no_strict_cookie(
    profile: Path, served: list[Site]
) -> None:
    here, there = two_sites(served)
    made = account.chrome(profile)
    everywhere = account.everywhere

    opened = await made.open(there.origin + "/set", everywhere, FakeStop())
    await made.close(opened.page)
    opened = await made.open(here.origin + "/", everywhere, FakeStop())
    await made.click(opened.page, "#post")
    glanced = await made.glance(opened.page, selector=None, expect="sent", seconds=10)

    assert glanced.shown is True
    assert carried(there) == "", "what the browser would not send, the gate does not add"


# ----------------------------------------------------------------------------------------
# What the tools do with a page that ended off the boundary (found by the re-read of 2026-10-12)
# ----------------------------------------------------------------------------------------
#
# The step is told ``browser.left_site`` when **the gate refused** a navigation; nothing compares
# where the page **is** with the site of the question, except the login when it opens its page.
# So a chain that leaves at its second hop is not only a request that arrives: a read returns the
# text of the page of the other site, and an action types on it.


def chain_to(other: Site, path: str, served: list[Site]) -> Site:
    return site(
        served,
        {
            "/": (302, {"Location": "/hop"}, ""),
            "/hop": (302, {"Location": other.origin + path}, ""),
        },
    )


async def test_a_read_does_not_return_the_text_of_a_site_nobody_declared(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    from ela.domain import ExecutionStatus
    from ela.permissions import BROWSER_READ
    from ela.testing.fakes import FakeIdGenerator
    from ela.tools.browser import LEFT_SITE, BrowserReadTool

    other = site(served, {"/altro": (200, {}, "<h1>Il testo di un sito non dichiarato</h1>")})
    web = chain_to(other, "/altro?chiave=segreta", served)
    arguments = {"site": "sito0.example", "path": "/", "selector": "h1", "purpose": "x"}

    result = await BrowserReadTool(
        shell.browsing(web), browser, shell.CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    ).execute(shell.decision(BROWSER_READ), arguments, FakeStop())
    page = result.output.get("page")
    if isinstance(page, str):
        await browser.close(page)

    assert "non dichiarato" not in str(result.output), "nothing of that page is in the result"
    assert "chiave=segreta" not in str(result.output)
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == LEFT_SITE


FOREIGN_FORM = """
<form method="post" action="/preso"><input id="nome" name="nome">
<button id="invia">Invia</button></form>
<script>
document.addEventListener("input", (event) => navigator.sendBeacon("/event", event.target.value));
</script>
"""


async def test_an_action_types_nothing_on_the_page_of_a_site_nobody_declared(
    browser: PlaywrightBrowser, served: list[Site]
) -> None:
    from ela.permissions import BROWSER_ACT
    from ela.testing.fakes import FakeIdGenerator
    from ela.tools.browser import LEFT_SITE, BrowserActTool

    other = site(served, {"/modulo": (200, {}, FOREIGN_FORM)})
    web = chain_to(other, "/modulo", served)
    arguments = {
        "site": "sito0.example",
        "path": "/",
        "fill": [["#nome", "ciò che il piano scrive"]],
        "click": "#invia",
        "expect_text": "Grazie",
        "purpose": "x",
    }

    result = await BrowserActTool(
        shell.browsing(web), browser, shell.CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    ).execute(shell.decision(BROWSER_ACT), arguments, FakeStop())
    page = result.output.get("page")
    if isinstance(page, str):
        await browser.close(page)

    assert other.events == [], "what the plan writes was not typed on a page of that site"
    assert "POST /preso" not in other.requests
    assert result.error is not None and result.error.code == LEFT_SITE
    assert result.output.get("gestures", 0) == 0


@ON_A_MAC
async def test_with_the_profile_the_second_hop_carries_no_cookie_to_a_site_off_the_boundary(
    profile: Path, served: list[Site]
) -> None:
    """With the profile the request that should not leave is one that carries the user's
    session there."""
    kept = {"Set-Cookie": "session=of-the-user; Max-Age=3600; Path=/"}
    other = site(served, {"/": (200, kept, "<p>altrove</p>")})
    web = chain_to(other, "/", served)
    made = account.chrome(profile)

    first = await made.open(other.origin + "/", account.everywhere, FakeStop())
    await made.close(first.page)
    opened = await made.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
    await made.close(opened.page)

    assert other.cookies[1:] == [], (
        "no request after the visit that gave the cookie — and so no cookie carried there"
    )
    assert other.requests == ["GET /"]
