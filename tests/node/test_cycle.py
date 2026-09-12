"""The seven answers of dec. D, and what a node does about each (M12.3; ADR 0039 §7).

The table in the ADR is the specification and this file is it, answer by answer. Two properties run
through all of them. **A node decides nothing**: every branch here is a reaction to something the
Core said, and the one thing a node is allowed to hold on to is an envelope it has not managed to
deliver (M12.1 D7). And **a node never decides the time**: it reads the deadline the order carries,
asks for more before it passes, and at the cap stops asking instead of taking what it was refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ela.domain import CapabilityId
from ela.node import (
    CoreUnreachable,
    NodeRevoked,
    Reply,
    TwinNode,
    declaration,
    envelope_of,
    forever,
)
from ela.testing.fakes import FakeClock
from tests.node.support import (
    costly,
    dropped,
    node_of,
    ok,
    order,
    refused,
    replies,
    slowly,
    status,
    world,
)
from tests.tools.support import allowed

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
SOON = NOW + timedelta(seconds=120)


def decision() -> dict[str, Any]:
    return allowed(CapabilityId("core.echo")).model_dump(mode="json")


# ----------------------------------------------------------------------------------------
# Coming up: read the revision, announce against it, say you are here
# ----------------------------------------------------------------------------------------


async def test_a_node_that_came_back_reads_the_revision_it_must_announce_against(
    tmp_path: Path,
) -> None:
    """Dec. L: the file has two fields, so the revision is asked for — and the answer carries it
    where the announcement already looks, in the ``ETag``."""
    script = replies(ok({}, ETag='"7"'), ok({}, ETag='"8"'))
    node, _ = node_of(world(tmp_path), script)

    await node.refresh()
    assert node.revision == 7

    await node.announce()
    assert node.revision == 8
    assert script.seen == [("GET", "/nodes/me"), ("PUT", "/nodes/me")]


async def test_a_412_is_read_again_once_and_the_second_one_is_a_twin(tmp_path: Path) -> None:
    """Dec. D and ADR 0035 §5, in one test because the two halves are one decision.

    Once is a revision that moved while this node was not looking. Twice, straight after reading
    it, is somebody else writing — and a node that announced harder instead would take from
    ADR 0035 §5 its only proof: two processes chasing each other for ever, neither telling anyone.
    """
    twice = replies(
        status(412), ok({}, ETag='"4"'), status(412), status(412), ok({}, ETag='"9"'), status(412)
    )
    node, _ = node_of(world(tmp_path), twice)

    with pytest.raises(TwinNode, match="second process"):
        await node.announce()

    assert [method for method, _ in twice.seen] == ["PUT", "GET", "PUT"]


async def test_a_412_that_the_reread_repairs_is_not_a_twin(tmp_path: Path) -> None:
    script = replies(status(412), ok({}, ETag='"4"'), ok({}, ETag='"5"'))
    node, _ = node_of(world(tmp_path), script)

    await node.announce()

    assert node.revision == 5


@pytest.mark.parametrize("act", ["refresh", "announce", "report"])
async def test_a_401_stops_the_node_wherever_it_arrives(tmp_path: Path, act: str) -> None:
    """M12.1 D13: a revoked node has nothing to retry, and one that kept asking would write a
    ``DEVICE_REJECTED`` on every cycle — an audit log filled by a process nobody told to stop."""
    node, _ = node_of(world(tmp_path), replies(status(401), status(401)))

    with pytest.raises(NodeRevoked, match="revoked"):
        await getattr(node, act)()


# ----------------------------------------------------------------------------------------
# One turn of the work
# ----------------------------------------------------------------------------------------


async def test_no_work_is_the_normal_answer_and_the_node_simply_asks_again(
    tmp_path: Path,
) -> None:
    """A clean shutdown answers ``204`` at once instead of holding the request, and it is the
    **same** ``204``: the node does not have to tell the two apart."""
    node, _ = node_of(world(tmp_path), replies(status(204)))

    assert await node.turn() is False
    assert node.held is None


async def test_a_401_on_the_ask_stops_the_node(tmp_path: Path) -> None:
    node, _ = node_of(world(tmp_path), replies(status(401)))

    with pytest.raises(NodeRevoked):
        await node.turn()


async def test_work_is_run_here_and_the_envelope_goes_back(tmp_path: Path) -> None:
    given = order(expires_at=SOON, decision=decision())
    script = replies(status(200, given), ok({"state": "DELIVERED", "step": "COMPLETED"}))
    node, _ = node_of(world(tmp_path), script)

    assert await node.turn() is True

    assert node.held is None
    assert script.seen == [("POST", "/nodes/work"), ("POST", "/nodes/work/result")]


# ----------------------------------------------------------------------------------------
# The envelope: kept on a "not now", let go on a decision (D7)
# ----------------------------------------------------------------------------------------


async def test_the_envelope_is_kept_when_the_core_says_not_now(tmp_path: Path) -> None:
    """``409 already_running``: the Core is busy with that task and wrote nothing. This is the
    case D7 exists for, and the node comes back with the same envelope."""
    given = order(expires_at=SOON, decision=decision())
    script = replies(
        status(200, given),
        refused(409, "already_running"),
        ok({"state": "DELIVERED", "step": "COMPLETED"}),
    )
    node, _ = node_of(world(tmp_path), script)

    await node.turn()
    assert node.held is not None

    assert await node.turn() is True
    assert node.held is None
    assert [path for _, path in script.seen].count("/nodes/work/result") == 2


@pytest.mark.parametrize(
    ("code", "error"),
    [(409, "delivery.conflict"), (404, "not_assigned"), (410, "too_late")],
)
async def test_the_envelope_is_let_go_when_the_core_has_already_decided(
    tmp_path: Path, code: int, error: str
) -> None:
    """Holding it would be holding the user's content for no reason: the Core is not going to
    change its mind, and the two ``409`` are told apart by ``error.code`` and never by the status.
    """
    given = order(expires_at=SOON, decision=decision())
    node, _ = node_of(world(tmp_path), replies(status(200, given), refused(code, error)))

    await node.turn()

    assert node.held is None


async def test_a_401_on_the_delivery_stops_the_node(tmp_path: Path) -> None:
    given = order(expires_at=SOON, decision=decision())
    node, _ = node_of(world(tmp_path), replies(status(200, given), status(401)))

    with pytest.raises(NodeRevoked):
        await node.turn()


# ----------------------------------------------------------------------------------------
# The time: asked for, never taken
# ----------------------------------------------------------------------------------------


async def test_more_time_is_asked_for_before_the_deadline_and_read_back_from_the_answer(
    tmp_path: Path,
) -> None:
    """M12.2 dec. K. The clock is stopped on the deadline, so the wait is zero and the renewal is
    the only way forward — which is what makes this a test of the asking and not of the waiting."""
    given = order(expires_at=NOW, decision=decision())
    script = replies(
        status(200, given),
        ok({"assignment_id": given["assignment_id"], "expires_at": SOON.isoformat()}),
        ok({"state": "DELIVERED", "step": "COMPLETED"}),
    )
    node, _ = node_of(slowly(world(tmp_path, clock=FakeClock(NOW))), script)

    await node.turn()

    assert ("POST", "/nodes/work/renew") in script.seen
    assert node.held is None


async def test_at_the_cap_the_node_stops_asking_instead_of_taking_the_time(
    tmp_path: Path,
) -> None:
    """``409`` on a renewal is the ceiling (ADR 0038 §13). A node that kept asking would be
    arguing with the one thing that is allowed to decide when its work is over."""
    given = order(expires_at=NOW, decision=decision())
    script = replies(
        status(200, given),
        refused(409, "renewal.capped"),
        ok({"state": "DELIVERED", "step": "COMPLETED"}),
    )
    node, _ = node_of(slowly(world(tmp_path, clock=FakeClock(NOW))), script)

    await node.turn()

    assert [path for _, path in script.seen].count("/nodes/work/renew") == 1


# ----------------------------------------------------------------------------------------
# The three forms of an envelope (ADR 0038 §4)
# ----------------------------------------------------------------------------------------


async def test_a_tool_that_answers_becomes_a_result(tmp_path: Path) -> None:
    built = world(tmp_path)

    envelope = await envelope_of(built, order(expires_at=SOON, decision=decision()))

    assert envelope["form"] == "result"
    assert envelope["output"]["message"] == "ciao"
    assert "ran_at" in envelope["node"]


async def test_a_decision_this_node_will_not_act_on_becomes_a_refusal(tmp_path: Path) -> None:
    """``check_decision`` runs against **this** node's clock, which is why that clock is a declared
    parameter: an expired decision is a refusal and not an exception."""
    stale = allowed(CapabilityId("core.echo"), expires_at=NOW - timedelta(hours=1))
    built = world(tmp_path, clock=FakeClock(NOW))

    envelope = await envelope_of(
        built, order(expires_at=SOON, decision=stale.model_dump(mode="json"))
    )

    assert envelope == {"form": "refused"}


async def test_an_order_for_a_capability_this_node_does_not_have_is_not_executed(
    tmp_path: Path,
) -> None:
    """Criterion 7, and §57 in the same line.

    Only the type's **name** travels, never the message, because a message can carry the user's
    content off the machine. The order here is for ``workspace.write_note`` — one of the four that
    do not travel (M12.1 D15) — and the point is what does *not* happen: the node does not build a
    tool, does not touch a workspace it has none of, and does not stop its cycle. In production the
    hard filter removes this node before the question is asked; this is the tool refusing to trust
    a caller that is now on another machine (§28).
    """
    built = world(tmp_path)

    envelope = await envelope_of(
        built,
        order(
            capability="workspace.write_note",
            expires_at=SOON,
            decision=decision(),
            arguments={"path": "segreto.md", "content": "niente"},
        ),
    )

    assert envelope["form"] == "exception"
    assert envelope["exception"] == "ToolNotFound"
    assert "segreto" not in str(envelope)
    assert not list(tmp_path.rglob("segreto.md"))


# ----------------------------------------------------------------------------------------
# Nobody at the address
# ----------------------------------------------------------------------------------------


async def test_a_dropped_connection_is_waited_out_and_the_count_resets_on_an_answer(
    tmp_path: Path,
) -> None:
    """A Core that is not there yet is not a reason to stop, and not a reason to re-enrol.

    Five drops against a ceiling of three, and the node survives them all — because they never
    come three **in a row**. A node that counted cumulatively instead would give up on a Core that
    is answering, which is the opposite of what the ceiling is for: a node that forgot it was ever
    away is the point.
    """
    script = replies(
        dropped(),
        dropped(),
        ok({}),
        status(204),  # answered: the count goes back to zero
        dropped(),
        dropped(),
        ok({}),
        status(204),  # answered again
        dropped(),
        ok({}),
        status(204),
        ok({}),  # the pass that is cut short: it says "I am here" before it asks
    )
    node, _ = node_of(world(tmp_path), script)

    with pytest.raises(TimeoutError):
        await _turns(node, 3, ceiling=3)

    assert len([one for one in script.seen if one == ("POST", "/nodes/work")]) == 3


async def _turns(node: Any, many: int, *, ceiling: int = 10) -> None:
    """``many`` passes of the loop and then out: ``forever`` has no other way to end."""
    turns = 0
    original = node.turn

    async def counted() -> bool:
        nonlocal turns
        turns += 1
        if turns > many:
            raise TimeoutError
        return await original()

    node.turn = counted
    await forever(node, wait=0, ceiling=ceiling)


async def test_a_ceiling_stops_a_node_whose_core_is_never_coming_back(tmp_path: Path) -> None:
    """A ceiling and not an infinite wait (ADR 0023 §3's argument about TTLs): a process that
    never gives up on a Core that is never coming back is a process nobody notices is useless."""
    node, _ = node_of(world(tmp_path), replies(dropped(), dropped(), dropped()))

    with pytest.raises(CoreUnreachable, match="3 tries"):
        await forever(node, wait=0, ceiling=3)


# ----------------------------------------------------------------------------------------
# What the node says about itself
# ----------------------------------------------------------------------------------------


def test_what_a_node_declares_comes_from_the_objects_it_actually_built(tmp_path: Path) -> None:
    """Dec. F: a declaration written by hand is a promise. And ``capabilities`` is empty on
    purpose — M12.1 D9 keeps ``MISSING_TRAIT`` out of production until some path can produce it."""
    built = world(tmp_path, node_name="il-mac")

    said = declaration(built)

    assert said["name"] == "il-mac"
    assert said["os"] == "MACOS"
    assert said["capabilities"] == []
    assert said["performance"] == "UNKNOWN"
    assert set(said["available_tools"]) == {
        "core-echo",
        "model-complete",
        "voice-speak",
        "voice-speak-online",
    }


async def test_an_envelope_carries_what_a_failure_cost_when_there_was_a_cost(
    tmp_path: Path,
) -> None:
    """``error`` and ``usage`` are in the envelope only when the tool produced them (ADR 0038 §4).

    A provider call that failed after spending tokens produces both, and the Core needs both: it
    has a bill to record for something that did not work, and it never sees the call itself.
    """
    envelope = await envelope_of(
        costly(world(tmp_path)), order(expires_at=SOON, decision=decision())
    )

    assert envelope["form"] == "result"
    assert envelope["error"]["code"] == "provider.overloaded"
    assert envelope["usage"]["input_tokens"] == 11


async def test_a_working_tool_sends_neither_an_error_nor_a_bill(tmp_path: Path) -> None:
    """The other arm, and it is worth a line: an envelope with an empty ``error`` key would make
    the Core record a failure that never happened."""
    envelope = await envelope_of(world(tmp_path), order(expires_at=SOON, decision=decision()))

    assert "error" not in envelope
    assert "usage" not in envelope


async def test_an_answer_without_an_etag_leaves_the_revision_where_it_was(tmp_path: Path) -> None:
    """Neither read nor announcement invents a number when the Core did not send one.

    A node that defaulted to zero here would announce against a revision nobody gave it, which is
    the ``412``-for-ever this whole decision exists to avoid (dec. L).
    """
    node, _ = node_of(world(tmp_path), replies(ok({}), ok({})))

    await node.refresh()
    await node.announce()

    assert node.revision == 0


def test_an_answer_that_is_not_a_refusal_has_no_error_code() -> None:
    """``Reply.code`` is how the node tells the two ``409`` apart, so it has to be silent — and
    not guess — on every answer that carries no error at all."""
    assert Reply(200, {}).code is None
    assert Reply(200, {"error": "una stringa"}).code is None
    assert Reply(409, {"error": {"message": "senza codice"}}).code is None
    assert Reply(409, {"error": {"code": "already_running"}}).code == "already_running"


async def test_the_node_says_it_is_here_on_every_pass_and_not_only_at_start_up(
    tmp_path: Path,
) -> None:
    """Found by hand, with two real processes, on 2026-09-12 — and then written down here.

    A node is available only while the Core has heard from it inside the heartbeat TTL
    (ADR 0016 §3). The first version of this cycle reported once, at start-up, and then asked for
    work for ever: a minute later the registry called it UNAVAILABLE, the orchestrator picked it
    and immediately refused it — ``is no longer eligible: UNAVAILABLE`` — and the step went
    nowhere. The process was up, the connection was fine, and nothing anywhere said so.

    The conformance suite could not catch it: its stories report once and act at once, on a clock
    that does not move by itself. This is the test that would have.
    """
    script = replies(ok({}), status(204), ok({}), status(204), ok({}), status(204), ok({}))
    node, _ = node_of(world(tmp_path), script)

    with pytest.raises(TimeoutError):
        await _turns(node, 3)

    beats = [path for _, path in script.seen].count("/nodes/heartbeat")
    assert beats >= 3, script.seen
