"""The spending cap's own rules (M14.1, ADR 0057): the UTC month, the ledger, the verdict, the gate.

Every branch of the ledger is a row of decision 14 of the review — not sent, sent with a cost,
sent without one, and the fact missing —, and every refusal names the line of the ``.env``
(decisions B and G). The executor's use of the gate is in ``test_spending_gate.py``; the race of
two reservations on a real database in ``tests/infrastructure/persistence/``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from ela.domain import (
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    Ledger,
    ProviderUsage,
    StepId,
    WorstCase,
)
from ela.executive.spending import (
    CAP_VARIABLE,
    Cleared,
    Foresight,
    Month,
    Refusal,
    SpendingCode,
    SpendingGate,
    dollars,
    judge,
    ledger,
    month_of,
)
from ela.ports import STARTED_ID
from ela.testing.fakes import FakeExecutionResultStore
from tests.contracts.test_execution_result_store import OTHER, STARTED

BOUND = WorstCase(
    amount=Decimal("0.25"), currency="USD", model="m", input_tokens=900, output_tokens=100
)
OCTOBER = month_of(datetime(2026, 10, 6, 12, tzinfo=UTC))


def reserved(number: int, *, bound: WorstCase = BOUND) -> ExecutionResult:
    return STARTED.model_copy(
        update={
            "id": ExecutionId(UUID(f"00000000-0000-4000-8000-0000000009{number:02d}")),
            "step_id": StepId(UUID(f"00000000-0000-4000-8000-0000000010{number:02d}")),
            "worst_case": bound,
        }
    )


def closing(
    reservation: ExecutionResult, usage: ProviderUsage | None, number: int
) -> ExecutionResult:
    return OTHER.model_copy(
        update={
            "id": ExecutionId(UUID(f"00000000-0000-4000-8000-0000000011{number:02d}")),
            "step_id": reservation.step_id,
            "usage": usage,
            "metadata": {STARTED_ID: str(reservation.id)},
        }
    )


def usage(*, sent: bool = True, cost: Decimal | None = None) -> ProviderUsage:
    return ProviderUsage(input_tokens=10, output_tokens=5, cost=cost, sent=sent)


# --------------------------------------------------------------------------------------
# The month: calendar, UTC
# --------------------------------------------------------------------------------------


def test_the_month_is_the_calendar_month_in_utc() -> None:
    month = month_of(datetime(2026, 10, 6, 12, tzinfo=UTC))
    assert month == Month(datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC))
    assert month.label == "2026-10"


def test_december_ends_in_january() -> None:
    month = month_of(datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC))
    assert (month.since, month.until) == (
        datetime(2026, 12, 1, tzinfo=UTC),
        datetime(2027, 1, 1, tzinfo=UTC),
    )


def test_an_instant_in_another_zone_is_read_in_utc() -> None:
    """00:30 on the first in Rome is still the last day of the month before, in UTC."""
    rome = timezone(timedelta(hours=2))
    assert month_of(datetime(2026, 11, 1, 0, 30, tzinfo=rome)).label == "2026-10"


def test_the_last_instant_and_the_first_belong_to_two_months() -> None:
    last = datetime(2026, 10, 31, 23, 59, 59, 999_999, tzinfo=UTC)
    assert month_of(last).label == "2026-10"
    assert month_of(last + timedelta(microseconds=1)).label == "2026-11"


# --------------------------------------------------------------------------------------
# The ledger: a fact per closing row, never a list of codes (review decision 14)
# --------------------------------------------------------------------------------------


def test_an_empty_month_is_an_empty_ledger() -> None:
    assert ledger(()) == Ledger(spent=Decimal(0), reserved=Decimal(0))


def test_a_reservation_nothing_closed_holds_its_worst_case() -> None:
    """In flight, interrupted, a claim that lapsed: the fail-safe on an unknown outcome."""
    assert ledger([reserved(1)]) == Ledger(spent=0, reserved=Decimal("0.25"), open=1)


def test_a_call_that_was_not_sent_costs_nothing() -> None:
    first = reserved(1)
    assert ledger([first, closing(first, usage(sent=False), 1)]) == Ledger()


def test_a_call_sent_with_a_cost_costs_the_cost() -> None:
    first = reserved(1)
    held = ledger([first, closing(first, usage(cost=Decimal("0.0021")), 1)])
    assert held == Ledger(spent=Decimal("0.0021"), reserved=Decimal(0))


def test_a_call_sent_without_a_cost_keeps_its_worst_case() -> None:
    first = reserved(1)
    held = ledger([first, closing(first, usage(cost=None), 1)])
    assert held == Ledger(spent=0, reserved=Decimal("0.25"), unknown=1)


def test_where_the_fact_is_missing_the_call_counts_as_sent() -> None:
    """An outcome with no usage — a tool that raised, a result that was not text — says nothing
    about the request: it counts as sent, without a cost."""
    first = reserved(1)
    held = ledger([first, closing(first, None, 1)])
    assert held == Ledger(spent=0, reserved=Decimal("0.25"), unknown=1)


def test_a_cost_of_zero_is_a_cost() -> None:
    """A request the API turned down cost nothing, and said so: zero, spent."""
    first = reserved(1)
    assert ledger([first, closing(first, usage(cost=Decimal(0)), 1)]) == Ledger()


def test_the_ledger_sums_every_kind_at_once() -> None:
    rows = [reserved(n) for n in range(1, 5)]
    rows += [
        closing(rows[0], usage(cost=Decimal("0.01")), 1),
        closing(rows[1], usage(sent=False), 2),
        closing(rows[2], usage(cost=None), 3),
    ]
    assert ledger(rows) == Ledger(
        spent=Decimal("0.01"), reserved=Decimal("0.50"), open=1, unknown=1
    )


def test_a_started_record_with_no_reservation_and_a_stray_outcome_count_for_nothing() -> None:
    stray = OTHER.model_copy(update={"metadata": {STARTED_ID: "elsewhere"}})
    assert ledger([STARTED, stray, OTHER]) == Ledger()


def test_the_same_rows_give_the_same_ledger() -> None:
    """Never a counter: reading twice changes nothing."""
    first = reserved(1)
    rows = [first, closing(first, usage(cost=Decimal("0.2")), 1), reserved(2)]
    assert ledger(rows) == ledger(rows) == ledger(reversed(rows))


# --------------------------------------------------------------------------------------
# The verdict: a cap, a bound, a price, room — and every sentence names the line
# --------------------------------------------------------------------------------------


def test_without_a_cap_nothing_that_spends_goes_out() -> None:
    refused = judge(cap=None, worst=BOUND, month=OCTOBER, held=Ledger())
    assert isinstance(refused, Refusal) and refused.code is SpendingCode.NO_CAP
    assert refused.reason == f"no monthly cap: {CAP_VARIABLE} in the Core's .env sets it, in USD"


def test_a_call_that_cannot_be_bounded_is_not_made() -> None:
    error = ErrorMetadata(code="routing.unknown_task_type", message="no route for 'x'")
    refused = judge(cap=Decimal(5), worst=error, month=OCTOBER)
    assert isinstance(refused, Refusal) and refused.code is SpendingCode.UNBOUNDED
    assert (
        refused.reason == "this call cannot be bounded: routing.unknown_task_type: no route for 'x'"
    )
    bare = judge(cap=Decimal(5), worst=ErrorMetadata(code="x", message=""), month=OCTOBER)
    assert isinstance(bare, Refusal) and bare.reason == "this call cannot be bounded: x"


def test_a_model_with_no_price_is_not_called_with_a_cap() -> None:
    """``None`` is not ``0`` (decision D)."""
    unpriced = BOUND.model_copy(update={"amount": None, "currency": None, "model": "gpt-4"})
    refused = judge(cap=Decimal(5), worst=unpriced, month=OCTOBER)
    assert isinstance(refused, Refusal) and refused.code is SpendingCode.UNPRICED
    assert refused.reason == (
        "gpt-4 has no price in ELA's table: a call whose cost cannot be bounded is not made "
        f"({CAP_VARIABLE})"
    )


def test_a_call_that_would_cross_the_cap_says_the_four_numbers() -> None:
    held = Ledger(spent=Decimal("4.5"), reserved=Decimal("0.3"))
    refused = judge(cap=Decimal(5), worst=BOUND, month=OCTOBER, held=held)
    assert isinstance(refused, Refusal) and refused.code is SpendingCode.OVER_CAP
    assert refused.reason == (
        "the monthly cap would be crossed: spent 4.5 + reserved 0.3 + this call's worst case "
        f"0.25 > cap 5 USD ({CAP_VARIABLE}, 2026-10)"
    )
    assert refused.payload == {
        "code": "spending.over_cap",
        "month": "2026-10",
        "cap": "5",
        "spent": "4.5",
        "reserved": "0.3",
        "worst_case": "0.25",
        "currency": "USD",
    }


def test_a_call_that_reaches_the_cap_exactly_goes_out() -> None:
    held = Ledger(spent=Decimal("4.5"), reserved=Decimal("0.25"))
    assert isinstance(judge(cap=Decimal(5), worst=BOUND, month=OCTOBER, held=held), Cleared)


def test_a_cap_of_zero_lets_nothing_out() -> None:
    refused = judge(cap=Decimal(0), worst=BOUND, month=OCTOBER, held=Ledger())
    assert isinstance(refused, Refusal) and refused.code is SpendingCode.OVER_CAP


def test_the_payload_of_a_refusal_without_numbers() -> None:
    refused = judge(cap=None, worst=ErrorMetadata(code="x", message="y"), month=OCTOBER)
    assert isinstance(refused, Refusal)
    assert refused.payload == {
        "code": "spending.no_cap",
        "month": "2026-10",
        "cap": None,
        "spent": None,
        "reserved": None,
        "worst_case": None,
        "currency": "USD",
    }


@pytest.mark.parametrize(
    ("amount", "printed"),
    [
        (Decimal("4.06553600"), "4.065536"),
        (Decimal("45.00"), "45"),
        (Decimal("0.00000000"), "0"),
        (Decimal("0.00000001"), "0.00000001"),
    ],
)
def test_dollars_are_printed_as_they_are(amount: Decimal, printed: str) -> None:
    """A fraction of a cent is printed, never rounded away (ADR 0020 §6)."""
    assert dollars(amount) == printed


# --------------------------------------------------------------------------------------
# The gate: foresee before a question, reserve where the STARTED record is born
# --------------------------------------------------------------------------------------

NOW = datetime(2026, 9, 4, 11, 0, tzinfo=UTC)
"""The day of :data:`~tests.domain.examples.LATER`, when the example rows were created."""


async def test_the_gate_reads_the_ledger_of_the_month_of_now() -> None:
    results = FakeExecutionResultStore()
    await results.add(reserved(1))
    gate = SpendingGate(results, Decimal(5))

    month, held = await gate.ledger(NOW)

    assert month.label == "2026-09"
    assert held == Ledger(spent=0, reserved=Decimal("0.25"), open=1)
    assert gate.cap == Decimal(5)
    assert (await gate.ledger(NOW + timedelta(days=30)))[1] == Ledger(), "October is empty"


async def test_foresee_says_what_is_left_before_the_call() -> None:
    results = FakeExecutionResultStore()
    await results.add(reserved(1))

    seen = await SpendingGate(results, Decimal(5)).foresee(BOUND, NOW)

    assert seen == Foresight(worst=BOUND, left=Decimal("4.75"), cap=Decimal(5), month=month_of(NOW))


async def test_foresee_refuses_what_a_yes_could_not_let_out() -> None:
    results = FakeExecutionResultStore()
    await results.add(reserved(1))

    seen = await SpendingGate(results, Decimal("0.4")).foresee(BOUND, NOW)

    assert isinstance(seen, Refusal) and seen.code is SpendingCode.OVER_CAP


async def test_reserve_writes_the_started_record_with_its_worst_case() -> None:
    results = FakeExecutionResultStore()
    record = STARTED

    refused = await SpendingGate(results, Decimal(5)).reserve(record, BOUND)

    assert refused is None
    assert (await results.get(record.id)).worst_case == BOUND


async def test_reserve_writes_nothing_over_the_cap_and_says_why() -> None:
    results = FakeExecutionResultStore()
    await results.add(reserved(1))

    refused = await SpendingGate(results, Decimal("0.4")).reserve(STARTED, BOUND)

    assert isinstance(refused, Refusal) and refused.code is SpendingCode.OVER_CAP
    assert refused.ledger == Ledger(spent=0, reserved=Decimal("0.25"), open=1)
    assert [row.id for row in await results.for_task(STARTED.task_id)] == [reserved(1).id]  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cap", "worst", "code"),
    [
        (None, BOUND, SpendingCode.NO_CAP),
        (Decimal(5), ErrorMetadata(code="x", message="y"), SpendingCode.UNBOUNDED),
        (Decimal(5), BOUND.model_copy(update={"amount": None}), SpendingCode.UNPRICED),
    ],
)
async def test_reserve_refuses_before_reading_anything(
    cap: Decimal | None, worst: WorstCase | ErrorMetadata, code: SpendingCode
) -> None:
    results = FakeExecutionResultStore()

    refused = await SpendingGate(results, cap).reserve(STARTED, worst)

    assert isinstance(refused, Refusal) and refused.code is code
    assert await results.spending(month_of(NOW).since, month_of(NOW).until) == ()
    assert STARTED.status is ExecutionStatus.STARTED
