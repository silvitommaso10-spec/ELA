"""Answering a request for consent (spec §30, §62; ADR 0015 §9, ADR 0023 §8).

The API is the **only** module of ELA that answers an approval (architecture rule 19), and the
order it does it in is the decision: ``respond`` first, the engine after. What is tested here is
that order, the crash window it leaves open (5c), and the two refusals — a second, different
answer, and an answer that comes too late.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela
from ela.domain import ApprovalId, ApprovalStatus, TaskId, TaskState
from ela.testing.fakes import FakeClock
from tests.api.support import AUTHORIZED, BASE, note_plan, queued


async def waiting(client: AsyncClient) -> tuple[str, str]:
    """A task stopped on a request for consent, and the id of the request."""
    task_id = await queued(client, note_plan())
    await client.post(f"/tasks/{task_id}/run")
    pending = (await client.get("/approvals")).json()
    assert len(pending) == 1
    return task_id, pending[0]["id"]


# ----------------------------------------------------------------------------------------
# The inbox
# ----------------------------------------------------------------------------------------


async def test_a_request_waiting_for_an_answer_is_listed(client: AsyncClient) -> None:
    task_id, _ = await waiting(client)

    request = (await client.get("/approvals")).json()[0]

    assert request["task_id"] == task_id
    assert request["status"] == ApprovalStatus.PENDING.value
    assert request["capability_id"] == "workspace.write_note"
    assert request["targets"] == ["workspace/notes/briefing.md"]
    assert request["prompt"]  # what the user is being asked


async def test_the_inbox_is_empty_when_nothing_is_waiting(client: AsyncClient) -> None:
    assert (await client.get("/approvals")).json() == []


async def test_the_inbox_can_be_limited(client: AsyncClient) -> None:
    await waiting(client)

    assert len((await client.get("/approvals", params={"limit": 1})).json()) == 1
    assert (await client.get("/approvals", params={"limit": 0})).status_code == 422


async def test_the_life_of_a_request_is_the_configured_one(client: AsyncClient, ela: Ela) -> None:
    """``ELA_APPROVAL_TTL_SECONDS`` reaches the executor that creates the request (ADR 0013)."""
    await waiting(client)

    request = (await client.get("/approvals")).json()[0]

    born = datetime.fromisoformat(request["created_at"])
    expires = datetime.fromisoformat(request["expires_at"])
    assert expires - born == ela.settings.core.approval_ttl


async def test_an_expired_request_is_not_shown_and_cannot_be_answered(ela: Ela) -> None:
    """ADR 0015 §1: ``respond`` would refuse it, and asking the user for something they can no
    longer give is asking the impossible (§33). The API is what has a clock and passes it."""
    app = create_app(ela)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
    ) as client:
        task_id, approval_id = await waiting(client)

    later = FakeClock(datetime.now(UTC) + timedelta(days=8))
    tomorrow = create_app(dataclasses.replace(ela, clock=later))
    async with AsyncClient(
        transport=ASGITransport(app=tomorrow), base_url=BASE, headers=AUTHORIZED
    ) as client:
        assert (await client.get("/approvals")).json() == []
        late = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert late.status_code == 409
    assert late.json()["error"]["code"] == "not_answerable"


# ----------------------------------------------------------------------------------------
# Yes and no
# ----------------------------------------------------------------------------------------


async def test_a_yes_queues_the_task_again(client: AsyncClient) -> None:
    task_id, approval_id = await waiting(client)

    answered = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert answered.status_code == 200
    assert answered.json()["state"] == TaskState.QUEUED.value
    assert (await client.post(f"/tasks/{task_id}/run")).json()["outcome"] == "completed"


async def test_a_no_denies_the_task(client: AsyncClient) -> None:
    task_id, approval_id = await waiting(client)

    answered = await client.post(f"/tasks/{task_id}/deny", json={"approval_id": approval_id})

    assert answered.status_code == 200
    assert answered.json()["state"] == TaskState.DENIED.value


async def test_the_answer_is_signed_by_the_user_of_the_settings(
    client: AsyncClient, ela: Ela
) -> None:
    """ADR 0023 §8: not by the caller. A caller that named itself would write that name into the
    audit trail, which is what "who said yes" is read from later (§32)."""
    task_id, approval_id = await waiting(client)

    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    stored = await ela.approvals.get(ApprovalId(uuid.UUID(approval_id)))
    assert stored.responded_by == ela.settings.core.user_name
    events = await ela.audit.read(task_id=TaskId(uuid.UUID(task_id)))
    assert any(event.actor.id == ela.settings.core.user_name for event in events)


async def test_an_unknown_request_is_not_found(client: AsyncClient) -> None:
    task_id, _ = await waiting(client)

    response = await client.post(
        f"/tasks/{task_id}/approve", json={"approval_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404


async def test_a_request_of_another_task_is_not_found(client: AsyncClient) -> None:
    """A "yes" is bound to a task, a step and a capability (§30): it cannot be spent elsewhere."""
    _, approval_id = await waiting(client)
    other = await queued(client, note_plan(path="workspace/notes/other.md"))

    response = await client.post(f"/tasks/{other}/approve", json={"approval_id": approval_id})

    assert response.status_code == 404


# ----------------------------------------------------------------------------------------
# Crash window 5c (ADR 0015 §8), repaired where it opens
# ----------------------------------------------------------------------------------------


async def test_an_answer_written_but_never_applied_is_completed_by_the_next_call(
    client: AsyncClient, ela: Ela
) -> None:
    """The store has the answer and the engine was never told — the process died between the
    two writes. Whoever answers finds a WAITING_APPROVAL task with a resolved request."""
    task_id, approval_id = await waiting(client)
    await ela.approvals.respond(
        ApprovalId(uuid.UUID(approval_id)),
        status=ApprovalStatus.GRANTED,
        responded_by=ela.settings.core.user_name,
        now=ela.clock.now(),
    )
    assert (await ela.repository.get(TaskId(uuid.UUID(task_id)))).state is (
        TaskState.WAITING_APPROVAL
    )

    repaired = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert repaired.status_code == 200
    assert repaired.json()["state"] == TaskState.QUEUED.value


async def test_the_opposite_answer_does_not_overwrite_one_the_crash_left_unapplied(
    client: AsyncClient, ela: Ela
) -> None:
    """Window 5c with a change of mind: the "yes" is in the store and the engine was never told,
    and now a "no" arrives. The first answer stands — one answer, ever (§30) — and the task is
    left exactly where it was, for the next call to complete."""
    task_id, approval_id = await waiting(client)
    await ela.approvals.respond(
        ApprovalId(uuid.UUID(approval_id)),
        status=ApprovalStatus.GRANTED,
        responded_by=ela.settings.core.user_name,
        now=ela.clock.now(),
    )

    changed = await client.post(f"/tasks/{task_id}/deny", json={"approval_id": approval_id})

    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "not_answerable"
    assert (await ela.repository.get(TaskId(uuid.UUID(task_id)))).state is (
        TaskState.WAITING_APPROVAL
    )


async def test_repeating_an_answer_that_was_already_applied_says_the_same_thing(
    client: AsyncClient,
) -> None:
    task_id, approval_id = await waiting(client)
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    again = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert again.status_code == 200
    assert again.json()["state"] == TaskState.QUEUED.value


async def test_the_opposite_answer_is_refused(client: AsyncClient) -> None:
    """One answer, ever (§30). A second one does not overwrite the first."""
    task_id, approval_id = await waiting(client)
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    changed = await client.post(f"/tasks/{task_id}/deny", json={"approval_id": approval_id})

    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "not_answerable"


async def test_the_store_is_written_before_the_engine_moves(client: AsyncClient, ela: Ela) -> None:
    """ADR 0015 §9. If the engine moved first and ``respond`` fell over, the task would be
    QUEUED with a request still PENDING and the executor's retry would ask for it again."""
    task_id, approval_id = await waiting(client)
    order: list[str] = []
    store, engine = ela.approvals, ela.engine

    class Watched:
        def __getattr__(self, name: str) -> object:
            return getattr(store, name)

        async def get(self, approval_id: ApprovalId) -> object:
            return await store.get(approval_id)

        async def respond(self, *args: object, **kwargs: object) -> object:
            order.append("respond")
            return await store.respond(*args, **kwargs)  # type: ignore[arg-type]

    class WatchedEngine:
        def __getattr__(self, name: str) -> object:
            return getattr(engine, name)

        async def approve(self, *args: object, **kwargs: object) -> object:
            order.append("approve")
            return await engine.approve(*args, **kwargs)  # type: ignore[arg-type]

    watched = dataclasses.replace(ela, approvals=Watched(), engine=WatchedEngine())  # type: ignore[arg-type]
    app = create_app(watched)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
    ) as client:
        await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert order == ["respond", "approve"]


