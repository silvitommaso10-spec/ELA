"""One whole turn of ELA, from outside (spec §27, §32, §63; ADR 0023).

This is the milestone's acceptance criterion as a test: create, plan, run, be asked, answer, run
again — over HTTP, on a real SQLite database, through the world the composition root built. What
it proves is not that a route answers, but that the pipeline of §27 runs end to end when nothing
is stubbed: catalogue, Guardian, authorization, tool, verification, audit chain, and a note on
the disk that a human could open.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import AuditEventType, TaskId, TaskState
from ela.infrastructure.persistence import verify_chain
from tests.api.support import NOTE_BODY, NOTE_PATH, note_plan, queued

E = AuditEventType


async def test_a_whole_turn_of_ela_over_http(client: AsyncClient, ela: Ela) -> None:
    health = await client.get("/health")
    assert health.status_code == 200

    task_id = await queued(client, note_plan(), text="scrivimi il briefing di domani")

    # It stops and asks: the step declares ``requires_authorization``, and consent is the
    # user's (§30). Not the risk: ``workspace.write_note`` is LOW, protected by its scope.
    first = (await client.post(f"/tasks/{task_id}/run")).json()
    assert first["outcome"] == "waiting_approval"

    inbox = (await client.get("/approvals")).json()
    assert [request["task_id"] for request in inbox] == [task_id]
    assert inbox[0]["targets"] == [NOTE_PATH]

    answered = await client.post(f"/tasks/{task_id}/approve", json={"approval_id": inbox[0]["id"]})
    assert answered.json()["state"] == TaskState.QUEUED.value
    assert (await client.get("/approvals")).json() == []

    second = (await client.post(f"/tasks/{task_id}/run")).json()
    assert second["outcome"] == "completed"
    assert second["task"]["state"] == TaskState.COMPLETED.value

    # The note exists, with what was asked in it.
    note = ela.settings.workspace.workspace_dir / NOTE_PATH
    assert note.read_text(encoding="utf-8") == NOTE_BODY

    # The task says so too, step by step.
    detail = (await client.get(f"/tasks/{task_id}")).json()
    assert [step["state"] for step in detail["steps"]] == ["COMPLETED"]

    # And the trail says how it happened, in order, once.
    kinds = [
        event["event_type"]
        for event in (await client.get("/audit", params={"task_id": task_id})).json()
    ]
    assert kinds.count(E.PERMISSION_DECIDED.value) == 2  # asked, then allowed
    assert kinds.count(E.APPROVAL_REQUESTED.value) == 1
    assert kinds.count(E.AUTHORIZATION_GRANTED.value) == 1
    assert kinds.count(E.TOOL_EXECUTED.value) == 1
    assert kinds.count(E.EXECUTION_VERIFIED.value) == 1
    assert kinds[-1] == E.TASK_COMPLETED.value

    # The chain of §32 links from the genesis: nothing was written around the log.
    summary = await verify_chain(ela.database)  # type: ignore[arg-type]
    assert summary.length == len(await ela.audit.read())


async def test_two_tasks_do_not_borrow_each_other_s_consent(client: AsyncClient) -> None:
    """A "yes" is bound to a task, a step and a capability (§30): the second task asks again."""
    first = await queued(client, note_plan(path="workspace/notes/one.md"), text="una")
    await client.post(f"/tasks/{first}/run")
    granted = (await client.get("/approvals")).json()[0]["id"]
    await client.post(f"/tasks/{first}/approve", json={"approval_id": granted})
    await client.post(f"/tasks/{first}/run")

    second = await queued(client, note_plan(path="workspace/notes/two.md"), text="due")
    outcome = (await client.post(f"/tasks/{second}/run")).json()

    assert outcome["outcome"] == "waiting_approval"
    assert [request["task_id"] for request in (await client.get("/approvals")).json()] == [second]


async def test_a_crash_between_two_runs_changes_nothing(client: AsyncClient, ela: Ela) -> None:
    """``run`` is re-entrant (ADR 0019 §5): calling it again is how a crashed run is resumed."""
    task_id = await queued(client, note_plan())
    await client.post(f"/tasks/{task_id}/run")
    approval = (await client.get("/approvals")).json()[0]["id"]
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval})

    assert (await client.post(f"/tasks/{task_id}/run")).json()["outcome"] == "completed"
    assert (await client.post(f"/tasks/{task_id}/run")).json()["outcome"] == "completed"

    results = await ela.results.for_step(
        TaskId(uuid.UUID(task_id)),
        (await ela.engine.graph(TaskId(uuid.UUID(task_id)))).graph.order[0],
    )
    assert len(results) == 1  # the tool ran once
