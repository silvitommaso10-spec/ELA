"""The thirteen stories of the work protocol, once, for every driver (M12.2, dec. P; ADR 0038 §18).

Each story is a property of the **protocol**, not of an implementation: a node enrolls, announces,
asks, runs, reports back, goes quiet, comes back late, comes back twice, is revoked halfway. They
are written against :class:`~tests.conformance.driver.NodeDriver` and parametrised over the drivers,
so M12.3–M12.5 recite these and do not copy them.

**What this suite cannot prove — read this before trusting it**, in the form of
``tests/foreign_machine.py:24``. The property this repository's suite claims of itself is *"the
suite says the same thing on two machines"*; this one has to say the same thing about four
implementations, and its limits are:

* **One process, one event loop.** Two nodes here interleave at their ``await`` points. The real
  concurrency of a claim is proved elsewhere, with two SQL connections and a barrier
  (``tests/infrastructure/persistence/test_assignment_claim_race.py``).
* **No network.** The ASGI transport has no TCP, no Tailscale, no NAT, no connection cut halfway
  through a body, no intermediary closing a long-poll. "It degrades into polling" is proved by a
  driver that asks again, not by a network that makes it.
* **The clock is the Core's ``FakeClock``.** No node's real clock, no drift, no timeout of a real
  HTTP client. The expiry is proved; its tuning is not.
* **No TCC, no microphone, no screen, no keys.** ``voice.speak`` runs on a fake ``SpeechPort``; the
  wall of ADR 0029 §16 — the grant of Terminal.app, a signed executable — is not here.
* **The envelope survives a restart only as far as the driver makes it.** In the fake node that is a
  simulation; a real node proves it with its own driver.
* **Where a node keeps its secret never travels over HTTP**, so this suite cannot see it. Each of
  M12.3–M12.5 measures that on its own machine.
* **A Shortcut cannot be driven from pytest.** For the companion the suite proves that the subset of
  the protocol a Shortcut speaks is enough — one request, one header, one JSON — not the Shortcut.
* It proves that **the Core honours the contract in front of these stories**. It does not prove that
  an implementation is right beyond the stories its driver can recite.

Green here means: the Core and this node say the same thing about the contract. Green with the
driver of a real node, on its machine, is what counts.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from ela.domain import ActorKind, AuditEvent, AuditEventType, StepId, TaskEventType, TaskId
from ela.tools.verifiers import SPEECH_TEXT_MATCHES, SPEECH_TOOK_REAL_TIME
from tests.api.support import echo_plan, note_plan
from tests.conformance.driver import Conformance, NodeDriver, NodeKit, needs
from tests.conformance.fake_node import FAKE

E = AuditEventType
T = TaskEventType
PAST_THE_TTL = timedelta(seconds=61)
"""One second past ``ELA_ASSIGNMENT_TTL_SECONDS`` of the suite: the work is over, and so is the
Core's belief that the node is there (the heartbeat TTL is a minute too)."""

KITS: tuple[NodeKit, ...] = (FAKE,)
"""Every implementation that recites the contract. M12.3–M12.5 append theirs here, and the stories
below do not change — which is the whole claim of dec. P."""


@pytest.fixture(params=KITS, ids=lambda kit: kit.name)
def kit(request: pytest.FixtureRequest) -> NodeKit:
    return request.param  # type: ignore[no-any-return]


def speak_plan() -> dict[str, Any]:
    """A plan of one ``voice.speak`` step: a capability that travels and **cannot be repeated**.

    It needs the user's consent every time (the capability requires an authorization), which is what
    makes it the right tool for the stories about a node that goes quiet: the Core wrote a STARTED
    record before handing it out, so "whether it acted is unknown" is a real doubt.
    """
    return {
        "goal": "dire una frase",
        "steps": [
            {
                "id": "3f1d2c4b-5a69-4e7f-8b01-2c3d4e5f6a71",
                "goal": "speak",
                "required_capabilities": ["voice.speak"],
                "arguments": {"text": "La riunione è spostata a giovedì.", "purpose": "confermare"},
                "risk": "MEDIUM",
                "expected_result": "the sentence is spoken",
                "success_conditions": [SPEECH_TOOK_REAL_TIME, SPEECH_TEXT_MATCHES],
                "requires_authorization": True,
            }
        ],
    }


def tid(task_id: str) -> TaskId:
    return TaskId(UUID(task_id))


async def audit(world: Conformance, task_id: str) -> tuple[AuditEvent, ...]:
    return await world.ela.audit.read(task_id=tid(task_id))


