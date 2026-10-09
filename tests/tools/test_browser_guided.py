"""The tool of ``browser.guided`` on its fakes (M14.3, ADR 0060): what the API's road misses.

«Partirebbe» before the question (ADR 0045 §6-bis): the arguments again, the route, the bound of
one call, a cost under it, the binary, the folder. After the yes: the model the question named, or
the step fails (``guided.route_changed``); a launch that does not start; the duration. And the
verifier's three conditions, each with the failure that makes it false — never a fourth, that the
sentence was done.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from ela.domain import ErrorMetadata, ExecutionStatus, StepId, TaskId, WorstCase
from ela.permissions import BROWSER_GUIDED
from ela.ports import (
    GUIDED_CAP_BELOW_ONE_CALL,
    GUIDED_DURATION,
    GUIDED_FAILED,
    GUIDED_FOLDER_CHANGED,
    GUIDED_NOT_INSTALLED,
    GUIDED_ROUTE_CHANGED,
    GUIDED_UNRESERVED,
    PROVIDER_UNAVAILABLE,
    ROUTING_UNKNOWN_TASK_TYPE,
    SessionEnd,
    SessionHost,
    SessionPlan,
)
from ela.testing.fakes import FakeAgentSession, FakeAuditLog, FakeStop, finished
from ela.tools import ARGUMENTS_INVALID
from ela.tools.guided import (
    ACT_DESCRIPTION,
    GUIDED_CLOSED,
    GUIDED_GESTURES_AUDITED,
    GUIDED_MAX_TOKENS,
    GUIDED_RESERVATIONS_CLOSED,
    READ_DESCRIPTION,
    BrowserGuidedVerifier,
)
from tests.domain.examples import STEP_ID, TASK_ID
from tests.tools.guided import ARGUMENTS, MODEL, GuidedWorld, guided_world


async def at_once(seconds: float) -> None:
    """A duration that is over as soon as it starts."""


async def forever(plan: SessionPlan, host: SessionHost) -> SessionEnd:
    await host.started(("mcp__ela__act", "mcp__ela__read"))
    await asyncio.Event().wait()
    raise AssertionError("never")  # pragma: no cover


@pytest.mark.parametrize(
    "update",
    [
        {"goal": ""},
        {"sites": []},
        {"sites": ["not a site"]},
        {"max_cost_usd": "1e3"},
        {"looks": 0},
        {"looks": True},
        {"seconds": 1},
        {"task_type": 7},
    ],
    ids=str,
)
async def test_arguments_the_schema_would_refuse_are_refused_again(update: dict[str, Any]) -> None:
    """§28: the tool never trusts its caller, whatever the Guardian checked."""
    world = guided_world()

    prospect = await world.tool.prospect({**ARGUMENTS, **update})
    worst = await world.tool.worst_case({**ARGUMENTS, **update})

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert isinstance(worst, ErrorMetadata) and worst.code == ARGUMENTS_INVALID


async def test_a_task_type_the_router_does_not_know_is_refused() -> None:
    world = guided_world()
    prospect = await world.tool.prospect({**ARGUMENTS, "task_type": "telepathy"})
    assert prospect.refusal is not None and prospect.refusal.code == ROUTING_UNKNOWN_TASK_TYPE


async def test_a_provider_that_is_not_there_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    world = guided_world()
    monkeypatch.setattr(
        world.tool, "_providers", type("Empty", (), {"get": staticmethod(_missing)})()
    )
    prospect = await world.tool.prospect(ARGUMENTS)
    assert prospect.refusal is not None and prospect.refusal.code == PROVIDER_UNAVAILABLE


def _missing(name: str) -> Any:
    from ela.ports import NotFoundError

    raise NotFoundError("provider", name)


async def test_a_provider_that_cannot_bound_one_call_refuses_the_session() -> None:
    world = guided_world(worst=None)
    world.provider._worst = ErrorMetadata(code="provider.unavailable", message="no key")  # noqa: SLF001

    prospect = await world.tool.prospect(ARGUMENTS)

    assert prospect.refusal is not None and prospect.refusal.code == "provider.unavailable"


async def test_a_cost_below_the_worst_case_of_one_call_is_refused_before_the_question() -> None:
    world = guided_world()
    cheap = {**ARGUMENTS, "max_cost_usd": "0.001"}

    prospect = await world.tool.prospect(cheap)
    worst = await world.tool.worst_case(cheap)

    assert prospect.refusal is not None and prospect.refusal.code == GUIDED_CAP_BELOW_ONE_CALL
    assert isinstance(worst, ErrorMetadata) and worst.code == GUIDED_CAP_BELOW_ONE_CALL


@pytest.mark.parametrize("code", [GUIDED_NOT_INSTALLED, GUIDED_FOLDER_CHANGED])
async def test_a_session_that_could_not_be_launched_is_refused_before_the_question(
    code: str,
) -> None:
    unready = ErrorMetadata(code=code, message="not now")
    world = guided_world(session=FakeAgentSession(unready=unready))

    prospect = await world.tool.prospect(ARGUMENTS)

    assert prospect.refusal == unready


async def test_the_question_names_the_session() -> None:
    world = guided_world()

    prospect = await world.tool.prospect(ARGUMENTS)

    assert prospect.refusal is None and prospect.guided is not None
    guided = prospect.guided
    assert (guided.phrase, guided.sites, guided.model) == (
        ARGUMENTS["goal"],
        ("www.youtube.com",),
        MODEL,
    )
    assert (guided.max_cost, guided.looks, guided.timeout_seconds) == ("0.05", 8, 120)
    assert "fake" in guided.sends


async def test_the_worst_case_is_the_session_s_with_the_tokens_of_one_call() -> None:
    world = guided_world()

    worst = await world.tool.worst_case(ARGUMENTS)

    assert isinstance(worst, WorstCase)
    assert (worst.amount, worst.model, worst.per_call) == (Decimal("0.05"), MODEL, True)
    assert (worst.input_tokens, worst.output_tokens) == (1_000, 100)


async def test_an_unpriced_call_leaves_the_session_without_an_amount() -> None:
    """The gate refuses it (``spending.unpriced``): the amount is the session's only if a call has
    one."""
    unpriced = WorstCase(amount=None, model="nobody", input_tokens=1, output_tokens=1)
    world = guided_world(worst=unpriced)

    worst = await world.tool.worst_case(ARGUMENTS)

    assert isinstance(worst, WorstCase) and worst.amount is None


async def test_a_session_runs_only_with_its_decision() -> None:
    world = guided_world()
    outcome = await world.tool._run(ARGUMENTS, FakeStop())  # noqa: SLF001
    assert outcome.code == ARGUMENTS_INVALID


async def test_a_step_with_no_reservation_launches_nothing() -> None:
    world = guided_world(reserved=None)

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_UNRESERVED
    assert world.session.launched == []


async def test_a_step_whose_session_is_open_already_launches_nothing_and_spends_nothing() -> None:
    """The room refuses a second session of a step id it has open (a plan by hand sent to two
    tasks): the step fails with the room's reason, nothing is launched, and the reservation closes
    at zero — a result with no usage would hold the month's worst case until its first day."""
    world = guided_world()
    opened = await world.room.open(
        TaskId(TASK_ID), STEP_ID, sites=("www.youtube.com",), tools=world.session.tools
    )
    assert not isinstance(opened, ErrorMetadata)

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_FOLDER_CHANGED
    assert world.session.launched == []
    assert result.usage is not None and result.usage.sent is False
    assert world.room.token(STEP_ID) == opened.token


