"""The bell on ntfy.sh (M12.5 dec. E; ADR 0043 §8): what it sends, and what it never sends.

No socket is opened here — ``tests/conftest.py`` makes the real transports raise — and what is
injected is ``httpx.MockTransport``, as the ElevenLabs tests do.
"""

from __future__ import annotations

import asyncio
import json
from typing import Final

import httpx
import pytest
from pydantic import SecretStr

from ela.domain import RiskLevel
from ela.providers.ntfy import (
    BELL_TIMEOUT_SECONDS,
    BELL_TITLE,
    DEFAULT_NTFY_URL,
    VOICES,
    NtfyBell,
    NtfySettings,
    tailnet_url,
)

TOPIC: Final = "un-argomento-di-128-bit"
TAILNET: Final = "100.101.102.103:8130"
LOOPBACK: Final = "127.0.0.1:8130"
PAGE: Final = f"http://{TAILNET}/companion/"


class Answers:
    """A transport that answers from a list and keeps every request it was given."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.given: list[httpx.Request] = []
        self._answers = list(answers)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    @property
    def body(self) -> dict[str, object]:
        parsed = json.loads(self.given[-1].content)
        assert isinstance(parsed, dict)
        return parsed

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.given.append(request)
        answer = self._answers.pop(0) if self._answers else httpx.Response(500)
        if isinstance(answer, Exception):
            raise answer
        return answer


async def bell_with(*answers: httpx.Response | Exception) -> tuple[NtfyBell, Answers]:
    given = Answers(*answers)
    bell = NtfyBell(
        topic=SecretStr(TOPIC),
        url=DEFAULT_NTFY_URL,
        timeout=BELL_TIMEOUT_SECONDS,
        transport=given.transport,
    )
    bell.serving_at((LOOPBACK, TAILNET))
    return bell, given


async def test_it_publishes_json_to_the_root_with_the_topic_in_the_body() -> None:
    """Dec. E: the topic is a credential, and a topic in a path is a credential in every log
    between here and there (docs.ntfy.sh/publish)."""
    bell, given = await bell_with(httpx.Response(200))

    assert await bell.approval_waiting(RiskLevel.MEDIUM) is True
    assert given.given[-1].url.path in {"", "/"}, "the topic is in the body, not in the path"
    assert TOPIC not in str(given.given[-1].url)
    assert given.body["topic"] == TOPIC


async def test_what_a_third_party_sees_is_two_keys_and_the_name() -> None:
    """The closed vocabulary: the title is ELA, the body is the state and the risk, and the tap
    opens the page. Nothing of the user's can be in it — the method takes a ``RiskLevel``."""
    bell, given = await bell_with(httpx.Response(200))

    await bell.approval_waiting(RiskLevel.LOW)

    assert given.body["title"] == BELL_TITLE
    assert given.body["message"] == f"{VOICES['approval_waiting']} · {RiskLevel.LOW.value}"
    assert given.body["click"] == PAGE
    assert "actions" not in given.body, "no action buttons: the yes is given on the page"


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(429), httpx.Response(500), httpx.ConnectError("no route"), OSError("down")],
    ids=["too many", "a broken provider", "no network", "a socket that is not there"],
)
async def test_a_bell_that_does_not_ring_is_false_and_never_raises(
    answer: httpx.Response | Exception,
) -> None:
    """Dec. E: a bell that did not ring must not fail a run — the question waits all the same."""
    bell, _ = await bell_with(answer)

    assert await bell.approval_waiting(RiskLevel.MEDIUM) is False


async def test_without_a_topic_or_without_an_address_nothing_is_sent() -> None:
    """Two absences, two facts: no topic is a configuration, no address is an ELA on loopback."""
    given = Answers(httpx.Response(200))
    silent = NtfyBell(topic=None, url=DEFAULT_NTFY_URL, timeout=1.0, transport=given.transport)
    silent.serving_at((TAILNET,))
    assert silent.ready is False
    assert await silent.approval_waiting(RiskLevel.MEDIUM) is False

    unbound = NtfyBell(
        topic=SecretStr(TOPIC), url=DEFAULT_NTFY_URL, timeout=1.0, transport=given.transport
    )
    assert unbound.ready is False
    unbound.serving_at((LOOPBACK,))
    assert unbound.ready is False, "loopback is what the Mac calls itself"
    assert await unbound.approval_waiting(RiskLevel.MEDIUM) is False
    assert given.given == []


async def test_a_slow_provider_does_not_hold_the_run_beyond_the_timeout() -> None:
    """Dec. E, the reason the timeout exists: the bell rings on the path of the run, so this is
    time the user waits for. The provider here never answers; the wait is the adapter's."""

    async def never(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(3600)
        return httpx.Response(200)

    bell = NtfyBell(
        topic=SecretStr(TOPIC),
        url=DEFAULT_NTFY_URL,
        timeout=0.05,
        transport=httpx.MockTransport(never),
    )
    bell.serving_at((TAILNET,))

    async with asyncio.timeout(5):
        assert await bell.approval_waiting(RiskLevel.MEDIUM) is False


def test_the_address_a_phone_can_open_is_the_one_that_is_not_loopback() -> None:
    """ADR 0037 §2: the tailnet address, taken from what was bound, and IPv6 keeps its brackets."""
    assert tailnet_url((LOOPBACK, TAILNET)) == PAGE
    assert tailnet_url((LOOPBACK,)) is None
    assert tailnet_url(()) is None
    assert tailnet_url(("mac.tailnet.ts.net:8130", TAILNET)) == PAGE, "a name is not an address"
    assert tailnet_url(("100.101.102.103",)) is None, "and an address without a port is not one"
    assert (
        tailnet_url(("[fd7a:115c:a1e0::1]:8130",)) == "http://[fd7a:115c:a1e0::1]:8130/companion/"
    )


def test_the_audit_learns_the_service_and_never_the_topic() -> None:
    """What ``BELL_RUNG`` records of the provider is this name (§57): the address, not the
    credential — on ntfy the topic *is* the password of the topic."""
    bell = NtfyBell(topic=SecretStr(TOPIC), url=DEFAULT_NTFY_URL, timeout=1.0)

    assert bell.name == DEFAULT_NTFY_URL
    assert TOPIC not in bell.name


def test_the_timeout_is_the_measured_constant() -> None:
    """A dozen times the 0,43 s of P4: it is the number, and it is written where it is read."""
    assert BELL_TIMEOUT_SECONDS == 5.0
    assert NtfySettings(_env_file=None).ntfy_timeout_seconds == BELL_TIMEOUT_SECONDS  # type: ignore[call-arg]


def test_a_blank_topic_is_no_topic_and_a_url_needs_a_scheme() -> None:
    assert NtfySettings(ntfy_topic=SecretStr("  "), _env_file=None).configured is False  # type: ignore[call-arg]
    assert NtfySettings(ntfy_topic=SecretStr(TOPIC), _env_file=None).configured is True  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="http"):
        NtfySettings(ntfy_url="ntfy.sh", _env_file=None)  # type: ignore[call-arg]
