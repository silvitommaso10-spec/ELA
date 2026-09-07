"""One whole turn of ELA from the command line (spec §27, §32, §54; ADR 0024).

The twin of ``tests/api/test_end_to_end.py``, and the acceptance criterion of M8.2 as a test:
create, plan, run, be asked, read the request, answer it, run again, read the trail, verify the
chain — with no ``curl`` and nothing stubbed between the CLI and the API.
"""

from __future__ import annotations

import json
from pathlib import Path

from ela.composition import Ela
from ela.domain import AuditEventType, TaskState
from tests.api.support import NOTE_BODY, NOTE_PATH, note_plan
from tests.cli.support import Cli
from tests.cli.test_tasks import written


async def test_a_whole_turn_of_ela_from_the_command_line(
    cli: Cli, ela: Ela, tmp_path: Path
) -> None:
    assert (await cli("health")).exit_code == 0

    created = await cli("task", "create", "scrivimi il briefing di domani", "--json")
    task_id = json.loads(created.stdout)["id"]
    planned = await cli("task", "plan", task_id, "--file", written(tmp_path, note_plan()))
    assert TaskState.QUEUED.value in planned.stdout

    # It stops and asks: writing a note is MEDIUM risk, and consent is the user's (§30).
    first = await cli("task", "run", task_id)
    assert "waiting_approval" in first.stdout

    inbox = json.loads((await cli("approvals", "--json")).stdout)
    assert [one["task_id"] for one in inbox] == [task_id]
    assert inbox[0]["targets"] == [NOTE_PATH]

    # The request is readable as a table too, which is how a person finds the id to answer.
    listed = await cli("approvals")
    assert inbox[0]["id"] in listed.stdout

    answered = await cli("task", "approve", task_id, "--approval", inbox[0]["id"])
    assert TaskState.QUEUED.value in answered.stdout
    assert json.loads((await cli("approvals", "--json")).stdout) == []

    second = await cli("task", "run", task_id)
    assert "completed" in second.stdout

    # The note exists, with what was asked in it.
    assert (ela.settings.workspace.workspace_dir / NOTE_PATH).read_text(
        encoding="utf-8"
    ) == NOTE_BODY

    # The task says so, step by step.
    detail = json.loads((await cli("task", "show", task_id, "--json")).stdout)
    assert [step["state"] for step in detail["steps"]] == ["COMPLETED"]

    # The trail says how it happened…
    trail = await cli("audit", "tail", "-n", "100", "--task", task_id, "--json")
    kinds = [event["event_type"] for event in json.loads(trail.stdout)]
    assert kinds.count(AuditEventType.APPROVAL_REQUESTED.value) == 1
    assert kinds.count(AuditEventType.TOOL_EXECUTED.value) == 1
    assert kinds[-1] == AuditEventType.TASK_COMPLETED.value

    # …and the chain says nothing was written around it.
    chain = json.loads((await cli("audit", "verify", "--json")).stdout)
    assert chain["length"] == len(await ela.audit.read())

    # ELA is the node that did it, and says so.
    nodes = json.loads((await cli("device", "list", "--json")).stdout)
    assert nodes[0]["available"] is True
