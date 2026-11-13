"""Whether a call could start in a place — the «partirebbe» of a policy, place by place (M13.14,
ADR 0068; proposal 7).

The birth of a policy of a capability whose scope is one value per call asks the tool about each
place of the scope. The two gestures answer for a site: the browser is there, on a system it runs
on, and with your accounts the folder is declared, safe and free — the site itself was judged by
the birth, and nothing resolves it. **A tool that cannot look at a place refuses**: the default of
:class:`~ela.tools.base.Tool` is a refusal with its own code, never a «yes». ``fs.write``'s answer
is in ``tests/tools/test_fs_protected.py``.
"""

from __future__ import annotations

import pytest

from ela.ports import PROFILE_WINDOW, BrowserUnsupported, ProfileUndeclared, Prospect
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakeTaskPages,
)
from ela.tools.account import PROFILE_BUSY, PROFILE_UNDECLARED, AccountActTool
from ela.tools.base import PLACE_UNSEEN
from ela.tools.browser import (
    NOT_INSTALLED,
    UNSUPPORTED_SYSTEM,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
)
from ela.tools.echo import EchoTool

SITES = Browsing(sites=("httpbin.org", "testpages.eviltester.com"))


def act(browser: FakeBrowser) -> BrowserActTool:
    return BrowserActTool(SITES, browser, FakeClock(), FakeIdGenerator(), pages=FakeTaskPages())


def act_as_you(browser: FakeAccountBrowser) -> AccountActTool:
    return AccountActTool(SITES, browser, FakeClock(), FakeIdGenerator(), pages=FakeTaskPages())


async def test_an_act_could_start_on_a_site_when_the_browser_is_there() -> None:
    browser = FakeBrowser()

    looked = await act(browser).prospect_place("httpbin.org")

    assert looked == Prospect()
    assert browser.opened == [], "asking opens nothing"


async def test_an_act_with_no_browser_installed_could_start_nowhere() -> None:
    looked = await act(FakeBrowser(installed=False)).prospect_place("httpbin.org")

    assert looked.refusal is not None and looked.refusal.code == NOT_INSTALLED
    assert looked.refusal.tool_name == act(FakeBrowser()).name
    assert "playwright install --only-shell chromium" in looked.refusal.message


async def test_an_act_on_a_system_where_the_browser_does_not_run_could_start_nowhere() -> None:
    browser = FakeBrowser()
    browser.raising["installed"] = BrowserUnsupported("Plan 9")

    looked = await act(browser).prospect_place("httpbin.org")

    assert looked.refusal is not None and looked.refusal.code == UNSUPPORTED_SYSTEM


async def test_an_act_as_you_could_start_when_the_folder_is_declared_and_free() -> None:
    browser = FakeAccountBrowser()

    looked = await act_as_you(browser).prospect_place("httpbin.org")

    assert looked == Prospect()
    assert browser.opened == []


async def test_an_act_as_you_with_the_folder_held_could_not_start_now() -> None:
    """Retryable, as before a question: what holds the folder ends."""
    looked = await act_as_you(FakeAccountBrowser(holder=PROFILE_WINDOW)).prospect_place(
        "httpbin.org"
    )

    assert looked.refusal is not None and looked.refusal.code == PROFILE_BUSY
    assert looked.refusal.retryable is True


async def test_an_act_as_you_with_no_folder_declared_could_start_nowhere() -> None:
    browser = FakeAccountBrowser()
    browser.raising["occupied"] = ProfileUndeclared("ELA_BROWSER_PROFILE_DIR is not set")

    looked = await act_as_you(browser).prospect_place("httpbin.org")

    assert looked.refusal is not None and looked.refusal.code == PROFILE_UNDECLARED
    assert looked.refusal.retryable is False


@pytest.mark.parametrize("which", ["echo", "browser.read"])
async def test_a_tool_that_cannot_look_at_a_place_refuses(which: str) -> None:
    """The default of ``Tool``: a refusal with its own code — a default «it would start» would
    be a defence that only looks active."""
    tool = (
        EchoTool(FakeClock(), FakeIdGenerator())
        if which == "echo"
        else BrowserReadTool(
            SITES, FakeBrowser(), FakeClock(), FakeIdGenerator(), pages=FakeTaskPages()
        )
    )

    looked = await tool.prospect_place("anything")

    assert looked.target is None
    assert looked.refusal is not None and looked.refusal.code == PLACE_UNSEEN
    assert looked.refusal.tool_name == tool.name
    assert looked.refusal.message == (
        f"{tool.capability_id} cannot say whether a call could start in a place"
    )
