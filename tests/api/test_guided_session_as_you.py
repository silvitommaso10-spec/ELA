"""A guided session with the profile, on a real ELA (M13.9, ADR 0063 §1 and §6).

The road of ``browser.guided_as_you`` from the plan to the end, with the browser of the profile a
fake and everything else ELA's own: the question of the session, which says that what goes to the
model is the user's own content; **a read its model writes, which runs with no question** — the
room's word, read when the step is decided (decision 29) —; **an act, which asks**, as every
``HIGH`` does; and both made on the browser with the profile, never on the empty one.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    AuditEventType,
    ErrorMetadata,
    ExecutionStatus,
    PermissionOutcome,
    TaskId,
    TaskState,
)
from ela.permissions import BROWSER_ACT_AS_YOU, BROWSER_READ_AS_YOU, Rule
from ela.testing.fakes import FakeAccountBrowser, FakePage
from ela.tools.guided import SESSION_AS_YOU
from tests.api.guided import Guided, Script, approve, gesture, guided, plan_of, question, run
from tests.api.test_guided_room import a_session

READ = {"site": "www.youtube.com", "path": "/feed/subscriptions"}
ACT = {
    "site": "www.youtube.com",
    "path": "/",
    "fill": [],
    "click": "button[type=submit]",
    "expect_text": "iscrizioni",
}


ALLOWED = PermissionOutcome.ALLOWED.value
ASKS = PermissionOutcome.REQUIRES_APPROVAL.value

WAIT_SECONDS = 20.0
"""How long a test waits for a session that should be ending: a red, and never a run that hangs."""


def tid(task: str) -> TaskId:
    return TaskId(UUID(task))


def the_profile() -> FakeAccountBrowser:
    return FakeAccountBrowser(FakePage(texts={None: "Le tue iscrizioni: tre canali"}))


async def planned(g: Guided) -> str:
    """A task with the plan of one session with the profile, queued: its id."""
    plan = plan_of()
    plan["steps"][0]["required_capabilities"] = [str(SESSION_AS_YOU.capability)]
    task = str(
        (await g.client.post("/tasks", json={"text": "guardare le iscrizioni"})).json()["id"]
    )
    response = await g.client.post(f"/tasks/{task}/plan", json=plan)
    assert response.status_code == 200, response.text
    return task


async def children(g: Guided, task: str) -> list[Any]:
    """The tasks of the session's gestures, in the order they were asked."""
    kids = [one for one in await g.ela.repository.tasks() if str(one.parent_id) == task]
    return sorted(kids, key=lambda one: one.goal)


async def waiting(g: Guided, task: str) -> Any:
    """The gesture of the session that waits for a yes: the session waits with it."""
    for _ in range(400):
        for kid in await children(g, task):
            if kid.state is TaskState.WAITING_APPROVAL:
                return kid
        await asyncio.sleep(0.01)
    raise AssertionError("no gesture of the session came to wait for a yes")


@asynccontextmanager
async def going[T](work: Coroutine[Any, Any, T]) -> AsyncIterator[asyncio.Future[T]]:
    """``work`` under way while the test answers it — and cancelled if the test leaves first: a
    red here is a red, and not a session left waiting for a yes nobody will give."""
    under_way = asyncio.ensure_future(work)
    try:
        yield under_way
    finally:
        under_way.cancel()
        await asyncio.gather(under_way, return_exceptions=True)


async def yes(g: Guided, child: Any) -> dict[str, Any]:
    """The user's yes to a gesture, and the run that makes it: the session waits for its end."""
    await approve(g, str(child.id))
    return await run(g, str(child.id))


async def no(g: Guided, child: Any) -> None:
    asked = await question(g, str(child.id))
    denied = await g.client.post(
        f"/tasks/{child.id}/deny", json={"approval_id": asked["id"], "reason": "no"}
    )
    assert denied.status_code == 200, denied.text


async def decided(g: Guided, child: Any) -> list[dict[str, Any]]:
    events = await g.ela.audit.read(task_id=TaskId(child.id))
    return [
        dict(event.payload)
        for event in events
        if event.event_type is AuditEventType.PERMISSION_DECIDED
    ]


async def test_the_question_of_a_session_with_the_profile_says_whose_content_goes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    accounts = the_profile()
    async with guided(monkeypatch, tmp_path, Script([]), accounts=accounts) as g:
        task = await planned(g)
        first = await run(g, task)
        asked = await question(g, task)

    assert first["outcome"] == "waiting_approval", first
    assert asked["capability_id"] == "browser.guided_as_you"
    assert asked["sites"] == ["www.youtube.com"]
    assert "go to anthropic" in asked["sends"]
    assert "your own content — your mail, your messages" in asked["sends"]
    assert g.sessions.launched == [] and accounts.opened == []


