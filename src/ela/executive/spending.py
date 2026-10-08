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

The month is the calendar month in UTC, **declared** (decision F). The documentation writes that
boundary for the usage tier's cap (``00:00 UTC on the first day of the next month``); of the limit
an organization sets — the second cap — it says only that the answer states when access resumes
(correction of 2026-10-07, review of ``be7f131``). So the provider's month need not be ELA's, and
the second cap can be reached with ELA in order: :meth:`SpendingGate.counted` puts what ELA counted
beside the provider's refusal. A call counts in the month of its ``STARTED``.

The cap is one line of the Core's ``.env``, :data:`CAP_VARIABLE`, in dollars like the price list
and the console. Without it no call that spends goes out (decision B), and every refusal names
the line. A "yes" does not raise it: only the person who wrote it does, by changing it (G).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from ela.domain import (
    Admission,
    ErrorMetadata,
    ExecutionResult,
    ExecutionStatus,
    Ledger,
    ProviderUsage,
    Reservation,
    StepId,
    TaskId,
    WorstCase,
)
from ela.ports import (
    GUIDED_CACHE,
    GUIDED_COST,
    GUIDED_MAX_TOKENS,
    GUIDED_MODEL_CHANGED,
    GUIDED_TOOLS_CHANGED,
    GUIDED_UNCHECKED,
    PROVIDER_SPEND_LIMIT,
    STARTED_ID,
    CallRequest,
    ExecutionResultStore,
)

__all__ = [
    "CAP_VARIABLE",
    "CURRENCY",
    "BudgetCode",
    "BudgetRefusal",
    "Cleared",
    "Foresight",
    "Month",
    "Refusal",
    "ReservationError",
    "SessionBudget",
    "SettledCall",
    "SpendingCode",
    "SpendingGate",
    "crossed",
    "dollars",
    "fits",
    "judge",
    "ledger",
    "month_of",
    "reservation_of",
    "worst_said",
]

CAP_VARIABLE: Final = "ELA_SPENDING_CAP_USD"
"""The line that sets the cap. Named here once, and in every refusal: B and G want the reason to
say where the number lives."""

CURRENCY: Final = "USD"
"""The cap's currency: the price list's and the console's. A conversion would be another belief."""


