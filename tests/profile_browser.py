"""Where a test takes the browser of the profile, and **the one place its skip is derived**
(decision 27 of the review after the red CI of ``56c672c``, 2026-11-10).

The browser with the user's accounts is Chrome for Testing, and the product has it on one system:
:data:`ela.infrastructure.machine.account.SUPPORTED`, the condition its adapter raises
``BrowserUnsupported`` by. A test of the real one cannot run anywhere else — and until 2026-11-10
each such test said so with a condition written by hand, which a new test had to remember to copy.
Three of M13.9b did not, and the ubuntu runner was red for a week.

* :func:`where_it_is` is the skip, **from the product's condition**: no system is written here.
* :data:`TAKEN` is the fixture every test takes that browser through — ``tests/conftest.py`` has
  it, and the folder of a test's profile asks for it (``profile`` in
  ``tests/infrastructure/machine/test_account_browser.py``). The collection marks every test whose
  fixtures reach it (:func:`marked`): a ``skipif``, which shows in the summary with its reason.
* :func:`built_through_the_fixture` is asked by the one function that builds the real browser of
  the profile in a test: **outside a test that took the fixture it raises, on every system** —
  so a new test cannot take the browser and leave the skip out.
* And the other way round (:func:`taken`): **a test that took the fixture and never built that
  browser is an error where it runs**. The skip is of the browser, not of a folder: the first
  form of this, on 2026-11-10, marked every test that took the folder of a profile, and three
  tests of the *empty* browser that took it — two for a helper that uses it only when the browser
  is the profile's, one for nothing — stopped running on Linux, where they had always run. Nothing
  said so: the skips were found by comparing two summaries line by line. Now the Mac says it.

**Nothing is skipped by catching**: where the product has the browser, a ``BrowserUnsupported``
is a red.
"""

from __future__ import annotations

import platform
from collections.abc import Iterable, Iterator
from typing import Final

import pytest

from ela.infrastructure.machine.account import SUPPORTED

SYSTEM: Final = platform.system()
"""The system these tests run on — or the one ``tests/foreign_machine.py`` pretends."""
REASON: Final = "the browser with the profile is Chrome for Testing on a Mac"
TAKEN: Final = "the_browser_of_the_profile"
"""The name of the fixture a test takes the browser of the profile through."""

NEVER_BUILT: Final = (
    f"a test took the fixture {TAKEN} — the folder of a profile asks for it — and never built the "
    "browser of the profile: it is skipped where the product does not have that browser, and it "
    "could run there. A test of the empty browser takes `nothing_left_behind`, or asks for the "
    "folder by name only when its browser is the profile's. (If the test failed before it built "
    "the browser, read that failure first.)"
)

_taking: list[int] = []
"""One entry while a test that took :data:`TAKEN` runs — how many times it built the browser of
the profile: a worker runs one test at a time."""


def where_it_is(system: str) -> pytest.MarkDecorator:
    """The skip of a test that takes the browser of the profile, on ``system``: true exactly
    where the product's adapter would raise ``BrowserUnsupported``."""
    return pytest.mark.skipif(system != SUPPORTED, reason=REASON)


ON_A_MAC: Final = where_it_is(SYSTEM)
"""The one mark: on the tests the collection finds, on a parameter, on a whole module."""


def marked(items: Iterable[object]) -> None:
    """Put :data:`ON_A_MAC` on every collected test whose fixtures reach :data:`TAKEN`."""
    for item in items:
        if TAKEN in getattr(item, "fixturenames", ()):
            item.add_marker(ON_A_MAC)  # type: ignore[attr-defined]


def taken() -> Iterator[None]:
    """What the fixture :data:`TAKEN` is, while its test runs: the browser of the profile may be
    built — and **has to be**. A test that ends without having built it took the skip and not the
    browser, and that is an error here, where it ran: on the systems of the skip it would be a
    test that stopped running, and nothing would say so."""
    _taking.append(0)
    yield
    if not _taking.pop():
        raise AssertionError(NEVER_BUILT)


def built_through_the_fixture() -> None:
    """Refuse to build the browser of the profile outside a test that took :data:`TAKEN` — and
    count the build for the test that took it."""
    if not _taking:
        raise AssertionError(
            f"a test builds the browser of the profile without the fixture {TAKEN}: take the "
            "folder of its profile from the `profile` fixture, which asks for it — the skip of "
            "the systems the product does not have that browser on comes with it"
        )
    _taking[-1] += 1