async def test_a_session_with_the_profile_reads_with_no_question_and_asks_for_its_act(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 29, end to end. The session was allowed once; the read its model writes is
    ``MEDIUM`` and would ask at every look — it does not, and the decision says which session
    covered it; the act is ``HIGH``, and the session waits for the user's own yes."""
    script = Script([gesture("read", **READ), gesture("act", **ACT)])
    accounts = the_profile()
    async with guided(monkeypatch, tmp_path, script, accounts=accounts) as g:
        task = await planned(g)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        async with going(run(g, task)) as running:
            act = await waiting(g, task)
            read, still = await children(g, task)
            pending = [one["task_id"] for one in (await g.client.get("/approvals")).json()]
            clicks_before_the_yes = list(accounts.clicks)
            made = await yes(g, act)
            ran = await asyncio.wait_for(running, WAIT_SECONDS)
        read_decided, act_decided = await decided(g, read), await decided(g, act)
        session_step = (await g.ela.repository.plan(tid(task))).steps[0].id
        rows = await g.ela.results.for_step(tid(task), session_step)
        ended = await children(g, task)

    assert ran["outcome"] == "completed", ran
    assert made["outcome"] == "completed", made
    assert still.id == act.id and read.state is TaskState.COMPLETED
    assert pending == [str(act.id)], "the read asked nobody, and the act asked"
    assert clicks_before_the_yes == [], "nothing is clicked before the yes of the act"

    (covered,) = read_decided
    assert (covered["outcome"], covered["rule"]) == (ALLOWED, Rule.SESSION.value)
    assert covered["session"] == str(session_step)
    assert [one["outcome"] for one in act_decided] == [ASKS, ALLOWED]
    assert all(one["rule"] != Rule.SESSION.value for one in act_decided)

    assert [kid.state for kid in ended] == [TaskState.COMPLETED, TaskState.COMPLETED]
    assert "Le tue iscrizioni" in script.read[0]
    assert script.read[1].startswith("gesture 2:") and "DENIED" not in script.read[1]
    assert accounts.opened == [
        "https://www.youtube.com/feed/subscriptions",
        "https://www.youtube.com/",
    ]
    assert accounts.clicks == ["button[type=submit]"]
    assert g.browser.opened == [] and g.browser.clicks == [], "the empty browser opens nothing"
    (outcome,) = [row for row in rows if row.status is ExecutionStatus.SUCCEEDED]
    assert (outcome.output["looks"], outcome.output["refused"]) == (2, 0)


async def test_an_act_with_the_profile_that_is_made_is_an_act_of_its_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The room says of each gesture whether it was the session's act and acted: for a session
    with the profile that is ``browser.act_as_you``, allowed and made — a read is not one, and
    neither is an act the user said no to."""
    accounts = the_profile()
    async with guided(monkeypatch, tmp_path, Script([]), accounts=accounts) as g:
        task, step, _ = await a_session(g, kind=SESSION_AS_YOU)
        looked = await g.ela.sessions.gesture(step, BROWSER_READ_AS_YOU, dict(READ))
        async with going(g.ela.sessions.gesture(step, BROWSER_ACT_AS_YOU, dict(ACT))) as making:
            act = await waiting(g, str(task))
            await yes(g, act)
            made = await asyncio.wait_for(making, WAIT_SECONDS)
        async with going(g.ela.sessions.gesture(step, BROWSER_ACT_AS_YOU, dict(ACT))) as making:
            again = await waiting(g, str(task))
            await no(g, again)
            refused = await asyncio.wait_for(making, WAIT_SECONDS)
        tally = await g.ela.sessions.close(step, reason="done")

    assert (looked.state, looked.acted) == (TaskState.COMPLETED, False)
    assert (made.state, made.acted) == (TaskState.COMPLETED, True)
    assert (refused.state, refused.acted) == (TaskState.DENIED, False)
    assert (tally.looks, tally.refused, tally.acts) == (3, 1, 2), "an act asked is an act counted"
    assert accounts.clicks == ["button[type=submit]"], "the act the user refused clicked nothing"


# ----------------------------------------------------------------------------------------
# A session that is ending covers nothing (re-read of 2026-10-11, defect 2)
# ----------------------------------------------------------------------------------------


async def ended_by(g: Guided, how: str, task: Any, step: Any) -> None:
    """The three ways ELA ends a session before its tool has closed the room."""
    if how == "the-ferma-of-its-task":
        await g.ela.sessions.stop_gestures(task, reason="ferma")
    else:
        await g.ela.sessions.halt(
            step, ErrorMetadata(code="guided.cost", message="a call the budget refused")
        )


@pytest.mark.parametrize("how", ["the-ferma-of-its-task", "a-halt-of-ela-s"])
async def test_a_session_ela_is_ending_covers_no_read_and_makes_no_gesture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, how: str
) -> None:
    """ADR 0063 §1: «una sessione è aperta nella stanza solo mentre il suo step gira». Between
    the «ferma» — or a halt — and the moment the tool closes the room, a read the model had
    pending arrived, was planned as a child of a task already stopped, and ran **as the user
    with no question**. The room's word is over as soon as ELA ends the session, and so are its
    gestures."""
    accounts = the_profile()
    async with guided(monkeypatch, tmp_path, Script([]), accounts=accounts) as g:
        task, step, _ = await a_session(g, kind=SESSION_AS_YOU)
        open_before = await g.ela.sessions.attest(step)
        await ended_by(g, how, task, step)

        attested = await g.ela.sessions.attest(step)
        made = await g.ela.sessions.gesture(step, BROWSER_READ_AS_YOU, dict(READ))
        kids = await children(g, str(task))
        tally = await g.ela.sessions.close(step, reason="done")

    assert open_before is not None, "the precondition: the session was open, and attested"
    assert attested is None, "no word for a session ELA is ending"
    assert made.state is TaskState.CANCELLED and "is over" in made.text
    assert kids == [], "no child is planned for a gesture that arrives after the end"
    assert accounts.opened == [], "and no page is opened as the user"
    assert tally.looks == 0
