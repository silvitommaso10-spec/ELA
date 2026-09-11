"""The crash windows of the work protocol (M12.2, ADR 0038 §19).

The order of the writes is what makes a repair possible, so each window is a *state a death leaves
behind* and the test is what the next call does with it. Nothing here simulates a crash by patching:
the state is built through ELA's own ports — the precedent of ``tamper_with_the_trail`` — because a
window is a row that exists and a row that does not.

The two in this file are the ones about the delivery, which is where the order matters most:
``results.add`` → ``store.deliver`` → ``TOOL_EXECUTED``, so *delivered* always implies *the outcome
is stored, or the step is already closed*. The remaining windows arrive with the rest of
criterion 28.
"""

from __future__ import annotations

from uuid import uuid5

from ela.domain import (
    AuditEventType,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PrivacyLevel,
    StepState,
    TaskState,
)
from ela.executive import (
    DELIVERY_NAMESPACE,
    RECOVERED,
    VERIFICATION_FAILED,
    RunOutcome,
    Standing,
)
from tests.executive.support import BAD, OK, World, world
from tests.permissions.support import ECHO

E = AuditEventType
REPAIRED = {"A8", "A9"}
"""The windows this file repairs so far; ADR 0038 §19 calls fifteen of them **Riparato**, and the
test that holds the document to this set comes with the rest of them (criterion 28)."""


async def delivered_but_unwritten(
    w: World, *, conditions: tuple[str, ...] = (OK,)
) -> tuple[object, object, object]:
    """What a death between ``results.add`` and ``TOOL_EXECUTED`` leaves: the outcome in the store,
    the assignment marked, the step still RUNNING and the audit without the event (window ``A9``).

    Built through the ports, so the state is the one a crash would leave and not a mock of it.
    """
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, conditions=conditions)
    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    assignment = stand.assignment
    claimed = await w.executor.begin(assignment.id, remote.id)
    await w.results.add(
        ExecutionResult(
            id=ExecutionId(uuid5(DELIVERY_NAMESPACE, str(assignment.id))),
            created_at=w.now,
            capability_id=assignment.decision.capability_id,
            status=ExecutionStatus.SUCCEEDED,
            task_id=assignment.task_id,
            step_id=assignment.step_id,
            tool_name=claimed.tool_name,
            device_id=remote.id,
            decision_id=assignment.decision.id,
            output={"ok": True},
        )
    )
    return task, step, assignment


async def test_window_a8_a_node_that_retries_finds_its_outcome_already_stored() -> None:
    """``results.add`` landed and ``store.deliver`` did not: the node retries with the same bytes.

    The id is deterministic per assignment, so the second insert is refused rather than
    duplicated — which is what makes the retry a no-op instead of a second run — and the delivery
    goes on from the first write that is missing. Without the deterministic id this would store a
    second row and the step would have two outcomes, which the executor refuses outright.
    """
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    from tests.executive.test_executor_remote import answered  # the envelope a node brings back

    delivered = await w.executor.deliver(assignment.id, assignment.device_id, answered())

    assert len(await w.results.for_step(task.id, step.id)) == 1
    assert delivered.assignment.state.value == "DELIVERED"
    assert delivered.step_state is StepState.COMPLETED
    types = await w.event_types(task.id)
    assert types[-3:] == [E.TOOL_EXECUTED, E.EXECUTION_VERIFIED, E.STEP_COMPLETED]


async def test_window_a9_the_next_run_finishes_a_delivery_whose_audit_is_missing() -> None:
    """``store.deliver`` landed and ``TOOL_EXECUTED`` did not: nobody retries, and the next ``run``
    finds the work delivered with the step still RUNNING — so it finishes it from the first write
    that is missing, and the event says it was written on a resume."""
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    await w.assignments.deliver(assignment.id, assignment.device_id, digest="ab" * 32, now=w.now)
    assert (await w.assignments.standing(task.id, step.id)).standing is Standing.DELIVERED

    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert run.outcome is RunOutcome.COMPLETED
    assert run.steps == (step.id,)
    executed = [e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED][-1]
    assert executed.payload[RECOVERED] is True


async def test_a_step_failed_by_a_verification_closes_its_task_on_the_next_finish() -> None:
    """Window 9a of ADR 0015 §8, reached through the remote path: the death between ``fail_step``
    and ``fail``.

    A failed verification is a contradiction between what the tool said and the world, so the step
    **and** the task are failed with one error (ADR 0014 §4). If the process dies between the two,
    the task is left EXECUTING with a step FAILED by a verification — and the next call closes it
    with the error already in the audit, rather than with a second description of the same failure.
    """
    w = world()
    task, step, assignment = await delivered_but_unwritten(w)
    failure = ErrorMetadata(
        code=VERIFICATION_FAILED, message="the world disagrees with the tool", retryable=True
    )
    await w.engine.fail_step(task.id, step.id, failure)
    assert (await w.task(task.id)).state is TaskState.EXECUTING

    execution = await w.executor.finish(task.id, step.id)

    assert execution.task.state is TaskState.FAILED
    (failed,) = [e for e in await w.events(task.id) if e.event_type is E.TASK_FAILED]
    assert failed.error is not None and failed.error.code == VERIFICATION_FAILED


async def test_window_a9_a_resumed_delivery_whose_verification_fails_closes_the_task() -> None:
    """The same window, with the verifier saying no: the step **and** the task are FAILED with one
    error (ADR 0014 §4), and the run returns the task as the resume closed it — not as the loop
    would have found it on a later iteration."""
    w = world()
    task, step, assignment = await delivered_but_unwritten(w, conditions=(BAD,))
    await w.assignments.deliver(assignment.id, assignment.device_id, digest="cd" * 32, now=w.now)

    run = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)

    assert run.outcome is RunOutcome.FAILED
    assert run.steps == (step.id,)
    assert (await w.task(task.id)).state is TaskState.FAILED
    assert await w.step_state(task.id, step.id) is StepState.FAILED
