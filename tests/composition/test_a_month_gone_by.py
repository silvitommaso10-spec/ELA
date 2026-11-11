"""A month gone by, on a model the list no longer has (M14.6b, decision 11; ADR 0067 §6).

What the real database holds since 2026-10-07: rows of October on the id of Haiku 4.5, which the
price list no longer has — a ``STARTED`` closed by a call with its cost written, one closed by a
call that was not sent, and the node that went silent at step 6 of that day, its ``STARTED`` still
open. Built here with the real stores, on a database of a folder of the test, never ELA's. The
ledger of the month, the recovery at startup, ``ela spend`` and the results of a task read them
**with the amounts written**: nothing prices them again from ``PRICES``, where Haiku 4.5 is no
longer — a reader that did would find no price, and these tests would see it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import (
    CapabilityId,
    ErrorMetadata,
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    Ledger,
    ProviderUsage,
    StepId,
    Task,
    TaskId,
    TaskState,
    WorstCase,
)
from ela.ports import PROVIDER_UNREACHABLE, STARTED_ID
from ela.providers.anthropic.models import MODELS
from ela.providers.anthropic.pricing import PRICES
from ela.testing.fakes import FakeClock, FakePower
from tests.api.support import AUTHORIZED, BASE
from tests.composition.support import create_schema, declare
from tests.domain.examples import HAIKU_4_5_ID

OCTOBER_7: Final = datetime(2026, 10, 7, 19, 30, tzinfo=UTC)
"""The evening of the proof of M14.1: the calls on Haiku 4.5 of the guide's section 23."""
NOVEMBER_11: Final = datetime(2026, 11, 11, 9, tzinfo=UTC)
MODEL_COMPLETE: Final = CapabilityId("model.complete")
ANSWER: Final = "Un tetto tiene la spesa del mese sotto un limite."

SHORT: Final = WorstCase(
    amount=Decimal("0.216384"),
    currency="USD",
    model=HAIKU_4_5_ID,
    input_tokens=195_904,
    output_tokens=4_096,
)
"""The worst case written on 2026-10-07 for a call with the default output (ADR 0057 §2)."""
LONG: Final = SHORT.model_copy(
    update={"amount": Decimal("0.232768"), "input_tokens": 191_808, "output_tokens": 8_192}
)
"""The long plan of step 6, the node that went silent: 8192 out."""
COST: Final = Decimal("0.000315")
"""What the call that answered cost, as the result wrote it: 40 tokens in and 55 out at 1 and 5
dollars per million, the price of that day."""


def _id(number: int) -> UUID:
    return UUID(f"00000000-0000-4000-8000-00000000a{number:03d}")


ANSWERED, NOT_SENT, SILENT = TaskId(_id(1)), TaskId(_id(2)), TaskId(_id(3))


def task(task_id: TaskId, state: TaskState) -> Task:
    return Task(
        id=task_id,
        created_at=OCTOBER_7,
        goal="chiedere una cosa al modello economico",
        state=state,
        finished_at=OCTOBER_7 + timedelta(minutes=2),
    )


def started(task_id: TaskId, number: int, worst: WorstCase) -> ExecutionResult:
    """The row the gate writes before the call: the reservation, with its worst case."""
    return ExecutionResult(
        id=ExecutionId(_id(100 + number)),
        created_at=OCTOBER_7,
        capability_id=MODEL_COMPLETE,
        status=ExecutionStatus.STARTED,
        task_id=task_id,
        step_id=StepId(_id(200 + number)),
        tool_name="model-complete",
        worst_case=worst,
    )


UNREACHABLE: Final = ErrorMetadata(
    code=PROVIDER_UNREACHABLE,
    message="the request did not leave this machine",
    tool_name="model-complete",
)


def closing(
    reservation: ExecutionResult,
    number: int,
    usage: ProviderUsage,
    error: ErrorMetadata | None = None,
) -> ExecutionResult:
    """The outcome that names the reservation it closes: answered, or failed with ``error``."""
    status = ExecutionStatus.SUCCEEDED if error is None else ExecutionStatus.FAILED
    return ExecutionResult(
        id=ExecutionId(_id(300 + number)),
        created_at=OCTOBER_7 + timedelta(seconds=3),
        capability_id=MODEL_COMPLETE,
        status=status,
        task_id=reservation.task_id,
        step_id=reservation.step_id,
        tool_name="model-complete",
        output={
            "provider": "anthropic",
            "model": HAIKU_4_5_ID,
            "finish_reason": "end_turn",
            "profile": "routine",
            "skipped": [],
            "workspace": None,
            **({"output": ANSWER} if usage.sent else {}),
        },
        error=error,
        usage=usage,
        metadata={STARTED_ID: str(reservation.id)},
    )


