"""``fs.no_answer`` and the spend of a policy (M13.17, ADR 0074; decision 53 of the review of its
SPEC): the rows the table of ADR 0068 §6 gains.

- **A wait abandoned at the look before the spend spends nothing**: the covered prospect refuses
  with ``fs.no_answer``, the step fails with that code, no use is spent and no tool runs.
- **A wait abandoned in the execution has spent its use**: the use goes before the tool, and the
  tool's failure — ``fs.no_answer`` — closes the step. The disk did not answer; the use was spent
  on a call that did start.
- **It is not retried**: the failure is not ``retryable``, and the step is not tried again.
"""

from __future__ import annotations

from ela.domain import ErrorMetadata, ExecutionStatus, PermissionOutcome, StepState
from ela.ports import Prospect
from ela.tools.disk import NO_ANSWER
from tests.executive.test_policy_high import HIGH_TERMED, a_policy, high_world
from tests.permissions.policy_support import TERMED_ARGS

SILENT = ErrorMetadata(
    code=NO_ANSWER,
    message="a look at 'x': the disk did not answer within 10 s, and ELA stopped waiting",
    tool_name="fake",
)


async def test_a_look_abandoned_before_the_spend_spends_nothing() -> None:
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w)
    w.tool(HIGH_TERMED.id).covered = Prospect(refusal=SILENT)

    execution = await w.execute(task.id, step.id)

    assert execution.decision.outcome is PermissionOutcome.ALLOWED
    assert execution.result is None or execution.result.status is ExecutionStatus.FAILED
    assert await w.store.uses(policy.id) == 0
    assert w.tool(HIGH_TERMED.id).calls == ()
    assert await w.step_state(task.id, step.id) is StepState.FAILED


async def test_a_wait_abandoned_in_the_execution_has_spent_its_use_and_is_not_retried() -> None:
    w = high_world()
    task, step = await w.running(HIGH_TERMED.id, arguments=TERMED_ARGS)
    policy = await a_policy(w)
    tool = w.tool(HIGH_TERMED.id)
    tool._status = ExecutionStatus.FAILED  # noqa: SLF001 — the fake's answer, set by the test
    tool._error = SILENT  # noqa: SLF001

    execution = await w.execute(task.id, step.id)

    assert execution.result is not None and execution.result.error is not None
    assert execution.result.error.code == NO_ANSWER
    assert execution.result.error.retryable is False
    assert await w.store.uses(policy.id) == 1
    assert len(tool.calls) == 1
    assert await w.step_state(task.id, step.id) is StepState.FAILED
