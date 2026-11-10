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
  an error on every system, this Mac included — a new test cannot forget what it cannot leave out;
* and **a test that took the fixture and never built that browser is an error too**, where it
  runs: the skip is of the browser, not of a folder. The first form of this marked every test
  that took the folder of a profile, and three tests of the *empty* browser stopped running on
  Linux (found on 2026-11-10 by comparing the skips of two ``make check-linux``, line by line,
  before anything was pushed).

**And the guard speaks only of a test that passed** (decision 34): one that fell before it built
the browser has its own reason already, and a second error at the closing of the fixture would
cover it. A failure is named once, by who caused it — so the report of the test's own phase is put
on the test as it runs (the hook of ``tests/conftest.py``), and the fixture reads it.

**On a system that has the browser nothing is skipped and nothing is caught**: there a
``BrowserUnsupported`` is a red.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ela.infrastructure.machine.account import SUPPORTED
from tests import profile_browser, profile_browser_cases
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine import test_the_boundary as bounded
from tests.infrastructure.machine import test_what_the_gate_does_not_stop as gate

nothing_left_behind = shell.nothing_left_behind
profile = account.profile

REPO = Path(__file__).resolve().parent.parent
CASES = "tests/profile_browser_cases.py"


def it_passed() -> bool:
    return True


def it_fell() -> bool:
    return False


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
    """This test carries no mark of its own, takes the folder of a profile and builds its browser:
    the mark is on it. Where the product does not have the browser it does not run — and says why
    in the summary."""
    assert account.chrome(profile) is not None
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


def test_a_test_that_took_the_fixture_and_never_built_the_browser_is_an_error() -> None:
    """The other half. A test that takes the folder of a profile and never builds its browser
    carries a skip that is not its own: where the product has no such browser it would stop
    running, and only a count in a summary would change. So it is an error where it does run."""
    taking = profile_browser.taken(it_passed)
    next(taking)

    with pytest.raises(AssertionError, match="never built the browser of the profile"):
        next(taking)


def test_a_test_that_took_the_fixture_and_built_the_browser_ends_clean() -> None:
    taking = profile_browser.taken(it_passed)
    next(taking)
    profile_browser.built_through_the_fixture()

    with pytest.raises(StopIteration):
        next(taking)


def test_the_guard_says_nothing_of_a_test_that_did_not_pass() -> None:
    """Decision 34. It fell before it built the browser, and it has its reason: the closing of the
    fixture adds no second error to it."""
    taking = profile_browser.taken(it_fell)
    next(taking)

    with pytest.raises(StopIteration):
        next(taking)


def test_the_reports_of_a_test_are_put_on_it_as_it_runs(request: pytest.FixtureRequest) -> None:
    """The standard hook: while the test runs its set-up is reported already, and its own phase
    is not — which is what the fixture reads at its closing, when it is."""
    reports = request.node.stash[profile_browser.REPORTS]

    assert reports["setup"].passed and "call" not in reports
    assert profile_browser.passed(request.node) is False, "not yet: it is running"


@profile_browser.ON_A_MAC
def test_a_test_that_falls_has_its_own_error_alone_and_one_that_passes_idle_the_guard_s() -> None:
    """In a pytest of their own, with the hook and the fixture of this suite: where a test that
    takes the fixture runs at all — elsewhere the three are skipped, which is the point of it."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", CASES, "-p", "no:cacheprovider", "--no-cov", "-n0"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    said = ran.stdout
    fell = f"{CASES}::test_falls_before_it_builds_the_browser"
    idle = f"{CASES}::test_passes_and_never_builds_the_browser"

    assert f"FAILED {fell} - RuntimeError: {profile_browser_cases.FELL}" in said, said
    assert f"ERROR {fell}" not in said, "a second error covers the reason the test fell for"
    assert f"ERROR {idle} - AssertionError: a test took the fixture" in said, said
    assert "test_builds_the_browser_and_passes" not in said
    assert "1 failed, 2 passed, 1 error in" in said, said


@pytest.mark.parametrize("builds", [0, 1, 2])
def test_after_a_test_that_took_the_fixture_the_browser_is_not_built_any_more(builds: int) -> None:
    """Whatever the test did: what it took ends with it."""
    taking = profile_browser.taken(it_passed)
    next(taking)
    for _ in range(builds):
        profile_browser.built_through_the_fixture()
    with pytest.raises((AssertionError, StopIteration)):
        next(taking)

    with pytest.raises(AssertionError, match="without the fixture"):
        profile_browser.built_through_the_fixture()


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
