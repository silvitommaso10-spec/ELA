"""Contract of ``AssignmentStore`` (§15; M12.2, ADR 0038): the work handed to a node, and time.

On the fake and on the SQL adapter in memory. What needs two real connections — two claims at
once, two expiries at once — is in ``test_assignment_claim_race.py`` under
``tests/infrastructure/persistence``, because an in-memory database has one connection by
construction.

The store keeps rows **as written**: an offer whose expiry passed is still ``OFFERED`` here, and
what it is *now* is the service's to say. What the store owes is that every move asks "has it
expired?" of the one ``expires_at``, closed, in the statement that moves it.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import Assignment, AssignmentId, AssignmentState, DeviceId, StepId
from ela.ports import (
    AlreadyExistsError,
    AssignmentExpiredError,
    AssignmentHeldElsewhereError,
    AssignmentNodeBusyError,
    AssignmentStateError,
    AssignmentStillLiveError,
    AssignmentStore,
    NotFoundError,
)
from tests.domain.examples import ASSIGNMENT, LATER, NOW

INSTANT = timedelta(microseconds=1)
NODE = ASSIGNMENT.device_id
OTHER_NODE = DeviceId(UUID("00000000-0000-4000-8000-000000000402"))
DIGEST = "ab" * 32
OFFER = ASSIGNMENT.model_copy(
    update={"state": AssignmentState.OFFERED, "claimed_at": None, "expires_at": LATER}
)
"""Offered at ``NOW`` and alive until ``LATER``, which is also when its decision expires."""
TAKEN = NOW + timedelta(minutes=5)
"""When the node takes the work."""
DUE = TAKEN + timedelta(minutes=2)
"""When the work taken at ``TAKEN`` is due: the TTL after the claim."""


def offer_for(number: int, *, device_id: DeviceId = NODE) -> Assignment:
    """An offer like :data:`OFFER`, under its own id, for a step of its own, to ``device_id``."""
    step_id = StepId(UUID(int=0x1000 + number))
    return OFFER.model_copy(
        update={
            "id": AssignmentId(UUID(int=number)),
            "step_id": step_id,
            "device_id": device_id,
            "decision": OFFER.decision.model_copy(update={"step_id": step_id}),
        }
    )


async def claimed(store: AssignmentStore, offer: Assignment = OFFER) -> Assignment:
    """``offer`` kept and taken at :data:`TAKEN`, due at :data:`DUE`."""
    await store.add(offer)
    return await store.claim(offer.id, device_id=offer.device_id, now=TAKEN, expires_at=DUE)


# ----------------------------------------------------------------------------------------
# Kept, and read back as written
# ----------------------------------------------------------------------------------------


async def test_an_offer_is_kept_and_read_back_as_written(assignment_store: AssignmentStore) -> None:
    await assignment_store.add(OFFER)

    assert await assignment_store.get(OFFER.id) == OFFER
    assert await assignment_store.for_step(OFFER.task_id, OFFER.step_id) == (OFFER,)
    assert await assignment_store.offered_to(NODE) == (OFFER,)
    assert await assignment_store.offered_to(OTHER_NODE) == ()


async def test_an_expired_offer_still_reads_offered(assignment_store: AssignmentStore) -> None:
    """The store does not derive the expiry: that is the service's reading (ADR 0016 §3)."""
    await assignment_store.add(OFFER)

    assert (await assignment_store.offered_to(NODE))[0].state is AssignmentState.OFFERED


async def test_an_id_is_kept_once(assignment_store: AssignmentStore) -> None:
    await assignment_store.add(OFFER)
    with pytest.raises(AlreadyExistsError) as caught:
        await assignment_store.add(offer_for(7).model_copy(update={"id": OFFER.id}))
    assert caught.value.kind == "assignment"


