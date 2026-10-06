"""``GET /spend``: what the month spent and holds, read with the gate's own function (M14.1).

Decision I: **what Tommaso reads is what the gate compares**. The route does not sum anything: it
asks :meth:`~ela.executive.spending.SpendingGate.ledger`, the method :meth:`foresee` and the
reservation judge with, and the proof is that a ledger put in that method's place is what both
the route and the gate see. The amounts are strings, exact: a fraction of a cent is shown.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from ela.domain import (
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    Ledger,
    ProviderUsage,
    WorstCase,
)
from ela.executive.spending import CAP_VARIABLE, Foresight, Month, Refusal, month_of
from ela.ports import STARTED_ID
from ela.tools.model import MODEL_COMPLETE
from tests.api.reasons import World, opened

WORST = WorstCase(
    amount=Decimal("1.26"), currency="USD", model="m", input_tokens=900, output_tokens=100
)


async def test_without_a_cap_it_says_so_and_names_the_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with opened(monkeypatch, tmp_path) as w:
        body = (await w.client.get("/spend")).json()

    month = month_of(datetime.now(UTC))
    assert body == {
        "month": month.label,
        "resets_at": month.until.isoformat().replace("+00:00", "Z"),
        "cap": None,
        "cap_setting": CAP_VARIABLE,
        "currency": "USD",
        "spent": "0",
        "reserved": "0",
        "open": 0,
        "unknown": 0,
        "left": None,
    }


async def test_it_reads_the_rows_of_the_month_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A call closed with its cost, one in flight, and one reserved in the last microsecond of the
    month before: that one is not here (decision F: the month of its ``STARTED``)."""
    async with opened(monkeypatch, tmp_path, **{CAP_VARIABLE: "5"}) as w:
        now = w.ela.clock.now()
        before = month_of(now).since - timedelta(microseconds=1)
        paid = started(w, now, Decimal("0.3"))
        for row in (paid, started(w, now, Decimal("0.2")), started(w, before, Decimal(4))):
            await w.ela.results.add(row)
        await w.ela.results.add(closed(w, now, paid, Decimal("0.0042")))

        body = (await w.client.get("/spend")).json()

    assert (body["spent"], body["reserved"], body["open"], body["unknown"]) == (
        "0.0042",
        "0.2",
        1,
        0,
    )
    assert (body["cap"], body["left"]) == ("5", "4.7958")


async def test_the_route_and_the_gate_read_one_function(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Put a ledger in the gate's method: the route prints it, and the gate judges on it — so
    ``left`` below a call's worst case is exactly a call the gate refuses."""
    held = Ledger(spent=Decimal("1.5"), reserved=Decimal("2.25"), open=3, unknown=1)
    async with opened(monkeypatch, tmp_path, **{CAP_VARIABLE: "5"}) as w:
        gate = w.ela.spending

        async def planted(now: datetime) -> tuple[Month, Ledger]:
            return month_of(now), held

        monkeypatch.setattr(gate, "ledger", planted)
        body = (await w.client.get("/spend")).json()
        refused = await gate.foresee(WORST, w.ela.clock.now())
        cleared = await gate.foresee(
            WORST.model_copy(update={"amount": Decimal("1.25")}), w.ela.clock.now()
        )

    assert (body["spent"], body["reserved"], body["open"], body["unknown"], body["left"]) == (
        "1.5",
        "2.25",
        3,
        1,
        "1.25",
    )
    assert isinstance(refused, Refusal) and refused.code.value == "spending.over_cap"
    assert isinstance(cleared, Foresight) and cleared.left == Decimal("1.25")


def started(w: World, at: datetime, amount: Decimal) -> ExecutionResult:
    return ExecutionResult(
        id=ExecutionId(w.ela.ids.new_uuid()),
        created_at=at,
        capability_id=MODEL_COMPLETE,
        status=ExecutionStatus.STARTED,
        worst_case=WORST.model_copy(update={"amount": amount}),
    )


def closed(w: World, at: datetime, reservation: ExecutionResult, cost: Decimal) -> ExecutionResult:
    return ExecutionResult(
        id=ExecutionId(w.ela.ids.new_uuid()),
        created_at=at,
        capability_id=MODEL_COMPLETE,
        status=ExecutionStatus.SUCCEEDED,
        usage=ProviderUsage(input_tokens=10, output_tokens=5, cost=cost, currency="USD"),
        metadata={STARTED_ID: str(reservation.id)},
    )
