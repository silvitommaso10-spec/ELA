"""The gateway of a guided session (M14.3, ADR 0060): the key put on, the body untouched, the answer
passed on event by event, and the usage read from the events as they pass — with a transport that
answers as Anthropic does and never opens a socket.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest

from ela.domain import Admission
from ela.providers.anthropic import AnthropicGateway, anthropic_gateway
from ela.providers.anthropic.gateway import unrun
from ela.providers.anthropic.models import HAIKU_5_5, MODELS
from ela.providers.anthropic.pricing import estimate_cost, worst_cost
from tests.api.guided import events
from tests.providers.support import SECRET, settings

ADMISSION = Admission(
    session=uuid4(),
    call=1,
    model=HAIKU_5_5,
    max_tokens=8192,
    worst=Decimal("0.516384"),
    request_bytes=2,
)
BODY = json.dumps({"model": HAIKU_5_5, "max_tokens": 8192, "messages": []}).encode()


def gateway(handler: object, key: str | None = SECRET) -> AnthropicGateway:
    return AnthropicGateway(key, timeout=5.0, transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


async def drained(gateway_: AnthropicGateway, beta: str | None = None) -> tuple[int, bytes, object]:
    forwarded = await gateway_.forward(ADMISSION, BODY, beta)
    body = b""
    async for chunk in forwarded.chunks:
        body += chunk
    return forwarded.status, body, forwarded.usage()


async def test_the_body_leaves_as_it_came_with_the_key_and_comes_back_as_it_streamed() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=events())

    status, body, usage = await drained(gateway(handler), "fine-grained-tool-streaming")

    (request,) = seen
    assert request.content == BODY
    assert request.headers["x-api-key"] == SECRET
    assert request.headers["anthropic-beta"] == "fine-grained-tool-streaming"
    assert str(request.url) == "https://api.anthropic.com/v1/messages?beta=true"
    assert (status, body) == (200, events())
    assert usage.cost == estimate_cost(  # type: ignore[attr-defined]
        HAIKU_5_5, input_tokens=1_200, output_tokens=40, cached_input_tokens=0
    )
    assert usage.request_bytes == len(BODY)  # type: ignore[attr-defined]


async def test_no_beta_no_beta_header() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=events())

    await drained(gateway(handler))

    assert "anthropic-beta" not in seen[0].headers


async def test_an_answer_without_a_stream_is_read_at_its_end() -> None:
    message = {
        "type": "message",
        "model": HAIKU_5_5,
        "usage": {"input_tokens": 300, "output_tokens": 7, "cache_read_input_tokens": 0},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=message)

    status, body, usage = await drained(gateway(handler))

    assert status == 200 and json.loads(body) == message
    assert (usage.input_tokens, usage.output_tokens) == (300, 7)  # type: ignore[attr-defined]


@pytest.mark.parametrize("answer", [b"not json", b"[1]", b'{"type": "error"}'])
async def test_an_answer_that_is_not_a_message_has_no_known_outcome(answer: bytes) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=answer)

    *_, usage = await drained(gateway(handler))

    assert usage is None


async def test_a_stream_that_stops_before_its_end_has_no_known_outcome() -> None:
    cut = events().split(b"event: message_stop")[0]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=cut)

    *_, usage = await drained(gateway(handler))

    assert usage is None


async def test_a_stream_broken_halfway_has_no_known_outcome() -> None:
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield events()[:40]
            raise httpx.ReadError("gone")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Broken())

    status, body, usage = await drained(gateway(handler))

    assert status == 200 and body == events()[:40]
    assert usage is None


async def test_events_the_gateway_does_not_read_are_passed_on_and_ignored() -> None:
    noise = (
        b"event: ping\ndata: not json\n\n"
        b"data: [1, 2]\n\n"
        b'data: {"type": "message_start", "message": "x"}\n\n'
        b'data: {"type": "message_delta", "usage": "x"}\n\n'
        b'data: {"type": "message_delta", "usage": {"output_tokens": -1}}\n\n'
        b'data: {"type": "content_block_delta", "delta": {"text": "x"}}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=noise + events()
        )

    status, body, usage = await drained(gateway(handler))

    assert body == noise + events()
    assert usage.output_tokens == 40  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", [400, 401, 429, 529])
async def test_a_call_the_api_turned_down_before_running_it_cost_nothing(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"type": "error", "error": {"type": "x"}})

    answered, _, usage = await drained(gateway(handler))

    assert answered == status
    assert usage.cost == 0 and usage.sent is True  # type: ignore[attr-defined]


async def test_a_server_error_has_no_known_outcome() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"type": "error"})

    *_, usage = await drained(gateway(handler))

    assert usage is None


async def test_a_call_that_could_not_leave_costs_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    status, body, usage = await drained(gateway(handler))

    assert status == 502 and b"could not be reached" in body
    assert usage.sent is False  # type: ignore[attr-defined]


async def test_a_call_that_failed_on_the_way_has_no_known_outcome() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    status, body, usage = await drained(gateway(handler))

    assert status == 504 and usage is None


async def test_without_a_key_nothing_leaves() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("no key, no call")

    status, body, usage = await drained(gateway(handler, key=None))

    assert status == 503 and usage.sent is False  # type: ignore[attr-defined]


async def test_a_call_is_read_for_its_model_its_tokens_its_tools_and_the_cache() -> None:
    reader = gateway(lambda request: httpx.Response(200))
    body = {
        "model": HAIKU_5_5,
        "max_tokens": 8192,
        "tools": [{"name": "mcp__ela__read"}, "noise", {"name": "mcp__ela__act"}],
        "messages": [{"role": "user", "content": [{"type": "text", "cache_control": {}}]}],
    }

    read = await reader.read(json.dumps(body).encode())

    assert (read.model, read.max_tokens) == (HAIKU_5_5, 8192)
    assert read.tools == ("mcp__ela__read", "mcp__ela__act")
    assert read.cached is True and read.request_bytes == len(json.dumps(body).encode())


@pytest.mark.parametrize(
    "body", [b"not json", b"[1]", json.dumps({"model": 7, "max_tokens": "x"}).encode()]
)
async def test_a_body_that_does_not_say_says_nothing(body: bytes) -> None:
    read = await gateway(lambda request: httpx.Response(200)).read(body)

    assert (read.model, read.max_tokens, read.tools, read.cached) == (None, None, None, False)


async def test_the_worst_case_of_a_call_is_the_price_list_s() -> None:
    priced = gateway(lambda request: httpx.Response(200))

    assert await priced.worst(HAIKU_5_5, 8192) == worst_cost(MODELS[HAIKU_5_5], output_tokens=8192)
    assert await priced.worst("nobody", 8192) is None


def test_the_statuses_of_a_call_turned_down_before_it_ran() -> None:
    assert [unrun(status) for status in (400, 499, 500, 529, 200)] == [
        True,
        True,
        False,
        True,
        False,
    ]


async def test_the_gateway_is_built_with_the_key_of_the_env() -> None:
    built = anthropic_gateway(settings=settings())
    absent = anthropic_gateway(settings=settings(anthropic_api_key=None))

    assert built._key == SECRET  # noqa: SLF001
    assert absent._key is None  # noqa: SLF001