async def test_a_step_has_one_assignment_that_is_not_expired(
    assignment_store: AssignmentStore,
) -> None:
    """A second concurrent handing-out of one step is the double execution the protocol exists
    to prevent: refused by a partial unique index on both implementations (ADR 0038)."""
    await assignment_store.add(OFFER)
    with pytest.raises(AlreadyExistsError) as caught:
        await assignment_store.add(OFFER.model_copy(update={"id": AssignmentId(UUID(int=99))}))
    assert caught.value.kind == "open assignment for step"
    assert caught.value.key == OFFER.step_id


async def test_what_is_unknown_is_not_found(assignment_store: AssignmentStore) -> None:
    unknown = AssignmentId(UUID(int=404))
    with pytest.raises(NotFoundError):
        await assignment_store.get(unknown)
    with pytest.raises(NotFoundError):
        await assignment_store.claim(unknown, device_id=NODE, now=TAKEN, expires_at=DUE)
    with pytest.raises(NotFoundError):
        await assignment_store.expire(unknown, now=LATER)


async def test_the_assignments_of_a_step_come_in_insertion_order(
    assignment_store: AssignmentStore,
) -> None:
    """The last is the standing one: what the service reads first on a RUNNING step."""
    await assignment_store.add(OFFER)
    expired = await assignment_store.expire(OFFER.id, now=LATER)
    again = OFFER.model_copy(update={"id": AssignmentId(UUID(int=2)), "created_at": LATER})
    await assignment_store.add(again)

    assert await assignment_store.for_step(OFFER.task_id, OFFER.step_id) == (expired, again)


# ----------------------------------------------------------------------------------------
# The claim: the node's own offer, alive, and nothing else alive in the node's hands
# ----------------------------------------------------------------------------------------


async def test_a_claim_takes_the_offer(assignment_store: AssignmentStore) -> None:
    taken = await claimed(assignment_store)

    assert taken == OFFER.model_copy(
        update={"state": AssignmentState.CLAIMED, "claimed_at": TAKEN, "expires_at": DUE}
    )
    assert await assignment_store.offered_to(NODE) == ()


async def test_nobody_claims_another_nodes_offer(assignment_store: AssignmentStore) -> None:
    """Refused, and nothing written: the offer is still there for its node."""
    await assignment_store.add(OFFER)
    with pytest.raises(AssignmentHeldElsewhereError) as caught:
        await assignment_store.claim(OFFER.id, device_id=OTHER_NODE, now=TAKEN, expires_at=DUE)

    assert caught.value.held_by == NODE
    assert str(NODE) not in str(caught.value)
    assert await assignment_store.get(OFFER.id) == OFFER


async def test_what_was_taken_is_not_taken_again(assignment_store: AssignmentStore) -> None:
    await claimed(assignment_store)
    with pytest.raises(AssignmentStateError) as caught:
        await assignment_store.claim(OFFER.id, device_id=NODE, now=TAKEN, expires_at=DUE)
    assert caught.value.state is AssignmentState.CLAIMED


async def test_expiry_is_closed(assignment_store: AssignmentStore) -> None:
    """Criterion 13, on the store: at ``expires_at`` the offer is expired and the claim refused,
    writing nothing; an instant earlier it is alive and taken (ADR 0005 §2-bis)."""
    await assignment_store.add(OFFER)
    with pytest.raises(AssignmentExpiredError) as caught:
        await assignment_store.claim(OFFER.id, device_id=NODE, now=OFFER.expires_at, expires_at=DUE)
    assert caught.value.expires_at == OFFER.expires_at
    assert (await assignment_store.get(OFFER.id)).state is AssignmentState.OFFERED

    before = OFFER.expires_at - INSTANT
    taken = await assignment_store.claim(OFFER.id, device_id=NODE, now=before, expires_at=LATER)
    assert taken.claimed_at == before


