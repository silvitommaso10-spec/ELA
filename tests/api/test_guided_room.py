"""The room of the guided sessions, on a real ELA (M14.3, ADR 0060): what the road of the API does
not reach by itself — a gesture whose session is interrupted while the runner walks it, the stop
carried down to live gestures, the children of an ended session closed at start-up, and the edges
of a call for a session that is not open.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from ela.domain import (
    ExecutionId,
    ExecutionResult,
    ExecutionStatus,
    PlanAuthor,
    PlanAuthorKind,
    StepId,
    TaskId,
    TaskState,
    WorstCase,
)
from ela.executive.sessions import START_WAIT_SECONDS, gesture_key
from ela.permissions import BROWSER_GUIDED, BROWSER_READ
from ela.ports import (
    GUIDED_FOLDER_CHANGED,
    GUIDED_SESSION_GONE,
    GUIDED_UNCHECKED,
    GUIDED_UNRESERVED,
    OpenedSession,
)
from ela.providers.anthropic.models import HAIKU_5_5
from ela.tasks.engine import child_id
from ela.testing.fakes import FAKE_SESSION_TOOLS
from tests.api.guided import Guided, Script, body_of, guided, planned


def tid(task: str) -> TaskId:
    return TaskId(UUID(task))


async def a_session(g: Guided, *, reserve: bool = True) -> tuple[TaskId, StepId, Any]:
    """A planned session's task, its step, and — with ``reserve`` — the ``STARTED`` record the cap
    writes for it, then the session opened in the room."""
    task = tid(await planned(g))
    plan = await g.ela.repository.plan(task)
    step = plan.steps[0].id
    if reserve:
        record = ExecutionResult(
            id=ExecutionId(uuid4()),
            created_at=g.ela.clock.now(),
            capability_id=BROWSER_GUIDED,
            status=ExecutionStatus.STARTED,
            task_id=task,
            step_id=step,
            tool_name="browser-guided",
        )
        worst = WorstCase(
            amount=Decimal("0.60"),
            currency="USD",
            model=HAIKU_5_5,
            input_tokens=991_808,
            output_tokens=8_192,
            per_call=True,
        )
        assert await g.ela.spending.reserve(record, worst) is None
    opened = await g.ela.sessions.open(
        task, step, sites=("www.youtube.com",), tools=FAKE_SESSION_TOOLS
    )
    return task, step, opened


async def test_a_step_with_no_reservation_opens_no_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        _, step, opened = await a_session(g, reserve=False)

    assert not isinstance(opened, OpenedSession)
    assert opened.code == GUIDED_UNRESERVED
    assert not await g.ela.sessions.is_open(step)


async def test_a_gesture_whose_session_is_interrupted_is_walked_to_its_end_anyway(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The interrupt of a session cancels the call of its in-process tool: the walk of the child
    is not cancelled with it — a runner cancelled halfway would leave a step open and its lock
    released (shield). The child ends where its own stop finds it, and the lock is let go there."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task, step, _ = await a_session(g)
        g.browser.launch_reached, g.browser.launch_released = asyncio.Event(), asyncio.Event()
        asking = asyncio.ensure_future(
            g.ela.sessions.gesture(step, BROWSER_READ, {"site": "www.youtube.com", "path": "/"})
        )
        await g.browser.launch_reached.wait()
        asking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asking
        g.browser.launch_released.set()
        child = child_id(task, gesture_key(1, step))
        for _ in range(500):
            ended = (await g.ela.repository.get(child)).state is TaskState.COMPLETED
            if ended and child not in g.ela.running:
                break
            await asyncio.sleep(0.01)
        found = await g.ela.repository.get(child)

    assert found.state is TaskState.COMPLETED
    assert child not in g.ela.running


async def test_the_stop_goes_down_to_the_live_gestures_of_the_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task, step, _ = await a_session(g)
        acting = asyncio.ensure_future(
            g.ela.sessions.gesture(
                step,
                BROWSER_GUIDED.__class__("browser.act"),
                {
                    "site": "www.youtube.com",
                    "path": "/",
                    "fill": [],
                    "click": "button",
                    "expect_text": "ok",
                },
            )
        )
        child = child_id(task, gesture_key(1, step))
        for _ in range(500):
            try:
                if (await g.ela.repository.get(child)).state is TaskState.WAITING_APPROVAL:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.01)
        stopped = await g.ela.sessions.stop_gestures(task, reason="basta")
        elsewhere = await g.ela.sessions.stop_gestures(TaskId(uuid4()), reason="basta")
        done = await acting

    assert [one.id for one in stopped] == [child]
    assert stopped[0].state is TaskState.CANCELLED
    assert elsewhere == ()
    assert done.state is TaskState.CANCELLED
    assert "CANCELLED" in done.text


async def test_the_gestures_of_an_ended_session_are_stopped_at_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A crash, a restart with a question open: the room reads the repository and stops the
    gestures still alive whose session's task has ended — and none of anything else."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task, step, _ = await a_session(g)
        engine = g.ela.engine
        asked = await engine.create_child(task, key=gesture_key(1, step), goal="a gesture")
        await engine.start_planning(asked.id)
        bare = await engine.create_child(task, key=gesture_key(2, step), goal="a gesture")
        planning = await engine.create_child(task, key="planning", goal="a planning task")
        lone = tid(await planned(g))
        alive = await engine.create_child(lone, key=gesture_key(1, step), goal="a gesture")
        plan_of_asked = (await g.ela.repository.plan(task)).model_copy(
            update={
                "id": uuid4(),
                "task_id": asked.id,
                "author": PlanAuthor(by=PlanAuthorKind.SESSION, session=step, model=HAIKU_5_5),
            }
        )
        await engine.plan(asked.id, plan_of_asked)
        await engine.cancel(task, reason="the session's task ended")

        stopped = await g.ela.sessions.close_orphans()

    assert {one.id for one in stopped} == {asked.id, bare.id}
    assert all(one.state is TaskState.CANCELLED for one in stopped)
    assert planning.id not in {one.id for one in stopped}
    assert alive.id not in {one.id for one in stopped}


async def test_a_second_session_of_a_step_id_already_open_is_refused_and_the_first_is_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A plan by hand carries the caller's step ids (``StepIn``), so the same file sent to two
    tasks gives two sessions the same step — the identity of a session's path, of its folder
    (``<sessions>/<step>``) and of its place in the room. Found writing the proof by hand of M14.3,
    whose plans are files: the second ``open`` overwrote the first session in the room, and the
    first lost its token, its budget and its gestures. The second is refused before it touches
    anything, with the code the adapter gives a folder it cannot prepare."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        first, step, opened = await a_session(g)
        assert isinstance(opened, OpenedSession)
        second, same, refused = await a_session(g)

    assert same == step and second != first
    assert not isinstance(refused, OpenedSession)
    assert refused.code == GUIDED_FOLDER_CHANGED
    assert g.ela.sessions.token(step) == opened.token


async def test_a_call_for_a_session_that_is_not_open_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        nobody = StepId(uuid4())
        relayed = await g.ela.sessions.relay(nobody, b"{}", None)
        started = await g.ela.sessions.start(nobody, ())
        gone = await g.ela.sessions.halted(nobody)
        late = await g.ela.sessions.gesture(nobody, BROWSER_READ, {})

    assert not isinstance(relayed, OpenedSession) and relayed.code == GUIDED_SESSION_GONE  # type: ignore[union-attr]
    assert started is not None and started.code == GUIDED_SESSION_GONE
    assert gone.code == GUIDED_SESSION_GONE
    assert late.state is TaskState.CANCELLED
    assert g.ela.sessions.token(nobody) is None


async def test_a_call_before_the_start_was_checked_waits_and_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 22: no call is admitted before the start's check. A start that never comes is a
    session halted, not a call let out."""
    monkeypatch.setattr("ela.executive.sessions.START_WAIT_SECONDS", 0.01)
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        _, step, opened = await a_session(g)
        assert isinstance(opened, OpenedSession)
        plan_like = type(
            "Plan", (), {"model": HAIKU_5_5, "max_tokens": 8192, "instructions": "", "goal": ""}
        )()
        body = __import__("json").dumps(body_of(plan_like)).encode()  # type: ignore[arg-type]
        relayed = await g.ela.sessions.relay(step, body, None)
        halted = await g.ela.sessions.halted(step)

    assert START_WAIT_SECONDS > 0
    assert not isinstance(relayed, OpenedSession) and relayed.code == GUIDED_UNCHECKED  # type: ignore[union-attr]
    assert halted.code == GUIDED_UNCHECKED
    assert g.anthropic.received == []


