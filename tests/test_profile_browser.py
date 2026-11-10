"""A test that takes the browser of the profile is skipped where the product does not have it —
**derived in one place, and never written in the test** (decision 27 of the review after the red CI
of ``56c672c``, 2026-11-10).

On 2026-11-03 three new tests of M13.9b took the browser of the profile through its fixture and
carried no ``skipif`` of their own: on the ubuntu runner they fell with ``BrowserUnsupported:
Linux``, and nobody saw it for a week — the tests beside them each carried a condition written by
hand, and a new test had to remember to copy it. Reproduced on this Mac on 2026-11-10 with ``make
check-linux`` at ``56c672c``: «3 failed, 12110 passed, 163 skipped», the numbers of the runner.

So the skip is put by **where a test takes that browser** (``tests/profile_browser.py``):

* the condition is the product's own — :data:`ela.infrastructure.machine.account.SUPPORTED`, the
  one the adapter raises ``BrowserUnsupported`` by —, never a system written in a test;
* every test whose fixtures reach :data:`~tests.profile_browser.TAKEN` — the fixture the folder of
  a test's profile asks for — is marked at collection, a ``skipif`` that shows in the summary;
* and the browser of the profile **is built only through that fixture**: built outside it, it is
  an error on every system, this Mac included — a new test cannot forget what it cannot leave out.

**On a system that has the browser nothing is skipped and nothing is caught**: there a
``BrowserUnsupported`` is a red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ela.infrastructure.machine.account import SUPPORTED
from tests import profile_browser
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine import test_the_boundary as bounded
from tests.infrastructure.machine import test_what_the_gate_does_not_stop as gate

nothing_left_behind = shell.nothing_left_behind
profile = account.profile


def derived(node: pytest.Item) -> list[pytest.Mark]:
    """The marks of ``node`` that are the one skip of the browser of the profile."""
    return [mark for mark in node.iter_markers("skipif") if mark == profile_browser.ON_A_MAC.mark]


def test_the_skip_is_the_product_s_own_condition_and_no_system_written_in_a_test() -> None:
    """Skipped exactly where the adapter would raise ``BrowserUnsupported`` — and run where it
    would not: there the exception, if it comes, is a red."""
    assert profile_browser.where_it_is("Linux").mark.args == (True,)
    assert profile_browser.where_it_is("Windows").mark.args == (True,)
    assert profile_browser.where_it_is(SUPPORTED).mark.args == (False,)
    assert profile_browser.ON_A_MAC.mark == profile_browser.where_it_is(account.SYSTEM).mark


def test_a_test_that_takes_the_browser_of_the_profile_is_marked_and_wrote_nothing(
    request: pytest.FixtureRequest, profile: Path
) -> None:
    """This test carries no mark of its own and takes the folder of a profile: the mark is on it.
    Where the product does not have the browser it does not run — and says why in the summary."""
    assert len(derived(request.node)) == 1


def test_a_test_that_does_not_take_it_is_not_marked(request: pytest.FixtureRequest) -> None:
    assert derived(request.node) == []


def test_the_browser_of_the_profile_is_built_only_through_its_fixture(tmp_path: Path) -> None:
    """Outside a test that took the fixture the browser is not built at all, on any system: the
    one way to take it is the way that carries the skip."""
    with pytest.raises(AssertionError, match=profile_browser.TAKEN):
        account.chrome(tmp_path / "a-profile-of-nobody")


def test_inside_a_test_that_took_the_fixture_it_is_built(profile: Path) -> None:
    assert account.chrome(profile) is not None


def test_the_conditions_once_written_by_hand_are_the_one_source() -> None:
    """The three places that each wrote ``SYSTEM != "Darwin"`` (decision 27: the tests beside pass
    to the same source)."""
    assert account.pytestmark is profile_browser.ON_A_MAC
    assert bounded.ON_A_MAC is profile_browser.ON_A_MAC
    assert gate.ON_A_MAC is profile_browser.ON_A_MAC
    assert account.SYSTEM is profile_browser.SYSTEM


class Item:
    """What the collection hands to the hook, as far as the hook reads it."""

    def __init__(self, *fixtures: str) -> None:
        self.fixturenames = list(fixtures)
        self.marks: list[pytest.MarkDecorator] = []

    def add_marker(self, mark: pytest.MarkDecorator) -> None:
        self.marks.append(mark)


def test_the_collection_marks_every_test_whose_fixtures_reach_the_one_fixture() -> None:
    takes, does_not, no_fixtures = Item("served", profile_browser.TAKEN), Item("served"), object()

    profile_browser.marked([takes, does_not, no_fixtures])

    assert takes.marks == [profile_browser.ON_A_MAC]
    assert does_not.marks == []
