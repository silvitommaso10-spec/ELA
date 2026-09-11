"""The three instants of a call that runs on another machine (M12.2, ADR 0038 §2, §4, §12).

What the Core writes when a node takes the work, what it builds from the envelope the node brings
back, and what it refuses on the way. On the fakes and without a route: the HTTP of it is
``tests/api/test_nodes_work.py``, and whether a node can play the whole protocol is
``tests/conformance``.

The envelope is the point of most of these: the node says what its tool said, and **everything that
places the run in the chain of §32 is the Core's** — the id, the instant, the stamp of the call. A
result arriving whole from outside would put the order of the audit in another machine's clock.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid5

import pytest

from ela.domain import (
    AssignmentState,
    AuditEventType,
    ExecutionId,
    ExecutionStatus,
    PrivacyLevel,
    StepState,
    TaskStep,
)
from ela.executive import (
    DELIVERY_NAMESPACE,
    TOOL_EXCEPTION,
    TOOL_REFUSED,
    AssignmentVoidError,
    Delivery,
    DeliveryConflictError,
    Envelope,
    ExecutorError,
    RunOutcome,
    WorkNotYoursError,
    WorkRejection,
    check_envelope,
)
from ela.ports import (
    AssignmentExpiredError,
    AssignmentHeldElsewhereError,
)
from tests.executive.support import OK, World, world
from tests.permissions.support import ECHO

E = AuditEventType
INSTANT = timedelta(microseconds=1)
NODE_INSTANTS = {"started_at": "2026-09-11T08:00:00Z", "finished_at": "2026-09-11T08:00:02Z"}
"""The node's own instants, an hour behind the Core's clock: reported data, never the chain's."""


async def handed(
    w: World, *, conditions: tuple[str, ...] = (OK,)
) -> tuple[TaskStep, object, object]:
    """A step of an EXECUTING task handed to a node that is not this machine."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, conditions=conditions)
    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    return step, remote, stand.assignment


def answered(**update: object) -> Envelope:
    """What a node brings back when its tool answered: the node's half, and nothing else."""
    fields: dict[str, object] = {
        "form": Delivery.RESULT,
        "status": ExecutionStatus.SUCCEEDED,
        "output": {"ok": True},
        "duration_ms": 12,
        "node": NODE_INSTANTS,
    }
    return Envelope(**{**fields, **update})  # type: ignore[arg-type]


# ----------------------------------------------------------------------------------------
# The claim: what the Core writes when a node takes the work (D14)
# ----------------------------------------------------------------------------------------


async def test_the_started_record_is_born_when_the_node_claims() -> None:
    """Criterion 9. Until a node takes the work nothing can have acted, so the STARTED record of a
    tool that cannot be repeated is written **at the claim** and not in ``run``: an offer nobody
    claimed leaves the step releasable, whatever its tool."""
    w = world()
    w.tool(ECHO.id).idempotent = False
    step, remote, assignment = await handed(w)
    task_id = assignment.task_id  # type: ignore[attr-defined]
    assert await w.results.for_step(task_id, step.id) == ()

    claimed = await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    (record,) = await w.results.for_step(task_id, step.id)
    assert record.status is ExecutionStatus.STARTED
    assert record.device_id == remote.id  # type: ignore[attr-defined]
    assert record.authorization_id is None
    assert claimed.assignment.state is AssignmentState.CLAIMED
    assert claimed.tool_name == w.tool(ECHO.id).name
    assert claimed.arguments == step.arguments  # the plan's, never the node's


async def test_a_repeatable_tool_leaves_nothing_behind_at_the_claim() -> None:
    """``core.echo`` can be run again, so there is nothing for a STARTED record to protect: at the
    expiry such a step is released and placed again (dec. F)."""
    w = world()
    step, remote, assignment = await handed(w)

    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    assert await w.results.for_step(assignment.task_id, step.id) == ()  # type: ignore[attr-defined]


async def test_work_another_node_claims_is_refused_and_nothing_is_written() -> None:
    w = world()
    step, remote, assignment = await handed(w)
    other = await w.remote("phone")
    before = len(await w.events())

    with pytest.raises(AssignmentHeldElsewhereError):
        await w.executor.begin(assignment.id, other.id)  # type: ignore[attr-defined]

    assert len(await w.events()) == before
    assert await w.results.for_step(assignment.task_id, step.id) == ()  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------------------
