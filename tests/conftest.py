"""What holds for every test of ELA, whatever it is testing.

**No test talks to the network.** The provider tests replace the SDK client with a double, and
this fixture makes that a property of the suite rather than a habit of one package: the HTTP
transports are unusable, so a test that reached the real API — by forgetting a double, by picking
up a key from the machine it runs on — fails loudly instead of spending money quietly (§57, §58).
"""

from __future__ import annotations

from typing import Any, NoReturn

import httpx2
import pytest

NO_NETWORK = "a test tried to open a network connection"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError(NO_NETWORK)

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", refuse)
    monkeypatch.setattr(httpx2.HTTPTransport, "handle_request", refuse)