async def types(world: Conformance, task_id: str) -> list[AuditEventType]:
    return [event.event_type for event in await audit(world, task_id)]


async def chosen(world: Conformance, task_id: str) -> list[AuditEvent]:
    return [one for one in await audit(world, task_id) if one.event_type is E.DEVICE_SELECTED]


async def released(world: Conformance, task_id: str) -> list[object]:
    events = await world.ela.repository.events(tid(task_id))
    return [one for one in events if one.event_type is T.STEP_RELEASED]


async def step_of(world: Conformance, task_id: str) -> StepId:
    detail = (await world.client.get(f"/tasks/{task_id}")).json()
    return StepId(UUID(detail["steps"][0]["id"]))


async def stored(world: Conformance, task_id: str) -> tuple[object, ...]:
    return await world.ela.results.for_step(tid(task_id), await step_of(world, task_id))


async def handed(
    world: Conformance,
    kit: NodeKit,
    plan: Mapping[str, Any],
    *,
    node: NodeDriver | None = None,
    privacy: str | None = "TRUSTED",
) -> tuple[str, NodeDriver]:
    """A task whose one step is handed out: the walk of production, and the user's consent if asked.

    Nothing here is a shortcut around the Core: the task is created through ``POST /tasks`` with the
    sensitivity the user declares, and the walk is ``POST /tasks/{id}/run``.
    """
    worker = await kit.node(world) if node is None else node
    task_id = await world.task(plan, privacy=privacy)
    walked = await world.walk(task_id)
    if walked.body["outcome"] == "waiting_approval":
        await world.approve(task_id)
        walked = await world.walk(task_id)
    assert walked.body["outcome"] == "assigned", walked.body
    return task_id, worker


async def taken(
    world: Conformance,
    kit: NodeKit,
    plan: Mapping[str, Any],
    *,
    node: NodeDriver | None = None,
) -> tuple[str, NodeDriver, Mapping[str, Any]]:
    """Handed out **and claimed**: the order the node received is what it will run."""
    task_id, worker = await handed(world, kit, plan, node=node)
    asked = await worker.ask()
    assert asked.status == 200, asked.body
    return task_id, worker, asked.body


# ----------------------------------------------------------------------------------------
# 1. Enrolled, announces, asks, runs, reports
# ----------------------------------------------------------------------------------------


async def test_story_enrolled_and_reports(world: Conformance, kit: NodeKit) -> None:
    """The whole turn, and who wrote each part of it: a declared task, a node that wins it, the call
    it receives, the envelope it brings back, the step that closes, the run that completes.

    **Every decision is the Core's.** Not one event of this task is written by a node: the
    permission, the execution, the verification and the closing are ELA's, and what the node
    contributed is the half of the result that is its tool's word (D7).
    """
    needs(kit, "enrolled_and_reports")
    task_id, node = await handed(world, kit, echo_plan())

    asked = await node.ask()
    envelope = await node.run(asked.body)
    delivered = await node.deliver(envelope)
    closed = await world.walk(task_id)

    assert asked.status == 200
    assert delivered.status == 200, delivered.body
    assert delivered.body["step"] == "COMPLETED"
    assert closed.body["outcome"] == "completed"
    assert [
        str(one.device_id)
        for one in await audit(world, task_id)
        if one.event_type is E.TOOL_EXECUTED
    ] == [node.device_id]
    assert E.EXECUTION_VERIFIED in await types(world, task_id)
    assert ActorKind.DEVICE not in {one.actor.kind for one in await audit(world, task_id)}


# ----------------------------------------------------------------------------------------
# 2. Never asks
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("plan", [echo_plan, speak_plan], ids=["core-echo", "voice-speak"])
async def test_story_never_asks(world: Conformance, kit: NodeKit, plan: Any) -> None:
    """An offer nobody claimed: nobody can have acted, so the step goes back in play — **whatever
    the tool** (dec. F). Choosing by idempotency here would fail a step nothing ever started."""
    needs(kit, "never_asks")
    task_id, node = await handed(world, kit, plan())

    world.clock.advance(PAST_THE_TTL)
    await node.report()  # alive, and still never asked: the expiry is about the work
    await world.walk(task_id)

    assert len(await released(world, task_id)) == 1
    assert len(await chosen(world, task_id)) == 2  # placed again, by whoever chooses (ADR 0026 §10)
    assert "execution.interrupted" not in str(await audit(world, task_id))


# ----------------------------------------------------------------------------------------
# 3. Goes quiet
# ----------------------------------------------------------------------------------------


