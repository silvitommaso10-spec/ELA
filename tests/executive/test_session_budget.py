"""The budget of a guided session (M14.3, ADR 0060; decision 5): each call weighed before it leaves.

A call goes out only if ``spent + in flight + its worst case <= the reservation``, with the worst
case on the model and the ``max_tokens`` of the request itself; it is refused before the network
for a model the router did not choose, a ``max_tokens`` over the declared one, a ``cache_control``,
tools that are not exactly the session's (decision 22) — and before the tools of the start were
checked. A call settles with what it consumed; an unknown outcome counts its worst case.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from ela.domain import ExecutionStatus, ProviderUsage, Reservation
from ela.executive.spending import (
    BudgetCode,
    BudgetRefusal,
    SessionBudget,
    SpendingGate,
    reservation_of,
)
from ela.ports import CallRequest
from ela.testing.fakes import FakeExecutionResultStore
from tests.domain.examples import STEP_ID, TASK_ID
from tests.tools.guided import started

TOOLS = frozenset({"mcp__ela__act", "mcp__ela__read"})
MODEL = "fake-model"
WORST = Decimal("0.01")


def reservation(amount: str = "0.05", output_tokens: int = 100) -> Reservation:
    found = reservation_of(started(Decimal(amount)))
    assert found is not None
    return found.model_copy(update={"output_tokens": output_tokens})


def budget(amount: str = "0.05") -> SessionBudget:
    opened = SessionBudget(reservation(amount), TOOLS)
    assert opened.start(sorted(TOOLS)) is None
    return opened


def call(**update: object) -> CallRequest:
    fields: dict[str, object] = {
        "model": MODEL,
        "max_tokens": 100,
        "tools": tuple(sorted(TOOLS)),
        "cached": False,
        "request_bytes": 400,
    }
    return CallRequest(**{**fields, **update})  # type: ignore[arg-type]


def used(cost: str | None = "0.002", *, sent: bool = True, tokens: int = 150) -> ProviderUsage:
    return ProviderUsage(
        input_tokens=tokens,
        output_tokens=20,
        cost=None if cost is None else Decimal(cost),
        sent=sent,
    )


def test_the_reservation_is_read_off_the_started_record() -> None:
    held = reservation()
    record = started(Decimal("0.05"))
    assert (held.task_id, held.step_id, held.started_id) == (TASK_ID, STEP_ID, record.id)
    assert (held.amount, held.model) == (Decimal("0.05"), MODEL)


def test_only_a_started_record_with_an_amount_is_a_reservation() -> None:
    record = started(Decimal("0.05"))
    assert reservation_of(record.model_copy(update={"worst_case": None})) is None
    unpriced = record.worst_case.model_copy(update={"amount": None})  # type: ignore[union-attr]
    assert reservation_of(record.model_copy(update={"worst_case": unpriced})) is None
    assert reservation_of(record.model_copy(update={"task_id": None})) is None
    assert reservation_of(record.model_copy(update={"step_id": None})) is None


def test_an_admitted_call_is_minted_with_its_worst_case_and_its_bytes() -> None:
    opened = budget()

    admitted = opened.admit(call(), WORST)

    assert not isinstance(admitted, BudgetRefusal)
    assert (admitted.session, admitted.call, admitted.model) == (STEP_ID, 1, MODEL)
    assert (admitted.worst, admitted.request_bytes, admitted.max_tokens) == (WORST, 400, 100)
    assert opened.flying == WORST


def test_no_call_before_the_tools_of_the_start_are_checked() -> None:
    """Decision 22: the start is checked before the first call, and a call before it is refused."""
    opened = SessionBudget(reservation(), TOOLS)

    refused = opened.admit(call(), WORST)

    assert isinstance(refused, BudgetRefusal) and refused.code is BudgetCode.UNCHECKED


@pytest.mark.parametrize(
    "tools",
    [
        ("mcp__ela__read",),
        ("mcp__ela__act", "mcp__ela__read", "Bash"),
        ("mcp__ela__read", "mcp__ela__read"),
        (),
        None,
    ],
    ids=["one-less", "one-more", "twice", "none", "no-field"],
)
def test_tools_that_are_not_exactly_the_session_s_are_refused(
    tools: tuple[str, ...] | None,
) -> None:
    """Decision 22, at every call and at the start: neither one more, nor one less, nor none."""
    opened = budget()
    refused = opened.admit(call(tools=tools), WORST)
    assert isinstance(refused, BudgetRefusal) and refused.code is BudgetCode.TOOLS

    fresh = SessionBudget(reservation(), TOOLS)
    at_the_start = fresh.start(() if tools is None else tools)
    assert at_the_start is not None and at_the_start.code is BudgetCode.TOOLS
    assert not fresh.checked


def test_exactly_the_session_s_tools_pass_in_any_order() -> None:
    opened = budget()
    assert not isinstance(
        opened.admit(call(tools=("mcp__ela__read", "mcp__ela__act")), WORST), BudgetRefusal
    )


@pytest.mark.parametrize(
    ("update", "code"),
    [
        ({"model": "claude-opus-5-5"}, BudgetCode.MODEL),
        ({"model": None}, BudgetCode.MODEL),
        ({"max_tokens": 101}, BudgetCode.MAX_TOKENS),
        ({"max_tokens": None}, BudgetCode.MAX_TOKENS),
        ({"max_tokens": 0}, BudgetCode.MAX_TOKENS),
        ({"cached": True}, BudgetCode.CACHE),
    ],
    ids=["another-model", "no-model", "more-tokens", "no-tokens", "zero-tokens", "the-cache"],
)
def test_what_the_worst_case_would_not_hold_is_refused(
    update: dict[str, object], code: BudgetCode
) -> None:
    refused = budget().admit(call(**update), WORST)
    assert isinstance(refused, BudgetRefusal) and refused.code is code


def test_a_call_with_no_price_is_refused() -> None:
    refused = budget().admit(call(), None)
    assert isinstance(refused, BudgetRefusal) and refused.code is BudgetCode.COST


def test_a_call_that_does_not_fit_beside_the_ones_in_flight_is_refused() -> None:
    """«In volo» because the session can have two requests at once (proposal 2)."""
    opened = budget("0.02")
    first, second = opened.admit(call(), WORST), opened.admit(call(), WORST)
    assert not isinstance(first, BudgetRefusal) and not isinstance(second, BudgetRefusal)

    third = opened.admit(call(), WORST)

    assert isinstance(third, BudgetRefusal) and third.code is BudgetCode.COST
    assert "in flight 0.02" in third.reason


def test_what_a_call_cost_frees_the_rest_of_its_worst_case() -> None:
    opened = budget("0.02")
    first = opened.admit(call(), WORST)
    assert not isinstance(first, BudgetRefusal)
    opened.settle(first, used("0.002"))
    second, third = opened.admit(call(), WORST), opened.admit(call(), WORST)

    assert not isinstance(second, BudgetRefusal)
    assert isinstance(third, BudgetRefusal), "0.002 + 0.01 + 0.01 > 0.02"


def test_the_session_closes_with_the_sum_and_an_unknown_call_at_its_worst_case() -> None:
    """Decision 11 (a): the cost is the sum, a call with no known outcome at its worst case."""
    opened = budget()
    known, lost, never, open_ = (opened.admit(call(), WORST) for _ in range(4))
    for admitted in (known, lost, never, open_):
        assert not isinstance(admitted, BudgetRefusal)
    opened.settle(known, used("0.002", tokens=500))  # type: ignore[arg-type]
    opened.settle(lost, None)  # type: ignore[arg-type]
    opened.settle(never, used(None, sent=False, tokens=0))  # type: ignore[arg-type]
    opened.close()

    usage = opened.usage()

    assert usage.cost == Decimal("0.002") + WORST + WORST
    assert usage.sent is True
    assert usage.request_bytes == 4 * 400
    assert (usage.input_tokens, usage.output_tokens) == (500, 40)
    assert opened.unknown == 2
    assert opened.input_minus_bytes_max == 100


def test_a_call_settled_twice_or_after_the_close_counts_once() -> None:
    opened = budget()
    admitted = opened.admit(call(), WORST)
    assert not isinstance(admitted, BudgetRefusal)
    opened.settle(admitted, used("0.002"))
    opened.settle(admitted, used("0.009"))
    opened.close()
    opened.settle(admitted, None)

    assert opened.spent == Decimal("0.002")


def test_a_session_that_called_nothing_sent_nothing_and_has_no_bytes() -> None:
    opened = budget()
    opened.close()

    usage = opened.usage()

    assert (usage.sent, usage.cost, usage.request_bytes) == (False, Decimal(0), None)
    assert opened.input_minus_bytes_max is None


async def test_the_gate_reads_the_reservation_past_the_rows_that_are_not_one() -> None:
    """The step's rows in the order they were written: a row that reserved nothing is passed over,
    and a step with none has no reservation."""
    store = FakeExecutionResultStore()
    record = started(Decimal("0.05"))
    plain = record.model_copy(
        update={"id": uuid4(), "status": ExecutionStatus.SUCCEEDED, "worst_case": None}
    )
    await store.add(plain)
    gate = SpendingGate(store, Decimal("30"))

    assert await gate.reservation(TASK_ID, STEP_ID) is None
    await store.add(record)
    found = await gate.reservation(TASK_ID, STEP_ID)
    assert found is not None and found.started_id == record.id
