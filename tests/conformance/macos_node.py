"""The macOS node of M12.3, driving the contract with the code production runs (dec. G).

The second implementation of :class:`~tests.conformance.driver.NodeDriver`, and the first that is
not written for the suite: every act below calls the same :class:`~ela.node.NodeClient` that
``ela node run`` calls, over the same :func:`~ela.composition.build_node`, with the same four
tools. What the kit adds is a transport and two seams, and nothing else — if this file ever grows a
behaviour of its own, the suite stops proving the node and starts proving the file.

**Three things are not real, and all three are declared** (the shape of ADR 0031 §6, applied to a
kit instead of a test):

* the **transport** is ASGI, so no socket is opened — ``tests/conftest.py`` forbids the suite a
  real one and §57 is why. That a socket opens is proved by hand, in ``GETTING_STARTED.md``;
* the **clock** is a ``FakeClock`` an hour behind the Core's, exactly as the fake node's is: a node
  on the system clock would find every decision of a Core stopped in 2026 expired, and would answer
  ``refused`` to the eight stories that run a tool;
* the **voice** speaks into a ``FakeSpeech``, because a suite has no speakers and ``say`` on a test
  runner is a machine talking to an empty room. This is the seam dec. G added to ``build_node``,
  and the reason it is a declared parameter rather than a patch.

What is real: the identity written to a file with ``O_EXCL`` and ``0o600``, the HTTP acts, the
tools, the envelope, and the fact that a restart forgets the revision — which is the one thing the
fake node could not show, because its "new process" was the same Python object.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from httpx import ASGITransport

from ela.composition import NodeConfig, build_node
from ela.node import (
    Node,
    NodeClient,
    NodeIdentity,
    declaration,
    envelope_of,
    open_node_client,
    read_identity,
    write_identity,
)
from ela.testing.fakes import FakeClock, FakeSpeech
from tests.conformance.driver import Answered, Conformance, NodeDriver
from tests.conformance.fake_node import ONE_HOUR_BEHIND


def _scratch(world: Conformance) -> Path:
    """Where this suite's nodes keep their state: beside the Core's database, under ``tmp_path``.

    Derived from the capture store, which ``tests/composition/support.declare`` points at
    ``tmp_path``, for the reason ``ELA_CAPTURE_DIR`` itself exists: a test that left the default
    alone would write ``~/.ela/node.json`` into the home of whoever ran the suite — and that file
    is a secret, and ``O_EXCL`` would then make the second run fail on the first one's leftovers.
    """
    return world.ela.settings.captures.capture_dir.parent / "nodes"


def _config(world: Conformance, directory: Path) -> NodeConfig:
    """The node's five sections, pointed at this world and at a directory of its own.

    ``NodeConfig.load`` and not ``Settings.load``: a node reads five sections and not thirteen, and
    ``ELA_API_TOKEN`` — which the Core's loader refuses to start without — is none of its business.
    That is criterion 11, and it is worth having the kit go through the real loader so the claim is
    exercised on every story rather than in one test.
    """
    loaded = NodeConfig.load()
    return loaded.model_copy(
        update={
            "node": loaded.node.model_copy(
                update={"node_state_dir": directory, "node_core_url": world.base_url}
            )
        }
    )


class MacosNode:
    """One real node, driven act by act: the production cycle, taken apart for the stories."""

    def __init__(
        self,
        world: Conformance,
        *,
        directory: Path,
        clock: FakeClock,
        identity: NodeIdentity | None = None,
        tools: tuple[str, ...] | None = None,
    ) -> None:
        self._world = world
        self._directory = directory
        self._clock = clock
        self._declared_tools = tools
        self.speech = FakeSpeech()
        """The port the voice speaks through here: what it was asked to say is in ``said``."""
        self._built = build_node(_config(world, directory), clock=clock, speech=self.speech)
        self._client = self._open(identity)
        self._node = Node(self._built, self._client)
        self.held: dict[str, Any] | None = None
        """The envelope it has not delivered yet — the one thing a node keeps (D7)."""

    def _open(self, identity: NodeIdentity | None) -> NodeClient:
        return open_node_client(
            self._built.config.node.node_core_url,
            identity,
            ASGITransport(app=self._world.app),
        )

    # ----------------------------------------------------------------------------------
    # Who it is
    # ----------------------------------------------------------------------------------

    @property
    def device_id(self) -> str:
        identity = self._client.identity
        return "" if identity is None else identity.device_id

    @property
    def revision(self) -> int:
        return self._node.revision

    @property
    def tool_names(self) -> tuple[str, ...]:
        """What this node declares: the names of the tools that were actually built."""
        return tuple(tool.name for tool in self._built.tools.tools())

    def _declaration(self, declared: Mapping[str, Any]) -> dict[str, Any]:
        body = declaration(self._built)
        if self._declared_tools is not None:
            body["available_tools"] = list(self._declared_tools)
        return {**body, **dict(declared)}

    # ----------------------------------------------------------------------------------
    # The acts of M12.1: enroll, announce, report
    # ----------------------------------------------------------------------------------

    async def enroll(self, code: str, **declared: Any) -> Answered:
        """Present the code, and write the identity down before anything else happens."""
        answered = await self._client.enroll(code, self._declaration(declared))
        identity = self._client.identity
        if answered.status == 201 and identity is not None:
            write_identity(self._directory, identity)
            await self._node.refresh()
        return Answered(answered.status, answered.body)

    async def announce(self, **declared: Any) -> Answered:
        """The raw act, and the raw answer — a ``412`` comes back as a ``412``.

        The reading-and-retrying of dec. D lives in :meth:`~ela.node.Node.announce`, one floor up,
        and deliberately not here: the contract says every act answers with what the Core said, and
        story 5 asserts that the second of two announcements is a ``412``. An act that swallowed it
        would be the one line that turns that story green while breaking what it proves.
        """
        answered = await self._client.announce(self._declaration(declared), self._node.revision)
        if answered.etag is not None:
            self._node.saw(int(answered.etag.strip('"')))
        return Answered(answered.status, answered.body, answered.etag)

    async def report(self, **observed: Any) -> Answered:
        answered = await self._client.report(**observed)
        return Answered(answered.status, answered.body)

    # ----------------------------------------------------------------------------------
    # The acts of the work (ADR 0038 §11)
    # ----------------------------------------------------------------------------------

    async def ask(self) -> Answered:
        answered = await self._client.ask()
        return Answered(answered.status, answered.body)

    async def run(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run the call with this node's tools and keep the envelope until the Core has it."""
        envelope = await envelope_of(self._built, order)
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
        answered = await self._client.deliver(body)
        if answered.status == 200:
            self.held = None
        return Answered(answered.status, answered.body)

    async def renew(self, assignment_id: str) -> Answered:
        answered = await self._client.renew(assignment_id)
        return Answered(answered.status, answered.body)

    # ----------------------------------------------------------------------------------
    # Dying and coming back, and being two
    # ----------------------------------------------------------------------------------

    async def restart(self) -> None:
        """A new process: it reads its identity off the disk and asks for everything else.

        This is the production start-up, and it is where the difference between the two kits is.
        The revision is **not** read from a field that survived — this object keeps one only
        because a Python object cannot help it — it is read from the Core, with ``GET /nodes/me``,
        exactly as ``ela node run`` does before its first announcement. A node built the other way
        would come back believing a number nobody promised it.
        """
        await self._client.aclose()
        self._client = self._open(read_identity(self._directory))
        self._node = Node(self._built, self._client)
        await self._node.refresh()

    def clone(self) -> NodeDriver:
        """A second process claiming this identity (ADR 0035 §5): same id and secret, own client.

        Its own directory, because the real one would refuse to write over a state file that is
        already there — which is ``O_EXCL`` doing exactly what it is for, and not something to work
        around here. The twin does not enroll: it is handed the identity, which is what makes it a
        twin and not a second node.
        """
        twin = MacosNode(
            self._world,
            directory=self._directory / "twin",
            clock=FakeClock(self._clock.now()),
            identity=self._client.identity,
            tools=self._declared_tools,
        )
        twin._node.saw(self._node.revision)  # noqa: SLF001 — a twin starts from the same belief
        return twin

    async def aclose(self) -> None:
        await self._client.aclose()


