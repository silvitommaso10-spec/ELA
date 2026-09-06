"""Contract of ``VerifierPort`` (spec §20, §63; ADR 0014 §1): fail-safe on its own, read-only,
and independent of the tool it verifies.

What ``verify`` must do before looking at any condition is the same for every implementation:
a result of another capability, a result that did not succeed, no condition, a condition
outside the vocabulary — each a failure with the code of ``check_verifiable``, never a pass and
never an exception. What holds for a *known* condition depends on the world and is tested per
verifier (``tests/tools/test_verifiers.py``); here every verifier is asked its whole vocabulary
on a result it can only judge by its preconditions.
"""

from __future__ import annotations

from typing import get_type_hints

import pytest

from ela.domain import CapabilityId, ErrorMetadata, ExecutionResult, ExecutionStatus
from ela.ports import (
    VERIFICATION_NO_CONDITIONS,
    VERIFICATION_NOT_SUCCEEDED,
    VERIFICATION_UNKNOWN_CONDITION,
    VERIFICATION_WRONG_CAPABILITY,
    AuthorizationStore,
    AuthorizingGuardianPort,
    PermissionGuardianPort,
    ToolPort,
    VerifierPort,
)
from tests.domain.examples import EXECUTION_RESULT

ARGUMENTS = {"path": "workspace/notes/briefing.md", "body": "...", "message": "hello"}


def succeeded(verifier: VerifierPort, **update: object) -> ExecutionResult:
    """A SUCCEEDED result about this verifier's capability, then ``update`` applied."""
    base = {
        "capability_id": verifier.capability_id,
        "status": ExecutionStatus.SUCCEEDED,
        "error": None,
        "output": {},
    }
    return EXECUTION_RESULT.model_copy(update={**base, **update})


def codes(failures: tuple[ErrorMetadata, ...]) -> list[str]:
    return [failure.code for failure in failures]


def test_the_vocabulary_is_a_non_empty_frozenset_of_dotted_names(verifier: VerifierPort) -> None:
    assert isinstance(verifier.conditions, frozenset)
    assert verifier.conditions
    for condition in verifier.conditions:
        assert "." in condition and condition == condition.strip()


async def test_a_result_of_another_capability_is_a_failure(verifier: VerifierPort) -> None:
    other = CapabilityId("some.other_capability")
    assert other != verifier.capability_id
    result = succeeded(verifier, capability_id=other)
    failures = await verifier.verify(sorted(verifier.conditions), ARGUMENTS, result)
    assert codes(failures) == [VERIFICATION_WRONG_CAPABILITY]
    assert failures[0].details["condition"] is None


@pytest.mark.parametrize(
    "status",
    [s for s in ExecutionStatus if s is not ExecutionStatus.SUCCEEDED],
    ids=lambda s: s.value,
)
async def test_a_result_that_did_not_succeed_is_a_failure(
    verifier: VerifierPort, status: ExecutionStatus
) -> None:
    result = succeeded(verifier, status=status)
    failures = await verifier.verify(sorted(verifier.conditions), ARGUMENTS, result)
    assert codes(failures) == [VERIFICATION_NOT_SUCCEEDED]
    assert status.value in failures[0].message


async def test_no_condition_is_a_failure_not_a_pass(verifier: VerifierPort) -> None:
    """The empty truth is a doubt (§33): nothing to check means nothing verified."""
    failures = await verifier.verify((), ARGUMENTS, succeeded(verifier))
    assert codes(failures) == [VERIFICATION_NO_CONDITIONS]


async def test_an_unknown_condition_is_a_failure_per_condition(verifier: VerifierPort) -> None:
    unknown = ("x.unknown", "y.unknown")
    assert not (set(unknown) & verifier.conditions)
    failures = await verifier.verify(unknown, ARGUMENTS, succeeded(verifier))
    assert codes(failures) == [VERIFICATION_UNKNOWN_CONDITION] * 2
    assert [f.details["condition"] for f in failures] == list(unknown)
    one = await verifier.verify(("x.unknown",), ARGUMENTS, succeeded(verifier))
    assert codes(one) == [VERIFICATION_UNKNOWN_CONDITION]


async def test_an_unknown_condition_stops_the_verification_before_the_known_ones(
    verifier: VerifierPort,
) -> None:
    """A step that names one condition the verifier cannot check is not verifiable at all."""
    known = sorted(verifier.conditions)[0]
    failures = await verifier.verify((known, "x.unknown"), ARGUMENTS, succeeded(verifier))
    assert codes(failures) == [VERIFICATION_UNKNOWN_CONDITION]
    assert failures[0].details["condition"] == "x.unknown"


async def test_the_preconditions_come_in_order(verifier: VerifierPort) -> None:
    """Wrong capability before wrong status before no condition before unknown condition."""
    other = CapabilityId("some.other_capability")
    wrong_everything = succeeded(verifier, capability_id=other, status=ExecutionStatus.FAILED)
    failures = await verifier.verify((), ARGUMENTS, wrong_everything)
    assert codes(failures) == [VERIFICATION_WRONG_CAPABILITY]
    failed = succeeded(verifier, status=ExecutionStatus.FAILED)
    assert codes(await verifier.verify((), ARGUMENTS, failed)) == [VERIFICATION_NOT_SUCCEEDED]


async def test_every_failure_is_error_metadata_naming_its_condition(
    verifier: VerifierPort,
) -> None:
    failures = await verifier.verify(("x.unknown",), ARGUMENTS, succeeded(verifier))
    assert isinstance(failures, tuple)
    for failure in failures:
        assert isinstance(failure, ErrorMetadata)
        assert "condition" in failure.details


async def test_known_conditions_answer_with_a_tuple_and_never_raise(
    verifier: VerifierPort,
) -> None:
    """On a world the verifier knows nothing about (no file, empty output) every known condition
    either holds or fails with a code of its own — never one of the preconditions'."""
    preconditions = {
        VERIFICATION_WRONG_CAPABILITY,
        VERIFICATION_NOT_SUCCEEDED,
        VERIFICATION_NO_CONDITIONS,
        VERIFICATION_UNKNOWN_CONDITION,
    }
    failures = await verifier.verify(sorted(verifier.conditions), ARGUMENTS, succeeded(verifier))
    assert isinstance(failures, tuple)
    for failure in failures:
        assert failure.code not in preconditions
        assert failure.details["condition"] in verifier.conditions


def test_verifier_holds_no_tool_no_guardian_and_no_store(verifier: VerifierPort) -> None:
    """Independent by construction (ADR 0014 decision D): a verifier that held the tool would
    be the tool certifying itself; one that held the Guardian or the store could decide."""
    forbidden = (ToolPort, PermissionGuardianPort, AuthorizingGuardianPort, AuthorizationStore)
    for name, value in vars(verifier).items():
        assert not isinstance(value, forbidden), f"{type(verifier).__name__}.{name}"
    for method in (type(verifier).__init__, type(verifier).verify):
        for name, hint in get_type_hints(method).items():
            assert hint not in forbidden, f"{method.__qualname__}({name})"
