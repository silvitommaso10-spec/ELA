"""``SqlAssignmentStore``: what only a real database can show (M12.2 criterion 15; ADR 0038).

The port is under contract in ``tests/contracts/test_assignment_store.py``, on the fake and on
this adapter in memory. **A race of the claim is not proved with two coroutines**: in one event
loop they alternate only at an ``await``, and a proof of that kind would pass with a naive claim
too. It is proved here with two real connections on one file and a barrier in front of the write,
asserting on the ``rowcount`` — and with a claim written naively, read then write, which the same
proof lets win twice: the test shows it can fail.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import Assignment, AssignmentId, AssignmentState, DeviceId
from ela.infrastructure.persistence import SqlAssignmentStore, make_engine, make_session_factory
from ela.infrastructure.persistence.orm import AssignmentRow
from ela.ports import AssignmentNodeBusyError, AssignmentStateError
from tests.contracts.test_assignment_store import DUE, NODE, OFFER, TAKEN, offer_for
from tests.domain.examples import LATER
from tests.infrastructure.persistence.concurrency import Meeting
from tests.infrastructure.persistence.conftest import Recorder, create_schema

Attach = Callable[[AsyncEngine], Recorder]
WRITE = "UPDATE assignments"


class NaiveAssignmentStore(SqlAssignmentStore):
    """Read, decide, write: the claim this file exists to refuse — the negative case.

    It reads the row in one transaction, checks in Python, and writes in another with an
    ``UPDATE`` on the id alone. Both connections can read ``OFFERED`` before either writes.
    """

    async def claim(
        self,
        assignment_id: AssignmentId,
        *,
        device_id: DeviceId,
        now: datetime,
        expires_at: datetime,
    ) -> Assignment:
        held = await self.get(assignment_id)
        if held.state is not AssignmentState.OFFERED:
            raise AssignmentStateError(assignment_id, held.state)
        async with make_session_factory(self.engine)() as session, session.begin():
            await session.execute(
                update(AssignmentRow)
                .where(AssignmentRow.id == assignment_id)
                .values(state=AssignmentState.CLAIMED.value, claimed_at=now, expires_at=expires_at)
                .execution_options(synchronize_session=False)
            )
        return await self.get(assignment_id)


async def _claim_twice(
    file_url: str,
    kind: type[SqlAssignmentStore],
    first_offer: Assignment,
    second_offer: Assignment,
) -> tuple[list[int], list[object]]:
    """Two connections claim for :data:`NODE`, held at the barrier in front of the write."""
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        await SqlAssignmentStore(first).add(first_offer)
        if second_offer.id != first_offer.id:
            await SqlAssignmentStore(first).add(second_offer)
        meeting = Meeting(WRITE)
        meeting.attend(first)
        meeting.attend(second)
        outcomes = await asyncio.gather(
            kind(first).claim(first_offer.id, device_id=NODE, now=TAKEN, expires_at=DUE),
            kind(second).claim(second_offer.id, device_id=NODE, now=TAKEN, expires_at=DUE),
            return_exceptions=True,
        )
        return sorted(meeting.rowcounts), list(outcomes)
    finally:
        await first.dispose()
        await second.dispose()


async def test_two_claims_of_one_assignment_hand_it_out_once(file_url: str) -> None:
    """Criterion 15: two processes with one node's identity take the same offer at once.

    *Fails if* the claim were not one conditional statement: see the naive store below.
    """
    rowcounts, outcomes = await _claim_twice(file_url, SqlAssignmentStore, OFFER, OFFER)

    assert rowcounts == [0, 1]
    assert [type(outcome) for outcome in outcomes].count(Assignment) == 1
    refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert [type(outcome) for outcome in refused] == [AssignmentStateError]


async def test_the_naive_claim_hands_one_assignment_out_twice(file_url: str) -> None:
    """The negative case, on the same barrier: read, then write, and both writers win. The proof
    above is a proof because this one fails it."""
    rowcounts, outcomes = await _claim_twice(file_url, NaiveAssignmentStore, OFFER, OFFER)

    assert rowcounts == [1, 1]
    assert all(isinstance(outcome, Assignment) for outcome in outcomes)


async def test_two_claims_of_one_node_leave_it_one_piece_of_work(file_url: str) -> None:
    """M12.1, D16 on a real database: the ``NOT EXISTS`` is inside the ``UPDATE``, so two claims of
    one node on two offers cannot both see "no live claim" (SQLite's single writer, declared)."""
    rowcounts, outcomes = await _claim_twice(file_url, SqlAssignmentStore, OFFER, offer_for(2))

    assert rowcounts == [0, 1]
    refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
    assert [type(outcome) for outcome in refused] == [AssignmentNodeBusyError]


async def test_two_expiries_of_one_assignment_write_it_once(file_url: str) -> None:
    """The concurrency window of ADR 0038: two ``lapse`` from two processes on one database. The
    conditional ``UPDATE`` gives the expiry to one; the other reads it back, already expired."""
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        await SqlAssignmentStore(first).add(OFFER)
        meeting = Meeting(WRITE)
        meeting.attend(first)
        meeting.attend(second)
        expired = await asyncio.gather(
            SqlAssignmentStore(first).expire(OFFER.id, now=LATER),
            SqlAssignmentStore(second).expire(OFFER.id, now=LATER),
        )
        assert sorted(meeting.rowcounts) == [0, 1]
        assert expired[0] == expired[1]
        assert expired[0].state is AssignmentState.EXPIRED
    finally:
        await first.dispose()
        await second.dispose()


async def test_a_claim_is_one_conditional_update(engine: AsyncEngine, statements: Attach) -> None:
    """The check and the write are one statement, and no read comes before it (ADR 0012 §5)."""
    store = SqlAssignmentStore(engine)
    await store.add(OFFER)
    recorded = statements(engine)
    await store.claim(OFFER.id, device_id=NODE, now=TAKEN, expires_at=DUE)
    seen = recorded()
    writes = [statement for statement in seen if statement.startswith(WRITE)]

    assert len(writes) == 1
    for clause in ("state = ?", "expires_at > ?", "NOT (EXISTS (SELECT"):
        assert clause in writes[0], clause
    assert not any(statement.startswith("SELECT") for statement in seen[: seen.index(writes[0])])
