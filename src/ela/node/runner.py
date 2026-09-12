"""The cycle of a node: enrol, read, announce, report, ask, run, deliver, renew (M12.3).

This is the one module of ``ela.node`` that calls ``Tool.execute`` — architecture rule 16, widened
by path and by caller and not by package. The reason is M12.1 D1's: the Core's executor stays the
only thing that runs a tool **on this machine**, and this is the only thing that runs one on a
machine the Core is not. Everything the Guardian decided arrives inside the order; nothing here
decides anything, and in particular nothing here decides *when*: a node never mints an expiry, it
asks for more time and is told (architecture rule 53).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final

import httpx

from ela.composition.node import NodeWorld
from ela.domain import CapabilityId, PermissionDecision
from ela.node.client import NodeClient
from ela.node.errors import (
    REVOKED,
    TWIN,
    UNCONDITIONAL,
    CoreUnreachable,
    NodeError,
    NodeRevoked,
    TwinNode,
)
from ela.ports import NotAllowedError

__all__ = ["Node", "declaration", "envelope_of"]

RENEW_AT: Final = 0.5
"""How much of the remaining time to let pass before asking for more.

Half, so a renewal that is refused still leaves as much time again to finish or to lose the work
cleanly. Asking at the very end would mean a slow network turns "renewed" into "expired", and
asking immediately would mean asking constantly for work that is about to finish anyway.
"""

DELIVERY_CONFLICT: Final = "delivery.conflict"
"""``409`` on delivery, and the one that means **the Core has already decided** (ADR 0038 §12)."""

IDLE: Final = "IDLE"
BUSY: Final = "BUSY"
"""What the node reports of itself, and the only two it can honestly tell apart."""

DECIDED: Final = frozenset({httpx.codes.NOT_FOUND, httpx.codes.GONE})
"""The statuses on which the Core has decided about this work, so the envelope is nobody's."""

ALREADY_RUNNING: Final = "already_running"
"""``409`` on delivery, and the one the node **keeps the envelope** for (ADR 0038 §12).

The Core is busy with that task and has written nothing: this is a "not now". The other ``409``
there — ``delivery.conflict`` — is the Core having already decided, and then the envelope is
nobody's. The two are told apart by ``error.code`` and never by the status, which is the same.
"""


def declaration(world: NodeWorld) -> dict[str, Any]:
    """What this node says about itself: five fields, and four of them are derived (dec. F).

    ``available_tools`` comes from the objects that were actually built, the way the fake node's
    does, and for the same reason: a declaration written by hand is a promise, and the hard filter
    drops a node that lacks a tool it claimed only after a step has already been placed on it.

    ``capabilities`` is **empty and deliberately so**: a ``DeviceCapability`` is a trait, no step
    requires one today, and M12.1 D9 keeps ``MISSING_TRAIT`` out of production until some path can
    produce it. Traits arrive with the filter that reads them.
    """
    return {
        "name": world.config.node.node_name,
        "os": "MACOS",
        "capabilities": [],
        "available_tools": [tool.name for tool in world.tools.tools()],
        "performance": world.config.node.node_performance.value,
    }


