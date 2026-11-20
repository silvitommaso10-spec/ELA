"""What holds for every test of ELA, whatever it is testing.

**The HTTP transports of ``httpx`` and ``httpx2`` are unusable for every test and every fixture of
any scope.** The provider tests replace the SDK client with a double, and this makes that a
property of the suite rather than a habit of one package: a test that reached the real API with one
of those two clients — by forgetting a double, by picking up a key from the machine it runs on —
fails loudly instead of spending money quietly (§57, §58). ``httpx2`` is what the vendor SDK calls
with, ``httpx`` is what the API tests drive the app with (M8.1); ``ASGITransport`` is a different
class and stays usable — it speaks to the application in this process and opens no socket at all.
**Since M13.17b** the refusal is installed once per process, in ``pytest_configure``, and not by a
fixture of a function, which a fixture of a module or of the session ran before.

**What is not true, and is said** (answer 34 of M13.17b): a test **without** a script of
``scripts/`` on its stack that opens a socket with another client — ``urllib``, ``http.client``, a
socket — is stopped by nothing here. The fence of the socket is the scripts'
(``tests/script_fences.py``); the rest is M7.1b, which M13.17b registers when it closes.

**And the fences of the scripts and of the environment** (M13.17b, ``tests/script_fences.py``): a
script of ``scripts/`` launches nothing, connects to nothing and resolves no name of the world in a
test that did not replace it; no test reads the ``.env`` or the ``ELA_`` variables of whoever runs
the suite, and every process works in a folder and with a home of the test's.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from typing import Any

import pytest

from tests import machines, profile_browser, script_fences, suite_log
from tests.browser_leftovers import RAN_LAST

NO_NETWORK = script_fences.NO_NETWORK


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


@pytest.fixture
def script_may(request: pytest.FixtureRequest) -> Iterator[script_fences.Named]:
    """**What a test lets a script of ``scripts/`` do, exactly and with its reason** (M13.17b,
    decision 6 and answer 36): ``launch(*argv, why=...)``, ``run(line, why=...)``,
    ``connect(host, port, why=...)``. It holds from this fixture's set-up to its closing, which
    pytest runs before the closing of a fixture of a module — and a fixture of a module cannot ask
    for it: a fixture of a wider scope never gets an exemption. **An entry the test never used
    fails it**, at this closing and only for a test that passed — like the browser of the
    profile, above: one that fell keeps its one failure."""
    yield from script_fences.named_for_a_test(lambda: profile_browser.passed(request.node))


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    """Every report pytest makes of a test is put on the test, as it is made: the standard hook
    for a fixture that has to know how its test went (decision 34) — the guard of the browser of
    the profile reads the one of the test's own phase at its closing, and so does ``script_may``."""
    report = yield
    profile_browser.reported(item, report)
    return report


@pytest.hookimpl(trylast=True)
def pytest_configure(config: pytest.Config) -> None:
    """The mark of the one place (``tests/machines.py``), who this process is for the log of the
    suite (``tests/suite_log.py``), and **the fences of M13.17b**
    (``tests/script_fences.py``): once per process, before any fixture of any scope is set up.
    Last among the plugins' own ``pytest_configure``: the folder of pytest's temporary files is
    made by its own."""
    suite_log.configured(config)
    config.addinivalue_line(
        "markers",
        f"{machines.MARK}(*conditions, why=''): what of the machine a test needs — "
        "tests/machines.py, and nowhere else",
    )
    factory: Any = config._tmp_path_factory  # type: ignore[attr-defined]
    script_fences.install(factory.getbasetemp())


def pytest_collection_finish(session: pytest.Session) -> None:
    """The folder of work of this process becomes a folder of the test's (M13.17b, answer 56): after
    the collection, which reads the paths of the command line against the folder pytest started
    from, and before any fixture."""
    script_fences.work_in_the_test_s_folder()


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