async def test_a_node_holds_one_claim_at_a_time(assignment_store: AssignmentStore) -> None:
    """M12.1, D16: an offer waits while the node's work in hand is alive."""
    await claimed(assignment_store)
    second = offer_for(2)
    await assignment_store.add(second)
    with pytest.raises(AssignmentNodeBusyError) as caught:
        await assignment_store.claim(second.id, device_id=NODE, now=TAKEN, expires_at=DUE)

    assert caught.value.device_id == NODE
    assert await assignment_store.offered_to(NODE) == (second,)


async def test_an_expired_claim_does_not_hold_the_node(assignment_store: AssignmentStore) -> None:
    """Criterion 15, the reason of D16: a ``CLAIMED`` row whose expiry passed and that nobody has
    marked yet does not block the node — which is exactly what an index would get wrong."""
    await claimed(assignment_store)
    second = offer_for(2)
    await assignment_store.add(second)

    taken = await assignment_store.claim(second.id, device_id=NODE, now=DUE, expires_at=LATER)

    assert taken.state is AssignmentState.CLAIMED
    assert (await assignment_store.get(OFFER.id)).state is AssignmentState.CLAIMED


async def test_another_nodes_claim_does_not_hold_this_node(
    assignment_store: AssignmentStore,
) -> None:
    await claimed(assignment_store)
    theirs = offer_for(3, device_id=OTHER_NODE)
    await assignment_store.add(theirs)

    taken = await assignment_store.claim(theirs.id, device_id=OTHER_NODE, now=TAKEN, expires_at=DUE)

    assert taken.device_id == OTHER_NODE


# ----------------------------------------------------------------------------------------
# The delivery and the renewal: work in hand, the node's, alive
# ----------------------------------------------------------------------------------------


async def test_a_delivery_closes_the_work_with_its_digest(
    assignment_store: AssignmentStore,
) -> None:
    await claimed(assignment_store)
    delivered = await assignment_store.deliver(
        OFFER.id, device_id=NODE, now=TAKEN + INSTANT, digest=DIGEST
    )

    assert delivered.state is AssignmentState.DELIVERED
    assert (delivered.delivered_at, delivered.delivery_digest) == (TAKEN + INSTANT, DIGEST)


async def test_a_delivery_needs_work_in_hand(assignment_store: AssignmentStore) -> None:
    await assignment_store.add(OFFER)
    with pytest.raises(AssignmentStateError) as caught:
        await assignment_store.deliver(OFFER.id, device_id=NODE, now=TAKEN, digest=DIGEST)
    assert caught.value.state is AssignmentState.OFFERED


async def test_a_delivery_is_the_assignees(assignment_store: AssignmentStore) -> None:
    await claimed(assignment_store)
    with pytest.raises(AssignmentHeldElsewhereError):
        await assignment_store.deliver(OFFER.id, device_id=OTHER_NODE, now=TAKEN, digest=DIGEST)


async def test_a_late_delivery_is_refused_at_the_instant_of_the_expiry(
    assignment_store: AssignmentStore,
) -> None:
    await claimed(assignment_store)
    with pytest.raises(AssignmentExpiredError):
        await assignment_store.deliver(OFFER.id, device_id=NODE, now=DUE, digest=DIGEST)
    assert (await assignment_store.get(OFFER.id)).state is AssignmentState.CLAIMED


async def test_a_delivery_is_accepted_once(assignment_store: AssignmentStore) -> None:
    """The store refuses the second; telling a replay from a conflict is the service's, by the
    digest the first one left."""
    await claimed(assignment_store)
    await assignment_store.deliver(OFFER.id, device_id=NODE, now=TAKEN, digest=DIGEST)
    with pytest.raises(AssignmentStateError) as caught:
        await assignment_store.deliver(OFFER.id, device_id=NODE, now=TAKEN, digest=DIGEST)
    assert caught.value.state is AssignmentState.DELIVERED


