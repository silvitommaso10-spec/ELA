"""The bytes of the body of a call, beside its usage (M14.6, decision 26; ADR 0061).

ADR 0057 §2 names the measure with which its worst case is to be revised — «the true input tokens
of ELA's calls, compared with the bytes of the input that made them» —, and a month of usage has
those bytes only if somebody writes them. The adapter reads them from the request the SDK sent, not
from a second serialization of its own: the SDK serializes in its own way, and a copy could tell
another number. A request that was never built has no bytes, and says ``None``.
"""

from __future__ import annotations

import json
from decimal import Decimal

import anthropic
import httpx2

from ela.domain import ProviderUsage
from ela.executive import Envelope
from ela.providers.anthropic import AnthropicProvider
from ela.testing.fakes import FakeClock, FakeIdGenerator
from tests.executive.test_executor_remote import answered
from tests.providers.support import (
    API_URL,
    SECRET,
    Sleeper,
    Ticks,
    answer,
    make_provider,
    request,
    settings,
)


async def test_an_answered_call_says_the_bytes_of_the_body_the_sdk_sent() -> None:
    provider, client = make_provider(answer())

    usage = (await provider.complete(request())).usage

    assert client is not None
    (sent,) = client.messages.sent_bodies
    assert usage.request_bytes == len(sent)
    naive = json.dumps(client.messages.calls[0]).encode()
    assert len(sent) != len(naive), "the fake's body is the SDK's, not a naive json.dumps"


async def test_a_failure_after_the_network_says_the_bytes_that_left() -> None:
    body = b'{"model":"claude-sonnet-5-5","max_tokens":4096}'
    failure = anthropic.InternalServerError(
        "500 api_error",
        response=httpx2.Response(500, request=httpx2.Request("POST", API_URL, content=body)),
        body={"type": "error", "error": {"type": "api_error", "message": "boom"}},
    )
    provider, _ = make_provider(failure)

    usage = (await provider.complete(request())).usage

    assert usage.sent is True
    assert usage.request_bytes == len(body)


async def test_a_request_never_built_has_no_bytes() -> None:
    provider, client = make_provider()

    usage = (await provider.complete(request(parameters={"temperature": 1}))).usage

    assert usage.sent is False
    assert usage.request_bytes is None
    assert client is not None and client.messages.calls == []


def test_the_bytes_are_never_negative() -> None:
    ProviderUsage(input_tokens=1, output_tokens=1, request_bytes=0)
    try:
        ProviderUsage(input_tokens=1, output_tokens=1, request_bytes=-1)
    except ValueError:
        return
    raise AssertionError("a negative number of bytes was accepted")


def test_the_digest_of_an_envelope_without_bytes_is_the_one_it_was() -> None:
    """A delivery made before M14.6 is the same answer after it: the bytes are listed only when
    there are some, like the verdict (ADR 0048)."""
    before = ProviderUsage(input_tokens=10, output_tokens=2, cost=Decimal("0.00002"))
    envelope = answered(usage=before)
    legacy = before.model_dump(mode="json")
    legacy.pop("request_bytes", None)
    assert envelope.digest == _digest_with_usage(envelope, legacy)


def test_two_envelopes_that_differ_only_in_their_bytes_have_two_digests() -> None:
    usage = ProviderUsage(input_tokens=10, output_tokens=2, request_bytes=100)
    other = ProviderUsage(input_tokens=10, output_tokens=2, request_bytes=101)
    assert answered(usage=usage).digest != answered(usage=other).digest


def _digest_with_usage(envelope: Envelope, usage: dict[str, object]) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(
            {
                "form": envelope.form.value,
                "status": None if envelope.status is None else envelope.status.value,
                "output": dict(envelope.output),
                "error": None,
                "usage": usage,
                "duration_ms": envelope.duration_ms,
                "exception": envelope.exception,
                "node": dict(envelope.node),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8", "surrogatepass")
    ).hexdigest()


async def test_the_bytes_are_the_ones_the_transport_saw_through_the_real_sdk() -> None:
    """Not the fake's copy: a real ``AsyncAnthropic`` on a transport that records what it was
    handed. The number in the usage is the length of that body."""
    seen: list[bytes] = []

    def handler(sent: httpx2.Request) -> httpx2.Response:
        seen.append(sent.content)
        return httpx2.Response(200, json=answer().model_dump(mode="json"))

    client = anthropic.AsyncAnthropic(
        api_key=SECRET,
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    provider = AnthropicProvider(
        client,
        clock=FakeClock(),
        ids=FakeIdGenerator(),
        settings=settings(),
        sleep=Sleeper(),
        monotonic=Ticks(),
    )

    usage = (await provider.complete(request(text="caffè ☕"))).usage

    (body,) = seen
    assert usage.request_bytes == len(body)
    assert "caffè ☕".encode() in body, "the body is the SDK's, with its own escaping"
