"""What the month has spent under the cap, read with the gate's own function (M14.1, ADR 0057).

One route, read-only. **What Tommaso reads is what the gate compares** (decision I): the numbers
come from :meth:`~ela.executive.spending.SpendingGate.ledger`, the function the gate judges with,
on the rows of the same month — never from a second sum kept somewhere for display. The amounts
travel as the strings :func:`~ela.executive.spending.dollars` writes, exact and without rounding:
a fraction of a cent is shown, never rounded to zero.
"""

from __future__ import annotations

from fastapi import APIRouter

from ela.api.deps import ElaDep
from ela.api.schemas import SpendOut
from ela.executive.spending import CAP_VARIABLE, CURRENCY, dollars

__all__ = ["router"]

router = APIRouter(tags=["spend"])


@router.get("/spend")
async def spend(ela: ElaDep) -> SpendOut:
    """The month (calendar, UTC), when it resets, the cap and the line that sets it, what was
    spent, what is held reserved, and what is left — ``None`` without a cap, which lets nothing
    out."""
    month, held = await ela.spending.ledger(ela.clock.now())
    cap = ela.spending.cap
    return SpendOut(
        month=month.label,
        resets_at=month.until,
        cap=None if cap is None else dollars(cap),
        cap_setting=CAP_VARIABLE,
        currency=CURRENCY,
        spent=dollars(held.spent),
        reserved=dollars(held.reserved),
        open=held.open,
        unknown=held.unknown,
        left=None if cap is None else dollars(cap - held.spent - held.reserved),
    )
