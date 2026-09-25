"""An effect verified where it happened: the node's verdict, and the Core that records it (M13.3).

Form B of the SPEC, ADR 0048. A verifier that reads the machine proves an effect only on the
machine it reads, so for a node's result it runs **on the node**, with the plan's conditions, and
the Core records the verdict and where it was taken — never verifying on its own disk, not at the
delivery and not on a resume. What the Core still proves is that the verdict names exactly the
plan's conditions and speaks the verifier's vocabulary; anything else is ``verification.missing``.

The capability here is the world's echo with its verifier declared to read the machine and the set
the composition hands in naming it: the protocol under test is the same for ``fs.*``, whose real
tools and verifiers the conformance story and ``tests/node`` drive.
"""

from __future__ import annotations

from typing import Any

import pytest

from ela.domain import AuditEventType, ExecutionStatus, PrivacyLevel, StepState, TaskState
from ela.executive import (
    RECOVERED,
    RESULT_NOT_TEXT,
    VERDICT,
    VERIFICATION_EXCEPTION,
    VERIFICATION_FAILED,
    VERIFICATION_MISSING,
    DeliveryConflictError,
    RunOutcome,
    Verdict,
    check_envelope,
)
from tests.executive.support import BAD, OK, World, audit_of, crashing_world, world
from tests.executive.test_executor_remote import answered
from tests.permissions.support import ECHO

E = AuditEventType


def verified_there(w: World) -> World:
    """The echo, as a capability whose verifier reads the machine and that a node carries."""
    w.verifier(ECHO.id).reads_the_machine = True
    return w


def a_world(**options: Any) -> World:
    return verified_there(world(carried=frozenset({ECHO.id}), **options))


async def claimed(w: World, *, conditions: tuple[str, ...] = (OK,)) -> tuple[Any, Any, Any, Any]:
    """A step of a TRUSTED task, offered to a node and taken by it."""
    remote = await w.remote()
    task, (step,) = await w.queued(ECHO.id, conditions=conditions, max_privacy=PrivacyLevel.TRUSTED)
    run = await w.runner.run(task.id)
    assert run.outcome is RunOutcome.ASSIGNED
    stand = await w.assignments.standing(task.id, step.id)
    assert stand.assignment is not None
    taken = await w.executor.begin(stand.assignment.id, remote.id)
    return task, step, taken, remote


def never(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("the Core verified on its own disk an effect that happened on a node")


async def verified_event(w: World, task_id: Any) -> Any:
    return [e for e in await w.events(task_id) if e.event_type is E.EXECUTION_VERIFIED][-1]


# ----------------------------------------------------------------------------------------
# The order asks, the node answers, the Core records (criteria 1, 2)
# ----------------------------------------------------------------------------------------


async def test_the_order_carries_the_plan_s_conditions_only_for_work_the_node_verifies() -> None:
    w = a_world()
    _, step, taken, _ = await claimed(w)
    echo = world()
    _, _, plain, _ = await claimed(echo)

    assert taken.conditions == step.success_conditions == (OK,)
    assert plain.conditions is None


async def test_a_verdict_that_passed_completes_the_step_and_says_where_it_was_taken() -> None:
    w = a_world()
    task, step, taken, remote = await claimed(w)
    w.verifier(ECHO.id).verify = never  # type: ignore[method-assign]

    delivered = await w.executor.deliver(
        taken.assignment.id, remote.id, answered(verdict=Verdict((OK,)))
    )

    assert delivered.step_state is StepState.COMPLETED
    event = await verified_event(w, task.id)
    assert event.payload["passed"] is True
    assert event.payload["verified_on"] == str(remote.id)
    (result,) = await w.results.for_step(task.id, step.id)
    assert result.metadata[VERDICT] == {"conditions": (OK,), "failed": (), "exception": None}


async def test_a_verdict_that_failed_fails_the_step_and_the_task_in_the_core_s_words() -> None:
    w = a_world()
    task, step, taken, remote = await claimed(w, conditions=(OK, BAD))
    w.verifier(ECHO.id).verify = never  # type: ignore[method-assign]

    await w.executor.deliver(
        taken.assignment.id,
        remote.id,
        answered(verdict=Verdict((OK, BAD), failed=((BAD, "fake.mismatch"),))),
    )

    assert (await w.task(task.id)).state is TaskState.FAILED
    error = (await verified_event(w, task.id)).error
    assert error is not None and error.code == VERIFICATION_FAILED
    (failure,) = error.details["failures"]  # type: ignore[misc]
    assert failure["code"] == "fake.mismatch"  # type: ignore[index]
    assert failure["message"] == f"{BAD} did not hold on the node {remote.id} (fake.mismatch)"  # type: ignore[index]


async def test_a_verifier_that_raised_on_the_node_is_the_exception_it_is_here() -> None:
    w = a_world()
    task, _, taken, remote = await claimed(w)

    await w.executor.deliver(
        taken.assignment.id, remote.id, answered(verdict=Verdict((OK,), exception="OSError"))
    )

    error = (await verified_event(w, task.id)).error
    assert error is not None
    assert [f["code"] for f in error.details["failures"]] == [VERIFICATION_EXCEPTION]  # type: ignore[index, union-attr]
    assert "OSError" in error.message + str(error.details)


# ----------------------------------------------------------------------------------------
# What the Core still proves: exactly the plan's conditions, in the verifier's words (crit. 3)
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("verdict", "why"),
    [
        (None, "delivered no verdict"),
        (Verdict((BAD,)), "other conditions than the plan's"),
        (Verdict(()), "other conditions than the plan's"),
        (Verdict((OK,), failed=((OK, "made.up"),)), "outside the verifier's vocabulary"),
        (Verdict((OK,), failed=(("elsewhere", "fake.mismatch"),)), "the plan did not name"),
        (
            Verdict((OK,), failed=((OK, "fake.mismatch"), (OK, "fake.mismatch"))),
            "one condition twice",
        ),
        (Verdict((OK,), failed=((OK, "fake.mismatch"),), exception="OSError"), "shape"),
        (Verdict((OK,), exception="not a name"), "not a name"),
    ],
    ids=[
        "none",
        "other-conditions",
        "no-conditions",
        "code-out-of-vocabulary",
        "condition-not-named",
        "twice",
        "exception-and-failures",
        "exception-not-a-name",
    ],
)
async def test_a_verdict_the_core_cannot_read_as_the_plan_s_is_verification_missing(
    verdict: Verdict | None, why: str
) -> None:
    w = a_world()
    task, _, taken, remote = await claimed(w)
    w.verifier(ECHO.id).verify = never  # type: ignore[method-assign]

    delivered = await w.executor.deliver(taken.assignment.id, remote.id, answered(verdict=verdict))

    assert delivered.step_state is StepState.FAILED
    assert (await w.task(task.id)).state is TaskState.FAILED
    error = (await verified_event(w, task.id)).error
    assert error is not None and error.code == VERIFICATION_FAILED
    (failure,) = error.details["failures"]  # type: ignore[misc]
    assert failure["code"] == VERIFICATION_MISSING  # type: ignore[index]
    assert why in failure["message"]  # type: ignore[index, operator]