class MacosNodeKit:
    """How the suite gets a node of this implementation. Recites every story of the contract."""

    name = "macos-node"

    def __init__(self) -> None:
        self._made = 0

    @property
    def unsupported(self) -> Mapping[str, str]:
        """**Empty**, and that is the claim of the milestone (dec. G, criterion 1).

        The map is where an implementation says what its platform cannot do. macOS can do all of
        it: it can be two processes, it can die and come back, it can keep a secret in a file. A
        node declaring a story unrecitable would be saying something about its platform, and this
        one has nothing to say.
        """
        return {}

    async def node(
        self,
        world: Conformance,
        *,
        privacy: str = "TRUSTED",
        tools: tuple[str, ...] | None = None,
    ) -> MacosNode:
        """Enrolled through the routes of M12.1, reporting once so the registry finds it available.

        A directory per node, because two nodes on one machine would be two state files and
        ``O_EXCL`` is what says so.
        """
        self._made += 1
        node = MacosNode(
            world,
            directory=_scratch(world) / f"node-{self._made}",
            clock=FakeClock(ONE_HOUR_BEHIND),
            tools=tools,
        )
        born = await node.enroll(await world.issue(privacy))
        assert born.status == 201, born.body
        if tools is not None:
            announced = await node.announce(available_tools=list(tools))
            assert announced.status == 200, announced.body
        reported = await node.report(status="IDLE", power_source="AC")
        assert reported.status == 200, reported.body
        return node


MACOS = MacosNodeKit()
"""The kit of M12.3, beside the fake node's. The stories do not change — dec. P."""
