"""A plan written by hand passes the executor's preconditions before it is queued (M14.2, ADR 0058).

The defect, found by the census of the SPEC with two probes on the real API (decision 8 of the
review): a plan with **zero or two capabilities** in a step, or with **a success condition outside
the vocabulary**, came in — ``200``, ``QUEUED`` —, and at the first run the executor raised
``ExecutorError`` after ``start`` and ``start_step``: the task stayed ``EXECUTING`` with the step
``RUNNING``, and every run after it answered ``409`` until the ``recover`` of the next start-up.
ADR 0014 had asked for this to be checkable «alla validazione del piano», and nobody had made it so.

Now the route asks :func:`~ela.executive.readiness.readiness` — the very function the executor asks
— before it moves the task: ``422``, and nothing written. The sentence names the step by position
and quotes no word of the plan (§57).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient

from ela.api.schemas import PlanIn
from ela.composition import Ela
from ela.domain import TaskId, TaskState
from tests.api.support import echo_plan


async def created(client: AsyncClient) -> str:
    return str((await client.post("/tasks", json={"text": "un task"})).json()["id"])


def with_first_step(**changed: Any) -> dict[str, Any]:
    plan = echo_plan()
    plan["steps"][0].update(changed)
    return plan


@pytest.mark.parametrize(
    ("changed", "said"),
    [
        (
            {"required_capabilities": ["core.echo", "workspace.write_note"]},
            "step 1 of 1 declares 2 capabilities; an executable step declares exactly one",
        ),
        (
            {"required_capabilities": []},
            "step 1 of 1 declares 0 capabilities; an executable step declares exactly one",
        ),
        (
            {"success_conditions": []},
            "step 1 of 1 declares no success condition; an action that cannot be verified is "
            "not executed",
        ),
        (
            {"success_conditions": ["echo.message_matches", "made.up.condition"]},
            "step 1 of 1 names 1 success condition core-echo-verifier cannot check",
        ),
    ],
    ids=["two-capabilities", "no-capability", "no-condition", "outside-the-vocabulary"],
)
async def test_a_step_the_executor_would_refuse_is_refused_before_the_queue(
    client: AsyncClient, changed: dict[str, Any], said: str
) -> None:
    task_id = await created(client)

    response = await client.post(f"/tasks/{task_id}/plan", json=with_first_step(**changed))

    assert response.status_code == 422, response.text
    assert said in response.json()["error"]["message"]
    task = (await client.get(f"/tasks/{task_id}")).json()
    assert task["state"] == TaskState.CREATED.value
    assert task["plan_id"] is None


async def test_the_refusal_quotes_no_word_of_the_plan(client: AsyncClient) -> None:
    task_id = await created(client)
    plan = with_first_step(success_conditions=["echo.message_matches", "a-word-of-the-caller"])

    response = await client.post(f"/tasks/{task_id}/plan", json=plan)

    assert response.status_code == 422
    assert "a-word-of-the-caller" not in response.text


async def test_a_task_that_was_refused_runs_nothing_and_is_never_left_executing(
    client: AsyncClient,
) -> None:
    """The defect itself: before ADR 0058 this run left the task EXECUTING and answered 409."""
    task_id = await created(client)
    await client.post(f"/tasks/{task_id}/plan", json=with_first_step(success_conditions=[]))

    run = await client.post(f"/tasks/{task_id}/run")

    assert run.status_code == 409
    task = (await client.get(f"/tasks/{task_id}")).json()
    assert task["state"] != TaskState.EXECUTING.value


async def test_a_plan_that_passes_is_queued_as_before(client: AsyncClient) -> None:
    task_id = await created(client)

    response = await client.post(f"/tasks/{task_id}/plan", json=echo_plan())

    assert response.status_code == 200, response.text
    assert response.json()["state"] == TaskState.QUEUED.value


async def test_a_plan_saved_before_the_check_still_waits_for_a_node_that_cannot_exist(
    client: AsyncClient, ela: Ela
) -> None:
    """Decision 20 of the review of the summary: from the API ``UNKNOWN_CAPABILITY`` is reached no
    more, and it stays true of the plans saved **before** the check — tasks ``QUEUED`` with a plan
    by hand already in the database, which a migration does not revisit. The row is written as the
    route wrote it then: ``start_planning``, ``plan`` and ``queue`` of the engine, author ``HAND``
    (the default ``0014`` gives the rows it finds), and no question to the executor. The
    orchestrator's own refusal is in ``tests/devices/test_orchestrator.py``."""
    task_id = TaskId(UUID(await created(client)))
    body = with_first_step(required_capabilities=["core.rm_rf"])
    plan = PlanIn.model_validate(body).to_domain(task_id, ela.ids.new_uuid(), ela.clock.now())
    await ela.engine.start_planning(task_id)
    await ela.engine.plan(task_id, plan)
    await ela.engine.queue(task_id, reason="planned through the API")

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "waiting_device"
    assert "UNKNOWN_CAPABILITY" in (run["reason"] or "")
    assert run["task"]["state"] == TaskState.QUEUED.value
