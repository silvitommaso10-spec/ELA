"""``/tasks`` (spec §14, §15, §65; ADR 0023 §6, §9).

Creating, reading, planning, walking, stopping. Every transition belongs to the Task Engine and
this module only proves that the route asks for the right one — and that what the engine refuses
comes back as a conflict rather than as a traceback.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import TaskId, TaskState
from tests.api.support import ECHO_MESSAGE, echo_plan, note_plan, queued

UNKNOWN = str(uuid.uuid4())


# ----------------------------------------------------------------------------------------
# Creating and reading
# ----------------------------------------------------------------------------------------


async def test_a_task_is_created_from_what_the_user_asked(client: AsyncClient) -> None:
    response = await client.post("/tasks", json={"text": "prepara la riunione di domani"})

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == TaskState.CREATED.value
    assert body["goal"] == "prepara la riunione di domani"
    assert body["plan_id"] is None  # nothing runs until there is a plan


async def test_a_goal_and_a_deadline_may_be_given(client: AsyncClient) -> None:
    response = await client.post(
        "/tasks",
        json={"text": "fai la cosa", "goal": "la cosa", "deadline": "2026-12-31T10:00:00Z"},
    )

    assert response.json()["goal"] == "la cosa"
    assert response.json()["deadline"].startswith("2026-12-31T10:00:00")


async def test_a_task_without_a_request_is_refused(client: AsyncClient) -> None:
    assert (await client.post("/tasks", json={"text": ""})).status_code == 422
    assert (await client.post("/tasks", json={})).status_code == 422


async def test_the_list_filters_by_state_and_limits_after_the_filter(
    client: AsyncClient,
) -> None:
    await client.post("/tasks", json={"text": "una"})
    await queued(client, echo_plan(), text="due")

    everything = (await client.get("/tasks")).json()
    queued_only = (await client.get("/tasks", params={"state": "QUEUED"})).json()
    first = (await client.get("/tasks", params={"limit": 1})).json()

    assert len(everything) == 2
    assert [task["goal"] for task in queued_only] == ["due"]
    assert len(first) == 1


async def test_a_limit_of_zero_is_a_caller_s_bug(client: AsyncClient) -> None:
    assert (await client.get("/tasks", params={"limit": 0})).status_code == 422


async def test_an_unknown_task_is_not_found(client: AsyncClient) -> None:
    """And the message says *which* task, in the form the caller sent (review of M8.2): that
    string travels into the error body and out of the CLI, and it has to be pasteable."""
    response = await client.get(f"/tasks/{UNKNOWN}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert str(UNKNOWN) in response.json()["error"]["message"]
    assert "UUID(" not in response.json()["error"]["message"]


async def test_a_task_without_a_plan_has_no_steps(client: AsyncClient) -> None:
    created = (await client.post("/tasks", json={"text": "senza piano"})).json()

    body = (await client.get(f"/tasks/{created['id']}")).json()

    assert body["steps"] == []


async def test_the_detail_shows_the_arguments_of_each_step(client: AsyncClient) -> None:
    """ADR 0023 §6: the user's content coming back to the user. The audit is another matter."""
    task_id = await queued(client, echo_plan())

    step = (await client.get(f"/tasks/{task_id}")).json()["steps"][0]

    assert step["arguments"] == {"message": ECHO_MESSAGE}
    assert step["state"] == "PENDING"
    assert step["risk"] == "SAFE"


# ----------------------------------------------------------------------------------------
# Planning, until the Planner exists (§13)
# ----------------------------------------------------------------------------------------


async def test_a_plan_queues_the_task(client: AsyncClient) -> None:
    created = (await client.post("/tasks", json={"text": "fai"})).json()

    planned = (await client.post(f"/tasks/{created['id']}/plan", json=echo_plan())).json()

    assert planned["state"] == TaskState.QUEUED.value
    assert planned["plan_id"] is not None


async def test_a_second_plan_is_refused(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())

    response = await client.post(f"/tasks/{task_id}/plan", json=echo_plan())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_a_plan_that_is_not_a_dag_is_refused_before_anything_is_written(
    client: AsyncClient,
) -> None:
    """The same check every plan goes through (``TaskGraph.from_plan``), reached from outside."""
    created = (await client.post("/tasks", json={"text": "fai"})).json()
    plan = echo_plan()
    plan["steps"][0]["dependencies"] = [plan["steps"][0]["id"]]  # a step depending on itself

    response = await client.post(f"/tasks/{created['id']}/plan", json=plan)

    assert response.status_code == 422
    assert (await client.get(f"/tasks/{created['id']}")).json()["state"] == TaskState.CREATED.value


