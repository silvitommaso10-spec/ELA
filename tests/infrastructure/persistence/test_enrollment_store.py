"""``SqlEnrollmentStore``: what only a real database can show (M12.1 criterion 3).

The behaviour of the port is under contract in ``tests/contracts/test_enrollment_store.py``, on
the fake and on this adapter in memory. What is here needs a file — two real connections — or the
statements themselves.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine

from ela.domain import DeviceId, Enrollment
from ela.infrastructure.persistence import SqlEnrollmentStore, make_engine
from ela.ports import EnrollmentConsumedError
from tests.domain.examples import LATER, WAITING_ENROLLMENT
from tests.infrastructure.persistence.concurrency import Meeting
from tests.infrastructure.persistence.conftest import Recorder, create_schema

Attach = Callable[[AsyncEngine], Recorder]
NODE = DeviceId(UUID("00000000-0000-4000-8000-000000000401"))
OTHER_NODE = DeviceId(UUID("00000000-0000-4000-8000-000000000402"))
SPEND = "UPDATE enrollments"


async def test_two_nodes_presenting_one_code_let_exactly_one_be_born(file_url: str) -> None:
    """Criterion 3: two connections, a barrier before the write, exactly one ``rowcount`` of one.

    *Fails if* the consumption were not conditional: an ``UPDATE`` on the hash alone matches the
    row on both connections, both ``rowcount`` values are one, and two nodes are born of one code.
    """
    first, second = make_engine(file_url), make_engine(file_url)
    try:
        await create_schema(first)
        await SqlEnrollmentStore(first).offer(WAITING_ENROLLMENT)
        meeting = Meeting(SPEND)
        meeting.attend(first)
        meeting.attend(second)
        outcomes = await asyncio.gather(
            SqlEnrollmentStore(first).consume(
                WAITING_ENROLLMENT.code_hash, device_id=NODE, now=LATER
            ),
            SqlEnrollmentStore(second).consume(
                WAITING_ENROLLMENT.code_hash, device_id=OTHER_NODE, now=LATER
            ),
            return_exceptions=True,
        )
        assert sorted(meeting.rowcounts) == [0, 1]
        born = [outcome for outcome in outcomes if isinstance(outcome, Enrollment)]
        refused = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        assert len(born) == 1
        assert len(refused) == 1
        assert isinstance(refused[0], EnrollmentConsumedError)
        assert refused[0].device_id == born[0].device_id
    finally:
        await first.dispose()
        await second.dispose()


async def test_a_code_is_spent_by_one_conditional_update(
    engine: AsyncEngine, statements: Attach
) -> None:
    """The check and the write are one statement, and no read comes before it (ADR 0012 §5)."""
    store = SqlEnrollmentStore(engine)
    await store.offer(WAITING_ENROLLMENT)
    recorded = statements(engine)
    await store.consume(WAITING_ENROLLMENT.code_hash, device_id=NODE, now=LATER)
    seen = recorded()
    spends = [statement for statement in seen if statement.startswith(SPEND)]
    assert len(spends) == 1
    for clause in ("code_hash = ?", "consumed_at IS NULL", "expires_at > ?"):
        assert clause in spends[0], clause
    assert not any(statement.startswith("SELECT") for statement in seen[: seen.index(spends[0])])
