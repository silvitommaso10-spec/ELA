"""The browser of a test that opens nothing, for the callers of the production registries.

``production_tools`` builds ``browser.read`` and ``browser.act`` like every other tool (M13.4), so
whoever calls it names the browser it wants. Most tests want none: no site declared —
``ELA_BROWSER_SITES=[]``, an answer and not a doubt — and a browser that records what it would have
been asked.
"""

from __future__ import annotations

from ela.testing.fakes import FakeBrowser
from ela.tools.browser import BROWSER_TIMEOUT_SECONDS, Browsing


def no_sites() -> Browsing:
    return Browsing(sites=())


def a_browser() -> FakeBrowser:
    return FakeBrowser()


SECONDS: float = float(BROWSER_TIMEOUT_SECONDS)
"""What the verifiers of the production registries are given: the tool's own time."""