# The delivery: the result the Core mints (dec. B)
# ----------------------------------------------------------------------------------------


async def test_a_node_an_hour_behind_does_not_reorder_the_chain() -> None:
    """Criterion 8. ``created_at`` is the Core's, at the instant of the gate; the node's instants
    travel in ``metadata["node"]`` as reported data. With the node's clock, ``TOOL_EXECUTED`` would
    be born before the ``PERMISSION_DECIDED`` that allowed it, and the order of §32 would come from
    outside."""
    w = world()
    step, remote, assignment = await handed(w)
    task_id = assignment.task_id  # type: ignore[attr-defined]
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    delivered = await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    (result,) = await w.results.for_step(task_id, step.id)
    assert result.id == ExecutionId(uuid5(DELIVERY_NAMESPACE, str(assignment.id)))  # type: ignore[attr-defined]
    assert result.created_at == w.now
    assert result.metadata["node"] == NODE_INSTANTS
    assert result.duration_ms == 12  # reported: the Core could only measure the network
    assert result.device_id == remote.id  # type: ignore[attr-defined]
    assert result.decision_id == assignment.decision.id  # type: ignore[attr-defined]
    assert result.tool_name == w.tool(ECHO.id).name
    types = await w.event_types(task_id)
    assert types.index(E.PERMISSION_DECIDED) < types.index(E.TOOL_EXECUTED)
    executed = [e for e in await w.events(task_id) if e.event_type is E.TOOL_EXECUTED][-1]
    assert executed.created_at == result.created_at
    assert delivered.step_state is StepState.COMPLETED
    assert delivered.assignment.state is AssignmentState.DELIVERED


async def test_the_second_half_of_a_remote_call_writes_what_a_local_one_writes() -> None:
    """The one implementation of the second half, seen from the trail: audit, verification, close.

    The parity with ``local`` is asserted in full by ``test_local_remote_parity.py``; what this one
    fixes is that the delivery goes through the **same** method, so a ``recovered`` mark — which a
    resume would add — never appears on a first delivery.
    """
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    types = await w.event_types(assignment.task_id)  # type: ignore[attr-defined]
    assert types[-3:] == [E.TOOL_EXECUTED, E.EXECUTION_VERIFIED, E.STEP_COMPLETED]
    for event in await w.events(assignment.task_id):  # type: ignore[attr-defined]
        assert "recovered" not in event.payload


async def test_an_exception_on_the_node_becomes_a_failed_result_the_core_mints() -> None:
    """The form ``_run_tool`` gives an exception here too: a FAILED result whose error names the
    type and never the message (§57)."""
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    delivered = await w.executor.deliver(  # type: ignore[attr-defined]
        assignment.id, remote.id, Envelope(form=Delivery.EXCEPTION, exception="TimeoutError")
    )

    (result,) = await w.results.for_step(assignment.task_id, step.id)  # type: ignore[attr-defined]
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert (result.error.code, result.error.message) == (TOOL_EXCEPTION, "TimeoutError")
    assert delivered.step_state is StepState.FAILED


async def test_a_tool_that_refused_the_decision_there_fails_the_step_here() -> None:
    """The node's clock found the decision expired: no result is stored, as in this process, and
    the step fails with ``tool.refused``. The assignment is marked after, so *delivered* implies
    the step is closed."""
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    delivered = await w.executor.deliver(  # type: ignore[attr-defined]
        assignment.id, remote.id, Envelope(form=Delivery.REFUSED)
    )

    assert await w.results.for_step(assignment.task_id, step.id) == ()  # type: ignore[attr-defined]
    assert delivered.step_state is StepState.FAILED
    assert delivered.assignment.state is AssignmentState.DELIVERED
    failed = [e for e in await w.events(assignment.task_id) if e.event_type is E.STEP_FAILED]  # type: ignore[attr-defined]
    assert failed[-1].error is not None and failed[-1].error.code == TOOL_REFUSED


async def test_the_outcome_of_a_tool_that_cannot_be_repeated_names_its_started_record() -> None:
    """The two rows of one run are one run (ADR 0021 §1): the outcome carries the id of the STARTED
    record the claim wrote, so a resume can tell "it was started and came back" from two runs."""
    w = world()
    w.tool(ECHO.id).idempotent = False
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    (record,) = await w.results.for_step(assignment.task_id, step.id)  # type: ignore[attr-defined]

    await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    settled = [
        one
        for one in await w.results.for_step(assignment.task_id, step.id)  # type: ignore[attr-defined]
        if one.status is not ExecutionStatus.STARTED
    ]
    assert [one.metadata["started_id"] for one in settled] == [str(record.id)]