class ReservationError(Exception):
    """A reservation the ledger cannot count: a ``STARTED`` record whose worst case has no amount.

    The domain refuses one (ADR 0057 §4), so a row that has it was not made by the domain; counted
    at zero it would count in the wrong direction. The ledger says no number at all, and whoever
    asked — the gate before a call, ``GET /spend`` — lets nothing out (§33)."""

    def __init__(self, record: ExecutionResult) -> None:
        self.record_id = record.id
        super().__init__(
            f"the reservation {record.id} has no amount: the ledger does not count it at zero "
            "(ADR 0057 §4)"
        )


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
        amount = row.worst_case.amount
        if amount is None:
            raise ReservationError(row)
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
    each = " per call" if worst.per_call else ""
    return (
        f"{amount}, {worst.model}, up to {worst.input_tokens} tokens in and "
        f"{worst.output_tokens} out{each}"
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

    async def counted(self, outcome: ExecutionResult, now: datetime) -> ExecutionResult:
        """``outcome``, and if a provider's spend limit stopped it, how much ELA counted beside it.

        The provider's month need not be ELA's (review of ``be7f131``): its limit can be reached
        with ELA in order with its own cap, so the adapter's reason says only which limit, and the
        Core adds what it counted of its cap — the ledger of the month **with this outcome in it**,
        which closes its own reservation. The causes are for the guide (§23). Every other outcome
        is returned as it is.
        """
        error = outcome.error
        if error is None or error.code != PROVIDER_SPEND_LIMIT:
            return outcome
        month = month_of(now)
        held = ledger([*await self._results.spending(month.since, month.until), outcome])
        said = f"ELA counted {dollars(held.spent)} spent and {dollars(held.reserved)} reserved"
        if self._cap is None:
            said = f"{said} in {month.label}, with no cap ({CAP_VARIABLE})"
        else:
            said = (
                f"{said} of its cap of {dollars(self._cap)} {CURRENCY} in {month.label} "
                f"({CAP_VARIABLE})"
            )
        told = error.model_copy(update={"message": f"{error.message}; {said}"})
        return outcome.model_copy(update={"error": told})

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

    async def reservation(self, task_id: TaskId, step_id: StepId) -> Reservation | None:
        """What this gate reserved for the step, as a :class:`~ela.domain.Reservation`, or
        ``None`` if it reserved nothing (M14.3, ADR 0060): read from the ``STARTED`` record, which
        is the reservation (ADR 0057 §4), and never from what the caller says."""
        for row in await self._results.for_step(task_id, step_id):
            reserved = reservation_of(row)
            if reserved is not None:
                return reserved
        return None


def reservation_of(record: ExecutionResult) -> Reservation | None:
    """The :class:`~ela.domain.Reservation` a ``STARTED`` record holds, or ``None`` for any other
    row and for a record that reserved nothing. **The one place one is minted** (rule 65)."""
    worst = record.worst_case
    if (
        record.status is not ExecutionStatus.STARTED
        or worst is None
        or worst.amount is None
        or record.task_id is None
        or record.step_id is None
    ):
        return None
    return Reservation(
        task_id=record.task_id,
        step_id=record.step_id,
        started_id=record.id,
        amount=worst.amount,
        currency=worst.currency or CURRENCY,
        model=worst.model,
        input_tokens=worst.input_tokens,
        output_tokens=worst.output_tokens,
    )


# ----------------------------------------------------------------------------------------
# The budget of a guided session (M14.3, ADR 0060)
# ----------------------------------------------------------------------------------------


class BudgetCode(StrEnum):
    """Why a call of a guided session was not let out — each refused **before the network**, and
    each the code of the step ELA fails when it stops the session for it. The values are the
    shared vocabulary of ``ela.ports``, where the tool of the session declares them."""

    UNCHECKED = GUIDED_UNCHECKED
    TOOLS = GUIDED_TOOLS_CHANGED
    MODEL = GUIDED_MODEL_CHANGED
    MAX_TOKENS = GUIDED_MAX_TOKENS
    CACHE = GUIDED_CACHE
    COST = GUIDED_COST


@dataclass(frozen=True, slots=True)
class BudgetRefusal:
    """A call of the session not let out: the code, and a sentence in ELA's words — never a word
    of the request, which is the user's content (§57)."""

    code: BudgetCode
    reason: str


@dataclass(frozen=True, slots=True)
class SettledCall:
    """One call of the session as it closed: numbers only. ``cost`` is ``None`` when the outcome
    is unknown — counted at its worst case (ADR 0057 §10)."""

    call: int
    model: str
    input_tokens: int
    output_tokens: int
    request_bytes: int
    cost: Decimal | None
    worst: Decimal

    @property
    def counted(self) -> Decimal:
        return self.worst if self.cost is None else self.cost


@dataclass(slots=True)
class SessionBudget:
    """The reservation of one guided session, spent call by call (M14.3, ADR 0060; decision 5).

    A call goes out only if ``spent + in flight + its worst case <= the reservation``, with the
    worst case of ADR 0057 §2 **on the model and the** ``max_tokens`` **of the request itself**,
    which whoever holds the price list hands to :meth:`admit`. In memory: the reservation is
    already in the month's ledger, and a crash leaves the ``STARTED`` record open at its worst
    case, which is ADR 0057 §4. The checks are pure, and their order is the order of what is wrong
    — the start not checked, the tools, the model, the budget of output, the cache, the money.
    """

    reservation: Reservation
    tools: frozenset[str]
    checked: bool = False
    calls: int = 0
    in_flight: dict[int, Admission] = field(default_factory=dict)
    settled: list[SettledCall] = field(default_factory=list)

    @property
    def spent(self) -> Decimal:
        """What the closed calls count: their cost, or their worst case when it is unknown."""
        return sum((call.counted for call in self.settled), Decimal(0))

    @property
    def flying(self) -> Decimal:
        return sum((admission.worst for admission in self.in_flight.values()), Decimal(0))

    def start(self, tools: Iterable[str]) -> BudgetRefusal | None:
        """The tools the session's start lists, checked before any call (decision 22)."""
        refused = self._tools(tools, "the start of the session")
        if refused is None:
            self.checked = True
        return refused

    def _tools(self, tools: Iterable[str] | None, where: str) -> BudgetRefusal | None:
        offered = None if tools is None else list(tools)
        if offered is None or len(offered) != len(set(offered)) or set(offered) != self.tools:
            said = "none" if not offered else f"{len(offered)}"
            return BudgetRefusal(
                BudgetCode.TOOLS,
                f"{where} offers {said} tools, not exactly the session's {sorted(self.tools)}",
            )
        return None

    def admit(self, request: CallRequest, worst: Decimal | None) -> Admission | BudgetRefusal:
        """An :class:`~ela.domain.Admission` for this call, or why it does not go out. ``worst`` is
        the worst case of one call to the reservation's model with the request's ``max_tokens`` —
        ``None`` for a model with no price."""
        if not self.checked:
            return BudgetRefusal(
                BudgetCode.UNCHECKED, "a call before the tools of the start were checked"
            )
        refused = self._tools(request.tools, "the call")
        if refused is not None:
            return refused
        if request.model != self.reservation.model:
            return BudgetRefusal(
                BudgetCode.MODEL,
                f"the call asks for another model than {self.reservation.model}, the one the "
                "router chose and the question named",
            )
        max_tokens = request.max_tokens
        if max_tokens is None or not 1 <= max_tokens <= self.reservation.output_tokens:
            return BudgetRefusal(
                BudgetCode.MAX_TOKENS,
                f"the call's max_tokens is not between 1 and the "
                f"{self.reservation.output_tokens} the session declared",
            )
        if request.cached:
            return BudgetRefusal(
                BudgetCode.CACHE,
                "the call asks for the cache, whose writes the worst case does not price",
            )
        if worst is None:
            return BudgetRefusal(
                BudgetCode.COST, f"{self.reservation.model} has no price in ELA's table"
            )
        if self.spent + self.flying + worst > self.reservation.amount:
            return BudgetRefusal(
                BudgetCode.COST,
                f"the call does not fit: spent {dollars(self.spent)} + in flight "
                f"{dollars(self.flying)} + its worst case {dollars(worst)} > the session's "
                f"{dollars(self.reservation.amount)} {CURRENCY}",
            )
        self.calls += 1
        admission = Admission(
            session=self.reservation.step_id,
            call=self.calls,
            model=self.reservation.model,
            max_tokens=max_tokens,
            worst=worst,
            request_bytes=request.request_bytes,
        )
        self.in_flight[admission.call] = admission
        return admission

    def settle(self, admission: Admission, usage: ProviderUsage | None) -> None:
        """Close one call with what it consumed. ``None``, or a usage with no cost after the
        network, is an unknown outcome: the worst case stays. A call settled twice, or after the
        session closed, changes nothing."""
        if self.in_flight.pop(admission.call, None) is None:
            return
        if usage is not None and not usage.sent:
            cost: Decimal | None = Decimal(0)
        else:
            cost = None if usage is None else usage.cost
        self.settled.append(
            SettledCall(
                call=admission.call,
                model=admission.model,
                input_tokens=0 if usage is None else usage.input_tokens,
                output_tokens=0 if usage is None else usage.output_tokens,
                request_bytes=admission.request_bytes,
                cost=cost,
                worst=admission.worst,
            )
        )

    def close(self) -> None:
        """The session is over: a call still in flight has no outcome, and counts its worst
        case."""
        for admission in list(self.in_flight.values()):
            self.settle(admission, None)

    def usage(self) -> ProviderUsage:
        """The usage of the whole session, which closes its reservation: the sum of the calls,
        those with an unknown outcome at their worst case (decision 11 (a)); nothing sent when no
        call went out."""
        calls = self.settled
        return ProviderUsage(
            input_tokens=sum(call.input_tokens for call in calls),
            output_tokens=sum(call.output_tokens for call in calls),
            cost=self.spent,
            currency=CURRENCY,
            sent=bool(calls),
            request_bytes=sum(call.request_bytes for call in calls) if calls else None,
        )

    @property
    def unknown(self) -> int:
        return sum(1 for call in self.settled if call.cost is None)

    @property
    def input_minus_bytes_max(self) -> int | None:
        """The most, over the calls, of input tokens minus the bytes of the body (decision 26): the
        number ADR 0057 §2's month of usage reads. ``None`` with no call."""
        known = [
            call.input_tokens - call.request_bytes
            for call in self.settled
            if call.cost is not None and call.input_tokens
        ]
        return max(known) if known else None