async def test_story_goes_quiet_with_a_repeatable_tool(world: Conformance, kit: NodeKit) -> None:
    """It claimed and said nothing. ``core.echo`` can be run again, so there is no STARTED record to
    protect: the step is released and the node that is still reporting takes it."""
    needs(kit, "goes_quiet")
    task_id, gone, _ = await taken(world, kit, echo_plan())
    alive = await kit.node(world)

    world.clock.advance(PAST_THE_TTL)
    await alive.report()  # the other one stays silent, and silence is what the expiry reads
    walked = await world.walk(task_id)

    assert walked.body["outcome"] == "assigned"
    assert len(await released(world, task_id)) == 1
    assert str((await chosen(world, task_id))[-1].device_id) == alive.device_id


async def test_story_goes_quiet_with_a_tool_that_cannot_be_repeated(
    world: Conformance, kit: NodeKit
) -> None:
    """Same silence, different answer: ``voice.speak`` was started on the node, so whether it acted
    is unknown — the step is failed ``execution.interrupted`` with ``retryable``, and **no row
    claims the tool ran**. The Core does not invent an outcome, and it does not run it again."""
    needs(kit, "goes_quiet")
    task_id, gone, _ = await taken(world, kit, speak_plan())
    alive = await kit.node(world)

    world.clock.advance(PAST_THE_TTL)
    await alive.report()
    walked = await world.walk(task_id)

    assert walked.body["outcome"] == "failed"
    failed = [one for one in await audit(world, task_id) if one.event_type is E.STEP_FAILED][-1]
    assert failed.error is not None
    assert failed.error.code == "execution.interrupted"
    assert failed.error.retryable is True
    assert len(await released(world, task_id)) == 0  # it was not released: something may have run
    rows = [one.status.value for one in await stored(world, task_id)]  # type: ignore[attr-defined]
    assert set(rows) == {"STARTED"}  # the record of an intention, and no outcome beside it


# ----------------------------------------------------------------------------------------
# 4. Comes back late
# ----------------------------------------------------------------------------------------


async def test_story_comes_back_late(world: Conformance, kit: NodeKit) -> None:
    """Delivered after the expiry: ``410``, and the step is not touched by it.

    Accepting it would make the expiry of D6 a fact that depends on who passed by. What the node
    reports is kept as its **word** — the status, never the output — because for a tool that cannot
    be repeated it is the only thing that resolves "whether it acted"."""
    needs(kit, "comes_back_late")
    task_id, node, order = await taken(world, kit, echo_plan())
    envelope = await node.run(order)

    world.clock.advance(PAST_THE_TTL)
    late = await node.deliver(envelope)

    assert late.status == 410
    assert late.code == "assignment.expired"
    refusals = [one for one in await world.ela.audit.read() if one.event_type is E.DEVICE_REJECTED]
    assert refusals[-1].payload["reason"] == "late"
    assert refusals[-1].payload["reported_status"] == "SUCCEEDED"
    assert "ciao" not in str(refusals[-1].payload)
    assert await stored(world, task_id) == ()  # nothing of the delivery was written


# ----------------------------------------------------------------------------------------
# 5. Comes back in two
# ----------------------------------------------------------------------------------------


async def test_story_comes_back_twice_over(world: Conformance, kit: NodeKit) -> None:
    """Two processes claiming one identity (ADR 0035 §5, ADR 0037 §9).

    They announce at the same revision: one wins and reads the new ``ETag``, the other is told it
    believed something false about the row — ``412`` and ``DEVICE_IDENTITY_CONFLICT``. Then they ask
    together: exactly **one** order comes out, because work is taken once (D16). Then they both
    deliver: the same envelope is the same answer, and a different one is a conflict.
    """
    needs(kit, "comes_back_twice_over")
    node = await kit.node(world)
    twin = node.clone()

    first = await node.announce(name="pc-uno")
    second = await twin.announce(name="pc-due")

    assert (first.status, second.status) == (200, 412)
    assert first.etag is not None
    assert any(one.event_type is E.DEVICE_IDENTITY_CONFLICT for one in await world.ela.audit.read())

    task_id, _ = await handed(world, kit, echo_plan(), node=node)
    answers = [await node.ask(), await twin.ask()]
    assert sorted(one.status for one in answers) == [200, 204]
    winner, order = next(
        (one, got.body) for one, got in zip((node, twin), answers, strict=True) if got.status == 200
    )
    envelope = await winner.run(order)
    accepted = await winner.deliver(envelope)
    events = len(await world.ela.audit.read())

    replica = await twin.deliver(envelope, assignment_id=str(order["assignment_id"]))

    assert accepted.status == 200
    assert replica.status == 200  # the same bytes: the same answer, and nothing written twice
    assert len(await world.ela.audit.read()) == events

    other = await twin.deliver(
        {**envelope, "output": {"message": "altro"}}, assignment_id=str(order["assignment_id"])
    )

    assert other.status == 409
    assert other.code == "delivery.conflict"
    # A conflict *is* an action of the way of the work: exactly one ``DEVICE_REJECTED`` for it.
    assert len(await world.ela.audit.read()) == events + 1


