"""``scripts/misura_m13_10.py`` on a page of the real browser (M13.10, after the first measure of
WhatsApp Web, 2026-10-14).

In the first measure the loading bar stood still and empty for two hours and no chat came
(decision 65). The script had two defects that a page with the chat would have met: it asked the
first ``footer`` of the page only, and for ``contenteditable="true"`` only. Here the box is in the
pages a chat can be — a first footer that is not the chat's, no footer and no pane named ``main``,
a box editable in another way —, next to a search box that looks the same; and the box is **the
element written into**, by its focus — never by its text.

And what says why the box has not come (decision 63): the errors of the console by their type, and
what the real gate refused and the browser announced, by origin and type — never a text."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from ela.infrastructure.machine import browser as adapter
from ela.testing.fakes import FakeStop
from ela.tools.browser import boundary
from tests.infrastructure.machine import test_browser as shell
from tests.scripts.test_misura_m13_10 import misura

nothing_left_behind = shell.nothing_left_behind
browser = shell.browser
served = shell.served
LONG = 20.0
"""The bound of a wait for an event of the browser: past it the test fails, saying what it waited
for. Never the measure of anything."""

ENVIRONMENT = {"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"}
STYLE = "<style>[contenteditable] { display: block; min-height: 20px; width: 200px; }</style>"
SEARCH = '<div contenteditable="true" role="textbox" data-tab="3"></div>'
LOOKALIKE = '<div contenteditable="true" role="textbox"></div>'
WRITTEN_INTO = "<script>document.getElementById('written').focus()</script>"
"""Where Tommaso wrote a character: the box has the focus, as it has in the window. Its ``id`` is
the test's mark, which the script does not write selectors from."""


def box(editable: str = "true", tab: str = ' data-tab="10"') -> str:
    return f'<div id="written" contenteditable="{editable}" role="textbox"{tab}></div>'


PAGES = {
    "the first footer of the page is not the chat's": (
        f'<div id="side"><header>{SEARCH}</header><footer><span></span></footer></div>'
        f'<div id="main"><footer>{box()}</footer></div>'
    ),
    "no footer and no pane named main": f"<div>{SEARCH}</div><div><div>{box()}</div></div>",
    "a box editable in another way than true": (
        f'<div id="side">{SEARCH}</div>'
        f'<div id="main"><footer>{box("plaintext-only")}</footer></div>'
    ),
    "a box like the search box in all but its place": (
        f'<div id="side">{LOOKALIKE}</div><div id="main"><footer>{box(tab="")}</footer></div>'
    ),
}


@pytest.fixture
async def page() -> AsyncIterator[Any]:
    """A page of the empty browser, launched with the options of its adapter."""
    async with async_playwright() as playwright:
        launched = await playwright.chromium.launch(
            headless=True,
            env=ENVIRONMENT,
            handle_sigint=False,
            handle_sigterm=False,
            handle_sighup=False,
        )
        try:
            yield await launched.new_page()
        finally:
            await launched.close()


@pytest.mark.parametrize("shape", PAGES)
async def test_the_box_is_the_element_written_into_wherever_it_is_and_its_selector_finds_it_alone(
    page: Any, shape: str
) -> None:
    await page.set_content(f"{STYLE}{PAGES[shape]}{WRITTEN_INTO}")

    writable, _, chosen = await misura.the_box(page)

    assert len(writable) == 2, "the whole page is searched: the search box is seen too"
    assert chosen is not None
    assert await page.locator(chosen).get_attribute("id") == "written"


async def until(look: Any, what: str) -> None:
    """Wait for something a test can only see by looking, and say what it was if it never came."""
    deadline = asyncio.get_running_loop().time() + LONG
    while not look():
        if asyncio.get_running_loop().time() > deadline:
            pytest.fail(f"never happened within {LONG:g} s: {what}")
        await asyncio.sleep(0.02)


ERRORS = (
    "<script>console.error('Mario 393331234567'); fetch('http://127.0.0.1:9/x');"
    "Promise.reject(new DOMException('Mario', 'SecurityError'));</script>"
)


async def test_the_errors_of_the_console_are_seen_by_their_type_and_never_by_their_text(
    page: Any,
) -> None:
    """Those before the script listens too — the page has been loading since it was opened — and
    those after."""
    await page.set_content(ERRORS)
    seen = misura.Seen()

    await misura.listening(page, seen)
    await until(lambda: len(seen.errors) >= 4, "the four kinds of error of the page")
    await page.evaluate("() => setTimeout(() => { throw new RangeError('Mario'); }, 0)")
    await until(lambda: "un'eccezione RangeError" in seen.errors, "the error after listening")

    assert seen.errors["console.error"] == 1
    assert seen.errors["il registro del browser: network"] >= 1
    assert seen.errors["un'eccezione DOMException"] == 1
    assert seen.errors["un'eccezione TypeError"] == 1, "the fetch that failed, never caught"
    written = "\n".join(seen.lines())
    assert "Mario" not in written and "393331234567" not in written


SHARED = (
    "<p id='s'>waiting</p><script>const w = new SharedWorker('/shared.js');"
    "w.port.onmessage = (e) => document.querySelector('#s').textContent = e.data;"
    "w.port.start();</script>"
)
ASKS = (
    "onconnect = (e) => fetch('/asked').then(() => e.ports[0].postMessage('done'),"
    " () => e.ports[0].postMessage('failed'));"
)


async def test_what_the_real_gate_refuses_and_the_browser_announces_is_seen_by_origin_and_type(
    browser: Any, served: list[Any]
) -> None:
    """A shared worker of the page: its script is the page's request and leaves, what it asks for
    is refused (ADR 0064 §2) — one of the candidates of the bar that stood still (decision 62)."""
    web = shell.site(
        served,
        {
            "/": (200, {}, SHARED),
            "/shared.js": (200, {"Content-Type": "text/javascript"}, ASKS),
            "/asked": (200, {}, "x"),
        },
    )
    seen = misura.Seen()

    undo = misura.watching(adapter._Gate, seen)
    try:
        opened = await browser.open(
            web.origin + "/?phone=393331234567", boundary(frozenset({web.origin})), FakeStop()
        )
        await until(lambda: web.origin in seen.refused, "the gate refused what the worker asked")
        said = await browser.text(opened.page, "#s")
    finally:
        undo()

    assert ("shared_worker", web.origin) in seen.targets
    assert said in ("waiting", "failed")
    written = "\n".join(seen.lines())
    assert "393331234567" not in written and "phone" not in written
