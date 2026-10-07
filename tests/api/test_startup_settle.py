"""The start-up settles what a planning left open (M14.2, decision 13 of the review).

Every gesture that ends a planning task settles the task it plans — the planning route, the run,
the no, the stop. Two ends are reached by no gesture: **a question that expires**, which only
``recover()`` writes, at start-up; and **a crash between the end of the planning task and the
settle**, which leaves the child ``COMPLETED`` and the parent ``PLANNING`` with no plan. The SPEC
had declared the second a constraint; the review removed it: the lifespan of ``app.py``, after
``recover()`` and ``close_every_open_step()``, settles every ``PLANNING`` parent whose planning
task has ended, found with a read of the repository.

Both states are built as production reaches them: the question by the route, the end of the
child by ELA's own runner — what a crash leaves, written by the code that would have written it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI

from ela.api import create_app
from ela.composition import build
from ela.domain import TaskId, TaskState
from ela.executive.planner import PLANNER_UNANSWERED, PlanAuthorKind, PlanningOutcome
from ela.testing.fakes import FakeClock, FakePower
from tests.api.planning import NOTE_PLAN, asked, created, said, with_a_model
from tests.api.reasons import World

S = TaskState


@asynccontextmanager
async def started(world: World, *, minutes: float = 0) -> AsyncIterator[FastAPI]:
    """A second start-up over the same database, ``minutes`` later, through its lifespan."""
    after = datetime.now(UTC) + timedelta(minutes=minutes)
    built = await build(world.settings, clock=FakeClock(after), power=FakePower())
    app = create_app(built)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        await built.aclose()


async def test_a_question_that_expired_at_start_up_fails_the_task_it_plans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)
        ttl = world.settings.core.approval_ttl.total_seconds() / 60

        async with started(world, minutes=ttl + 1) as app:
            (planning,) = app.state.planned

        assert planning.task.id == TaskId(UUID(task_id))
        assert planning.outcome is PlanningOutcome.FAILED
        assert planning.planning_task is not None
        assert planning.planning_task.state is S.EXPIRED
        assert PLANNER_UNANSWERED in (planning.reason or "")
        child = await world.ela.repository.get(TaskId(UUID(body["planning_task"]["id"])))
        assert child.state is S.EXPIRED
        assert (await world.ela.repository.get(TaskId(UUID(task_id)))).state is S.FAILED
        assert model.messages.calls == []


async def test_a_planning_task_that_completed_unsettled_plans_its_task_at_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)
        child = body["planning_task"]["id"]
        await world.client.post(
            f"/tasks/{child}/approve", json={"approval_id": body["approval"]["id"]}
        )
        # The crash: the runner walks the planning task to its end, and nobody settles the parent.
        await world.ela.runner.run(TaskId(UUID(child)))
        assert (await world.ela.repository.get(TaskId(UUID(child)))).state is S.COMPLETED
        assert (await world.ela.repository.get(TaskId(UUID(task_id)))).state is S.PLANNING

        async with started(world) as app:
            (planning,) = app.state.planned

        assert planning.outcome is PlanningOutcome.PLANNED
        task = await world.ela.repository.get(TaskId(UUID(task_id)))
        assert task.state is S.QUEUED
        assert (await world.ela.repository.plan(task.id)).author.by is PlanAuthorKind.MODEL
        assert len(model.messages.calls) == 1, "settled from the stored answer, not asked again"


async def test_a_start_up_with_nothing_left_open_settles_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        await asked(world.client, await created(world.client))

        async with started(world) as app:
            assert app.state.planned == ()
