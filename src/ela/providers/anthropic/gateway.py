"""The gateway of a guided session (M14.3, ADR 0060): where its calls leave with the key.

A session of Claude Code launched by ELA sends its calls to ELA's own port, to
``/sessions/<step>/v1/messages``, with a token that is worth nothing anywhere else. The route asks
the room of the sessions to weigh each call against the session's reservation; a call the room
admits comes here, with its :class:`~ela.domain.Admission`, and **only here does it get the key**.
The body leaves as it arrived — not read again, not rewritten —, and the answer goes back **event
by event**, as the documentation of an LLM gateway asks (``llm-gateway-protocol``), while the usage
is read from the events as they pass: ``message_start`` gives the input, ``message_delta`` the
output, ``message_stop`` says the call is over. A stream that stops before ``message_stop`` is an
outcome nobody knows, and the call counts its worst case (ADR 0057 §10).

The key stays in this package (§26, contract 10): the session never sees it, and the module that
holds it calls Anthropic only with an admission in hand (architecture rule 65).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

import httpx

from ela.domain import Admission, ProviderUsage
from ela.ports import CallRequest, Forwarded
from ela.providers.anthropic.models import MODELS
from ela.providers.anthropic.pricing import CURRENCY, estimate_cost, worst_cost

__all__ = [
    "ANTHROPIC_API",
    "ANTHROPIC_VERSION",
    "MESSAGES_PATH",
    "AnthropicGateway",
    "unrun",
]

ANTHROPIC_API: Final = "https://api.anthropic.com"
MESSAGES_PATH: Final = "/v1/messages?beta=true"
"""The one path a session's call goes to: the path Claude Code asks of a gateway."""
ANTHROPIC_VERSION: Final = "2023-06-01"
EVENT_STREAM: Final = "text/event-stream"
JSON_TYPE: Final = "application/json"
OVERLOADED: Final = 529


def unrun(status: int) -> bool:
    """Whether the API turned the call down before running it — a ``4xx``, or the ``529`` —, the
    reading of ``classify`` (ADR 0057 §10): sent, and paid nothing. Every other failure after the
    network is an outcome nobody knows."""
    return 400 <= status < 500 or status == OVERLOADED


@dataclass(slots=True)
class _Read:
    """The usage of one call, read from its events as they pass."""

    input_tokens: int = 0
    cached: int = 0
    output_tokens: int = 0
    model: str | None = None
    finished: bool = False
    buffer: bytes = b""

    def feed(self, chunk: bytes) -> None:
        self.buffer += chunk
        while b"\n\n" in self.buffer:
            event, self.buffer = self.buffer.split(b"\n\n", 1)
            for line in event.split(b"\n"):
                if line.startswith(b"data:"):
                    self._data(line[len(b"data:") :].strip())

    def _data(self, raw: bytes) -> None:
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        kind = data.get("type")
        if kind == "message_start":
            message = data.get("message")
            if isinstance(message, dict):
                self.model = _text(message.get("model"))
                self._usage(message.get("usage"))
        elif kind == "message_delta":
            self._usage(data.get("usage"))
        elif kind == "message_stop":
            self.finished = True

    def whole(self, raw: bytes) -> None:
        """A call answered without a stream: one JSON message, read at its end."""
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if isinstance(data, dict) and data.get("type") == "message":
            self.model = _text(data.get("model"))
            self._usage(data.get("usage"))
            self.finished = True

    def _usage(self, usage: object) -> None:
        if not isinstance(usage, dict):
            return
        self.input_tokens = _count(usage.get("input_tokens"), self.input_tokens)
        self.cached = _count(usage.get("cache_read_input_tokens"), self.cached)
        self.output_tokens = _count(usage.get("output_tokens"), self.output_tokens)


def _count(value: object, otherwise: int) -> int:
    return value if type(value) is int and value >= 0 else otherwise


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _cached(value: Any) -> bool:
    """Whether any part of a body asks for the cache: a ``cache_control`` anywhere in it."""
    if isinstance(value, dict):
        return "cache_control" in value or any(_cached(item) for item in value.values())
    if isinstance(value, list):
        return any(_cached(item) for item in value)
    return False


