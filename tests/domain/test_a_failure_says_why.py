"""A result that did not succeed says why (M13.1c, ADR 0055; spec §64).

«Un errore non deve essere semplicemente: FAILED. Deve diventare informazione utile» (§64). Until
M13.1c a result could be ``FAILED`` with no ``error``, and the executor minted one from the status —
``tool.failed``, «ended with status FAILED» —, the one reason a run could not pass on because nobody
had given it. The domain refuses the result instead (decision E of the session): the branch does not
exist, and this test is its defence. Measured before it was written: no producer of production
builds such a result, and the database of the Mac holds none (``docs/milestones/M13.1c.md``, «Chi
costruisce un risultato non riuscito senza perché»).

``STARTED`` is not an ending — it records that a tool was about to act (ADR 0021 §1) — and has
nothing to explain; ``SUCCEEDED`` has nothing to explain either.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ela.domain import ExecutionResult, ExecutionStatus
from tests.domain.examples import ERROR_METADATA, EXECUTION_RESULT

EXPLAINED = frozenset({ExecutionStatus.SUCCEEDED, ExecutionStatus.STARTED})
"""The statuses that need no reason: the one that succeeded, and the one that has not ended."""

UNEXPLAINED = sorted(set(ExecutionStatus) - EXPLAINED)


def built(status: ExecutionStatus, *, with_error: bool) -> ExecutionResult:
    """Through the constructor, the way a tool and the mapper of the database build one."""
    fields = EXECUTION_RESULT.model_dump()
    fields.update(status=status, error=ERROR_METADATA.model_dump() if with_error else None)
    return ExecutionResult.model_validate(fields)


@pytest.mark.parametrize("status", UNEXPLAINED, ids=str)
def test_a_result_that_did_not_succeed_is_refused_without_its_error(
    status: ExecutionStatus,
) -> None:
    with pytest.raises(ValidationError, match="§64"):
        built(status, with_error=False)


@pytest.mark.parametrize("status", UNEXPLAINED, ids=str)
def test_a_result_that_did_not_succeed_is_kept_with_its_error(status: ExecutionStatus) -> None:
    assert built(status, with_error=True).error == ERROR_METADATA


@pytest.mark.parametrize("status", sorted(EXPLAINED), ids=str)
def test_a_result_that_succeeded_or_has_not_ended_needs_no_error(status: ExecutionStatus) -> None:
    assert built(status, with_error=False).error is None


def test_the_statuses_are_split_in_two_and_none_is_left_out() -> None:
    """Closed over the enum: a status a future milestone adds is on one side, by a decision."""
    assert set(UNEXPLAINED) | EXPLAINED == set(ExecutionStatus)
    assert UNEXPLAINED
