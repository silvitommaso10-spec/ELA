"""``GET /tasks/{id}/results`` (spec §57, §63; M8.3, ADR 0025 §4).

The one route that returns the user's **content**: what a tool produced, and not what happened.
The pair of tests that matter most are the two halves of that sentence — the output comes back
here, and it still does not come back through ``/audit``.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import ExecutionStatus
from ela.permissions import CORE_ECHO, WORKSPACE_WRITE_NOTE
from tests.api.support import ECHO_MESSAGE, NOTE_BODY, NOTE_PATH, echo_plan, note_plan, queued


async def test_a_task_that_ran_reports_what_its_tool_produced(client: AsyncClient) -> None:
    plan = echo_plan()
    task_id = await queued(client, plan)
    await client.post(f"/tasks/{task_id}/run")

    results = (await client.get(f"/tasks/{task_id}/results")).json()

    assert len(results) == 1
    assert results[0]["capability_id"] == CORE_ECHO
    assert results[0]["status"] == ExecutionStatus.SUCCEEDED.value
    assert results[0]["step_id"] == plan["steps"][0]["id"]
    assert results[0]["task_id"] == task_id
    assert results[0]["output"]["message"] == ECHO_MESSAGE


async def test_the_output_is_the_content_the_audit_refuses_to_carry(
    client: AsyncClient,
) -> None:
    """The two halves of §57 in one test: it comes back here, and it does not come back there."""
    task_id = await queued(client, note_plan())
    await client.post(f"/tasks/{task_id}/run")
    approval = (await client.get("/approvals")).json()[0]
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})
    await client.post(f"/tasks/{task_id}/run")

    results = (await client.get(f"/tasks/{task_id}/results")).text
    trail = (await client.get("/audit")).text

    assert NOTE_PATH in results
    assert NOTE_BODY not in trail
    assert WORKSPACE_WRITE_NOTE in trail  # the capability is recorded, the content is not


async def test_a_task_that_never_ran_has_no_results(client: AsyncClient) -> None:
    task_id = await queued(client, echo_plan())

    assert (await client.get(f"/tasks/{task_id}/results")).json() == []


async def test_a_task_that_does_not_exist_is_a_404_and_not_an_empty_list(
    client: AsyncClient,
) -> None:
    """ "No such task" and "this task produced nothing" are different answers (ADR 0025 §4)."""
    answer = await client.get(f"/tasks/{uuid.uuid4()}/results")

    assert answer.status_code == 404
    assert answer.json()["error"]["code"] == "not_found"


async def test_the_results_are_every_step_of_the_task_in_order(client: AsyncClient) -> None:
    plan = echo_plan()
    second = dict(plan["steps"][0])
    second["id"] = str(uuid.uuid4())
    second["dependencies"] = [plan["steps"][0]["id"]]
    second["arguments"] = {"message": "e ancora"}
    plan["steps"] = [plan["steps"][0], second]
    task_id = await queued(client, plan)
    await client.post(f"/tasks/{task_id}/run")

    results = (await client.get(f"/tasks/{task_id}/results")).json()

    assert [one["step_id"] for one in results] == [step["id"] for step in plan["steps"]]
    assert [one["output"]["message"] for one in results] == [ECHO_MESSAGE, "e ancora"]


async def test_the_results_of_one_task_are_not_another_task_s(client: AsyncClient) -> None:
    first = await queued(client, echo_plan(), text="una")
    await client.post(f"/tasks/{first}/run")
    second = await queued(client, echo_plan(), text="due")
    await client.post(f"/tasks/{second}/run")

    results = (await client.get(f"/tasks/{first}/results")).json()

    assert {one["task_id"] for one in results} == {first}


async def test_the_route_says_under_which_decision_the_tool_ran(
    client: AsyncClient, ela: Ela
) -> None:
    """A result knows where it comes from (ADR 0015): the decision is the link to the trail."""
    task_id = await queued(client, echo_plan())
    await client.post(f"/tasks/{task_id}/run")

    result = (await client.get(f"/tasks/{task_id}/results")).json()[0]

    decisions = [
        event.decision_id
        for event in await ela.audit.read(task_id=None)
        if event.decision_id is not None
    ]
    assert result["decision_id"] in [str(one) for one in decisions]
