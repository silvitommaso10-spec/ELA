"""The same plan leaves the same trail here and on a node (M12.2, criterion 5; dec. A).

The defect of two paths is the one ADR 0031 was written about: two roads that should say the same
thing and drift in silence. M12.2 guards against it by sharing everything except the transport —
the second half of a call has one implementation — and by **measuring it**: the audit of a plan run
in this process and the audit of the same plan run on a node are compared, event type by event type.

They are equal, with no exceptions to list, and that is a property of the design rather than a
coincidence: the claim writes no audit event (the STARTED record lives in the result store) and
``STEP_RELEASED`` appears only when an assignment expires, which here none does.
"""

from __future__ import annotations

from ela.domain import AuditEventType, ExecutionStatus, PrivacyLevel, StepState
from ela.executive import Delivery, Envelope, RunOutcome
from tests.executive.support import world
from tests.permissions.support import ECHO

E = AuditEventType


async def here() -> list[AuditEventType]:
    """The plan walked in this process, as every plan was walked before M12.2."""
    w = world()
    task, _ = await w.queued(ECHO.id)

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    return await w.event_types(task.id)


async def there() -> list[AuditEventType]:
    """The same plan, on a node that is not this machine: assigned, claimed, delivered, closed."""
    w = world()
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id)

    assigned = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    assert assigned.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    await w.executor.begin(stand.assignment.id, remote.id)
    delivered = await w.executor.deliver(
        stand.assignment.id,
        remote.id,
        Envelope(
            form=Delivery.RESULT,
            status=ExecutionStatus.SUCCEEDED,
            output={"ok": True},
            duration_ms=7,
            node={"finished_at": "2026-09-11T08:00:02Z"},
        ),
    )
    assert delivered.step_state is StepState.COMPLETED
    closed = await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    assert closed.outcome is RunOutcome.COMPLETED
    return await w.event_types(task.id)


async def test_the_same_plan_leaves_the_same_trail_here_and_there() -> None:
    """The measurement dec. A promised. A divergence in the second half — a ``TOOL_EXECUTED`` with
    the ``recovered`` mark, a missing ``EXECUTION_VERIFIED``, an extra event of the transport —
    fails here, which is the only place that would notice it."""
    assert await there() == await here()


async def test_the_trail_of_a_remote_run_still_names_the_node_that_ran_it() -> None:
    """Equal sequences are not identical events: what changes is the node, and it must change.

    A trail that named this machine for work done elsewhere would be the worst of both — the same
    shape and a false fact — so the parity above is about the *shape*, and this is about the fact.
    """
    w = world()
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id)
    await w.runner.run(task.id, max_privacy=PrivacyLevel.TRUSTED)
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    await w.executor.begin(stand.assignment.id, remote.id)
    await w.executor.deliver(
        stand.assignment.id,
        remote.id,
        Envelope(form=Delivery.RESULT, status=ExecutionStatus.SUCCEEDED, output={"ok": True}),
    )

    executed = [e for e in await w.events(task.id) if e.event_type is E.TOOL_EXECUTED][-1]

    assert executed.device_id == remote.id
    assert executed.payload["device"] == str(remote.id)
    (result,) = await w.results.for_step(task.id, step.id)
    assert result.device_id == remote.id
