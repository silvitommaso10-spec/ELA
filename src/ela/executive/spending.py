"""The spending cap of §30 on the model's key (M14.1, ADR 0057): the month, the ledger, the gate.

ELA reserves, before a call that spends, the most the call can cost, and lets it out only if
``spent + reserved + worst case <= cap``. Three rules make that number a fact and not a belief
(ADR 0029 §7):

* **The ledger is derived, never counted.** :func:`ledger` reads the rows of
  ``execution_results`` — the ``STARTED`` records that carry a worst case, and what closes them —
  every time it is asked, and nothing updates it. The reservation *is* the ``STARTED`` record of
  ADR 0021 §1, with an amount: written before the call, closed by the outcome, left open when the
  outcome is unknown.
* **It reads a fact, not codes** (review decision 14). The outcome that closes a reservation says
  whether the request left the machine (``usage.sent``) and what it cost (``usage.cost``), written
  by whoever knows: not sent costs nothing; sent with a cost costs the cost; sent without one, and
  wherever the fact is missing, the worst case stays — until the month turns.
* **The check and the reservation are one operation**, under the database's write lock
  (:meth:`~ela.ports.ExecutionResultStore.reserve`): two calls in parallel do not pass on the
  same margin.

The month is the calendar month in UTC: the documentation writes it for the organisation's
monthly cap (``00:00 UTC on the first day of the next month``) and does not write it for a
workspace's limit, so it is declared (decision F). A call counts in the month of its ``STARTED``.

The cap is one line of the Core's ``.env``, :data:`CAP_VARIABLE`, in dollars like the price list
and the console. Without it no call that spends goes out (decision B), and every refusal names
the line. A "yes" does not raise it: only the person who wrote it does, by changing it (G).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from ela.domain import ErrorMetadata, ExecutionResult, ExecutionStatus, Ledger, WorstCase
from ela.ports import STARTED_ID, ExecutionResultStore

__all__ = [
    "CAP_VARIABLE",
    "CURRENCY",
    "Cleared",
    "Foresight",
    "Month",
    "Refusal",
    "SpendingCode",
    "SpendingGate",
    "crossed",
    "dollars",
    "fits",
    "judge",
    "ledger",
    "month_of",
    "worst_said",
]

CAP_VARIABLE: Final = "ELA_SPENDING_CAP_USD"
"""The line that sets the cap. Named here once, and in every refusal: B and G want the reason to
say where the number lives."""

CURRENCY: Final = "USD"
"""The cap's currency: the price list's and the console's. A conversion would be another belief."""


class SpendingCode(StrEnum):
    """Why a call that spends was not let out: the code in the audit payload of its denial. The
    reason is the sentence; the code is for whoever reads the audit."""

    NO_CAP = "spending.no_cap"
    OVER_CAP = "spending.over_cap"
    UNPRICED = "spending.unpriced"
    UNBOUNDED = "spending.unbounded"


@dataclass(frozen=True, slots=True)
class Month:
    """One calendar month in UTC: ``[since, until)``."""

    since: datetime
    until: datetime

    @property
    def label(self) -> str:
        """``YYYY-MM``: how the month is named in a reason and in ``ela spend``."""
        return f"{self.since.year:04d}-{self.since.month:02d}"


def month_of(instant: datetime) -> Month:
    """The UTC calendar month ``instant`` falls in."""
    moment = instant.astimezone(UTC)
    since = datetime(moment.year, moment.month, 1, tzinfo=UTC)
    if moment.month == 12:
        until = datetime(moment.year + 1, 1, 1, tzinfo=UTC)
    else:
        until = datetime(moment.year, moment.month + 1, 1, tzinfo=UTC)
    return Month(since, until)


def ledger(rows: Iterable[ExecutionResult]) -> Ledger:
    """What the month spent and what it holds reserved, from the rows and nothing else.

    ``rows`` are the period's reservations and the outcomes that name them
    (:meth:`~ela.ports.ExecutionResultStore.spending`). A ``STARTED`` row without a worst case
    reserved nothing and is not counted; an outcome that names no reservation is not either.
    """
    held = list(rows)
    closing = {
        row.metadata[STARTED_ID]: row
        for row in held
        if row.status is not ExecutionStatus.STARTED and STARTED_ID in row.metadata
    }
    spent = reserved = Decimal(0)
    unclosed = unknown = 0
    for row in held:
        if row.status is not ExecutionStatus.STARTED or row.worst_case is None:
            continue
        amount = row.worst_case.amount or Decimal(0)
        outcome = closing.get(str(row.id))
        if outcome is None:
            reserved += amount
            unclosed += 1
        elif outcome.usage is not None and not outcome.usage.sent:
            continue
        elif outcome.usage is not None and outcome.usage.cost is not None:
            spent += outcome.usage.cost
        else:
            reserved += amount
            unknown += 1
    return Ledger(spent=spent, reserved=reserved, open=unclosed, unknown=unknown)


def worst_said(worst: WorstCase) -> str:
    """A worst case in one line, as a question shows it: the amount, the model, the tokens."""
    amount = "no price" if worst.amount is None else f"{dollars(worst.amount)} {CURRENCY}"
    return (
        f"{amount}, {worst.model}, up to {worst.input_tokens} tokens in and "
        f"{worst.output_tokens} out"
    )


def dollars(amount: Decimal) -> str:
    """An amount as it is, without trailing zeros and without rounding: ``4.065536``, ``45``.

    A fraction of a cent is printed, never rounded to zero: a long series of cheap calls must not
    look free (ADR 0020 §6)."""
    return f"{amount.normalize():f}"


