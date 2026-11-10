"""Three tests the test of the guard runs **in a pytest of their own** (decision 34 of the review
after the red CI of ``56c672c``, 2026-11-10) — never collected by the suite: the name of this file
is not a test module's, and ``tests/test_profile_browser.py`` runs it by its path.

Each takes the fixture a test takes the browser of the profile through:

* one **falls before it builds the browser**: it has one failure, its own — the guard says nothing
  of a test that did not pass, because a failure is named once, by who caused it;
* one **passes and never builds the browser**: it has the error of the guard — it carries the skip
  of a browser it does not take;
* one **builds it and passes**: clean.
"""

from __future__ import annotations

from tests import profile_browser

FELL = "the reason this test fell for, its own"


def test_falls_before_it_builds_the_browser(the_browser_of_the_profile: None) -> None:
    raise RuntimeError(FELL)


def test_passes_and_never_builds_the_browser(the_browser_of_the_profile: None) -> None:
    pass


def test_builds_the_browser_and_passes(the_browser_of_the_profile: None) -> None:
    profile_browser.built_through_the_fixture()
