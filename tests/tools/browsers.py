"""The browser of a test that opens nothing, for the callers of the production registries.

``production_tools`` builds ``browser.read`` and ``browser.act`` like every other tool (M13.4), so
whoever calls it names the browser it wants. Most tests want none: no site declared —
``ELA_BROWSER_SITES=[]``, an answer and not a doubt — and a browser that records what it would have
been asked.
"""

from __future__ import annotations

from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakeClock
from ela.tools.browser import BROWSER_TIMEOUT_SECONDS, Browsing
from ela.tools.vault import VaultDoor


def no_sites() -> Browsing:
    return Browsing(sites=())


def a_browser() -> FakeBrowser:
    return FakeBrowser()


def an_account_browser() -> FakeAccountBrowser:
    """The browser with the profile of a test that opens nothing (M13.9): another object than
    :func:`a_browser`'s, as in production it is another browser."""
    return FakeAccountBrowser()


def a_door() -> VaultDoor:
    """The door of a vault nobody declared: every use says which line to write, and nothing is
    launched."""
    return VaultDoor(None, None, None, clock=FakeClock())


SECONDS: float = float(BROWSER_TIMEOUT_SECONDS)
"""What the verifiers of the production registries are given: the tool's own time."""