async def test_a_renewal_moves_the_expiry_of_work_in_hand(
    assignment_store: AssignmentStore,
) -> None:
    await claimed(assignment_store)
    later = DUE + timedelta(minutes=2)
    renewed = await assignment_store.renew(OFFER.id, device_id=NODE, now=TAKEN, expires_at=later)

    assert renewed.expires_at == later
    assert renewed.claimed_at == TAKEN


async def test_a_renewal_needs_work_in_hand_that_is_alive(
    assignment_store: AssignmentStore,
) -> None:
    await assignment_store.add(OFFER)
    with pytest.raises(AssignmentStateError):
        await assignment_store.renew(OFFER.id, device_id=NODE, now=TAKEN, expires_at=DUE)
    await assignment_store.claim(OFFER.id, device_id=NODE, now=TAKEN, expires_at=DUE)
    with pytest.raises(AssignmentExpiredError):
        await assignment_store.renew(OFFER.id, device_id=NODE, now=DUE, expires_at=LATER)


# ----------------------------------------------------------------------------------------
# The expiry, written by whoever acts on it; and the revocation, which makes one
# ----------------------------------------------------------------------------------------


async def test_an_offer_expires_only_once_its_time_has_come(
    assignment_store: AssignmentStore,
) -> None:
    await assignment_store.add(OFFER)
    with pytest.raises(AssignmentStillLiveError) as caught:
        await assignment_store.expire(OFFER.id, now=OFFER.expires_at - INSTANT)
    assert caught.value.expires_at == OFFER.expires_at

    expired = await assignment_store.expire(OFFER.id, now=OFFER.expires_at)
    assert expired.state is AssignmentState.EXPIRED


async def test_an_expiry_written_twice_is_one(assignment_store: AssignmentStore) -> None:
    """Two callers acting on one expiry agree, and the second writes nothing."""
    await assignment_store.add(OFFER)
    first = await assignment_store.expire(OFFER.id, now=LATER)

    assert await assignment_store.expire(OFFER.id, now=LATER + INSTANT) == first


async def test_a_claimed_assignment_expires_too(assignment_store: AssignmentStore) -> None:
    """Criterion 14: work taken and never returned expires, and the step can be handed out again.
    With an ``expire`` that wrote only from ``OFFERED`` the new assignment would meet the index."""
    await claimed(assignment_store)
    expired = await assignment_store.expire(OFFER.id, now=DUE)
    again = OFFER.model_copy(update={"id": AssignmentId(UUID(int=2)), "created_at": DUE})

    await assignment_store.add(again)

    assert expired.state is AssignmentState.EXPIRED
    assert await assignment_store.get(again.id) == again


async def test_a_delivered_assignment_does_not_expire(assignment_store: AssignmentStore) -> None:
    await claimed(assignment_store)
    await assignment_store.deliver(OFFER.id, device_id=NODE, now=TAKEN, digest=DIGEST)
    with pytest.raises(AssignmentStateError) as caught:
        await assignment_store.expire(OFFER.id, now=LATER)
    assert caught.value.state is AssignmentState.DELIVERED


async def test_a_revocation_cuts_every_live_assignment_of_the_node(
    assignment_store: AssignmentStore,
) -> None:
    """M12.1, D17: what a revoked node holds expires at the instant of the revocation — the offer
    it can no longer take as well as the work it took. Another node's is untouched, and what had
    expired already is not cut again."""
    taken = await claimed(assignment_store)
    offered = offer_for(2)
    theirs = offer_for(3, device_id=OTHER_NODE)
    await assignment_store.add(offered)
    await assignment_store.add(theirs)
    cut = TAKEN + INSTANT

    assert await assignment_store.cut_short(NODE, now=cut) == 2
    assert (await assignment_store.get(taken.id)).expires_at == cut
    assert (await assignment_store.get(offered.id)).expires_at == cut
    assert await assignment_store.get(theirs.id) == theirs
    assert await assignment_store.cut_short(NODE, now=cut) == 0