# ----------------------------------------------------------------------------------------
# 6. Ask together
# ----------------------------------------------------------------------------------------


async def test_story_ask_together(world: Conformance, kit: NodeKit) -> None:
    """Two nodes ask at the same time: each receives only its own, and an offer for one **never**
    comes out for the other — the order is the answer to the request of the node the assignment
    names (regola 51, D4)."""
    needs(kit, "ask_together")
    first = await kit.node(world)
    second = await kit.node(world)
    task_id, _ = await handed(world, kit, echo_plan(), node=first)
    named = str((await chosen(world, task_id))[-1].device_id)
    mine, theirs = (first, second) if named == first.device_id else (second, first)

    stranger = await theirs.ask()
    owner = await mine.ask()

    assert stranger.status == 204
    assert owner.status == 200
    assert str(owner.body["assignment_id"])


# ----------------------------------------------------------------------------------------
# 7. Delivers twice
# ----------------------------------------------------------------------------------------


async def test_story_delivers_twice(world: Conformance, kit: NodeKit) -> None:
    """A network that retries is not an action (ADR 0016 §6): the same answer, no new row, no new
    event, and the step is not reopened."""
    needs(kit, "delivers_twice")
    task_id, node, order = await taken(world, kit, echo_plan())
    envelope = await node.run(order)
    first = await node.deliver(envelope)
    events = len(await world.ela.audit.read())
    rows = len(await stored(world, task_id))

    again = await node.deliver(envelope, assignment_id=str(order["assignment_id"]))

    assert (first.status, again.status) == (200, 200)
    assert again.body == first.body
    assert len(await world.ela.audit.read()) == events
    assert len(await stored(world, task_id)) == rows


# ----------------------------------------------------------------------------------------
# 8. Delivers what is not its own
# ----------------------------------------------------------------------------------------


async def test_story_delivers_what_is_not_its_own(world: Conformance, kit: NodeKit) -> None:
    """A node delivering on another's work is told exactly what it is told about an id the Core
    never minted: ``404``, one sentence. The other node's work is untouched, and the audit — which
    the user reads and nodes do not — keeps the difference."""
    needs(kit, "delivers_what_is_not_its_own")
    task_id, owner, order = await taken(world, kit, echo_plan())
    stranger = await kit.node(world)
    envelope = await owner.run(order)

    refused = await stranger.deliver(envelope, assignment_id=str(order["assignment_id"]))
    unknown = await stranger.deliver(envelope, assignment_id="00000000-0000-4000-8000-00000000ffff")

    assert refused.status == unknown.status == 404
    assert refused.body == unknown.body  # the same sentence: the difference is not for a node
    assert await stored(world, task_id) == ()
    assert (await owner.deliver(envelope)).status == 200  # its own work was never disturbed


# ----------------------------------------------------------------------------------------
# 9. Revoked halfway
# ----------------------------------------------------------------------------------------


async def test_story_revoked_halfway(world: Conformance, kit: NodeKit) -> None:
    """The user revokes a node that is holding work (D17): the secret opens nothing, and the work is
    over at that instant — so the next walk applies D14's answer **without waiting the TTL**."""
    needs(kit, "revoked_halfway")
    task_id, node, order = await taken(world, kit, echo_plan())
    envelope = await node.run(order)

    await world.revoke(node.device_id)
    refused = await node.deliver(envelope)
    world.clock.advance(timedelta(seconds=1))
    walked = await world.walk(task_id)

    assert refused.status == 401
    revoked = [
        one
        for one in await world.ela.audit.read()
        if one.event_type is E.DEVICE_REJECTED and one.payload.get("reason") == "revoked"
    ]
    assert revoked  # written by M12.1's registry, and not written twice by the way of the work
    assert world.clock.now().isoformat() < str(order["expires_at"])  # the TTL had not passed
    assert walked.body["outcome"] == "completed"  # released, placed again, and run here
    assert len(await released(world, task_id)) == 1


# ----------------------------------------------------------------------------------------
# 10. Works longer than the TTL
# ----------------------------------------------------------------------------------------