class AnthropicGateway:
    """Implements :class:`~ela.ports.ModelGateway` with the key of ELA's ``.env``."""

    def __init__(
        self,
        key: str | None,
        *,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        base_url: str = ANTHROPIC_API,
    ) -> None:
        self._key = key
        self._timeout = timeout
        self._transport = transport
        self._base_url = base_url

    async def read(self, body: bytes) -> CallRequest:
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            return CallRequest(None, None, None, cached=False, request_bytes=len(body))
        tools = data.get("tools")
        names = (
            tuple(str(one.get("name")) for one in tools if isinstance(one, dict))
            if isinstance(tools, list)
            else None
        )
        max_tokens = data.get("max_tokens")
        return CallRequest(
            model=_text(data.get("model")),
            max_tokens=max_tokens if type(max_tokens) is int else None,
            tools=names,
            cached=_cached(data),
            request_bytes=len(body),
        )

    async def worst(self, model: str, max_tokens: int) -> Decimal | None:
        found = MODELS.get(model)
        return None if found is None else worst_cost(found, output_tokens=max_tokens)

    async def forward(self, admission: Admission, body: bytes, beta: str | None) -> Forwarded:
        """``body`` to Anthropic with the key, as it is; the answer back as it comes."""
        if self._key is None:
            return _refused(503, "ELA has no key for the model's provider", sent=False)
        headers = {
            "x-api-key": self._key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": JSON_TYPE,
        }
        if beta:
            headers["anthropic-beta"] = beta
        client = httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        )
        try:
            request = client.build_request("POST", MESSAGES_PATH, content=body, headers=headers)
            response = await client.send(request, stream=True)
        except httpx.ConnectError:
            await client.aclose()
            return _refused(502, "the model's provider could not be reached", sent=False)
        except httpx.HTTPError:
            await client.aclose()
            return _refused(504, "the call to the model's provider did not complete", sent=None)
        read = _Read()
        streamed = response.headers.get("content-type", "").startswith(EVENT_STREAM)

        async def chunks() -> AsyncIterator[bytes]:
            whole = b""
            try:
                async for chunk in response.aiter_bytes():
                    if streamed:
                        read.feed(chunk)
                    else:
                        whole += chunk
                    yield chunk
                if not streamed:
                    read.whole(whole)
            except httpx.HTTPError:
                return
            finally:
                await response.aclose()
                await client.aclose()

        def usage() -> ProviderUsage | None:
            if unrun(response.status_code):
                return ProviderUsage(
                    input_tokens=0,
                    output_tokens=0,
                    cost=Decimal(0),
                    currency=CURRENCY,
                    request_bytes=len(body),
                )
            if response.status_code != 200 or not read.finished:
                return None
            cost = estimate_cost(
                read.model or admission.model,
                input_tokens=read.input_tokens,
                output_tokens=read.output_tokens,
                cached_input_tokens=read.cached,
            )
            return ProviderUsage(
                input_tokens=read.input_tokens,
                output_tokens=read.output_tokens,
                cached_input_tokens=read.cached,
                cost=cost,
                currency=None if cost is None else CURRENCY,
                request_bytes=len(body),
            )

        return Forwarded(
            status=response.status_code,
            content_type=response.headers.get("content-type", JSON_TYPE),
            chunks=chunks(),
            usage=usage,
        )


def _refused(status: int, message: str, *, sent: bool | None) -> Forwarded:
    """An answer of the gateway's own, in the shape of the provider's errors: ``sent`` ``False``
    is a call that never left (it costs nothing), ``None`` one whose outcome nobody knows."""
    body = json.dumps({"type": "error", "error": {"type": "api_error", "message": message}})

    async def chunks() -> AsyncIterator[bytes]:
        yield body.encode()

    def usage() -> ProviderUsage | None:
        if sent is None:
            return None
        return ProviderUsage(input_tokens=0, output_tokens=0, sent=False)

    return Forwarded(status=status, content_type=JSON_TYPE, chunks=chunks(), usage=usage)
