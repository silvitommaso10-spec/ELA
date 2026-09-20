"""The bell, on ntfy.sh (port :class:`~ela.ports.Bell`; M12.5 dec. E; ADR 0043 §8).

One request, as JSON, **to the root** of the service, with the topic in the body and never in the
path (docs.ntfy.sh/publish): a topic in a URL is a credential in every log between here and there.

What a third party sees is what this module composes, and it is a closed vocabulary: a title that
is the word ``ELA`` and a body made of two keys of the design system — the state and the risk. No
sentence of the user's reaches it, and not because somebody remembered: the port takes a
:class:`~ela.domain.RiskLevel`, so there is no string to pass.

**The tap opens the page**, in one gesture, measured on 2026-09-20 (P4): the notification carries
the address of the companion's home page, composed from the address this process actually bound —
not from a setting, because if the tailnet was not there at start-up ELA is listening on loopback
only and a bell would open an address that answers nobody.

No action buttons (the user's fixed point 5): the answer is given on the page, where the question
is, and never through a third party.
"""

from __future__ import annotations

import asyncio
import ipaddress
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final

import httpx
from pydantic import SecretStr

from ela.domain import RiskLevel

__all__ = ["BELL_TITLE", "HOME", "VOICES", "NtfyBell", "tailnet_url"]

BELL_TITLE: Final = "ELA"
"""The title of every notification: the name, and nothing that says what waits."""

VOICES: Final[Mapping[str, str]] = MappingProxyType({"approval_waiting": "WAITING APPROVAL"})
"""One row per method of the port, and the row is the **key of the state** in ``tokens.json``.

A method per voice, not an enum (dec. E): a second thing ELA can ring has to arrive with its own
method, its own caller and its own row here, and a test walks all three together — a voice with no
row, a row with no voice or a second place that publishes all fail the census.
"""

HOME: Final = "/companion/"
"""What the tap opens: the page where the question is. A fixed path, never an id."""

PRIORITY: Final = 3
"""ntfy's default. A constant and not a knob: *when* ELA may insist is §7 and §34, the Fase 15,
and a number in a ``.env`` would be that decision taken without anybody making it."""


def tailnet_url(addresses: Sequence[str]) -> str | None:
    """The address a phone can open, out of the ones this process bound, or ``None``.

    Loopback is what the Mac calls itself; a bell that opened it would be a notification that does
    nothing on the phone. The addresses arrive as ``host:port``, with an IPv6 host in brackets, as
    ``api/server.py`` writes them (ADR 0037 §2).
    """
    for address in addresses:
        host, _, port = address.rpartition(":")
        try:
            parsed = ipaddress.ip_address(host.strip("[]"))
        except ValueError:
            continue
        if not parsed.is_loopback and port:
            return f"http://{host}:{port}{HOME}"
    return None


class NtfyBell:
    """ntfy.sh, one ``POST`` per bell, with a timeout that bounds what a run may wait.

    Holds no state but its configuration: the topic, the address of the service, the timeout, and
    the URL the tap opens — which the composition hands over **after** the bind and before serving,
    because before that nobody knows it.
    """

    __slots__ = ("_client", "_open", "_timeout", "_topic", "_url")

    def __init__(
        self,
        *,
        topic: SecretStr | None,
        url: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._topic = topic
        self._url = url.rstrip("/")
        self._timeout = timeout
        self._client = client
        self._open: str | None = None

    @property
    def name(self) -> str:
        """The service, as the audit records it — never the topic, which is the credential."""
        return self._url

    @property
    def ready(self) -> bool:
        """A topic to ring on, and an address the phone can open: without either, silence."""
        return self._topic is not None and self._open is not None

    def serving_at(self, addresses: Sequence[str]) -> None:
        """Where this process is listening, given once the sockets are bound (dec. E).

        Called by ``api/server.py`` after the bind and before serving. An ELA that never serves —
        a test, a CLI command — never calls it, and its bell is not ready, which is the truth.
        """
        self._open = tailnet_url(addresses)

    async def approval_waiting(self, risk: RiskLevel) -> bool:
        """Ring: a question waits. The body is two keys, and the tap opens the page."""
        return await self._ring(f"{VOICES['approval_waiting']} · {risk.value}")

    async def _ring(self, message: str) -> bool:
        """One ``POST`` of JSON to the root; ``False`` for every way it can not arrive.

        A bell that did not ring is not a failure of the run (dec. E): the question waits on the
        page and in the CLI all the same, and what happened is written by whoever called.

        **The wait is bounded here**, and not left to the client: the bell rings on the path of a
        run, so how long a provider may hold the user is a decision of ELA's and not of whatever
        HTTP library is underneath.
        """
        if self._topic is None or self._open is None:
            return False
        payload = {
            "topic": self._topic.get_secret_value(),
            "title": BELL_TITLE,
            "message": message,
            "click": self._open,
            "priority": PRIORITY,
        }
        try:
            async with asyncio.timeout(self._timeout):
                answered = await self._post(payload)
        except (httpx.HTTPError, OSError, TimeoutError):
            return False
        return answered.status_code == httpx.codes.OK

    async def _post(self, payload: Mapping[str, object]) -> httpx.Response:
        """The request itself, with the client a test injects or one of its own."""
        if self._client is not None:
            return await self._client.post(self._url, json=payload)
        async with httpx.AsyncClient() as client:
            return await client.post(self._url, json=payload)
