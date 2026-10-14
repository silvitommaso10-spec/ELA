"""``scripts/misura_m13_10.py`` on a page of the real browser: where the box is in the page, and
which one it is (M13.10, the first measure of WhatsApp Web, 2026-10-14).

Tommaso had the chat with himself open, with the box at the bottom, and the script found no element
to write in: it asked the first ``footer`` of the page only, and for ``contenteditable="true"``
only. Here the box is in the pages a chat can be — a first footer that is not the chat's, no footer
and no pane named ``main``, a box editable in another way —, next to a search box that looks the
same; and the box is **the element written into**, by its focus — never by its text."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import async_playwright

from tests.infrastructure.machine import test_browser as shell
from tests.scripts.test_misura_m13_10 import misura

nothing_left_behind = shell.nothing_left_behind

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
