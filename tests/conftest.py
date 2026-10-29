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

from typing import Any, NoReturn

import httpx
import httpx2
import pytest

from tests.browser_leftovers import RAN_LAST

NO_NETWORK = "a test tried to open a network connection"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError(NO_NETWORK)

    for library in (httpx, httpx2):
        monkeypatch.setattr(library.AsyncHTTPTransport, "handle_async_request", refuse)
        monkeypatch.setattr(library.HTTPTransport, "handle_request", refuse)


def pytest_runtest_logfinish(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Every test, as it ends, is the one its worker ran last — of any module, and whether or not
    it reached a teardown —: what the fixture of the real browser names a process it finds before
    a test with (decision 86 (a) of the review of M13.10). Before, only the tests that ask for that
    fixture counted, and only once torn down: on ubuntu, on 2026-10-29, eighty-six tests were told
    «no test ran before it on this worker», and it was false every time."""
    RAN_LAST[0] = nodeid
