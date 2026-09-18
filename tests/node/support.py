"""A node wired to a transport that answers whatever a test tells it to (M12.3).

No socket and no Core: what is under test here is the **cycle** — which answer means keep the
envelope, which means stop, which means wait — and the Core's side of each of those answers is
already proved in ``tests/api``. The conformance suite is where the two meet.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import httpx

from ela.api.app import FAILURES
from ela.api.security import unauthorized
from ela.composition import NodeConfig, NodeSettings, build_node
from ela.composition.node import NodeWorld
from ela.domain import ProviderUsage
from ela.node import Node, NodeClient, open_node_client
from ela.ports import WireCode
from ela.providers.anthropic import AnthropicSettings
from ela.providers.elevenlabs import ElevenLabsSettings
from ela.routing import RoutingSettings
from ela.testing.fakes import FakeClock, FakePower, FakeSpeech
from ela.tools import ToolRegistry
from ela.tools.base import Outcome, Tool
from ela.tools.echo import CORE_ECHO, ECHO_TOOL_NAME
from ela.tools.settings import VoiceSettings

CORE = "http://core.test"


def config(directory: Path, **node: Any) -> NodeConfig:
    """A node's five sections, with nothing read from the environment."""
    return NodeConfig(
        node=NodeSettings(node_state_dir=directory, node_core_url=CORE, **node),
        anthropic=AnthropicSettings(),
        routing=RoutingSettings(),
        voice=VoiceSettings(),
        elevenlabs=ElevenLabsSettings(),
    )


def world(
    directory: Path, clock: FakeClock | None = None, *, system: str = "Darwin", **node: Any
) -> NodeWorld:
    """A node of a named system with both voices faked, so what it declares is the same everywhere.

    Both, and the system named (M12.4 dec. F, G): a node declares only the voices its machine can
    use, and the online voice's player is ``afplay`` — present on a Mac, absent on the Ubuntu job.
    A world that left either to the machine would declare four tools here and three there. Darwin
    unless a test names another, and a test names Windows to take the writer that system's
    composition chooses (M12.4 dec. B).

    And the power source, which every heartbeat reads (M12.3c): left to the machine, a beat would
    carry ``AC`` at the desk, ``BATTERY`` on the train and ``UNKNOWN`` on the Ubuntu job.
    """
    return build_node(
        config(directory, **node),
        clock=clock or FakeClock(),
        speech=FakeSpeech(),
        speech_online=FakeSpeech(),
        system=system,
        power=FakePower(),
    )


class Script:
    """The Core, as a list of answers. Records every request so a test can count them."""

    def __init__(self, answers: Iterable[Callable[[httpx.Request], httpx.Response]]) -> None:
        self._answers = list(answers)
        self.seen: list[tuple[str, str]] = []
        self.sent: list[str | None] = []
        """The ``If-Match`` of each request, so a test can pin what the node announced against."""

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._answer)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.method, request.url.path))
        self.sent.append(request.headers.get("If-Match"))
        if not self._answers:
            raise AssertionError(f"the script ran out at {request.method} {request.url.path}")
        return self._answers.pop(0)(request)


def replies(*answers: Callable[[httpx.Request], httpx.Response]) -> Script:
    return Script(answers)


def ok(body: Any = None, **headers: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(200, json=body if body is not None else {}, headers=headers)


def status(code: int, body: Any = None) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _: httpx.Response(code, json=body if body is not None else {})


STATUS_OF: dict[WireCode, int] = {
    **{failure.code: failure.status for failure in FAILURES},
    WireCode.UNAUTHORIZED: unauthorized().status_code,
}
"""The status each code of the wire travels with, read off the API's own table and not written here.

A code has one status on the wire (``not_assigned`` two rows, both ``404``), so a script that took
both could pair them as no Core ever does."""


def refused(error: WireCode) -> Callable[[httpx.Request], httpx.Response]:
    """A refusal of the Core: a member of the wire's vocabulary, with the status the API gives it.

    ``WireCode(error)``, checked here and not inside the answer: this file once scripted three codes
    no Core sends — ``renewal.capped``, ``too_late``, ``code_reused`` — and the node, which branches
    on the status, passed on all three. A list of codes nobody checks is a list that does not know
    it is false; an invented one now raises at the line that invents it (M12.4).
    """
    wire = WireCode(error)
    body = {"error": {"code": wire.value, "message": wire.value}}
    return lambda _: httpx.Response(STATUS_OF[wire], json=body)


def dropped() -> Callable[[httpx.Request], httpx.Response]:
    def _raise(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nobody there", request=request)

    return _raise


def node_of(built: NodeWorld, script: Script) -> tuple[Node, NodeClient]:
    client = open_node_client(CORE, _identity(), script.transport())
    return Node(built, client), client


def _identity() -> Any:
    from ela.node import NodeIdentity

    return NodeIdentity(device_id="a-node", secret="a-secret-long-enough-to-look-real")


def order(
    *,
    capability: str = "core.echo",
    expires_at: datetime,
    decision: dict[str, Any],
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "assignment_id": "3f2b1a00-0000-4000-8000-000000000002",
        "capability_id": capability,
        "tool_name": "core-echo",
        "decision": decision,
        "arguments": arguments if arguments is not None else {"message": "ciao"},
        "expires_at": expires_at.isoformat(),
    }


class SlowEcho(Tool):
    """``core.echo`` that takes as long as a test needs it to.

    The renewal is the thing under test, and a renewal only happens while a tool is *still
    running* — with the real echo, which returns at once, the node would rightly never ask for
    more time. So the work is made slow instead of the deadline being made strange.
    """

    output_keys: ClassVar[frozenset[str]] = frozenset({"message"})
    idempotent: ClassVar[bool] = True

    def __init__(self, clock: Any, ids: Any, delay: float) -> None:
        super().__init__(CORE_ECHO, clock, ids, name=ECHO_TOOL_NAME)
        self._delay = delay

    async def _run(self, arguments: Any) -> Outcome:
        await asyncio.sleep(self._delay)
        return Outcome({"message": "fatto"})


def slowly(built: NodeWorld, delay: float = 0.05) -> NodeWorld:
    """The same node, with work that does not finish immediately."""
    return replace(built, tools=ToolRegistry((SlowEcho(built.clock, built.ids, delay),)))


class CostlyEcho(Tool):
    """A tool that fails *and* reports what the failure cost, which is the rarer envelope.

    ``error`` and ``usage`` travel in the envelope only when a tool produced them, and a provider
    call that failed after spending tokens produces both — the case the Core needs in order to
    record a bill for something that did not work (§32).
    """

    output_keys: ClassVar[frozenset[str]] = frozenset({"message"})
    idempotent: ClassVar[bool] = True

    def __init__(self, clock: Any, ids: Any) -> None:
        super().__init__(CORE_ECHO, clock, ids, name=ECHO_TOOL_NAME)

    async def _run(self, arguments: Any) -> Outcome:
        return Outcome(
            {},
            code="provider.overloaded",
            message="il fornitore era occupato",
            retryable=True,
            usage=ProviderUsage(input_tokens=11, output_tokens=0),
        )


def costly(built: NodeWorld) -> NodeWorld:
    return replace(built, tools=ToolRegistry((CostlyEcho(built.clock, built.ids),)))
