"""Every member of the browser's port that uses a page asks the boundary where the page is
(M13.4f, ADR 0064 §4).

The boundary of a page is the function its tool hands to ``open``. Until M13.4f only the gate
asked it, about a request; since then **whoever holds the page asks it at every use**, about
where the page is, and a use on a page that is outside raises ``LeftSite``. A rule of behaviour,
not of the tree: it is proved by calling — every member of the port that is given a page, found
by its signature and never listed, on an implementation whose page is outside its boundary.

Here the fakes, which stand in for the adapters in every test of a tool: **a fake that forgets
the predicate in one member would let a tool's test pass on a page the real browser refuses**.
The real adapters are walked with the real browsers
(``tests/infrastructure/machine/test_the_boundary.py``), which reads :func:`uses` from here.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import pytest

from ela.ports import AccountBrowser, Browser, Secret
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakeStop

NOT_A_USE = {
    "keep": "hands the page to the verifier: it reads nothing and writes nothing",
    "close": "ends the page",
    "another": "says what the gate stopped of another page, and nothing of this one",
}
"""The members that are given a page and do not use it, each with its reason."""

ASKED_BEFORE_ONLY = {
    "left": "reads nothing of the page: it says what the gate refused, and nothing is thrown away",
}
"""The uses that ask the boundary before and not after, each with its reason."""


def given_a_page(port: type) -> list[str]:
    """The members of ``port`` whose first argument is a page."""
    return sorted(
        name
        for name, member in inspect.getmembers(port, inspect.isfunction)
        if list(inspect.signature(member).parameters)[:2] == ["self", "page"]
    )


def uses(port: type) -> list[str]:
    """The members of ``port`` that use a page: every one that is given a page, but
    :data:`NOT_A_USE`."""
    return [name for name in given_a_page(port) if name not in NOT_A_USE]


def _arguments(member: Any) -> dict[str, object]:
    """Something to call ``member`` with, by the names of its parameters after the page."""
    values: dict[str, object] = {"selector": "#x", "expect": "x", "seconds": 0.0}
    parameters = inspect.signature(member).parameters
    if "value" in parameters:
        wrapped = "Secret" in str(parameters["value"].annotation)
        values["value"] = Secret("a value of this test") if wrapped else "a value"
    return {name: values[name] for name in parameters if name not in ("self", "page")}


async def unguarded(made: Callable[[], Any], port: type) -> list[str]:
    """The uses of a page ``made`` makes on a page that is outside its boundary: each member
    that did not raise ``LeftSite``, with what it did instead."""
    from ela.ports import LeftSite

    found: list[str] = []
    admitted = [True]
    for name in uses(port):
        browser = made()
        admitted[0] = True
        opened = await browser.open("https://sito.example/", lambda url: admitted[0], FakeStop())
        await browser.keep(opened.page)
        admitted[0] = False
        member = getattr(browser, name)
        try:
            await member(opened.page, **_arguments(getattr(port, name)))
        except LeftSite:
            continue
        except Exception as error:  # noqa: BLE001 — said, as what the member did instead
            found.append(f"{name}: {type(error).__name__}")
            continue
        found.append(name)
    return found


class Closing:
    """A boundary that admits every address until it has been asked ``closes_at`` times: the
    page that is inside when a use begins and outside when it ends, built and not raced for."""

    def __init__(self) -> None:
        self.asked = 0
        self.closes_at: int | None = None

    def __call__(self, address: str) -> bool:
        self.asked += 1
        return self.closes_at is None or self.asked < self.closes_at


async def unguarded_after(made: Callable[[], Any], port: type) -> list[str]:
    """The uses of a page ``made`` makes on a page that ends outside its boundary **while the
    use is made**: each member that did not raise ``LeftSite`` saying the use was made, with
    what it did instead."""
    from ela.ports import LeftSite

    found: list[str] = []
    for name in uses(port):
        if name in ASKED_BEFORE_ONLY:
            continue
        browser, allowed = made(), Closing()
        opened = await browser.open("https://sito.example/", allowed, FakeStop())
        await browser.keep(opened.page)
        allowed.closes_at = allowed.asked + 2
        try:
            await getattr(browser, name)(opened.page, **_arguments(getattr(port, name)))
        except LeftSite as elsewhere:
            if not elsewhere.made:
                found.append(f"{name}: found elsewhere before the use, not after")
            continue
        except Exception as error:  # noqa: BLE001 — said, as what the member did instead
            found.append(f"{name}: {type(error).__name__}")
            continue
        found.append(name)
    return found


def test_the_uses_of_a_page_are_found_by_the_port_and_the_exceptions_are_its_members() -> None:
    """The control of the derivation: it finds the gestures and the readings nobody doubts,
    and no exception names a member the port does not have."""
    assert {"count", "field", "fill", "click", "text", "title", "glance"} <= set(uses(Browser))
    assert set(uses(Browser)) <= set(uses(AccountBrowser))
    assert set(NOT_A_USE) <= set(given_a_page(Browser))
    assert set(ASKED_BEFORE_ONLY) <= set(uses(Browser))


@pytest.mark.parametrize(
    ("made", "port"), [(FakeBrowser, Browser), (FakeAccountBrowser, AccountBrowser)]
)
async def test_every_use_of_a_page_by_a_fake_asks_the_boundary(
    made: Callable[[], Any], port: type
) -> None:
    assert await unguarded(made, port) == []


class Forgetful(FakeBrowser):
    """A fake that reads the title of a page without asking where the page is."""

    async def title(self, page: str) -> str:
        return self.page.title


async def test_a_fake_that_forgets_the_boundary_in_one_member_is_found() -> None:
    assert await unguarded(Forgetful, Browser) == ["title"]


@pytest.mark.parametrize(
    ("made", "port"), [(FakeBrowser, Browser), (FakeAccountBrowser, AccountBrowser)]
)
async def test_every_use_of_a_page_by_a_fake_asks_the_boundary_again_once_it_is_made(
    made: Callable[[], Any], port: type
) -> None:
    """The second half of the predicate (decision 122): what was read on a page that ended
    elsewhere meanwhile is thrown away, and a gesture is said as made."""
    assert await unguarded_after(made, port) == []


class ForgetfulAfterwards(FakeBrowser):
    """A fake that asks where the page is before reading its title, and not after."""

    async def title(self, page: str) -> str:
        self._on(page, "title")
        return self.page.title


async def test_a_fake_that_does_not_ask_again_in_one_member_is_found() -> None:
    assert await unguarded(ForgetfulAfterwards, Browser) == []  # the control: it asks before
    assert await unguarded_after(ForgetfulAfterwards, Browser) == ["title"]
