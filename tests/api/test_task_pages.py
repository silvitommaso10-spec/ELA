"""A page a task keeps between two of its steps, through the whole of ELA (M13.10, ADR 0065 §3).

One ELA as ``build`` makes it, with the browser of ``ela.testing``: the room is the real one, over
the real database, and so are the executor, the question and the engine's stop of a task.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from ela.testing.fakes import FakeAccountBrowser
from tests.api.guided import Guided, Script, approve, guided, question, run

READ_ID = "c4c2d7e1-5a3f-4b69-8d20-0000000000a1"
ACT_ID = "c4c2d7e1-5a3f-4b69-8d20-0000000000a2"


def read(capability: str = "browser.read") -> dict[str, Any]:
    return {
        "id": READ_ID,
        "goal": "aprire il modulo",
        "required_capabilities": [capability],
        "arguments": {"site": "httpbin.org", "path": "/forms/post", "purpose": "la prova"},
        "risk": "LOW" if capability == "browser.read" else "MEDIUM",
        "expected_result": "il modulo",
        "success_conditions": ["browser.text_matches"],
        "requires_authorization": capability != "browser.read",
    }


def act(capability: str = "browser.act", **arguments: object) -> dict[str, Any]:
    return {
        "id": ACT_ID,
        "goal": "mandare il modulo",
        "required_capabilities": [capability],
        "arguments": {
            "site": "httpbin.org",
            "continues": True,
            "fill": [["input[name=custname]", "ELA prova"]],
            "click": "form button",
            "expect_text": "ELA prova",
            "purpose": "la prova",
            **arguments,
        },
        "risk": "HIGH",
        "expected_result": "il modulo mandato",
        "success_conditions": ["browser.expect_visible"],
        "requires_authorization": True,
        "dependencies": [READ_ID],
    }


async def planned(g: Guided, *steps: dict[str, Any]) -> str:
    task = str((await g.client.post("/tasks", json={"text": "una prova"})).json()["id"])
    attached = await g.client.post(
        f"/tasks/{task}/plan", json={"goal": "una prova", "steps": list(steps)}
    )
    assert attached.status_code == 200, attached.text
    return task


async def test_two_tasks_with_the_same_plan_each_continue_on_their_own_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criteria 13 and 16: the question of the step that continues says so and where the page is
    — host and path, never the query —, and the yes to one task's step takes that task's page."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        one = await planned(g, read(), act())
        other = await planned(g, read(), act())
        assert (await run(g, one))["outcome"] == "waiting_approval"
        assert (await run(g, other))["outcome"] == "waiting_approval"
        asked = await question(g, other)
        assert g.browser.holding == ["page-1", "page-2"]

        await approve(g, other)
        ran = await run(g, other)

        assert asked["address"] == "httpbin.org/forms/post"
        assert asked["does"].startswith("opens no page: it fills in and clicks on the page")
        assert ran["outcome"] == "completed", ran
        assert g.browser.resumed == ["page-2"]
        assert g.browser.opened == ["https://httpbin.org/forms/post"] * 2, "no page opened again"
        waiting = (await g.client.get("/browser")).json()["waiting"]
        assert [page["task"] for page in waiting] == [one]


async def test_a_step_that_continues_without_a_page_asks_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 15: nobody is asked a yes that cannot help."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        alone = act()
        alone.pop("dependencies")
        task = await planned(g, alone)

        ran = await run(g, task)

        assert ran["outcome"] == "failed" and "browser.no_page_to_continue" in ran["reason"], ran
        assert (await g.client.get("/approvals")).json() == []
        assert g.browser.opened == [] and g.browser.resumed == []


@pytest.mark.parametrize("end", ["deny", "cancel", "complete"])
async def test_a_task_that_ends_leaves_no_page_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, end: str
) -> None:
    """Criterion 17, through the engine: a no, a stop and a completion each end the task, and the
    room hears the end with nobody calling it."""
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task = await planned(g, read(), act())
        assert (await run(g, task))["outcome"] == "waiting_approval"
        assert g.browser.holding == ["page-1"] and "page-1" not in g.browser.closed
        asked = await question(g, task)

        if end == "deny":
            answered = await g.client.post(f"/tasks/{task}/deny", json={"approval_id": asked["id"]})
            assert answered.status_code == 200, answered.text
        elif end == "cancel":
            stopped = await g.client.post(f"/tasks/{task}/cancel", json={"reason": "basta"})
            assert stopped.status_code == 200, stopped.text
        else:
            await approve(g, task)
            assert (await run(g, task))["outcome"] == "completed"
        for _ in range(50):
            if await g.browser.where("page-1") is None:
                break
            await asyncio.sleep(0.01)

        assert await g.browser.where("page-1") is None, "the page is open no more"
        assert (await g.client.get("/browser")).json()["waiting"] == []


async def test_a_task_that_fails_leaves_no_page_behind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with guided(monkeypatch, tmp_path, Script([])) as g:
        task = await planned(g, read(), act())
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        g.browser.page.shown = False  # the text the action waits for never appears

        ran = await run(g, task)

        assert ran["outcome"] == "failed", ran
        for _ in range(50):
            if not (await g.client.get("/browser")).json()["waiting"]:
                break
            await asyncio.sleep(0.01)
        assert (await g.client.get("/browser")).json()["waiting"] == []


async def test_the_status_of_the_browser_says_which_task_keeps_a_page_until_when_and_how_it_ends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 19 (decision 27): the word is ``task``, with the id of the task, beside
    ``step``."""
    accounts = FakeAccountBrowser()
    async with guided(monkeypatch, tmp_path, Script([]), accounts=accounts) as g:
        task = await planned(g, read("browser.read_as_you"), act("browser.act_as_you"))
        assert (await run(g, task))["outcome"] == "waiting_approval"
        await approve(g, task)
        assert (await run(g, task))["outcome"] == "waiting_approval"
        asked = await question(g, task)

        said = (await g.client.get("/browser")).json()

        assert said["state"] == "task"
        assert f"task {task}" in said["message"]
        assert f"ela task cancel {task}" in said["message"]
        (waiting,) = said["waiting"]
        assert waiting == {
            "task": task,
            "profile": True,
            "until": asked["expires_at"],
            "stop": f"ela task cancel {task}",
        }