async def test_a_result_that_did_not_succeed_asks_for_no_verdict_and_may_carry_none() -> None:
    w = a_world()
    task, step, taken, remote = await claimed(w)

    delivered = await w.executor.deliver(
        taken.assignment.id, remote.id, answered(status=ExecutionStatus.FAILED)
    )

    assert delivered.step_state is StepState.FAILED
    assert E.EXECUTION_VERIFIED not in await w.event_types(task.id)
    with pytest.raises(ValueError, match="a verdict is about a result that succeeded"):
        check_envelope(answered(status=ExecutionStatus.FAILED, verdict=Verdict((OK,))))


async def test_a_verdict_about_work_the_core_verifies_is_refused_before_any_write() -> None:
    w = world()
    task, _, taken, remote = await claimed(w)
    before = len(await w.events(task.id))

    with pytest.raises(ValueError, match="verified here, by the Core"):
        await w.executor.deliver(taken.assignment.id, remote.id, answered(verdict=Verdict((OK,))))

    assert len(await w.events(task.id)) == before


async def test_two_envelopes_that_differ_only_in_the_verdict_are_a_conflict() -> None:
    w = a_world()
    _, _, taken, remote = await claimed(w)
    await w.executor.deliver(taken.assignment.id, remote.id, answered(verdict=Verdict((OK,))))

    with pytest.raises(DeliveryConflictError):
        await w.executor.deliver(
            taken.assignment.id,
            remote.id,
            answered(verdict=Verdict((OK,), failed=((OK, "fake.mismatch"),))),
        )


async def test_an_envelope_without_a_verdict_keeps_the_digest_it_had() -> None:
    """The verdict enters the digest only when there is one: a replay of a delivery made before
    M13.3 is still the same answer."""
    assert answered().digest != answered(verdict=Verdict((OK,))).digest
    assert answered().digest == answered(verdict=None).digest


async def test_a_verdict_that_is_not_text_is_a_result_that_cannot_be_kept() -> None:
    w = a_world()
    task, step, taken, remote = await claimed(w)

    await w.executor.deliver(
        taken.assignment.id, remote.id, answered(verdict=Verdict((OK,), exception="x\ud800"))
    )

    (result,) = await w.results.for_step(task.id, step.id)
    assert result.error is not None and result.error.code == RESULT_NOT_TEXT
    assert "verdict" in result.error.message and VERDICT not in result.metadata


# ----------------------------------------------------------------------------------------
# A resume reads the verdict it kept, and never the Core's disk (criterion 2)
# ----------------------------------------------------------------------------------------


async def test_a_death_before_the_verification_is_repaired_with_the_kept_verdict() -> None:
    w, crashes = crashing_world(carried=frozenset({ECHO.id}))
    verified_there(w)
    task, step, taken, remote = await claimed(w)
    crashes.audit.arm("append", audit_of(E.EXECUTION_VERIFIED))
    with pytest.raises(Exception, match="never happened"):
        await w.executor.deliver(taken.assignment.id, remote.id, answered(verdict=Verdict((OK,))))
    crashes.disarm()
    w.verifier(ECHO.id).verify = never  # type: ignore[method-assign]

    run = await w.runner.run(task.id)

    assert run.outcome is RunOutcome.COMPLETED
    event = await verified_event(w, task.id)
    assert event.payload[RECOVERED] is True
    assert event.payload["verified_on"] == str(remote.id)
    assert await w.step_state(task.id, step.id) is StepState.COMPLETED
