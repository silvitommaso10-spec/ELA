"""The spending cap where a call that spends is about to leave (M14.1, ADR 0057).

The gate sits where the ``STARTED`` record is born — the call on this machine, and the claim of a
node —, and before a question: a call the month cannot let out is **denied before it leaves**
(criterion 1), with a transition whose reason names the line and whose audit row carries the
numbers (decision G), and the tool is never called. A call that fits leaves its reservation in the
record (criterion 2). The tools here are fakes that declare a worst case: what is under test is
the executor's gate, for every tool that spends, and not the one that brought it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from ela.domain import (
    AuditEventType,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PrivacyLevel,
    ProviderUsage,
    StepState,
    TaskState,
    WorstCase,
)
from ela.executive import RunOutcome
from ela.executive.executor import ASKED
from ela.executive.spending import CAP_VARIABLE, SpendingCode, SpendingGate, month_of
from ela.ports import AssignmentStateError
from ela.testing.fakes import FakeExecutionResultStore, FakeTool
from tests.executive.support import OK, World, fake_tools, world
from tests.permissions.support import ECHO, NOTE

E = AuditEventType
BOUND = WorstCase(
    amount=Decimal("0.25"), currency="USD", model="m", input_tokens=900, output_tokens=100
)
COST = ProviderUsage(input_tokens=10, output_tokens=5, cost=Decimal("0.002"), currency="USD")


def a_world(
    *,
    cap: Decimal | None,
    bound: WorstCase | ErrorMetadata | None = BOUND,
    usage: ProviderUsage | None = COST,
    results: FakeExecutionResultStore | None = None,
) -> World:
    """A world whose ``core.echo`` and ``workspace.write_note`` spend: tools that cannot be run
    twice, nor moved, and that say ``bound`` is the most they cost."""
    store = FakeExecutionResultStore() if results is None else results
    base = world()
    tools = fake_tools(base.clock, base.ids)
    for spec in (ECHO, NOTE):
        tool = FakeTool(
            spec.id,
            base.clock,
            base.ids,
            name=f"fake-{spec.id}",
            output={"ok": True},
            idempotent=False,
            usage=usage,
        )
        tool.bound = bound
        tools[spec.id] = tool
    fresh = world(tools=tools.values(), results=store, spending=SpendingGate(store, cap))
    fresh.fake_tools.update(tools)
    return fresh


async def payload_of_the_denial(w: World, task_id: object) -> dict[str, object]:
    (denied,) = [e for e in await w.events(task_id) if e.event_type is E.TASK_DENIED]  # type: ignore[arg-type]
    return dict(denied.payload)


# --------------------------------------------------------------------------------------
# On this machine: the gate before the STARTED record and the call
# --------------------------------------------------------------------------------------


async def test_without_a_cap_a_call_that_spends_is_denied_before_it_leaves() -> None:
    """Criterion 1 (decision B): the tool is never called, no record is written, and the reason
    names the line."""
    w = a_world(cap=None)
    task, step = await w.running(ECHO.id, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.DENIED
    assert w.tool(ECHO.id).calls == ()
    assert await w.results.for_step(task.id, step.id) == ()
    assert await w.step_state(task.id, step.id) is StepState.CANCELLED
    payload = await payload_of_the_denial(w, task.id)
    assert payload["operation"] == "deny_by_cap"
    assert payload["code"] == SpendingCode.NO_CAP.value
    assert CAP_VARIABLE in str(payload["reason"])


async def test_the_guardian_allowed_and_the_cap_said_no_in_that_order() -> None:
    """The cap is not a permission (decision G): ``PERMISSION_DECIDED`` allowed, then the denial."""
    w = a_world(cap=None)
    task, step = await w.running(ECHO.id, conditions=(OK,))

    await w.execute(task.id, step.id)

    kinds = await w.event_types(task.id)
    assert kinds.index(E.PERMISSION_DECIDED) < kinds.index(E.TASK_DENIED)
    assert E.TOOL_EXECUTED not in kinds


async def test_a_call_that_fits_leaves_its_reservation_in_the_started_record() -> None:
    """Criterion 2: the record is the reservation, and the outcome closes it with its cost."""
    w = a_world(cap=Decimal(5))
    task, step = await w.running(ECHO.id, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is not TaskState.DENIED
    started, outcome = await w.results.for_step(task.id, step.id)
    assert started.status is ExecutionStatus.STARTED and started.worst_case == BOUND
    assert outcome.worst_case is None and outcome.usage == COST
    assert len(w.tool(ECHO.id).calls) == 1


async def test_a_call_that_would_cross_the_cap_is_denied_with_the_four_numbers() -> None:
    w = a_world(cap=Decimal("0.3"))
    first, step = await w.running(ECHO.id, conditions=(OK,))
    await w.results.add(open_reservation(w))  # a call of this month still in flight

    execution = await w.execute(first.id, step.id)

    assert execution.task.state is TaskState.DENIED
    assert w.tool(ECHO.id).calls == ()
    payload = await payload_of_the_denial(w, first.id)
    month = month_of(w.now).label
    assert payload["code"] == SpendingCode.OVER_CAP.value
    assert (payload["spent"], payload["reserved"], payload["worst_case"], payload["cap"]) == (
        "0",
        "0.25",
        "0.25",
        "0.3",
    )
    assert payload["month"] == month
    assert str(payload["reason"]).endswith(f"> cap 0.3 USD ({CAP_VARIABLE}, {month})")


def open_reservation(w: World, amount: Decimal = Decimal("0.25")) -> ExecutionResult:
    """A ``STARTED`` record of another call of this month, with ``amount`` reserved, and no
    outcome: a call in flight."""
    return ExecutionResult(
        id=ExecutionId(w.ids.new_uuid()),
        created_at=w.now,
        capability_id=ECHO.id,
        status=ExecutionStatus.STARTED,
        worst_case=BOUND.model_copy(update={"amount": amount}),
    )


async def test_a_call_that_cannot_be_bounded_is_not_made() -> None:
    error = ErrorMetadata(code="routing.unknown_task_type", message="no route")
    w = a_world(cap=Decimal(5), bound=error)
    task, step = await w.running(ECHO.id, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.DENIED
    payload = await payload_of_the_denial(w, task.id)
    assert payload["code"] == SpendingCode.UNBOUNDED.value
    assert "routing.unknown_task_type: no route" in str(payload["reason"])


async def test_a_tool_that_spends_nothing_never_meets_the_gate() -> None:
    """No cap, and a tool that says ``None``: nothing changes for the tools that cost nothing."""
    w = a_world(cap=None, bound=None)
    task, step = await w.running(ECHO.id, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is not TaskState.DENIED
    started, _ = await w.results.for_step(task.id, step.id)
    assert started.worst_case is None


# --------------------------------------------------------------------------------------
# Before a question: what it costs, and no question a yes could not make pass
# --------------------------------------------------------------------------------------


async def test_the_question_names_the_worst_case_and_what_the_month_has_left() -> None:
    """Decision H: the parts of the question, which every surface shows."""
    w = a_world(cap=Decimal(5))
    task, step = await w.running(NOTE.id, requires_authorization=True, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.approval is not None
    asked = execution.approval.metadata[ASKED]
    assert asked["worst_case"] == "0.25 USD, m, up to 900 tokens in and 100 out"  # type: ignore[index]
    assert asked["left"] == f"5 of 5 USD left in {month_of(w.now).label}"  # type: ignore[index]
    assert "USD" not in execution.approval.prompt, "the money is not in the audit of the question"


async def test_a_question_a_yes_could_not_make_pass_is_not_asked() -> None:
    """Review decision 7: denied before the question, and nobody is asked or woken."""
    w = a_world(cap=None)
    task, step = await w.running(NOTE.id, requires_authorization=True, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.DENIED
    assert execution.approval is None
    assert await w.approvals.for_task(task.id) == ()
    assert E.APPROVAL_REQUESTED not in await w.event_types(task.id)


async def test_a_yes_does_not_raise_the_cap() -> None:
    """Decision G: the numbers of the question are the moment's; the gate reads the month again
    after the yes, and a margin taken in between denies the call."""
    w = a_world(cap=Decimal("0.3"))
    task, step = await w.running(NOTE.id, requires_authorization=True, conditions=(OK,))
    asked = await w.execute(task.id, step.id)
    assert asked.approval is not None
    await w.results.add(open_reservation(w))  # another call takes the margin
    await w.engine.approve(task.id, await w.answered(asked.approval))
    await w.engine.start(task.id)

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.DENIED
    assert w.tool(NOTE.id).calls == ()
    assert (await payload_of_the_denial(w, task.id))["code"] == SpendingCode.OVER_CAP.value


# --------------------------------------------------------------------------------------
# At a node's claim: the Core decides before it sends (decision B)
# --------------------------------------------------------------------------------------


async def handed(w: World) -> tuple[object, object, object]:
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, conditions=(OK,), max_privacy=PrivacyLevel.TRUSTED)
    run = await w.runner.run(task.id)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    return step, remote, stand.assignment


async def test_the_claim_carries_the_reservation_to_the_node() -> None:
    w = a_world(cap=Decimal(5))
    step, remote, assignment = await handed(w)

    claimed = await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    assert claimed.worst_case == BOUND
    (record,) = await w.results.for_step(assignment.task_id, step.id)  # type: ignore[attr-defined]
    assert record.status is ExecutionStatus.STARTED and record.worst_case == BOUND


async def test_a_claim_the_month_cannot_let_out_withdraws_the_offer_and_sends_nothing() -> None:
    w = a_world(cap=None)
    step, remote, assignment = await handed(w)

    with pytest.raises(AssignmentStateError) as refused:
        await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    assert refused.value.state.value == "WITHDRAWN"
    task_id = assignment.task_id  # type: ignore[attr-defined]
    assert (await w.task(task_id)).state is TaskState.DENIED
    assert await w.results.for_step(task_id, step.id) == ()  # type: ignore[attr-defined]
    held = await w.assignments.held(assignment.id)  # type: ignore[attr-defined]
    assert held.state.value == "WITHDRAWN"
    assert (await payload_of_the_denial(w, task_id))["code"] == SpendingCode.NO_CAP.value


class LostTheRace(FakeExecutionResultStore):
    """A store where another call takes the whole margin between the look and the reservation:
    the window ``foresee`` cannot close, and ``reserve`` does."""

    def __init__(self, rival: Callable[[], ExecutionResult]) -> None:
        super().__init__()
        self._rival = rival

    async def reserve(
        self,
        record: ExecutionResult,
        since: datetime,
        until: datetime,
        admits: Callable[[tuple[ExecutionResult, ...]], bool],
    ) -> bool:
        await self.add(self._rival())
        return await super().reserve(record, since, until, admits)


def racing(cap: Decimal) -> World:
    holder: list[World] = []
    store = LostTheRace(lambda: open_reservation(holder[0], cap))
    holder.append(a_world(cap=cap, results=store))
    return holder[0]


async def test_a_claim_that_loses_the_margin_after_the_look_sends_no_order() -> None:
    """The window between ``foresee`` and the reservation: the task is denied, no STARTED record is
    written, and the node is told the work is not to be had — the claim lapses with nothing done."""
    w = racing(Decimal(5))
    step, remote, assignment = await handed(w)

    with pytest.raises(AssignmentStateError) as refused:
        await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]

    assert refused.value.state.value == "CLAIMED"
    task_id = assignment.task_id  # type: ignore[attr-defined]
    assert (await w.task(task_id)).state is TaskState.DENIED
    assert await w.results.for_step(task_id, step.id) == ()  # type: ignore[attr-defined]
    assert await w.step_state(task_id, step.id) is StepState.CANCELLED  # type: ignore[attr-defined]


async def test_a_local_call_that_loses_the_margin_is_denied_too() -> None:
    w = racing(Decimal(5))
    task, step = await w.running(ECHO.id, conditions=(OK,))

    execution = await w.execute(task.id, step.id)

    assert execution.task.state is TaskState.DENIED
    assert (await payload_of_the_denial(w, task.id))["code"] == SpendingCode.OVER_CAP.value


async def test_a_claim_that_lapses_with_its_call_unknown_stays_at_the_worst_case() -> None:
    """The silent node of ADR 0040: the step closes ``execution.interrupted``, nothing says whether
    the call left, and the month keeps the reservation at its worst case until it turns
    (decision 14)."""
    w = a_world(cap=Decimal(5))
    step, remote, assignment = await handed(w)
    await w.executor.begin(assignment.id, remote.id)  # type: ignore[attr-defined]
    w.clock.advance(timedelta(seconds=121))
    await w.alive()

    run = await w.runner.run(assignment.task_id)  # type: ignore[attr-defined]

    assert run.outcome is RunOutcome.FAILED
    _, held = await SpendingGate(w.results, Decimal(5)).ledger(w.now)
    assert (held.spent, held.reserved, held.open) == (Decimal(0), BOUND.amount, 1)