# ----------------------------------------------------------------------------------------
# Finishing what a node left behind (ADR 0038 §2)
# ----------------------------------------------------------------------------------------


async def test_finishing_a_step_of_a_task_that_closed_is_refused() -> None:
    """``finish`` writes the second half of a call; a task nobody is waiting for has no second half,
    and a doubt is a failure (§33)."""
    w = world()
    step, _, assignment = await handed(w)
    await w.engine.cancel(assignment.task_id, reason="basta")  # type: ignore[attr-defined]

    with pytest.raises(ExecutorError, match="needs an EXECUTING task"):
        await w.executor.finish(assignment.task_id, step.id)  # type: ignore[attr-defined]


async def test_finishing_a_step_nothing_ran_on_is_refused() -> None:
    """Nothing in the store means nobody can have acted: that step was to be **released**, and
    finishing it would invent an outcome. The runner never asks — ``lapse`` releases it — so this is
    the guard on a caller that would."""
    w = world()
    step, _, assignment = await handed(w)

    with pytest.raises(ExecutorError, match="released and not finished"):
        await w.executor.finish(assignment.task_id, step.id)  # type: ignore[attr-defined]


# ----------------------------------------------------------------------------------------
# The gate: the four refusals of the way of the work (ADR 0038 §12)
# ----------------------------------------------------------------------------------------


async def rejections(w: World) -> list[dict[str, object]]:
    return [dict(e.payload) for e in await w.events() if e.event_type is E.DEVICE_REJECTED]


async def test_work_the_core_never_minted_is_not_assigned_and_says_so() -> None:
    w = world()
    _, remote, _ = await handed(w)
    unknown = UUID("00000000-0000-4000-8000-0000000009ff")

    with pytest.raises(WorkNotYoursError):
        await w.executor.deliver(unknown, remote.id, answered())  # type: ignore[arg-type,attr-defined]

    (refusal,) = await rejections(w)
    assert refusal["reason"] == WorkRejection.NOT_ASSIGNED.value
    assert refusal["assignment_known"] is False


async def test_work_of_another_node_gets_the_same_answer_and_another_payload() -> None:
    """Criterion 16: one answer for both — a node is told nothing about other nodes' work — and two
    different reasons in the audit, because the two facts are different."""
    w = world()
    _, _, assignment = await handed(w)
    other = await w.remote("phone")

    with pytest.raises(WorkNotYoursError):
        await w.executor.deliver(assignment.id, other.id, answered())  # type: ignore[attr-defined]

    (refusal,) = await rejections(w)
    assert refusal["reason"] == WorkRejection.NOT_ASSIGNED.value
    assert refusal["assignment_known"] is True


async def test_work_not_taken_cannot_be_delivered() -> None:
    w = world()
    _, remote, assignment = await handed(w)  # offered, never claimed

    with pytest.raises(WorkNotYoursError):
        await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    assert (await rejections(w))[0]["reason"] == WorkRejection.NOT_ASSIGNED.value


async def test_the_three_ways_work_is_not_yours_are_told_one_thing() -> None:
    """Unknown, another node's, no longer taken: **one** error with one message.

    A node that could tell them apart could map which assignments exist for the others — the reason
    ADR 0023 §7 answers ``401`` and not ``404`` to a path that does not exist. The audit keeps the
    difference, where the user reads and nodes do not.
    """
    w = world()
    _, remote, assignment = await handed(w)  # offered, and so not deliverable
    other = await w.remote("phone")
    said: list[str] = []

    for when, who in (
        (UUID("00000000-0000-4000-8000-0000000009ff"), remote.id),  # type: ignore[attr-defined]
        (assignment.id, other.id),  # type: ignore[attr-defined]
        (assignment.id, remote.id),  # type: ignore[attr-defined]
    ):
        with pytest.raises(WorkNotYoursError) as caught:
            await w.executor.deliver(when, who, answered())  # type: ignore[arg-type]
        said.append(str(caught.value).replace(str(when), "<id>"))

    assert len(set(said)) == 1, said
    assert [one["assignment_known"] for one in await rejections(w)] == [False, True, True]