@dataclass(frozen=True, slots=True)
class Refusal:
    """A call that spends, not let out: the code, the sentence, and the numbers it was judged on."""

    code: SpendingCode
    reason: str
    month: Month
    cap: Decimal | None
    worst: WorstCase | ErrorMetadata | None
    ledger: Ledger | None

    @property
    def payload(self) -> dict[str, str | None]:
        """What the audit row of the denial keeps of it: the code and the numbers, as strings of
        ``Decimal`` — never the user's content (§57)."""
        amount = self.worst.amount if isinstance(self.worst, WorstCase) else None
        return {
            "code": self.code.value,
            "month": self.month.label,
            "cap": None if self.cap is None else dollars(self.cap),
            "spent": None if self.ledger is None else dollars(self.ledger.spent),
            "reserved": None if self.ledger is None else dollars(self.ledger.reserved),
            "worst_case": None if amount is None else dollars(amount),
            "currency": CURRENCY,
        }


@dataclass(frozen=True, slots=True)
class Cleared:
    """A call the cap lets out, as far as the cap, the bound and the price go: what the rest of the
    gate needs, typed."""

    cap: Decimal
    worst: WorstCase
    amount: Decimal


@dataclass(frozen=True, slots=True)
class Foresight:
    """A call that would fit now: its worst case, and what the month has left before it."""

    worst: WorstCase
    left: Decimal
    cap: Decimal
    month: Month


def judge(
    *,
    cap: Decimal | None,
    worst: WorstCase | ErrorMetadata,
    month: Month,
    held: Ledger | None = None,
) -> Refusal | Cleared:
    """Whether a call may go out. The order is the order of what is missing: a cap, a bound, a
    price, room — the last only when ``held`` is given."""
    if cap is None:
        reason = f"no monthly cap: {CAP_VARIABLE} in the Core's .env sets it, in {CURRENCY}"
        return Refusal(SpendingCode.NO_CAP, reason, month, None, worst, held)
    if isinstance(worst, ErrorMetadata):
        said = f"{worst.code}: {worst.message}" if worst.message else worst.code
        reason = f"this call cannot be bounded: {said}"
        return Refusal(SpendingCode.UNBOUNDED, reason, month, cap, worst, held)
    if worst.amount is None:
        reason = (
            f"{worst.model} has no price in ELA's table: a call whose cost cannot be bounded is "
            f"not made ({CAP_VARIABLE})"
        )
        return Refusal(SpendingCode.UNPRICED, reason, month, cap, worst, held)
    cleared = Cleared(cap=cap, worst=worst, amount=worst.amount)
    if held is not None and not fits(held, cleared):
        return crossed(cleared, month, held)
    return cleared


def fits(held: Ledger, cleared: Cleared) -> bool:
    """``spent + reserved + worst case <= cap``: the whole rule, in one place."""
    return held.spent + held.reserved + cleared.amount <= cleared.cap


def crossed(cleared: Cleared, month: Month, held: Ledger) -> Refusal:
    """The refusal of a call that would cross the cap, with the four numbers."""
    reason = (
        f"the monthly cap would be crossed: spent {dollars(held.spent)} + reserved "
        f"{dollars(held.reserved)} + this call's worst case {dollars(cleared.amount)} > cap "
        f"{dollars(cleared.cap)} {CURRENCY} ({CAP_VARIABLE}, {month.label})"
    )
    return Refusal(SpendingCode.OVER_CAP, reason, month, cleared.cap, cleared.worst, held)


class SpendingGate:
    """The cap, applied where a call that spends is about to be made (ADR 0057).

    Holds the cap — ``None`` when the line is not there — and the store of results. The month of
    a reservation is the month of its ``STARTED`` record.
    """

    def __init__(self, results: ExecutionResultStore, cap: Decimal | None) -> None:
        self._results = results
        self._cap = cap

    @property
    def cap(self) -> Decimal | None:
        """The cap of the Core's ``.env``, or ``None``: no call that spends goes out."""
        return self._cap

    async def ledger(self, now: datetime) -> tuple[Month, Ledger]:
        """The month of ``now`` and its ledger, read now: the same function the gate judges with,
        on the same rows — what ``ela spend`` prints and what an approval names."""
        month = month_of(now)
        return month, ledger(await self._results.spending(month.since, month.until))

    async def foresee(self, worst: WorstCase | ErrorMetadata, now: datetime) -> Refusal | Foresight:
        """Would this call fit **now**? Read-only: what a question shows before anybody answers
        it, and the denial of a question a "yes" could not make pass (review decision 7)."""
        month, held = await self.ledger(now)
        judged = judge(cap=self._cap, worst=worst, month=month, held=held)
        if isinstance(judged, Refusal):
            return judged
        left = judged.cap - held.spent - held.reserved
        return Foresight(worst=judged.worst, left=left, cap=judged.cap, month=month)

    async def reserve(
        self, record: ExecutionResult, worst: WorstCase | ErrorMetadata
    ) -> Refusal | None:
        """Write ``record`` — a ``STARTED`` record — with ``worst`` as its reservation, if the
        month admits it; otherwise write nothing and say why. The check is one operation with the
        read (:meth:`~ela.ports.ExecutionResultStore.reserve`)."""
        month = month_of(record.created_at)
        judged = judge(cap=self._cap, worst=worst, month=month)
        if isinstance(judged, Refusal):
            return judged
        seen: list[Ledger] = []

        def admits(rows: tuple[ExecutionResult, ...]) -> bool:
            seen.append(ledger(rows))
            return fits(seen[-1], judged)

        reserved = record.model_copy(update={"worst_case": judged.worst})
        if await self._results.reserve(reserved, month.since, month.until, admits):
            return None
        return crossed(judged, month, seen[-1])