async def test_declaring_a_different_user_changes_who_signs(ela: Ela) -> None:
    """``ELA_USER_NAME`` is the identity of a single-user ELA on loopback (ADR 0023 §4)."""
    named = dataclasses.replace(
        ela,
        settings=ela.settings.model_copy(
            update={"core": ela.settings.core.model_copy(update={"user_name": "tommaso"})}
        ),
    )
    app = create_app(named)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
    ) as client:
        task_id, approval_id = await waiting(client)
        await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    stored = await ela.approvals.get(ApprovalId(uuid.UUID(approval_id)))
    assert stored.responded_by == "tommaso"


# ----------------------------------------------------------------------------------------
# A question that can no longer do anything (review of M8.1)
# ----------------------------------------------------------------------------------------


async def test_a_request_of_a_task_that_was_stopped_is_not_in_the_inbox(
    client: AsyncClient,
) -> None:
    """§65 and §33 together: the user stopped the task, so the question ELA had asked cannot do
    anything any more. Leaving it in the inbox asks for something that no longer matters — the
    same reason an expired request is not shown (ADR 0015 §1)."""
    task_id, _ = await waiting(client)
    await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ci ho ripensato"})

    assert (await client.get("/approvals")).json() == []


async def test_answering_a_request_whose_task_cannot_move_writes_nothing(
    client: AsyncClient, ela: Ela
) -> None:
    """The refusal came anyway — the engine cannot take a CANCELLED task to QUEUED — but the
    answer had already been written to the store, and nothing would ever act on it."""
    task_id, approval_id = await waiting(client)
    await client.post(f"/tasks/{task_id}/cancel", json={})

    refused = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval_id})

    assert refused.status_code == 409
    stored = await ela.approvals.get(ApprovalId(uuid.UUID(approval_id)))
    assert stored.status is ApprovalStatus.PENDING
    assert stored.responded_by is None and stored.responded_at is None
