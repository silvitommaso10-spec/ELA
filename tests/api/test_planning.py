"""``POST /tasks/{task_id}/planning``: ELA's Planner over HTTP (M14.2, ADR 0058).

The route asks the Planner, and the Planner asks nobody: the call that writes a plan is a
``model.complete`` step of a planning task — a child of the task, on the road of every call: the
Guardian, the question with its worst case, the yes, the cap in the ``STARTED``, the verifier, the
audit. The task is settled from where its planning task ended — ``QUEUED`` with the model's plan,
or closed with its planning task's reason — by whichever gesture ended it: the planning route, the
``run`` of the planning task, the no, the stop. **Nothing is started** (decision H): the run of a
plan the model wrote is the user's, after reading it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

from ela.api.approvals import answered_and_resumed
from ela.api.schemas import ApprovalOut
from ela.api.security import Identity, Kind
from ela.domain import DeviceId, DeviceRole, TaskId, TaskState
from ela.executive.planner import PLANNING_OUTPUT_TOKENS
from ela.executive.spending import CAP_VARIABLE
from ela.providers.anthropic.models import OPUS_5_5
from tests.api.planning import GOAL, NO_PLAN, NOTE_PLAN, asked, created, said, with_a_model
from tests.api.reasons import World
from tests.api.support import echo_plan
from tests.executive.planning import NO_PLAN_REASON, NOTE_BODY

S = TaskState
WORST = "4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out"


async def yes(client: AsyncClient, body: dict[str, Any]) -> None:
    child = body["planning_task"]["id"]
    response = await client.post(
        f"/tasks/{child}/approve", json={"approval_id": body["approval"]["id"]}
    )
    assert response.status_code == 200, response.text


async def no(client: AsyncClient, body: dict[str, Any]) -> dict[str, Any]:
    child = body["planning_task"]["id"]
    response = await client.post(
        f"/tasks/{child}/deny", json={"approval_id": body["approval"]["id"]}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def state_of(client: AsyncClient, task_id: str) -> str:
    return str((await client.get(f"/tasks/{task_id}")).json()["state"])


# ----------------------------------------------------------------------------------------
# No cap: what everybody who clones the repository gets
# ----------------------------------------------------------------------------------------


async def test_without_a_cap_the_planning_is_denied_and_nobody_is_asked(
    client: AsyncClient,
) -> None:
    task_id = await created(client)

    response = await client.post(f"/tasks/{task_id}/planning")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "denied"
    assert body["task"]["state"] == S.DENIED.value
    assert body["planning_task"]["state"] == S.DENIED.value
    assert body["planning_task"]["parent_id"] == task_id
    assert body["reason"].startswith("deny_by_planning: PLANNING -> DENIED (the planning task ")
    assert CAP_VARIABLE in body["reason"]
    assert body["approval"] is None
    assert (await client.get("/approvals")).json() == []


# ----------------------------------------------------------------------------------------
# The question, the yes, the call
# ----------------------------------------------------------------------------------------


async def test_the_first_call_asks_for_the_yes_with_the_worst_case_of_the_planner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)

        body = await asked(world.client, task_id)

        assert body["task"]["state"] == S.PLANNING.value
        assert body["task"]["planning_task_id"] == body["planning_task"]["id"]
        assert body["planning_task"]["state"] == S.WAITING_APPROVAL.value
        assert body["approval"]["task_id"] == body["planning_task"]["id"]
        assert body["approval"]["capability_id"] == "model.complete"
        assert body["approval"]["worst_case"] == WORST
        assert model.messages.calls == [], "nothing leaves before the yes"


async def test_asked_again_before_the_yes_it_answers_the_same_question(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)
        first = await asked(world.client, task_id)

        again = await asked(world.client, task_id)

        assert again["planning_task"]["id"] == first["planning_task"]["id"]
        assert again["approval"]["id"] == first["approval"]["id"]
        assert len((await world.client.get("/approvals")).json()) == 1
        assert model.messages.calls == []


async def test_after_the_yes_the_plan_is_the_models_and_the_task_is_queued_not_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)
        await yes(world.client, await asked(world.client, task_id))

        response = await world.client.post(f"/tasks/{task_id}/planning")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["outcome"] == "planned"
        assert body["planning_task"]["state"] == S.COMPLETED.value
        task = body["task"]
        assert task["state"] == S.QUEUED.value
        assert task["plan_author"]["by"] == "MODEL"
        assert task["plan_author"]["model"] == OPUS_5_5
        assert task["plan_author"]["result_id"] is not None
        assert [step["required_capabilities"] for step in task["steps"]] == [
            ["core.echo"],
            ["workspace.write_note"],
        ]
        assert task["steps"][1]["arguments"]["body"] == NOTE_BODY
        assert (await world.client.get(f"/tasks/{task_id}/results")).json() == []
        assert len(model.messages.calls) == 1


async def test_what_leaves_is_the_goal_the_instructions_and_the_catalogue_and_no_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)
        await yes(world.client, await asked(world.client, task_id))

        await world.client.post(f"/tasks/{task_id}/planning")

        (call,) = model.messages.calls
        sent = json.dumps(call, ensure_ascii=False)
        assert call["model"] == OPUS_5_5
        assert call["max_tokens"] == PLANNING_OUTPUT_TOKENS
        assert GOAL in sent
        assert "workspace.write_note" in sent
        assert str(tmp_path) not in sent, "no folder of this machine leaves (§57)"
        assert str(world.settings.filesystem.fs_root) not in sent


async def test_the_run_of_the_planning_task_settles_the_task_it_plans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, _):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)
        await yes(world.client, body)

        run = await world.client.post(f"/tasks/{body['planning_task']['id']}/run")

        assert run.status_code == 200, run.text
        assert run.json()["outcome"] == "completed"
        assert await state_of(world.client, task_id) == S.QUEUED.value


async def test_a_no_plan_fails_the_task_and_its_reason_is_read_and_never_audited(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NO_PLAN)) as (world, _):
        task_id = await created(world.client)
        await yes(world.client, await asked(world.client, task_id))

        body = (await world.client.post(f"/tasks/{task_id}/planning")).json()

        assert body["outcome"] == "failed"
        assert body["task"]["state"] == S.FAILED.value
        assert body["no_plan"] == NO_PLAN_REASON
        assert "planner.no_plan" in body["reason"]
        assert (await world.client.get(f"/tasks/{task_id}")).json()["no_plan"] == NO_PLAN_REASON
        for one in (task_id, body["planning_task"]["id"]):
            trail = (await world.client.get("/audit", params={"task_id": one})).text
            assert NO_PLAN_REASON not in trail


# ----------------------------------------------------------------------------------------
# The no, the stop, the lock
# ----------------------------------------------------------------------------------------


async def test_a_no_to_the_call_denies_the_task_it_plans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        answered = await no(world.client, body)

        assert answered["state"] == S.DENIED.value
        task = (await world.client.post(f"/tasks/{task_id}/planning")).json()
        assert task["outcome"] == "denied"
        assert task["reason"].startswith("deny_by_planning: PLANNING -> DENIED (the planning task ")
        assert model.messages.calls == []


async def test_a_stopped_task_stops_its_planning_task_and_its_question(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        stopped = await world.client.post(f"/tasks/{task_id}/cancel", json={"reason": "fermato"})

        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["state"] == S.CANCELLED.value
        assert await state_of(world.client, body["planning_task"]["id"]) == S.CANCELLED.value
        late = await world.client.post(
            f"/tasks/{body['planning_task']['id']}/approve",
            json={"approval_id": body["approval"]["id"]},
        )
        assert late.status_code == 409, "a yes given later pays for a plan nobody can attach"
        assert model.messages.calls == []


async def test_a_stopped_planning_task_stops_the_task_it_plans(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        await world.client.post(
            f"/tasks/{body['planning_task']['id']}/cancel", json={"reason": "fermato"}
        )

        planning = (await world.client.post(f"/tasks/{task_id}/planning")).json()
        assert planning["outcome"] == "cancelled"
        assert planning["task"]["state"] == S.CANCELLED.value
        assert "the planning task " in planning["reason"]


@pytest.mark.parametrize("which", ["task", "planning task"])
async def test_planning_while_either_task_is_walked_is_a_409(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, which: str
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)
        held = task_id if which == "task" else body["planning_task"]["id"]
        world.app.state.running.add(UUID(held))

        response = await world.client.post(f"/tasks/{task_id}/planning")

        assert response.status_code == 409, response.text
        world.app.state.running.discard(UUID(held))
        assert (await world.client.post(f"/tasks/{task_id}/planning")).status_code == 200


# ----------------------------------------------------------------------------------------
# Two doors, and who wrote the plan
# ----------------------------------------------------------------------------------------


async def test_a_task_ela_is_planning_takes_no_plan_by_hand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        task_id = await created(world.client)
        await asked(world.client, task_id)

        response = await world.client.post(f"/tasks/{task_id}/plan", json=echo_plan())

        assert response.status_code == 409, response.text
        assert "ELA is planning this task" in response.json()["error"]["message"]
        assert await state_of(world.client, task_id) == S.PLANNING.value


async def test_a_task_with_a_plan_by_hand_is_not_planned_again(client: AsyncClient) -> None:
    task_id = await created(client)
    await client.post(f"/tasks/{task_id}/plan", json=echo_plan())

    response = await client.post(f"/tasks/{task_id}/planning")

    assert response.status_code == 409, response.text
    assert "written by HAND" in response.json()["error"]["message"]


async def test_the_planning_task_is_not_asked_for_a_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        response = await world.client.post(f"/tasks/{body['planning_task']['id']}/planning")

        assert response.status_code == 409, response.text


async def test_a_plan_by_hand_says_so_in_the_detail(client: AsyncClient) -> None:
    task_id = await created(client)
    await client.post(f"/tasks/{task_id}/plan", json=echo_plan())

    detail = (await client.get(f"/tasks/{task_id}")).json()

    assert detail["plan_author"] == {
        "by": "HAND",
        "result_id": None,
        "session": None,
        "model": None,
    }
    assert detail["planning_task_id"] is None
    assert detail["no_plan"] is None


async def test_the_planning_task_says_the_planner_wrote_its_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        body = await asked(world.client, await created(world.client))

        detail = (await world.client.get(f"/tasks/{body['planning_task']['id']}")).json()

        assert detail["plan_author"]["by"] == "PLANNER"
        assert [step["required_capabilities"] for step in detail["steps"]] == [["model.complete"]]


# ----------------------------------------------------------------------------------------
# The road of the pages: the console and the phone answer the child's question (decision 19)
# ----------------------------------------------------------------------------------------

A_CONSOLE = Identity(
    kind=Kind.CONSOLE,
    device_id=DeviceId(UUID("00000000-0000-4000-8000-0000000000c1")),
    role=DeviceRole.CONSOLE,
)
"""Who a page of the Command Center is: the identity its middleware resolves."""


async def answered_from_a_page(world: World, body: dict[str, Any], *, said_yes: bool) -> None:
    """What the console and the phone call for a question, one conduct in one place (M17.2
    dec. K.1): the answer, and after a yes the run it would otherwise wait for."""
    await answered_and_resumed(
        ApprovalOut.model_validate(body["approval"]),
        said_yes=said_yes,
        ela=world.ela,
        identity=A_CONSOLE,
        running=world.app.state.running,
    )


async def test_a_yes_from_a_page_runs_the_call_and_plans_the_task_with_the_model_s_plan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The proof gives its yes from the command line, so nothing else reaches this road: the
    page's yes runs the planning task, and the run settles the task it plans."""
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        await answered_from_a_page(world, body, said_yes=True)

        detail = (await world.client.get(f"/tasks/{task_id}")).json()
        assert detail["state"] == S.QUEUED.value
        assert detail["plan_author"]["by"] == "MODEL"
        assert detail["plan_author"]["model"] == OPUS_5_5
        assert len(model.messages.calls) == 1
        assert (await world.client.get(f"/tasks/{task_id}/results")).json() == [], "not run"


async def test_a_no_from_a_page_denies_the_task_it_plans_with_deny_by_planning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, model):
        task_id = await created(world.client)
        body = await asked(world.client, task_id)

        await answered_from_a_page(world, body, said_yes=False)

        assert await state_of(world.client, task_id) == S.DENIED.value
        reason = (await world.ela.runner.answer(TaskId(UUID(task_id)))).reason or ""
        assert reason.startswith("deny_by_planning: PLANNING -> DENIED (the planning task ")
        assert model.messages.calls == []
