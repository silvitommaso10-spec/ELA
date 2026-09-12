"""A node of this repository: in-process, over ASGI, with real tools (M12.2, dec. P).

The first implementation of :class:`~tests.conformance.driver.NodeDriver`, and the one M12.3–M12.5
are measured against. It is **not** a mock of the protocol: it enrolls with a code the user issued,
announces at the revision it last saw, asks for work over HTTP, and runs the real tool of the
capability it was given — ``core.echo`` as it is, because nothing of it touches the world, and
``voice.speak`` on a fake :class:`~ela.ports.SpeechPort`, because a suite has no speakers.

What makes it a node and not a second Core: it holds an id the Core minted, a secret it presents on
every request, the revision of its own row, and the envelope it has not managed to deliver yet. It
decides nothing — there is no placement here, no clock of the Core, no access to the database.

Its ``UNSUPPORTED`` map is **empty**, and that is the pin of dec. P: every story of the contract is
recitable by an implementation that exists, so a real node declaring one unrecitable is declaring
something about its platform and not about the protocol.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ela.domain import CapabilityId, PermissionDecision
from ela.ports import NotAllowedError
from ela.testing.fakes import DEFAULT_START, FakeClock, FakeIdGenerator, FakeSpeech
from ela.tools import EchoTool, SpeakTool
from tests.conformance.driver import Answered, Conformance, NodeDriver

ONE_HOUR_BEHIND = DEFAULT_START.replace(hour=DEFAULT_START.hour - 1)
"""Where a node's own clock starts: an hour off the Core's, and deliberately.