async def test_a_plan_without_steps_is_refused(client: AsyncClient) -> None:
    created = (await client.post("/tasks", json={"text": "fai"})).json()

    response = await client.post(
        f"/tasks/{created['id']}/plan", json={"goal": "niente", "steps": []}
    )

    assert response.status_code == 422


async def test_a_step_naming_a_capability_nobody_implements_waits(client: AsyncClient) -> None:
    """§33 through the API: no node can run it, so the task **waits** instead of failing.

    The orchestrator advises and never moves a task (ADR 0017 §6): a capability no tool
    implements leaves the step unplaceable, and unplaceable is not the same as impossible.
    """
    plan = echo_plan()
    plan["steps"][0]["required_capabilities"] = ["core.rm_rf"]
    task_id = await queued(client, plan)

    body = (await client.post(f"/tasks/{task_id}/run")).json()

    assert body["outcome"] == "waiting_device"
    assert body["task"]["state"] == TaskState.QUEUED.value


# ----------------------------------------------------------------------------------------
# Walking the plan (ADR 0019, ADR 0023 §9)
# ----------------------------------------------------------------------------------------


async def test_a_run_walks_the_plan_to_the_end(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())

    body = (await client.post(f"/tasks/{task_id}/run")).json()

    assert body["outcome"] == "completed"
    assert body["task"]["state"] == TaskState.COMPLETED.value
    assert len(body["steps"]) == 1


async def test_a_run_of_a_task_without_a_plan_is_a_conflict(client: AsyncClient) -> None:
    created = (await client.post("/tasks", json={"text": "senza piano"})).json()

    response = await client.post(f"/tasks/{created['id']}/run")

    assert response.status_code == 409


async def test_a_second_run_of_the_same_task_is_refused_not_queued(
    client: AsyncClient, app: FastAPI
) -> None:
    """ADR 0023 §9: the executor has no lock of its own, and two runners on one task is a bug."""
    task_id = await queued(client, echo_plan())
    app.state.running.add(TaskId(uuid.UUID(task_id)))

    response = await client.post(f"/tasks/{task_id}/run")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_running"


async def test_a_finished_run_lets_the_next_one_through(client: AsyncClient, app: FastAPI) -> None:
    task_id = await queued(client, echo_plan())

    await client.post(f"/tasks/{task_id}/run")

    assert app.state.running == set()
    assert (await client.post(f"/tasks/{task_id}/run")).json()["outcome"] == "completed"


async def test_a_run_says_when_it_is_waiting_for_the_user(client: AsyncClient) -> None:
    task_id = await queued(client, note_plan())

    body = (await client.post(f"/tasks/{task_id}/run")).json()

    assert body["outcome"] == "waiting_approval"
    assert body["task"]["state"] == TaskState.WAITING_APPROVAL.value


# ----------------------------------------------------------------------------------------
# Stopping (§65)
# ----------------------------------------------------------------------------------------


async def test_the_user_can_always_stop_a_task(client: AsyncClient, ela: Ela) -> None:
    task_id = await queued(client, echo_plan())

    body = (
        await client.post(f"/tasks/{task_id}/cancel", json={"reason": "ci ho ripensato"})
    ).json()

    assert body["state"] == TaskState.CANCELLED.value
    events = await ela.audit.read(task_id=TaskId(uuid.UUID(task_id)))
    assert events[-1].actor.kind.value == "USER"
    assert events[-1].actor.id == ela.settings.core.user_name


async def test_a_cancelled_task_does_not_run(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())
    await client.post(f"/tasks/{task_id}/cancel", json={})

    body = (await client.post(f"/tasks/{task_id}/run")).json()

    assert body["outcome"] == "cancelled"
    assert body["steps"] == []


async def test_stopping_twice_says_the_same_thing(client: AsyncClient) -> None:
    """The engine is idempotent on an operation already applied (ADR 0008): asking again for
    something that already happened is not an error, it is the same answer."""
    task_id = await queued(client, echo_plan())
    await client.post(f"/tasks/{task_id}/cancel", json={})

    again = await client.post(f"/tasks/{task_id}/cancel", json={})

    assert again.status_code == 200
    assert again.json()["state"] == TaskState.CANCELLED.value
