"""The example plan in ``docs/examples/`` is a plan ELA really accepts (review of M8.2).

An example that has drifted is worse than no example: it is the first thing somebody types, and
it fails in their hands with a message about a capability they have never heard of. So the file
is not quoted in a test — it is **sent**, byte for byte, and then walked to the end: two steps,
one SAFE and one that asks for consent, a note on disk with the text the file carries.

``docs/GETTING_STARTED.md`` is the same round from the command line; ``tests/cli/`` walks it there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import TaskState

EXAMPLE = Path(__file__).resolve().parents[2] / "docs" / "examples" / "first-task.json"


def example_plan() -> dict[str, Any]:
    """The file as it is on disk. Nothing is patched in: that is the whole point."""
    plan: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return plan


async def test_the_example_is_accepted_as_it_stands(client: AsyncClient) -> None:
    task_id = (await client.post("/tasks", json={"text": "il mio primo task"})).json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=example_plan())

    assert planned.status_code == 200, planned.text
    assert planned.json()["state"] == TaskState.QUEUED.value


async def test_its_two_steps_arrive_in_the_order_the_file_declares(client: AsyncClient) -> None:
    """The second depends on the first, so the graph orders them: echo, then the note."""
    task_id = (await client.post("/tasks", json={"text": "il mio primo task"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=example_plan())

    steps = (await client.get(f"/tasks/{task_id}")).json()["steps"]

    assert [step["required_capabilities"] for step in steps] == [
        ["core.echo"],
        ["workspace.write_note"],
    ]
    assert steps[1]["dependencies"] == [steps[0]["id"]]


async def test_the_example_runs_to_the_end_and_leaves_the_note_it_promises(
    client: AsyncClient, ela: Ela
) -> None:
    """The whole example: the SAFE step runs, the MEDIUM one stops and asks, and after the "yes"
    the note is on disk with the body the file carries."""
    plan = example_plan()
    task_id = (await client.post("/tasks", json={"text": "il mio primo task"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=plan)

    first = (await client.post(f"/tasks/{task_id}/run")).json()
    assert first["outcome"] == "waiting_approval"

    approval = (await client.get("/approvals")).json()[0]
    assert approval["targets"] == [plan["steps"][1]["arguments"]["path"]]
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})

    second = (await client.post(f"/tasks/{task_id}/run")).json()
    assert second["outcome"] == "completed"

    note = ela.settings.workspace.workspace_dir / plan["steps"][1]["arguments"]["path"]
    assert note.read_text(encoding="utf-8") == plan["steps"][1]["arguments"]["body"]