async def test_story_works_longer_than_the_ttl(world: Conformance, kit: NodeKit) -> None:
    """A tool that takes longer than the TTL renews, and the renewal has a cap: at the cap ``409``,
    and the work expires when it says. No audit for a renewal — a sign of life is not an action."""
    needs(kit, "works_longer_than_the_ttl")
    task_id, node, order = await taken(world, kit, echo_plan())
    assignment_id = str(order["assignment_id"])
    events = len(await world.ela.audit.read())

    world.clock.advance(timedelta(seconds=30))
    first = await node.renew(assignment_id)
    world.clock.advance(timedelta(seconds=30))
    second = await node.renew(assignment_id)
    world.clock.advance(timedelta(seconds=30))
    at_cap = await node.renew(assignment_id)

    assert (first.status, second.status) == (200, 200)
    assert second.body["expires_at"] > first.body["expires_at"]
    assert at_cap.status == 409
    assert at_cap.code == "assignment.at_cap"
    assert len(await world.ela.audit.read()) == events  # no renewal is an action (ADR 0016 §6)

    delivered = await node.deliver(await node.run(order))

    assert delivered.status == 200  # still inside the cap: the work it renewed is the work it had
    assert delivered.body["step"] == "COMPLETED"


# ----------------------------------------------------------------------------------------
# 11. The Core dies halfway
# ----------------------------------------------------------------------------------------


async def test_story_the_core_dies_halfway(world: Conformance, kit: NodeKit) -> None:
    """A new process over the same database, between the claim and the delivery.

    The node reconnects and delivers, and it is accepted: nothing the Core needs for that lived in
    the memory of the process that died (M5.3, ADR 0015). And ``recover()`` — which runs in the
    lifespan of the new process — does **not** fail the task: an assignment alive is not silence
    (ADR 0038 §9), because every write that sets an expiry wrote a heartbeat first.
    """
    needs(kit, "the_core_dies_halfway")
    task_id, node, order = await taken(world, kit, echo_plan())
    envelope = await node.run(order)

    await world.reborn()
    await node.restart()  # for a node, a Core that went away is a connection to make again
    delivered = await node.deliver(envelope)

    assert delivered.status == 200, delivered.body
    assert delivered.body["step"] == "COMPLETED"
    assert (await world.client.get(f"/tasks/{task_id}")).json()["state"] != "FAILED"
    assert (await world.walk(task_id)).body["outcome"] == "completed"


# ----------------------------------------------------------------------------------------
# 12. An undeclared task never arrives
# ----------------------------------------------------------------------------------------


async def test_story_an_undeclared_task_never_arrives(world: Conformance, kit: NodeKit) -> None:
    """The same plan and the same node, with the sensitivity nobody declared: the step runs **here**
    and the node is offered nothing. The default is the strictest level (D18), and that is the one
    half of M12.1's criterion 8 that is still true."""
    needs(kit, "an_undeclared_task_never_arrives")
    node = await kit.node(world)
    task_id = await world.task(echo_plan())

    walked = await world.walk(task_id)
    asked = await node.ask()

    assert walked.body["outcome"] == "completed"
    assert asked.status == 204
    refusals = {
        candidate["device_id"]: candidate["refusals"]
        for candidate in (await chosen(world, task_id))[-1].payload["candidates"]
    }
    assert "PRIVACY" in refusals[node.device_id]


# ----------------------------------------------------------------------------------------
# 13. What is verified only here never arrives
# ----------------------------------------------------------------------------------------


async def test_story_what_is_verified_only_here_never_arrives(
    world: Conformance, kit: NodeKit
) -> None:
    """A ``workspace.write_note`` step of a declared task stays on this machine (D15): its verifier
    reads **this** disk, so from anywhere else it would prove nothing — and a note with the same
    path in the Core's workspace would be a false positive. The node is offered nothing, and the
    reason says ``UNVERIFIABLE``."""
    needs(kit, "what_is_verified_only_here_never_arrives")
    node = await kit.node(world)
    task_id = await world.task(note_plan(), privacy="TRUSTED")

    walked = await world.walk(task_id)
    if walked.body["outcome"] == "waiting_approval":
        await world.approve(task_id)
        walked = await world.walk(task_id)
    asked = await node.ask()

    assert walked.body["outcome"] == "completed"
    assert asked.status == 204
    refusals = {
        candidate["device_id"]: candidate["refusals"]
        for candidate in (await chosen(world, task_id))[-1].payload["candidates"]
    }
    assert "UNVERIFIABLE" in refusals[node.device_id]
