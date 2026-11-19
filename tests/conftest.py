"""What holds for every test of ELA, whatever it is testing.

**No test talks to the network.** The provider tests replace the SDK client with a double, and
this fixture makes that a property of the suite rather than a habit of one package: the HTTP
transports are unusable, so a test that reached the real API — by forgetting a double, by picking
up a key from the machine it runs on — fails loudly instead of spending money quietly (§57, §58).

Both clients are covered: ``httpx2`` is what the vendor SDK calls with, ``httpx`` is what the API
tests drive the app with (M8.1). ``ASGITransport`` is a different class and stays usable — it
speaks to the application in this process and opens no socket at all.
"""

from __future__ import annotations

import subprocess
from collections.abc import Generator, Iterator
from typing import Any, NoReturn

import httpx
import httpx2
import pytest

from tests import machines, profile_browser, proof_launches, suite_log
from tests.browser_leftovers import RAN_LAST

NO_NETWORK = "a test tried to open a network connection"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError(NO_NETWORK)

    for library in (httpx, httpx2):
        monkeypatch.setattr(library.AsyncHTTPTransport, "handle_async_request", refuse)
        monkeypatch.setattr(library.HTTPTransport, "handle_request", refuse)


@pytest.fixture(autouse=True)
def _no_launch_from_a_proof(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """**No proof script launches a real process in a test that did not replace the launch**
    (M13.17, decisions 62 and 68): ``tests/proof_launches.py``. Like the network above, a
    property of the suite rather than a habit of each test."""
    if request.node.get_closest_marker(proof_launches.ALLOWED) is not None:
        return
    real = subprocess.Popen._execute_child  # type: ignore[attr-defined]

    def guarded(self: subprocess.Popen[Any], args: Any, *rest: Any, **named: Any) -> Any:
        script = proof_launches.from_a_proof(proof_launches.calling_frame())
        if script is not None:
            raise proof_launches.refused(script, args)
        return real(self, args, *rest, **named)

    monkeypatch.setattr(subprocess.Popen, "_execute_child", guarded)


@pytest.fixture(name=profile_browser.TAKEN)
def _the_browser_of_the_profile(request: pytest.FixtureRequest) -> Iterator[None]:
    """**Where a test takes the browser of the profile** (decision 27 of the review after the red CI
    of ``56c672c``): the folder of a test's profile asks for this fixture, the collection marks
    every test whose fixtures reach it with the skip of the systems the product does not have that
    browser on, and the browser is built only while it is taken (``tests/profile_browser.py``).

    **And a test that took it, passed, and never built that browser is an error** — the guard of
    the other way round, and why it exists (decision 33): the first form of the skip marked every
    test that took the *folder* of a profile, and three tests of the empty browser stopped running
    on Linux with every run green. Found on 2026-11-10 by comparing the skipped tests of two runs
    line by line; the commit that shows it red is ``efac3a7``. With the guard, who is skipped
    elsewhere is exactly who builds that browser here.

    **It speaks only of a test that passed** (decision 34): the report of the test's own phase is
    on the test (the hook below), and one that fell before it built the browser keeps its one
    failure, its own."""
    yield from profile_browser.taken(lambda: profile_browser.passed(request.node))


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Every report pytest makes of a test is put on the test, as it is made: the standard hook
    for a fixture that has to know how its test went (decision 34) — the guard of the browser of
    the profile reads the one of the test's own phase at its closing."""
    report = yield
    profile_browser.reported(item, report)
    return report


def pytest_configure(config: pytest.Config) -> None:
    """The mark of the one place (``tests/machines.py``), and who this process is for the log of
    the suite (``tests/suite_log.py``)."""
    suite_log.configured(config)
    config.addinivalue_line(
        "markers",
        f"{machines.MARK}(*conditions, why=''): what of the machine a test needs — "
        "tests/machines.py, and nowhere else",
    )
    config.addinivalue_line(
        "markers",
        f"{proof_launches.ALLOWED}(why): a test that launches a real process through a proof "
        "script on purpose — tests/proof_launches.py",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """The mark of a test that takes the browser of the profile, put where it takes it and never
    written in the test: three tests of M13.9b forgot to copy it, and ubuntu was red."""
    profile_browser.marked(items)


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """The log of the suite (``tests/suite_log.py``, M9.5): off unless ``SUITE_LOG`` is set — the
    two jobs of ``make check`` set it, a run on this Mac does not."""
    suite_log.reported(report)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_setup(item: pytest.Item) -> Generator[None, None, None]:
    """**The guard** (M9.5, ``tests/machines.py``): before a test is set up — before the skips are
    read and before its fixtures —, what it needs of the machine decides whether it is skipped,
    red, or let run. A wrapper, so it comes before every other part of the set-up."""
    machines.guard(item)
    return (yield)


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Every test, as it ends, is the one its worker ran last — of any module, and whether or not
    it reached a teardown —: what the fixture of the real browser names a process it finds before
    a test with (decision 86 (a) of the review of M13.10). Before, only the tests that ask for that
    fixture counted, and only once torn down: on ubuntu, on 2026-10-29, eighty-six tests were told
    «no test ran before it on this worker», and it was false every time."""
    RAN_LAST[0] = nodeid