A node's clock is its own (D1), and the Core's chain must not inherit it — criterion 8. Behind and
not ahead, because a node ahead of the Core by more than a decision's remaining life refuses the
call at ``check_decision``, which is a story of its own and not the default.
"""


class FakeNode:
    """One node: its identity, its tools, its clock, and whatever it still owes the Core."""

    def __init__(
        self,
        world: Conformance,
        *,
        device_id: str,
        secret: str,
        revision: int,
        clock: FakeClock,
    ) -> None:
        self._world = world
        self._client = world.node_client()
        self._device_id = device_id
        self._secret = secret
        self._revision = revision
        self._clock = clock
        self._ids = FakeIdGenerator()
        self.speech = FakeSpeech()
        """The port the voice speaks through here: what it was asked to say is in ``said``."""
        self._tools = {
            CapabilityId("core.echo"): EchoTool(clock, self._ids),
            CapabilityId("voice.speak"): SpeakTool(
                self.speech, clock, self._ids, voice="Alice", enabled=True
            ),
        }
        self.order: Mapping[str, Any] | None = None
        """The last order this node received, as it received it."""
        self.held: dict[str, Any] | None = None
        """The envelope it has not delivered yet — the one thing a node keeps for the Core (D7)."""

    # ----------------------------------------------------------------------------------
    # Who it is
    # ----------------------------------------------------------------------------------

    @property
    def device_id(self) -> str:
        return self._device_id

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def tool_names(self) -> tuple[str, ...]:
        """What this node declares it can run: the names of the tools it actually has."""
        return tuple(tool.name for tool in self._tools.values())

    @property
    def _bearer(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._device_id}.{self._secret}"}

    # ----------------------------------------------------------------------------------
    # The acts of M12.1: enroll, announce, report
    # ----------------------------------------------------------------------------------

    async def enroll(self, code: str, **declared: Any) -> Answered:
        answered = await self._client.post(
            "/nodes/enroll",
            json=self._declaration(declared),
            headers={"Authorization": f"Bearer {code}"},
        )
        if answered.status_code == 201:
            born = answered.json()
            self._device_id = str(born["device_id"])
            self._secret = str(born["secret"])
            self._revision = int(born["revision"])
        return Answered(answered.status_code, answered.json())

    async def announce(self, **declared: Any) -> Answered:
        """At the revision last seen, and the new one is read back from the ``ETag`` (ADR 0037 §9).

        A node that announced unconditionally would overwrite whatever another process claiming its
        identity had written; a node that kept its own counter would be guessing. So: ``If-Match``
        out of what it was told, ``ETag`` in.
        """
        answered = await self._client.put(
            "/nodes/me",
            json=self._declaration(declared),
            headers={**self._bearer, "If-Match": f'"{self._revision}"'},
        )
        etag = answered.headers.get("ETag")
        if etag is not None:
            self._revision = int(etag.strip('"'))
        return Answered(answered.status_code, answered.json(), etag)

    async def report(self, **observed: Any) -> Answered:
        answered = await self._client.post(
            "/nodes/heartbeat", json=dict(observed), headers=self._bearer
        )
        return Answered(answered.status_code, answered.json())

    def _declaration(self, declared: Mapping[str, Any]) -> dict[str, Any]:
        """What this node says about itself: built to win on points, and honest about its tools."""
        return {
            "name": f"fake-{self._device_id[:8]}" if self._device_id else "fake-node",
            "os": "WINDOWS",
            "available_tools": list(self.tool_names),
            "performance": "HIGH",
            **dict(declared),
        }

    # ----------------------------------------------------------------------------------
    # The acts of the work (ADR 0038 §11)
    # ----------------------------------------------------------------------------------

    async def ask(self) -> Answered:
        answered = await self._client.post("/nodes/work", headers=self._bearer)
        body: Mapping[str, Any] = {} if answered.status_code == 204 else answered.json()
        if answered.status_code == 200:
            self.order = body
        return Answered(answered.status_code, body)

    async def run(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run the call on **this** node and keep the envelope until the Core has it.

        The three forms of ADR 0038 §4 come from the three ways a tool ends, and this is where they
        are told apart: an answer, a refusal of the decision (``check_decision`` against *this*
        node's clock), and an exception, whose type's name travels and whose message never does.
        """
        decision = PermissionDecision.model_validate(dict(order["decision"]))
        tool = self._tools[CapabilityId(str(order["capability_id"]))]
        envelope: dict[str, Any]
        try:
            result = await tool.execute(decision, dict(order["arguments"]))
        except NotAllowedError:
            envelope = {"form": "refused"}
        except Exception as raised:  # noqa: BLE001 — a node reports the type, never the message
            envelope = {"form": "exception", "exception": type(raised).__name__}
        else:
            envelope = {
                "form": "result",
                "status": result.status.value,
                "output": dict(result.output),
                "duration_ms": result.duration_ms,
                "node": {"ran_at": result.created_at.isoformat(), "result_id": str(result.id)},
            }
            if result.error is not None:
                envelope["error"] = result.error.model_dump(mode="json")
            if result.usage is not None:
                envelope["usage"] = result.usage.model_dump(mode="json")
        self.held = {**envelope, "assignment_id": str(order["assignment_id"])}
        return envelope

    async def deliver(
        self, envelope: Mapping[str, Any], *, assignment_id: str | None = None
    ) -> Answered:
        held = self.held or {}
        body = {
            **dict(envelope),
            "assignment_id": assignment_id
            if assignment_id is not None
            else str(held.get("assignment_id")),
        }
        answered = await self._client.post("/nodes/work/result", json=body, headers=self._bearer)
        if answered.status_code == 200:
            self.held = None  # the Core has it: a node keeps nothing it has been told about
        return Answered(answered.status_code, answered.json())

    async def renew(self, assignment_id: str) -> Answered:
        answered = await self._client.post(
            "/nodes/work/renew", json={"assignment_id": assignment_id}, headers=self._bearer
        )
        return Answered(answered.status_code, answered.json())

    # ----------------------------------------------------------------------------------
    # Dying and coming back, and being two
    # ----------------------------------------------------------------------------------

    async def restart(self) -> None:
        """A new process with the same identity — and the envelope it had not delivered.

        How much of that survives a real restart is the driver's business and nobody else's: here it
        is a simulation, and the suite says so among its limits. What is *not* simulated is the
        identity: the id and the secret are what the node kept on disk, as a real one does.
        """
        await self._client.aclose()
        self._client = self._world.node_client()

    def clone(self) -> NodeDriver:
        """A second process claiming this identity (ADR 0035 §5): same id and secret, own client."""
        twin = FakeNode(
            self._world,
            device_id=self._device_id,
            secret=self._secret,
            revision=self._revision,
            clock=FakeClock(self._clock.now()),
        )
        return twin

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeNodeKit:
    """How the suite gets a node of this implementation. Recites every story of the contract."""

    name = "fake-node"

    @property
    def unsupported(self) -> Mapping[str, str]:
        """Empty, and pinned empty by ``test_unsupported.py``: the implementation this repository
        ships can play the whole protocol, which is what makes the map meaningful for the others."""
        return {}

    async def node(
        self,
        world: Conformance,
        *,
        privacy: str = "TRUSTED",
        tools: tuple[str, ...] | None = None,
    ) -> FakeNode:
        """Enrolled through the routes of M12.1, reporting once so the registry finds it available.

        ``tools`` narrows what the node declares — the story of a capability that cannot travel uses
        it — and ``privacy`` is the level the **user** imposes on the code, never the node's claim.
        """
        node = FakeNode(
            world,
            device_id="",
            secret="",
            revision=0,
            clock=FakeClock(ONE_HOUR_BEHIND),
        )
        born = await node.enroll(await world.issue(privacy))
        assert born.status == 201, born.body
        if tools is not None:
            announced = await node.announce(available_tools=list(tools))
            assert announced.status == 200, announced.body
        reported = await node.report(status="IDLE", power_source="AC")
        assert reported.status == 200, reported.body
        return node


FAKE = FakeNodeKit()
"""The one kit of this milestone. M12.3–M12.5 each add theirs beside it, and the stories do not
change — which is the whole claim of dec. P."""
