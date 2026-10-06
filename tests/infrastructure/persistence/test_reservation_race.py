"""The reservation of the spending cap on a real database (M14.1, ADR 0057; criterion 5).

**Two calls in parallel do not pass on the same margin** (decision C). A race is not proved with
two coroutines on one loop, which alternate only at an ``await`` (``test_assignment_claim_race``):
it is proved here with two real connections on one file, held at a barrier in front of the
``BEGIN IMMEDIATE`` so that both are at the door at once and the database decides — and with a
reservation written naively, read then write, which the same proof lets through twice.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from ela.domain import ExecutionId, ExecutionResult, Ledger, StepId, WorstCase
from ela.executive.spending import ledger
from ela.infrastructure.persistence import SqlExecutionResultStore, make_engine
from tests.contracts.test_execution_result_store import STARTED
from tests.infrastructure.persistence.concurrency import Meeting
from tests.infrastructure.persistence.conftest import create_schema

AMOUNT = Decimal("0.6")
BOUND = WorstCase(amount=AMOUNT, currency="USD", model="m", input_tokens=900, output_tokens=100)
CAP = Decimal("1")
"""Room for one of the two reservations of :data:`BOUND`, and not for both."""
SINCE = datetime(2026, 9, 1, tzinfo=UTC)
UNTIL = datetime(2026, 10, 1, tzinfo=UTC)


def reservation(number: int) -> ExecutionResult:
    """A reservation of :data:`BOUND` on its own step."""
    return STARTED.model_copy(
        update={
            "id": ExecutionId(UUID(f"00000000-0000-4000-8000-0000000007{number:02d}")),
            "step_id": StepId(UUID(f"00000000-0000-4000-8000-0000000008{number:02d}")),
            "worst_case": BOUND,
        }
    )


def admits(rows: tuple[ExecutionResult, ...]) -> bool:
    held: Ledger = ledger(rows)
    return held.spent + held.reserved + AMOUNT <= CAP


class NaiveExecutionResultStore(SqlExecutionResultStore):
    """Read, decide, write — in two transactions: the reservation this file exists to refuse."""

    async def reserve(
        self,
        record: ExecutionResult,
        since: datetime,
        until: datetime,
        admits: Callable[[tuple[ExecutionResult, ...]], bool],
    ) -> bool:
        if not admits(await self.spending(since, until)):
            return False
        await self.add(record)
        return True


async def _reserve_twice(
    file_url: str, kind: type[SqlExecutionResultStore], prefix: str
) -> list[bool]:
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        meeting = Meeting(prefix)
        meeting.attend(first)
        meeting.attend(second)
        outcomes = await asyncio.gather(
            kind(first).reserve(reservation(1), SINCE, UNTIL, admits),
            kind(second).reserve(reservation(2), SINCE, UNTIL, admits),
        )
        return sorted(outcomes)
    finally:
        await first.dispose()
        await second.dispose()


async def test_two_reservations_on_one_margin_write_one(file_url: str) -> None:
    assert await _reserve_twice(file_url, SqlExecutionResultStore, "BEGIN IMMEDIATE") == [
        False,
        True,
    ]


async def test_the_naive_reservation_writes_both(file_url: str) -> None:
    """The negative case: both read an empty month before either writes, and both pass."""
    assert await _reserve_twice(file_url, NaiveExecutionResultStore, "INSERT INTO execution") == [
        True,
        True,
    ]