async def envelope_of(world: NodeWorld, order: Mapping[str, Any]) -> dict[str, Any]:
    """Run the call on **this** node and put what came back in an envelope (ADR 0038 §4).

    The three forms come from the three ways a tool ends, and this is where they are told apart: an
    answer, a refusal of the decision — ``check_decision`` against *this* node's clock, which is
    why that clock is a declared parameter — and an exception, whose type's name travels and whose
    message never does, because a message can carry the user's content off the machine (§57).

    No ``ExecutionResult`` is built here and none is sent: the Core rebuilds it from what this
    envelope reports (M12.1 D1). The node's own instants travel under ``node``, as reported data,
    and never as an instant of the chain.

    **The lookup is inside the ``try``, and that is criterion 7.** An order for a capability this
    node does not have comes back as an ``exception`` envelope instead of killing the cycle: a tool
    never trusts its caller (§28), and since M12.3 the caller is on another machine. In production
    it does not fire — the hard filter drops a node that lacks the tool before a step is placed on
    it (M12.2 dec. L) — which makes it a defence at a new boundary rather than a refusal with no
    producer in the sense of ADR 0026 §7.
    """
    try:
        decision = PermissionDecision.model_validate(dict(order["decision"]))
        tool = world.tools.get(CapabilityId(str(order["capability_id"])))
        result = await tool.execute(decision, dict(order["arguments"]))
    except NotAllowedError:
        return {"form": "refused"}
    except Exception as raised:  # noqa: BLE001 — a node reports the type, never the message
        return {"form": "exception", "exception": type(raised).__name__}
    envelope: dict[str, Any] = {
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
    return envelope


class Node:
    """One node, running: its identity, its tools, and the one envelope it may owe the Core."""

    def __init__(self, world: NodeWorld, client: NodeClient) -> None:
        self._world = world
        self._client = client
        self._revision = 0
        self._held: dict[str, Any] | None = None
        """The envelope it has not delivered yet — the one thing a node keeps (M12.1 D7).

        In memory and never on disk: it holds the user's content, and writing it down would put a
        second copy of that on a remote machine, with its own life and its own deletion, to protect
        a case the protocol already closes — if the node dies the assignment expires and M12.1 D6
        decides on the tool's idempotence.
        """

    @property
    def revision(self) -> int:
        return self._revision

    def saw(self, revision: int) -> None:
        """Remember a revision the Core just reported, as an ``ETag`` carried it.

        A node is *told* its revision and never counts one: a node keeping its own counter would be
        guessing, and the guess is wrong exactly when a second process is writing (ADR 0037 §9).
        """
        self._revision = revision

    @property
    def held(self) -> Mapping[str, Any] | None:
        return self._held

    # ----------------------------------------------------------------------------------
    # Coming up: read who I am, say what I am, say I am here
    # ----------------------------------------------------------------------------------

    async def refresh(self) -> None:
        """Read the revision from the Core, because this process does not remember one (dec. L)."""
        answered = await self._client.whoami()
        if answered.status == httpx.codes.UNAUTHORIZED:
            raise NodeRevoked(REVOKED)
        seen = answered.revision
        if seen is not None:
            self.saw(seen)

    async def announce(self) -> None:
        """Rewrite the declared half at the revision just read — and read once more on a ``412``.

        Once, and the second ``412`` is a twin (dec. D, dec. L). The refresh lives here, **above**
        the act and not inside it: the contract says every act answers with what the Core said, and
        story 5 asserts that the second of two announcements is a ``412``. An ``announce`` that
        swallowed it and returned the retry's ``200`` would be the one line that breaks that story.
        """
        answered = await self._client.announce(declaration(self._world), self._revision)
        if answered.status == httpx.codes.PRECONDITION_FAILED:
            await self.refresh()
            answered = await self._client.announce(declaration(self._world), self._revision)
            if answered.status == httpx.codes.PRECONDITION_FAILED:
                raise TwinNode(TWIN)
        if answered.status == httpx.codes.UNAUTHORIZED:
            raise NodeRevoked(REVOKED)
        if answered.status == httpx.codes.PRECONDITION_REQUIRED:
            # The node forgot its own ``If-Match``: a defect of this code, not of the Core, and it
            # would otherwise walk on into the work loop as though it had announced (dec. D).
            raise NodeError(UNCONDITIONAL)
        seen = answered.revision
        if seen is not None:
            self.saw(seen)

    async def report(self, status: str = IDLE) -> None:
        """A sign of life, so the registry finds this node available at all (ADR 0016 §3).

        **Only what it has observed.** The first version of this line sent ``power_source="AC"``,
        and the orchestrator pays 10 points for that and 10 more for ``IDLE`` — so 20 of the 25
        points this node scored in the measurement of dec. K.3 came from two things it had never
        looked at, on a laptop that may well have been on battery. ``STATUS_POINTS``'s own
        docstring says why that is wrong: "an unknown status must score zero … so that a fact
        nobody observed is never mistaken for a good one". The power source is not sent at all —
        reading it is a machine adapter, and a node has none yet — and the status is sent because
        the node does know it: idle when it is about to ask, busy while a tool of its own is
        running.
        """
        answered = await self._client.report(status=status)
        if answered.status == httpx.codes.UNAUTHORIZED:
            raise NodeRevoked(REVOKED)

    # ----------------------------------------------------------------------------------
    # One turn of the work: ask, run while asking for more time, deliver
    # ----------------------------------------------------------------------------------

    async def turn(self) -> bool:
        """One pass: ask, and if there was work, run it and deliver it. ``True`` if there was.

        A ``204`` is the normal answer and also what a Core being shut down cleanly gives, at once
        instead of holding the request (``api/nodes.py``): the node does not need to tell the two
        apart — they are the same ``204`` — and in both cases it asks again.
        """
        if self._held is not None:
            await self.deliver()
            return True
        asked = await self._client.ask()
        if asked.status == httpx.codes.UNAUTHORIZED:
            raise NodeRevoked(REVOKED)
        if asked.status != httpx.codes.OK:
            return False
        order = asked.body
        self._held = {
            **await self._run(order),
            "assignment_id": str(order["assignment_id"]),
        }
        await self.deliver()
        return True

    async def _run(self, order: Mapping[str, Any]) -> Mapping[str, Any]:
        """Run the tool, asking for more time while it is still running (M12.2 dec. K).

        The node never decides how long it has: it reads the deadline the order declares, asks
        before it passes, and reads the new one from the answer. At the cap the Core says ``409``
        and the node stops asking — it does not take the time it was refused.
        """
        running = asyncio.ensure_future(envelope_of(self._world, order))
        assignment_id = str(order["assignment_id"])
        expires_at = datetime.fromisoformat(str(order["expires_at"]))
        while True:
            left = (expires_at - self._world.clock.now()).total_seconds()
            done, _ = await asyncio.wait({running}, timeout=max(left * RENEW_AT, 0.0))
            if done:
                return await running
            # **A heartbeat here too, and it is not a courtesy.** Renewing keeps the *assignment*
            # alive; it says nothing about the *node*, whose availability has a TTL of its own
            # (``ELA_DEVICE_HEARTBEAT_TTL_SECONDS``, 60 s by default). Without this line a tool
            # that runs longer than a minute would leave the node UNAVAILABLE **while it is
            # working** — the work in hand survives, but placement and ``ela device list`` would
            # both be wrong about it for the duration. It is the same defect the by-hand proof
            # found at start-up, one floor down, and the comment that said a turn is bounded by
            # the poll window was false exactly here: a turn that gets work lasts the window
            # **plus** the tool.
            await self.report(BUSY)
            renewed = await self._client.renew(assignment_id)
            if renewed.status == httpx.codes.UNAUTHORIZED:
                raise NodeRevoked(REVOKED)
            if renewed.status != httpx.codes.OK:
                # The cap (``409``), or work that is no longer this node's (``404``, ``410``).
                # Either way there is no more time to be had: finish, and let the delivery say
                # what became of it.
                return await running
            expires_at = datetime.fromisoformat(str(renewed.body["expires_at"]))

    async def deliver(self) -> None:
        """Hand the envelope over, and keep it only when the Core said "not now" (D7).

        ``200`` the Core has it; ``409 already_running`` it is busy and wrote nothing, so the
        envelope stays here and goes again; anything else — ``404``, ``410``, the other ``409`` —
        is the Core having decided, and then the envelope is nobody's and holding it would be
        holding the user's content for no reason.
        """
        held = self._held
        if held is None:  # pragma: no cover - turn() never calls this with nothing in hand
            return
        answered = await self._client.deliver(held)
        if answered.status == httpx.codes.UNAUTHORIZED:
            raise NodeRevoked(REVOKED)
        if answered.status == httpx.codes.OK:
            self._held = None  # the Core has it: a node keeps nothing it has been told about
            return
        decided = answered.status in DECIDED or answered.code == DELIVERY_CONFLICT
        if decided:
            self._held = None
        # And on anything else the envelope **stays**. The first version let it go on every
        # answer that was not ``409 already_running``, which quietly included the ``503`` of a
        # database that was busy and the ``500`` of a Core having a bad day — cases where the Core
        # wrote nothing at all, which is precisely the case D7 exists for. The rule is not "which
        # status is it" but "did the Core decide": ``404`` and ``410`` say the work is not this
        # node's or is too late, and ``delivery.conflict`` says another envelope won. Everything
        # else is a Core that has not made up its mind, and a paid call thrown away for it would
        # be the user's money.


async def coming_up(node: Node) -> None:
    """Read who this node is, say what it is, say it is here (dec. L, dec. D).

    Three acts and not one, and they are here — inside what retries — rather than in
    :func:`~ela.node.run`, because **the ordinary way to start a node is before the Core is up**:
    a reboot brings both terminals back and nothing says which goes first. With these three above
    the loop, a Core that is not listening yet made ``httpx.ConnectError`` escape ``run`` and the
    command, past every ``except`` either of them has, and a person got a traceback and exit ``1``
    where dec. D says "wait and retry" and ADR 0039 §4 says exit ``3``.
    """
    await node.refresh()
    await node.announce()


async def forever(node: Node, *, wait: float, ceiling: int) -> None:
    """Ask, run, deliver, and keep doing it until something says to stop (dec. C, dec. D).

    A dropped connection is not a reason to stop and not a reason to re-enrol: it is a Core that is
    not there yet or not there any more, and the node's whole job is to be the one still waiting.
    It waits, tries again, and gives up only at the ceiling — the count resets on every answer, so
    a Core that comes back has a node that forgot it was ever away.

    Every pass says "I am here" before it asks for anything, because being there is not something
    the Core can infer from the asking: availability has a TTL of its own.
    """
    missed = 0
    ready = False
    while True:
        try:
            if not ready:
                await coming_up(node)
                ready = True
            # **Before every ask, and not only at start-up.** A node is available only as long as
            # the Core has heard from it inside ``ELA_DEVICE_HEARTBEAT_TTL_SECONDS`` (ADR 0016 §3),
            # and a node that reported once goes UNAVAILABLE a minute later — still running, still
            # asking, and never chosen again. Found by hand with two real processes on 2026-09-12:
            # the orchestrator picked this node and then refused it, "is no longer eligible:
            # UNAVAILABLE". The conformance suite could not see it — its stories report once and
            # act at once, on a clock that does not move on its own.
            #
            # Here rather than on a timer of its own, because a turn is bounded by the Core's own
            # poll window: one heartbeat per cycle is one per window, and a window longer than the
            # TTL is a Core whose two settings disagree with each other.
            await node.report()
            # **Here, and not in an ``else:`` after the whole pass.** The count is about "is
            # anybody there", and an answered heartbeat has already answered that. Resetting only
            # at the end of a clean pass meant a Core that answered every heartbeat but dropped
            # every long poll — an intermediary cutting a held connection is the ordinary way that
            # happens — would end the node with "nobody answered after 60 tries", which would have
            # been false sixty times.
            missed = 0
            await node.turn()
            if node.held is not None:
                # The Core said "not now" (``409 already_running``) and the envelope is still
                # here. Coming straight back would be a loop as tight as the socket allows, for
                # as long as the Core holds the task's lock. This is dec. K.2's interval of
                # resumption, and it is the same number the retry uses.
                await asyncio.sleep(wait)
        except httpx.TransportError:
            missed += 1
            if missed >= ceiling:
                raise CoreUnreachable(
                    f"nobody answered at the Core's address after {ceiling} tries."
                ) from None
            await asyncio.sleep(wait)
