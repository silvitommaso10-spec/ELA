"""A worst case on a result is a reservation, and a reservation is a ``STARTED`` record with an
amount (M14.1, ADR 0057 §4): the record written before a call that spends, and nothing else.

A worst case on a result that ended would count twice in the month's ledger — the outcome closes
a reservation with its cost —, and one without an amount is a call the cap does not let out: the
domain refuses both, before any store sees them.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ela.domain import ExecutionResult, ExecutionStatus
from tests.domain.examples import EXECUTION_RESULT, WORST_CASE


def result(status: ExecutionStatus, **changed: Any) -> dict[str, Any]:
    """The example result with ``status`` and the reservation of the example worst case."""
    return {
        **EXECUTION_RESULT.model_dump(),
        "status": status,
        "worst_case": WORST_CASE.model_dump(),
        **changed,
    }


def test_a_started_record_carries_its_reservation() -> None:
    record = ExecutionResult.model_validate(result(ExecutionStatus.STARTED))

    assert record.worst_case == WORST_CASE


@pytest.mark.parametrize(
    "status", [one for one in ExecutionStatus if one is not ExecutionStatus.STARTED], ids=str
)
def test_a_result_that_ended_carries_no_reservation(status: ExecutionStatus) -> None:
    with pytest.raises(ValidationError, match="a result that ended"):
        ExecutionResult.model_validate(result(status))


def test_a_reservation_without_an_amount_is_refused() -> None:
    unpriced = {**WORST_CASE.model_dump(), "amount": None}

    with pytest.raises(ValidationError, match="a reservation has an amount"):
        ExecutionResult.model_validate(result(ExecutionStatus.STARTED, worst_case=unpriced))