def october() -> tuple[tuple[Task, ...], tuple[ExecutionResult, ...]]:
    answered = started(ANSWERED, 1, SHORT)
    not_sent = started(NOT_SENT, 2, SHORT)
    silent = started(SILENT, 3, LONG)
    paid = ProviderUsage(input_tokens=40, output_tokens=55, cost=COST, currency="USD", sent=True)
    unsent = ProviderUsage(input_tokens=0, output_tokens=0, sent=False)
    tasks = (
        task(ANSWERED, TaskState.COMPLETED),
        task(NOT_SENT, TaskState.FAILED),
        task(SILENT, TaskState.FAILED),
    )
    rows = (
        answered,
        closing(answered, 1, paid),
        not_sent,
        closing(not_sent, 2, unsent, UNREACHABLE),
        silent,
    )
    return tasks, rows


OCTOBER_LEDGER: Final = Ledger(spent=COST, reserved=LONG.amount or Decimal(0), open=1, unknown=0)
"""Spent: the cost written. Held: the silent node's worst case. The call not sent: nothing."""


@dataclass(frozen=True)
class World:
    ela: Ela
    clock: FakeClock
    client: AsyncClient
    before: dict[TaskId, tuple[ExecutionResult, ...]]
    """Each task's rows as they were written, read before ELA started."""


@asynccontextmanager
async def month_gone_by(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[World]:
    """ELA started over October's rows the way ``ela serve`` starts it: ``build``, then the
    lifespan of the API, which runs the recovery (``src/ela/api/app.py``)."""
    declare(monkeypatch, tmp_path)
    settings = Settings.load()
    await create_schema(settings.persistence.db_url)
    clock = FakeClock(OCTOBER_7 + timedelta(hours=1))
    ela = await build(settings, clock=clock, power=FakePower())
    try:
        tasks, rows = october()
        for one in tasks:
            await ela.repository.add(one)
        for row in rows:
            await ela.results.add(row)
        before = {one.id: await ela.results.for_task(one.id) for one in tasks}
        application = create_app(ela)
        async with (
            application.router.lifespan_context(application),
            AsyncClient(
                transport=ASGITransport(app=application), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield World(ela, clock, client, before)
    finally:
        await ela.aclose()


def test_the_model_of_october_is_no_model_of_the_list() -> None:
    """The precondition: what these rows name, the list has not — so a reader that priced them
    again would find nothing to price them with."""
    assert HAIKU_4_5_ID not in MODELS and HAIKU_4_5_ID not in PRICES


async def test_the_ledger_of_october_is_the_amounts_written_and_november_s_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with month_gone_by(monkeypatch, tmp_path) as world:
        month, held = await world.ela.spending.ledger(OCTOBER_7)
        assert month.label == "2026-10"
        assert held == OCTOBER_LEDGER

        month, held = await world.ela.spending.ledger(NOVEMBER_11)
        assert month.label == "2026-11"
        assert held == Ledger(spent=Decimal(0), reserved=Decimal(0))


async def test_the_recovery_at_startup_leaves_the_rows_as_they_are(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Worst cases and costs included: the start-up of the API ran over them."""
    async with month_gone_by(monkeypatch, tmp_path) as world:
        after = {task_id: await world.ela.results.for_task(task_id) for task_id in world.before}

        assert after == world.before
        assert [(await world.ela.repository.get(task_id)).state for task_id in world.before] == [
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.FAILED,
        ]


async def test_ela_spend_says_october_s_numbers_in_october_and_nothing_in_november(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``GET /spend`` is what ``ela spend`` prints, on ELA's clock: the month it reads is now's."""
    async with month_gone_by(monkeypatch, tmp_path) as world:
        in_october = (await world.client.get("/spend")).json()
        world.clock.advance(NOVEMBER_11 - world.clock.now())
        in_november = (await world.client.get("/spend")).json()

    assert in_october["month"] == "2026-10"
    assert (Decimal(in_october["spent"]), Decimal(in_october["reserved"])) == (COST, LONG.amount)
    assert in_november["month"] == "2026-11"
    assert (Decimal(in_november["spent"]), Decimal(in_november["reserved"])) == (0, 0)


def answered_in(results: list[dict[str, Any]]) -> dict[str, Any]:
    (found,) = [one for one in results if one["status"] == ExecutionStatus.SUCCEEDED.value]
    return found


async def test_the_results_of_a_task_have_the_model_and_the_cost_written(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``GET /tasks/{id}/results`` — what ``ela task results`` prints — has the model and the cost
    as the call wrote them. ``GET /tasks/{id}`` — what ``ela task show`` prints — has the state and
    neither: no view shows a reservation's worst case; only the ledger counts it."""
    async with month_gone_by(monkeypatch, tmp_path) as world:
        results = (await world.client.get(f"/tasks/{ANSWERED}/results")).json()
        detail = (await world.client.get(f"/tasks/{ANSWERED}")).json()

    found = answered_in(results)
    assert found["output"]["model"] == HAIKU_4_5_ID
    assert Decimal(str(found["usage"]["cost"])) == COST
    assert all("worst_case" not in one for one in results)
    assert detail["state"] == TaskState.COMPLETED.value
    assert not {"model", "cost", "usage", "worst_case"} & set(detail)
