"""The fifteen crash windows of the work protocol (M12.2, criterion 28; ADR 0038 §19).

A window is an **order of writes**, so each test builds the state a death would leave between two of
them and asserts what the *next* call does with it. Nothing is simulated by patching the code under
test: the state is built through ELA's own ports — the precedent is ``tamper_with_the_trail`` — and
a window is a row that exists beside a row that does not. The one exception is ``A12``, where the
thing that dies is a write of the audit log, and what dies is wrapped rather than patched
(:class:`~tests.executive.support.Crashing`).

Nine rows are **repaired**: the next call reaches the same end by a different road, and the test
says which road. Six are **declared**: nobody repairs them, and the test fixes the behaviour anyway
— because what a retry does in a window nobody repairs is a fact, not a guess, and a fact that is
only written in prose is one the code can stop honouring in silence.

:data:`REPAIRED` and :data:`DECLARED` are read back by ``tests/docs/test_adr_work.py``, which holds
ADR 0038 §19 to this file: a row promoted to "repaired" without a test, or a test deleted, fails
there — the discipline ``tests/docs/test_adr_recovery.py`` keeps for ADR 0015 §8.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import uuid5

import pytest

from ela.domain import (
    AssignmentState,
    AuditEventType,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PrivacyLevel,
    StepState,
    TaskEventType,
    TaskState,
)
from ela.executive import (
    DELIVERY_NAMESPACE,
    RECOVERED,
    TOOL_REFUSED,
    VERIFICATION_FAILED,
    AssignmentVoidError,
    RunOutcome,
    Standing,
)
from ela.testing.fakes import FakeAssignmentStore
from tests.domain.examples import ELA_ACTOR
from tests.executive.support import BAD, OK, SimulatedCrash, World, crashing_world, world
from tests.permissions.support import ECHO

E = AuditEventType
T = TaskEventType
PAST_THE_TTL = timedelta(seconds=121)
"""One second past the default TTL of an assignment (two minutes): the work is over."""

REPAIRED = {"A2", "A3", "A4", "A7", "A8", "A9", "A11", "A13", "A14"}
"""The windows ADR 0038 §19 calls **Riparato.**: the next call gets there another way."""
DECLARED = {"A1", "A5", "A6", "A10", "A12", "A15"}
"""The windows nobody repairs. Each still has a test: the behaviour in a window is a fact."""


async def offered(
    w: World, *, repeatable: bool = True, conditions: tuple[str, ...] = (OK,)
) -> tuple[Any, Any, Any, Any]:
    """A step handed to a node that is not this machine: the state after ``store.add``.

    ``repeatable`` is the tool's own answer to "is twice once": it decides whether the claim writes
    a STARTED record, which is what several of these windows turn on (D14).
    """
    w.tool(ECHO.id).idempotent = repeatable
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, conditions=conditions, max_privacy=PrivacyLevel.TRUSTED)
    run = await w.runner.run(task.id)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    return task, step, stand.assignment, remote


async def trail(w: World, task_id: Any, kind: TaskEventType) -> list[Any]:
    return [one for one in await w.repository.events(task_id) if one.event_type is kind]


async def audited(w: World, task_id: Any, kind: AuditEventType) -> list[Any]:
    return [one for one in await w.events(task_id) if one.event_type is kind]


def envelope_of(w: World, assignment: Any, tool_name: str) -> ExecutionResult:
    """The outcome a delivery would store, with the deterministic id of its assignment."""
    return ExecutionResult(
        id=ExecutionId(uuid5(DELIVERY_NAMESPACE, str(assignment.id))),
        created_at=w.now,
        capability_id=assignment.decision.capability_id,
        status=ExecutionStatus.SUCCEEDED,
        task_id=assignment.task_id,
        step_id=assignment.step_id,
        tool_name=tool_name,
        device_id=assignment.device_id,
        decision_id=assignment.decision.id,
        output={"ok": True},
    )


# ----------------------------------------------------------------------------------------
# A1 — declared: a heartbeat with no assignment behind it
# ----------------------------------------------------------------------------------------


async def test_window_a1_a_heartbeat_without_an_assignment_claims_nothing() -> None:
    """Died inside ``assign``, after the heartbeat and before ``store.add``.

    Nobody repairs it because there is nothing to repair: the next ``run`` finds no assignment,
    confirms the node and redoes the first half. What the window leaves behind is **one extra sign
    of life**, and a sign of life asserts nothing about work — which is exactly why the order is
    heartbeat-then-row and not the reverse (ADR 0038 §9).
    """
    w = world()
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, max_privacy=PrivacyLevel.TRUSTED)
    await w.engine.start(task.id, device_id=remote.id)
    await w.engine.start_step(task.id, step.id, device_id=remote.id)
    await w.engine.heartbeat(task.id)  # the write that landed
    assert await w.assignments.standing(task.id, step.id) == (Standing.NONE, None)
    beats = len(await trail(w, task.id, T.HEARTBEAT))

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.ASSIGNED  # the first half, done again
    assert len(await trail(w, task.id, T.HEARTBEAT)) == beats + 1  # the one `assign` writes
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None and stand.standing is Standing.LIVE


# ----------------------------------------------------------------------------------------
# A2 — repaired: a live offer nobody answered for
# ----------------------------------------------------------------------------------------


async def test_window_a2_a_live_offer_is_found_by_the_next_run() -> None:
    """``store.add`` landed and ``run`` never returned: the offer is out, and nobody knows.

    The next call reads it — it does not place the step again, and it does not confirm the node —
    and says ``ASSIGNED`` without writing anything. A run that re-placed it here would hand the same
    step to a second node while the first still holds the offer.
    """
    w = world()
    task, step, assignment, _ = await offered(w)
    before = (len(await w.repository.events(task.id)), len(await w.events()))

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.ASSIGNED
    assert again.reason == await w.assignments.describe(assignment)
    assert (len(await w.repository.events(task.id)), len(await w.events())) == before


# ----------------------------------------------------------------------------------------
# A3 — repaired: a heartbeat, and the offer intact
# ----------------------------------------------------------------------------------------


async def test_window_a3_an_offer_survives_the_heartbeat_of_a_claim_that_died() -> None:
    """Died inside the claim, after the heartbeat and before ``store.claim``: the offer is intact.

    So the node asks again and the claim succeeds — the heartbeat in front of the row costs one
    extra sign of life and buys the property of ADR 0038 §9.
    """
    w = world()
    task, step, assignment, remote = await offered(w)
    await w.engine.heartbeat(task.id)  # the write that landed
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.LIVE

    claimed = await w.executor.begin(assignment.id, remote.id)

    assert claimed.assignment.state is AssignmentState.CLAIMED
    assert claimed.assignment.id == assignment.id


# ----------------------------------------------------------------------------------------
# A4 — repaired: a claim with no STARTED is an order that never went out
# ----------------------------------------------------------------------------------------


async def test_window_a4_a_claim_without_a_started_record_is_released() -> None:
    """``store.claim`` landed and the STARTED record did not: **the order never went out**.

    So at the expiry the step is released — *even for a tool that cannot be repeated*, which is the
    whole reason the claim is written before the record and not after. The other order would leave a
    STARTED record with no claim, and the next claim would write the step's second one against the
    index of migration ``0007``.
    """
    w = world()
    task, step, assignment, remote = await offered(w, repeatable=False)
    await w.assignments.claim(assignment.id, remote.id)  # claimed, and nothing else
    assert await w.results.for_step(task.id, step.id) == ()
    w.clock.advance(PAST_THE_TTL)
    await w.alive()

    await w.runner.run(task.id)

    released = await trail(w, task.id, T.STEP_RELEASED)
    assert [one.metadata["assignment_id"] for one in released] == [str(assignment.id)]
    assert "execution.interrupted" not in str(await w.events(task.id))


# ----------------------------------------------------------------------------------------
# A5 — declared: a claim with a STARTED record, and an order that may not have gone out
# ----------------------------------------------------------------------------------------


async def test_window_a5_a_started_record_with_no_order_out_still_closes_interrupted() -> None:
    """The STARTED record landed and the answer to the node did not.

    Declared, and this is the direction it declares: at the expiry the step is closed
    ``interrupted``. The Core **cannot tell this row from** ``A6`` — a claim with a record either
    way — so it does not invent an outcome for either: nothing says the tool ran, and nothing says
    it did not.
    """
    w = world()
    task, step, assignment, remote = await offered(w, repeatable=False)
    await w.executor.begin(assignment.id, remote.id)  # the record landed
    (record,) = await w.results.for_step(task.id, step.id)
    w.clock.advance(PAST_THE_TTL)
    await w.alive()

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    failed = (await audited(w, task.id, E.STEP_FAILED))[-1]
    assert failed.error is not None and failed.error.code == "execution.interrupted"
    assert failed.error.retryable is True
    assert [one.status for one in await w.results.for_step(task.id, step.id)] == [
        ExecutionStatus.STARTED
    ]
    assert record.device_id == assignment.device_id  # the node of the record, not of the retry


# ----------------------------------------------------------------------------------------
# A6 — declared, not repairable: whether the order arrived is unknowable
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("repeatable", [True, False], ids=["core-echo", "a-tool-that-cannot-be"])
async def test_window_a6_the_answer_does_not_depend_on_whether_the_order_arrived(
    repeatable: bool,
) -> None:
    """The ``200`` of the claim left the Core and nobody knows whether it arrived.

    Not repairable, and the test says what that costs: the state the Core can see is the same in
    both cases — a claim, and a STARTED record if the tool cannot be repeated — so the answer is
    decided by **the tool's idempotency and nothing else**. If the order arrived, the node runs and
    delivers, and the delivery is accepted while the work is alive.
    """
    w = world()
    task, step, assignment, remote = await offered(w, repeatable=repeatable)
    await w.executor.begin(assignment.id, remote.id)
    visible = [one.status for one in await w.results.for_step(task.id, step.id)]
    w.clock.advance(PAST_THE_TTL)
    await w.alive()

    run = await w.runner.run(task.id)

    assert visible == ([] if repeatable else [ExecutionStatus.STARTED])
    if repeatable:
        assert len(await trail(w, task.id, T.STEP_RELEASED)) == 1  # back in play
    else:
        assert run.outcome is RunOutcome.FAILED  # closed where it stood
        assert await trail(w, task.id, T.STEP_RELEASED) == []


# ----------------------------------------------------------------------------------------
# A7 — repaired: nothing written, and the node holds the envelope
# ----------------------------------------------------------------------------------------


async def test_window_a7_a_delivery_that_wrote_nothing_is_simply_made_again() -> None:
    """Died at the gate of the delivery, before ``results.add``: **nothing was written**.

    Which is why the node keeps the envelope (D7) — it is the only copy — and why the repair needs
    no machinery at all: the same delivery again writes everything, once.
    """
    w = world()
    task, step, assignment, remote = await offered(w)
    claimed = await w.executor.begin(assignment.id, remote.id)
    assert await w.results.for_step(task.id, step.id) == ()
    assert await audited(w, task.id, E.TOOL_EXECUTED) == []

    from tests.executive.test_executor_remote import answered  # the envelope of a node

    delivered = await w.executor.deliver(assignment.id, remote.id, answered())

    assert claimed.assignment.state is AssignmentState.CLAIMED
    assert delivered.step_state is StepState.COMPLETED
    assert len(await w.results.for_step(task.id, step.id)) == 1


# ----------------------------------------------------------------------------------------
# A8 and A9 — repaired: the outcome is stored, and the rest may be missing
# ----------------------------------------------------------------------------------------


async def delivered_but_unwritten(
    w: World, *, conditions: tuple[str, ...] = (OK,)
) -> tuple[Any, Any, Any]:
    """What a death between ``results.add`` and ``store.deliver`` leaves: the outcome in the store,
    the assignment still ``CLAIMED``, the step RUNNING and the audit without its event."""
    task, step, assignment, remote = await offered(w, conditions=conditions)
    claimed = await w.executor.begin(assignment.id, remote.id)
    await w.results.add(envelope_of(w, assignment, claimed.tool_name))
    return task, step, assignment


async def test_window_a8_a_node_that_retries_finds_its_outcome_already_stored() -> None:
    """``results.add`` landed and ``store.deliver`` did not: the node retries with the same bytes.

    The id is deterministic per assignment, so the second insert is refused rather than duplicated —
    which is what makes the retry a no-op instead of a second run — and the delivery goes on from
    the first write that is missing. Without that id this would store a second row, and a step with
    two outcomes is what the executor refuses outright.
    """
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    from tests.executive.test_executor_remote import answered

    delivered = await w.executor.deliver(assignment.id, assignment.device_id, answered())

    assert len(await w.results.for_step(task.id, step.id)) == 1
    assert delivered.assignment.state is AssignmentState.DELIVERED
    assert delivered.step_state is StepState.COMPLETED
    assert (await w.event_types(task.id))[-3:] == [
        E.TOOL_EXECUTED,
        E.EXECUTION_VERIFIED,
        E.STEP_COMPLETED,
    ]


async def test_window_a9_the_next_run_finishes_a_delivery_whose_audit_is_missing() -> None:
    """``store.deliver`` landed and ``TOOL_EXECUTED`` did not: nobody retries, and the next ``run``
    finds the work delivered with the step still RUNNING — so it finishes it from the first write
    that is missing, and the event says it was written on a resume."""
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    await w.assignments.deliver(assignment.id, assignment.device_id, digest="ab" * 32, now=w.now)
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.DELIVERED

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)
    assert (await audited(w, task.id, E.TOOL_EXECUTED))[-1].payload[RECOVERED] is True


async def test_window_a9_a_resumed_delivery_whose_verification_fails_closes_the_task() -> None:
    """The same window with the verifier saying no: the step **and** the task are FAILED with one
    error (ADR 0014 §4), and the run returns the task as the resume closed it."""
    w = world()
    task, step, assignment = await delivered_but_unwritten(w, conditions=(BAD,))
    await w.assignments.deliver(assignment.id, assignment.device_id, digest="cd" * 32, now=w.now)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    assert (await w.task(task.id)).state is TaskState.FAILED
    assert await w.step_state(task.id, step.id) is StepState.FAILED


async def test_a_step_failed_by_a_verification_closes_its_task_on_the_next_finish() -> None:
    """Window 9a of ADR 0015 §8, reached by the remote road: the death between ``fail_step`` and
    ``fail``. The next call closes the task with the error already in the audit, rather than with a
    second description of the same failure."""
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    failure = ErrorMetadata(
        code=VERIFICATION_FAILED, message="the world disagrees with the tool", retryable=True
    )
    await w.engine.fail_step(task.id, step.id, failure)
    assert (await w.task(task.id)).state is TaskState.EXECUTING

    execution = await w.executor.finish(task.id, step.id)

    assert execution.task.state is TaskState.FAILED
    (failed,) = await audited(w, task.id, E.TASK_FAILED)
    assert failed.error is not None and failed.error.code == VERIFICATION_FAILED


# ----------------------------------------------------------------------------------------
# A10 — declared: a refusal written, the assignment not yet marked
# ----------------------------------------------------------------------------------------


async def test_window_a10_a_refusal_written_before_the_mark_costs_the_node_its_place() -> None:
    """``fail_step`` with ``tool.refused`` landed and ``store.deliver`` did not.

    Declared with its cost, and the cost is real: the node's **legitimate** delivery is answered
    ``410`` and leaves a ``DEVICE_REJECTED`` ``task_closed``, because from the Core's side the step
    is closed; and the node's place stays occupied until the expiry, since the assignment is still
    the work it holds. The order is this way round anyway, because the reverse would leave a refusal
    a resume could not tell from an interruption.
    """
    w = world()
    task, step, assignment, remote = await offered(w)
    await w.executor.begin(assignment.id, remote.id)
    refused = ErrorMetadata(code=TOOL_REFUSED, message="the node's clock said no", tool_name="echo")
    await w.engine.fail_step(task.id, step.id, refused)  # the write that landed
    from tests.executive.test_executor_remote import answered

    with pytest.raises(AssignmentVoidError):
        await w.executor.deliver(assignment.id, remote.id, answered())

    rejections = [one.payload for one in await audited(w, task.id, E.DEVICE_REJECTED)]
    assert rejections[-1]["reason"] == "task_closed"
    held = await w.assignments.held(assignment.id)
    assert held.state is AssignmentState.CLAIMED  # the place stays taken
    assert held.expires_at > w.now  # until the expiry, and no longer


# ----------------------------------------------------------------------------------------
# A11 and A13 — repaired: an expiry marked, and what follows it missing
# ----------------------------------------------------------------------------------------


async def test_window_a11_an_expiry_without_its_release_is_released_by_the_next_run() -> None:
    """``store.expire`` landed and ``release_step`` did not: ``EXPIRED``, the step still RUNNING.

    The next ``run`` reads an expired assignment whose ``STEP_RELEASED`` is not in the trail and
    releases with **the same key**, so the repair cannot release twice (the key is the assignment's
    id, and ``release_step`` is idempotent by it).
    """
    store = FakeAssignmentStore()
    w = world(assignment_store=store)
    task, step, assignment, _ = await offered(w)
    w.clock.advance(PAST_THE_TTL)
    await store.expire(assignment.id, now=w.now)  # the write that landed
    assert await trail(w, task.id, T.STEP_RELEASED) == []
    await w.alive()

    await w.runner.run(task.id)

    released = await trail(w, task.id, T.STEP_RELEASED)
    assert [one.metadata["assignment_id"] for one in released] == [str(assignment.id)]


async def test_window_a13_an_expiry_over_a_started_record_is_closed_by_the_next_run() -> None:
    """``store.expire`` landed over a STARTED record with no outcome, and the ``TOOL_EXECUTED`` that
    closes it did not: the next ``run`` reads the lapse, does **not** release — something may have
    acted — and lets ``Executor.finish`` close the step ``interrupted``."""
    store = FakeAssignmentStore()
    w = world(assignment_store=store)
    task, step, assignment, remote = await offered(w, repeatable=False)
    await w.executor.begin(assignment.id, remote.id)
    w.clock.advance(PAST_THE_TTL)
    await store.expire(assignment.id, now=w.now)  # the write that landed
    await w.alive()

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.FAILED
    failed = (await audited(w, task.id, E.STEP_FAILED))[-1]
    assert failed.error is not None and failed.error.code == "execution.interrupted"
    assert await trail(w, task.id, T.STEP_RELEASED) == []


async def test_a_released_step_is_released_once() -> None:
    """Criterion 27: the release is idempotent **by key**, read from the trail and not from the
    state of the last assignment.

    A step released, placed here and left RUNNING by a crash has an ``EXPIRED`` assignment behind it
    — and must not be released a second time, which would undo the placement that followed the first
    release. This is why ``standing`` asks the trail whether *this* assignment's release was
    written, instead of looking at the state of the row: ``EXPIRED`` is true of both the one that
    has been dealt with and the one that has not.
    """
    w = world()
    task, step, assignment, _ = await offered(w)
    w.clock.advance(PAST_THE_TTL)
    await w.alive()
    await w.runner.run(task.id)
    released = await trail(w, task.id, T.STEP_RELEASED)

    again = await w.runner.run(task.id)

    assert again.outcome is RunOutcome.COMPLETED
    assert await trail(w, task.id, T.STEP_RELEASED) == released
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.NONE


# ----------------------------------------------------------------------------------------
# A12 — declared: the trail has the release, the audit does not
# ----------------------------------------------------------------------------------------


async def test_window_a12_a_release_the_audit_never_recorded_still_places_the_step() -> None:
    """``release_step`` wrote the trail and the audit event died.

    Declared, and it is **the engine's hole** (ADR 0008 §4): the trail is what the graph is derived
    from, so the step is PENDING and the next ``run`` places it, while the audit stays one event
    short of the story. Nobody repairs it here because repairing it is a property of how the engine
    writes, not of the work protocol — and a milestone that pretended otherwise would be hiding a
    known gap inside a new one.
    """
    w, crashes = crashing_world()
    task, step, assignment, _ = await offered(w)
    w.clock.advance(PAST_THE_TTL)
    await w.alive()
    crashes.audit.arm("append", lambda event: event.event_type is E.STEP_RELEASED)

    with pytest.raises(SimulatedCrash):
        await w.runner.run(task.id)

    assert len(await trail(w, task.id, T.STEP_RELEASED)) == 1  # the trail has it
    assert await audited(w, task.id, E.STEP_RELEASED) == []  # the audit never will
    crashes.disarm()

    assert (await w.runner.run(task.id)).outcome is RunOutcome.COMPLETED  # placed again, and run
    assert await audited(w, task.id, E.STEP_RELEASED) == []


# ----------------------------------------------------------------------------------------
# A14 — repaired: a revocation whose cut never happened
# ----------------------------------------------------------------------------------------


async def test_window_a14_a_revocation_without_its_cut_is_repaired_by_revoking_again() -> None:
    """``registry.revoke`` landed and ``cut_short`` did not: the node is out and its work is not.

    The work keeps its natural expiry — which bounds the damage — and repeating the revocation cuts
    it, which is why the route calls ``cut_short`` on the already-revoked branch too (D17).
    """
    w = world()
    task, step, assignment, remote = await offered(w)
    await w.executor.begin(assignment.id, remote.id)
    await w.devices.revoke(remote.id, by=ELA_ACTOR)  # the write that landed

    still_live = await w.assignments.held(assignment.id)
    cut = await w.assignments.cut_short(remote.id)  # `ela node revoke`, again

    assert still_live.expires_at > w.now  # the natural expiry, not touched by the revocation
    assert cut == 1
    assert (await w.assignments.held(assignment.id)).expires_at <= w.now


# ----------------------------------------------------------------------------------------
# A15 — declared: a heartbeat, and the old expiry
# ----------------------------------------------------------------------------------------


async def test_window_a15_a_renewal_that_died_after_its_heartbeat_leaves_the_old_expiry() -> None:
    """Died inside the renewal, after the heartbeat and before ``store.renew``.

    Innocuous, and declared rather than repaired: the expiry is the one it already had, so the node
    retries and renews — and if the expiry passes first, it is the expiry of always. One extra sign
    of life, again, is the price of the order that makes ``recover()`` safe.
    """
    w = world()
    task, step, assignment, remote = await offered(w)
    await w.executor.begin(assignment.id, remote.id)
    taken = await w.assignments.held(assignment.id)
    await w.engine.heartbeat(task.id)  # the write that landed

    unchanged = await w.assignments.held(assignment.id)
    w.clock.advance(timedelta(seconds=30))
    renewed = await w.assignments.renew(assignment.id, remote.id)

    assert unchanged.expires_at == taken.expires_at
    assert renewed.expires_at > taken.expires_at
