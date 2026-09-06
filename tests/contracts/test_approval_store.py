"""Contract of ``ApprovalStore`` (spec §30, §62; ADR 0015): a request is added PENDING, read
back as stored, and answered once — GRANTED or REJECTED — only while it can still be answered."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import ApprovalId, ApprovalStatus, TaskId
from ela.ports import (
    ANSWERS,
    ApprovalAlreadyAnsweredError,
    ApprovalExpiredError,
    ApprovalNotAnswerableError,
    ApprovalStore,
    NotFoundError,
    PortError,
)
from tests.domain.examples import APPROVAL, LATER, MUCH_LATER, NOW

PENDING = APPROVAL.model_copy(
    update={"status": ApprovalStatus.PENDING, "responded_at": None, "responded_by": None}
)
OTHER = PENDING.model_copy(update={"id": ApprovalId(UUID("00000000-0000-4000-8000-000000000501"))})
OTHER_TASK = PENDING.model_copy(
    update={
        "id": ApprovalId(UUID("00000000-0000-4000-8000-000000000502")),
        "task_id": TaskId(UUID("00000000-0000-4000-8000-000000000503")),
    }
)
OPEN_ENDED = PENDING.model_copy(
    update={"id": ApprovalId(UUID("00000000-0000-4000-8000-000000000504")), "expires_at": None}
)


async def test_add_then_get(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    assert await approval_store.get(PENDING.id) == PENDING


async def test_add_twice_is_rejected_and_the_first_stays(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    with pytest.raises(PortError):
        await approval_store.add(PENDING.model_copy(update={"prompt": "other"}))
    assert await approval_store.get(PENDING.id) == PENDING


@pytest.mark.parametrize(
    "status", [ApprovalStatus.GRANTED, ApprovalStatus.REJECTED, ApprovalStatus.EXPIRED]
)
async def test_only_a_pending_request_can_be_added(
    approval_store: ApprovalStore, status: ApprovalStatus
) -> None:
    """A "yes" enters the store only through ``respond`` (ADR 0015 §1)."""
    with pytest.raises(ValueError, match="PENDING"):
        await approval_store.add(PENDING.model_copy(update={"status": status}))
    with pytest.raises(NotFoundError):
        await approval_store.get(PENDING.id)


async def test_get_unknown_is_not_found(approval_store: ApprovalStore) -> None:
    with pytest.raises(NotFoundError):
        await approval_store.get(PENDING.id)


async def test_for_task_filters_by_task_in_insertion_order(approval_store: ApprovalStore) -> None:
    await approval_store.add(OTHER)
    await approval_store.add(OTHER_TASK)
    await approval_store.add(PENDING)
    assert await approval_store.for_task(PENDING.task_id) == (OTHER, PENDING)
    assert await approval_store.for_task(OTHER_TASK.task_id) == (OTHER_TASK,)
    assert await approval_store.for_task(TaskId(UUID(int=99))) == ()


async def test_for_task_keeps_every_status(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    await approval_store.add(OTHER)
    granted = await approval_store.respond(
        PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=LATER
    )
    assert await approval_store.for_task(PENDING.task_id) == (granted, OTHER)


async def test_pending_lists_what_waits_across_tasks_in_insertion_order(
    approval_store: ApprovalStore,
) -> None:
    await approval_store.add(OTHER_TASK)
    await approval_store.add(PENDING)
    await approval_store.add(OTHER)
    await approval_store.respond(
        PENDING.id, status=ApprovalStatus.REJECTED, responded_by="tommaso", now=LATER
    )
    assert await approval_store.pending() == (OTHER_TASK, OTHER)
    assert await approval_store.pending(limit=1) == (OTHER_TASK,)
    assert await approval_store.pending(limit=5) == (OTHER_TASK, OTHER)
    assert await approval_store.pending(now=NOW) == (OTHER_TASK, OTHER)


async def test_pending_without_an_instant_includes_an_expired_request(
    approval_store: ApprovalStore,
) -> None:
    """The store keeps no clock of its own: without ``now`` nothing is filtered by time."""
    await approval_store.add(PENDING)
    assert await approval_store.pending() == (PENDING,)


async def test_pending_with_an_instant_leaves_out_what_can_no_longer_be_answered(
    approval_store: ApprovalStore,
) -> None:
    """A request ``respond`` would refuse is not something that waits for an answer (§33)."""
    await approval_store.add(PENDING)
    await approval_store.add(OPEN_ENDED)
    assert await approval_store.pending(now=NOW) == (PENDING, OPEN_ENDED)
    assert await approval_store.pending(now=MUCH_LATER + timedelta(days=1)) == (OPEN_ENDED,)


async def test_pending_applies_the_same_closed_bound_as_respond(
    approval_store: ApprovalStore,
) -> None:
    """At the exact instant the request has expired, here as in ``respond`` (ADR 0005)."""
    await approval_store.add(PENDING)
    assert PENDING.expires_at == MUCH_LATER
    assert await approval_store.pending(now=MUCH_LATER - timedelta(seconds=1)) == (PENDING,)
    assert await approval_store.pending(now=MUCH_LATER) == ()
    with pytest.raises(ApprovalExpiredError):
        await approval_store.respond(
            PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=MUCH_LATER
        )


async def test_pending_filters_by_time_before_it_limits(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)  # expires at MUCH_LATER
    await approval_store.add(OTHER)  # expires at MUCH_LATER
    await approval_store.add(OPEN_ENDED)  # never expires
    late = MUCH_LATER + timedelta(seconds=1)
    assert await approval_store.pending(limit=2) == (PENDING, OTHER)
    assert await approval_store.pending(now=late, limit=2) == (OPEN_ENDED,)


@pytest.mark.parametrize("limit", [0, -1])
async def test_pending_refuses_a_non_positive_limit_with_an_instant_too(
    approval_store: ApprovalStore, limit: int
) -> None:
    with pytest.raises(ValueError, match="limit"):
        await approval_store.pending(now=NOW, limit=limit)


@pytest.mark.parametrize("limit", [0, -1])
async def test_pending_refuses_a_non_positive_limit(
    approval_store: ApprovalStore, limit: int
) -> None:
    with pytest.raises(ValueError, match="limit"):
        await approval_store.pending(limit=limit)


@pytest.mark.parametrize("status", sorted(ANSWERS))
async def test_respond_answers_once_and_returns_what_is_stored(
    approval_store: ApprovalStore, status: ApprovalStatus
) -> None:
    await approval_store.add(PENDING)
    answered = await approval_store.respond(
        PENDING.id, status=status, responded_by="tommaso", now=LATER
    )
    assert answered == PENDING.model_copy(
        update={"status": status, "responded_by": "tommaso", "responded_at": LATER}
    )
    assert await approval_store.get(PENDING.id) == answered


@pytest.mark.parametrize("status", [ApprovalStatus.PENDING, ApprovalStatus.EXPIRED])
async def test_respond_refuses_what_is_not_an_answer(
    approval_store: ApprovalStore, status: ApprovalStatus
) -> None:
    await approval_store.add(PENDING)
    with pytest.raises(ValueError, match="GRANTED or REJECTED"):
        await approval_store.respond(PENDING.id, status=status, responded_by="tommaso", now=LATER)
    assert await approval_store.get(PENDING.id) == PENDING


async def test_respond_to_an_unknown_request_is_not_found(approval_store: ApprovalStore) -> None:
    with pytest.raises(NotFoundError):
        await approval_store.respond(
            PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=LATER
        )


async def test_a_second_answer_is_refused_even_if_equal(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    first = await approval_store.respond(
        PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=LATER
    )
    for status in (ApprovalStatus.GRANTED, ApprovalStatus.REJECTED):
        with pytest.raises(ApprovalAlreadyAnsweredError) as excinfo:
            await approval_store.respond(
                PENDING.id, status=status, responded_by="someone", now=LATER + timedelta(hours=1)
            )
        assert excinfo.value.approval_id == PENDING.id
        assert excinfo.value.status is ApprovalStatus.GRANTED
    assert await approval_store.get(PENDING.id) == first


async def test_an_expired_request_cannot_be_answered(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    with pytest.raises(ApprovalExpiredError) as excinfo:
        await approval_store.respond(
            PENDING.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=MUCH_LATER + timedelta(seconds=1),
        )
    assert excinfo.value.approval_id == PENDING.id
    assert excinfo.value.expires_at == MUCH_LATER
    assert await approval_store.get(PENDING.id) == PENDING


async def test_expiry_is_closed_at_the_exact_instant(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    with pytest.raises(ApprovalExpiredError):
        await approval_store.respond(
            PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=MUCH_LATER
        )
    answered = await approval_store.respond(
        PENDING.id,
        status=ApprovalStatus.GRANTED,
        responded_by="tommaso",
        now=MUCH_LATER - timedelta(seconds=1),
    )
    assert answered.status is ApprovalStatus.GRANTED


async def test_a_request_without_expiry_can_always_be_answered(
    approval_store: ApprovalStore,
) -> None:
    await approval_store.add(OPEN_ENDED)
    answered = await approval_store.respond(
        OPEN_ENDED.id,
        status=ApprovalStatus.REJECTED,
        responded_by="tommaso",
        now=MUCH_LATER + timedelta(days=365),
    )
    assert answered.status is ApprovalStatus.REJECTED


async def test_already_answered_is_reported_before_expired(approval_store: ApprovalStore) -> None:
    """Answered in time and then expired is answered: the order of the errors."""
    await approval_store.add(PENDING)
    await approval_store.respond(
        PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=NOW
    )
    with pytest.raises(ApprovalAlreadyAnsweredError):
        await approval_store.respond(
            PENDING.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=MUCH_LATER + timedelta(days=1),
        )


async def test_a_refused_answer_is_a_named_port_error(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    with pytest.raises(ApprovalNotAnswerableError) as expired:
        await approval_store.respond(
            PENDING.id,
            status=ApprovalStatus.GRANTED,
            responded_by="tommaso",
            now=MUCH_LATER,
        )
    assert isinstance(expired.value, PortError)
    assert str(PENDING.id) in str(expired.value) and "expired" in str(expired.value)
    await approval_store.respond(
        PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=NOW
    )
    with pytest.raises(ApprovalNotAnswerableError) as answered:
        await approval_store.respond(
            PENDING.id, status=ApprovalStatus.REJECTED, responded_by="tommaso", now=NOW
        )
    assert isinstance(answered.value, PortError)
    assert "already GRANTED" in str(answered.value)


async def test_respond_changes_nothing_but_the_answer(approval_store: ApprovalStore) -> None:
    await approval_store.add(PENDING)
    answered = await approval_store.respond(
        PENDING.id, status=ApprovalStatus.GRANTED, responded_by="tommaso", now=LATER
    )
    untouched = {"status", "responded_by", "responded_at"}
    for name in type(PENDING).model_fields:
        if name not in untouched:
            assert getattr(answered, name) == getattr(PENDING, name), name