async def test_another_model_at_the_yes_fails_the_step_and_launches_nothing() -> None:
    """The model of the question is the model of the execution: never an effect other than the one
    approved."""
    other = WorstCase(
        amount=Decimal("0.01"),
        currency="USD",
        model="another-model",
        input_tokens=1,
        output_tokens=1,
    )
    world = guided_world(worst=other)

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_ROUTE_CHANGED
    assert world.session.launched == []
    assert result.usage is not None and result.usage.sent is False


async def test_a_launch_that_does_not_start_fails_with_its_reason_and_spends_nothing() -> None:
    refused = ErrorMetadata(code=GUIDED_FOLDER_CHANGED, message="the folder changed")
    world = guided_world(session=FakeAgentSession(refused=refused))

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_FOLDER_CHANGED
    assert result.usage is not None and result.usage.sent is False
    assert not await world.room.is_open(STEP_ID)


async def test_the_duration_stops_the_session() -> None:
    world = guided_world(session=FakeAgentSession(forever), sleep=at_once)

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_DURATION
    assert world.session.interrupted == [STEP_ID]
    assert result.output["ending"] == "error_during_execution"


async def test_a_session_that_ends_with_an_error_of_its_own_fails() -> None:
    async def failing(plan: SessionPlan, host: SessionHost) -> SessionEnd:
        await host.started(("mcp__ela__act", "mcp__ela__read"))
        return finished("", "error_max_budget_usd")

    world = guided_world(session=FakeAgentSession(failing))

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.error is not None and result.error.code == GUIDED_FAILED
    assert result.output["reported_cost"] == "0"