async def test_a_late_delivery_is_refused_and_the_audit_keeps_what_it_reported() -> None:
    """Accepting it would make the expiry of D6 a fact that depends on who passed by. What the node
    reports is kept as its **word** — the status, never the output — because for a tool that cannot
    be repeated it is the only thing that resolves "whether it acted"."""
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    w.clock.advance(assignment.expires_at - w.now)  # type: ignore[attr-defined]

    with pytest.raises(AssignmentExpiredError):
        await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    (refusal,) = await rejections(w)
    assert refusal["reason"] == WorkRejection.LATE.value
    assert refusal["reported_status"] == ExecutionStatus.SUCCEEDED.value
    assert "ok" not in str(refusal)
    assert await w.step_state(assignment.task_id, step.id) is StepState.RUNNING  # type: ignore[attr-defined]


async def test_a_delivery_for_a_task_that_closed_is_void() -> None:
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    await w.engine.cancel(assignment.task_id, reason="the user changed their mind")  # type: ignore[attr-defined]

    with pytest.raises(AssignmentVoidError):
        await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    (refusal,) = await rejections(w)
    assert refusal["reason"] == WorkRejection.TASK_CLOSED.value
    assert refusal["reported_status"] == ExecutionStatus.SUCCEEDED.value


async def test_the_same_envelope_twice_is_the_same_answer_and_no_second_row() -> None:
    """A network that retries is not an action (ADR 0016 §6): the same bytes give the same answer,
    one stored result, and not one new event."""
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    first = await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]
    events = len(await w.events())

    again = await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]

    assert again.step_state is first.step_state
    assert again.execution is None  # there was nothing left to complete
    assert len(await w.results.for_step(assignment.task_id, step.id)) == 1  # type: ignore[attr-defined]
    assert len(await w.events()) == events


async def test_a_second_envelope_is_a_conflict_and_the_first_one_stands() -> None:
    w = world()
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    await w.executor.deliver(assignment.id, remote.id, answered())  # type: ignore[attr-defined]
    stored = (await w.results.for_step(assignment.task_id, step.id))[0]  # type: ignore[attr-defined]

    with pytest.raises(DeliveryConflictError):
        await w.executor.deliver(  # type: ignore[attr-defined]
            assignment.id, remote.id, answered(output={"ok": False})
        )

    assert (await w.results.for_step(assignment.task_id, step.id))[0] == stored  # type: ignore[attr-defined]
    (refusal,) = await rejections(w)
    assert refusal["reason"] == WorkRejection.DELIVERY_CONFLICT.value
    assert stored.id is not None and "digest" not in str(refusal)


# ----------------------------------------------------------------------------------------
# What a coherent envelope looks like (ADR 0038 §4)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "envelope",
    [
        Envelope(form=Delivery.RESULT),
        Envelope(form=Delivery.RESULT, status=ExecutionStatus.STARTED),
        Envelope(form=Delivery.REFUSED, status=ExecutionStatus.SUCCEEDED),
        Envelope(form=Delivery.EXCEPTION),
        Envelope(form=Delivery.EXCEPTION, exception="not an identifier"),
        Envelope(form=Delivery.RESULT, status=ExecutionStatus.FAILED, exception="TimeoutError"),
        Envelope(form=Delivery.REFUSED, output={"ok": True}),
    ],
    ids=[
        "no-status",
        "a-status-no-tool-produces",
        "a-refusal-with-a-status",
        "an-exception-with-no-name",
        "a-name-that-is-not-one",
        "a-result-with-an-exception",
        "a-refusal-that-produced-something",
    ],
)
def test_an_envelope_that_tells_two_stories_is_refused(envelope: Envelope) -> None:
    """A ``ValueError`` here is a ``422`` at the route: the form says which fields mean anything,
    and ELA does not choose between two readings of one message (§33)."""
    with pytest.raises(ValueError):
        check_envelope(envelope)


def test_the_digest_is_of_the_whole_envelope_and_not_of_its_order() -> None:
    """What tells a retry from a second claim: the same envelope however its JSON arrived, and a
    different one as soon as any field differs."""
    assert answered().digest == answered().digest
    assert answered().digest != answered(output={"ok": False}).digest
    assert answered().digest != answered(duration_ms=13).digest
    assert (
        Envelope(form=Delivery.REFUSED).digest
        != Envelope(form=Delivery.EXCEPTION, exception="E").digest
    )