async def test_a_gesture_the_room_does_not_know_or_cannot_plan_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        _, step, _ = await a_session(g)
        unknown = await g.ela.sessions.gesture(step, BROWSER_GUIDED, {})
        unplannable = await g.ela.sessions.gesture(
            step,
            BROWSER_READ,
            {"site": "www.youtube.com", "path": object()},  # type: ignore[dict-item]
        )
        tally = await g.ela.sessions.close(step, reason="done")

    assert unknown.state is TaskState.DENIED and "no such gesture" in unknown.text
    assert unplannable.state is TaskState.DENIED and "can plan" in unplannable.text
    assert (tally.looks, tally.refused) == (2, 2)


async def test_the_room_is_bound_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        with pytest.raises(RuntimeError, match="bound already"):
            g.ela.sessions.bind(runner=g.ela.runner, verifiers=g.ela.verifiers)


async def test_a_gesture_whose_child_someone_else_walks_waits_for_its_end(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The lock of ``run`` taken by another — the route of a yes walking the child —: the room
    does not walk it a second time, and waits for its end."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task, step, _ = await a_session(g)
        child = child_id(task, gesture_key(1, step))
        g.ela.running.add(child)
        asking = asyncio.ensure_future(
            g.ela.sessions.gesture(step, BROWSER_READ, {"site": "www.youtube.com", "path": "/"})
        )
        for _ in range(500):
            try:
                if (await g.ela.repository.get(child)).state is TaskState.QUEUED:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.01)
        assert g.browser.opened == [], "the room did not walk a child somebody else holds"
        await g.ela.engine.cancel(child, reason="the other walker stopped it")
        done = await asking
        g.ela.running.discard(child)

    assert done.state is TaskState.CANCELLED