async def test_a_session_launched_with_the_plan_ela_wrote() -> None:
    world = guided_world()

    result = await world.tool.execute(world.decision, world.arguments, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED
    ((reservation, plan),) = world.session.launched
    assert plan.model == MODEL and plan.max_tokens == GUIDED_MAX_TOKENS
    assert plan.gateway.endswith(f"/sessions/{STEP_ID}")
    assert "www.youtube.com" in plan.instructions and "at most 8 gestures" in plan.instructions
    assert plan.seconds == 120 and plan.goal == ARGUMENTS["goal"]
    assert reservation.amount == Decimal("0.05")
    assert (plan.read_description, plan.act_description) == (READ_DESCRIPTION, ACT_DESCRIPTION)


# ----------------------------------------------------------------------------------------
# The verifier: three conditions, each with its failure
# ----------------------------------------------------------------------------------------


async def verified(world: GuidedWorld, audit: FakeAuditLog, result: Any) -> list[str]:
    verifier = BrowserGuidedVerifier(world.room, world.session, audit)
    found = await verifier.verify(
        (GUIDED_CLOSED, GUIDED_RESERVATIONS_CLOSED, GUIDED_GESTURES_AUDITED),
        world.arguments,
        result,
    )
    return [failure.code for failure in found]


async def a_result(world: GuidedWorld) -> Any:
    result = await world.tool.execute(world.decision, world.arguments, FakeStop())
    return result.model_copy(update={"metadata": {"started_id": "x"}})


async def test_a_session_that_closed_with_its_calls_and_no_gesture_is_verified() -> None:
    world = guided_world()
    result = await a_result(world)

    assert await verified(world, FakeAuditLog(), result) == []


async def test_a_process_left_running_fails_closed() -> None:
    world = guided_world(session=FakeAgentSession(left_running=True))
    result = await a_result(world)

    assert await verified(world, FakeAuditLog(), result) == ["guided.left_running"]


async def test_a_result_that_does_not_close_its_reservation_fails() -> None:
    world = guided_world()
    result = await a_result(world)
    unclosed = result.model_copy(update={"metadata": {}})
    no_cost = result.model_copy(update={"usage": result.usage.model_copy(update={"cost": None})})

    assert await verified(world, FakeAuditLog(), unclosed) == ["guided.reservation_open"]
    assert await verified(world, FakeAuditLog(), no_cost) == ["guided.reservation_open"]


async def test_a_gesture_counted_with_no_task_in_the_audit_fails() -> None:
    world = guided_world()
    result = await a_result(world)
    counted = result.model_copy(update={"output": {**result.output, "looks": 1}})

    assert await verified(world, FakeAuditLog(), counted) == ["guided.gesture_unaudited"]


@pytest.mark.parametrize(
    "update",
    [{"task_id": None}, {"output": {"looks": "two"}}],
    ids=["no-task", "no-count"],
)
async def test_a_result_the_verifier_cannot_read_fails_every_condition_it_touches(
    update: dict[str, Any],
) -> None:
    world = guided_world()
    result = (await a_result(world)).model_copy(update=update)

    codes = await verified(world, FakeAuditLog(), result)

    assert "verification.arguments_invalid" in codes


def test_the_ids_of_the_example_are_the_session_s() -> None:
    assert (TaskId(TASK_ID), StepId(STEP_ID)) == (TASK_ID, STEP_ID)
    assert BROWSER_GUIDED == "browser.guided"


async def test_arguments_refused_after_the_yes_launch_nothing() -> None:
    world = guided_world()

    result = await world.tool.execute(world.decision, {**ARGUMENTS, "looks": 0}, FakeStop())

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert world.session.launched == []
