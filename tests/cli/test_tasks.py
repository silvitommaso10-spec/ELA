"""``ela task …``: every route of the API that moves a task, driven from the command line."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ela.cli.errors import CONFIGURATION, REFUSED
from ela.domain import TaskState
from tests.api.support import ECHO_MESSAGE, echo_plan, note_plan
from tests.cli.support import Cli

MISSING = "11111111-1111-4111-8111-111111111111"


def written(tmp_path: Path, plan: dict[str, Any], name: str = "plan.json") -> str:
    path = tmp_path / name
    path.write_text(json.dumps(plan), encoding="utf-8")
    return str(path)


async def created(cli: Cli, text: str = "fai una cosa") -> str:
    answer = await cli("task", "create", text, "--json")
    assert answer.exit_code == 0, answer.output
    task_id: str = json.loads(answer.stdout)["id"]
    return task_id


async def test_create_shows_the_task_it_made(cli: Cli) -> None:
    result = await cli("task", "create", "scrivimi il briefing", "--goal", "briefing")

    assert result.exit_code == 0
    assert "briefing" in result.stdout
    assert TaskState.CREATED.value in result.stdout


async def test_create_takes_a_deadline(cli: Cli) -> None:
    result = await cli("task", "create", "una cosa", "--deadline", "2027-01-01T10:00:00Z", "--json")

    assert json.loads(result.stdout)["deadline"].startswith("2027-01-01T10:00:00")


async def test_list_shows_the_tasks_in_a_table(cli: Cli) -> None:
    await created(cli, "prima")
    await created(cli, "seconda")

    result = await cli("task", "list")

    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].split() == ["ID", "STATE", "CREATED", "GOAL"]
    assert "prima" in result.stdout and "seconda" in result.stdout


async def test_list_filters_by_state_and_limit(cli: Cli, tmp_path: Path) -> None:
    first = await created(cli, "prima")
    await cli("task", "plan", first, "--file", written(tmp_path, echo_plan()))
    await created(cli, "seconda")

    queued = await cli("task", "list", "--state", TaskState.QUEUED.value, "--json")
    limited = await cli("task", "list", "--limit", "1", "--json")

    assert [one["id"] for one in json.loads(queued.stdout)] == [first]
    assert len(json.loads(limited.stdout)) == 1


async def test_list_says_so_when_there_is_nothing(cli: Cli) -> None:
    result = await cli("task", "list")

    assert result.exit_code == 0
    assert result.stdout.strip() == "nothing to show"


async def test_show_lists_the_steps_of_the_plan(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    result = await cli("task", "show", task_id)

    assert result.exit_code == 0
    assert "STEP" in result.stdout
    assert "core.echo" in result.stdout
    assert "SAFE" in result.stdout


async def test_results_show_the_table_and_the_output_in_full(cli: Cli, tmp_path: Path) -> None:
    """``ela task results`` is the only command that gives back content (ADR 0025 §4).

    Nothing is shortened: with a key, the answer of a model is what somebody came here for.
    """
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))
    await cli("task", "run", task_id)

    result = await cli("task", "results", task_id)

    assert result.exit_code == 0
    header = result.stdout.splitlines()[0].split()
    assert header == ["STEP", "CAPABILITY", "STATUS", "TOOL", "WHEN"]
    assert "core.echo" in result.stdout
    assert ECHO_MESSAGE in result.stdout


async def test_results_of_a_task_that_never_ran_say_so(cli: Cli) -> None:
    result = await cli("task", "results", await created(cli))

    assert result.exit_code == 0
    assert "nothing to show" in result.stdout


async def test_results_as_json_are_the_api_s_own_answer(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))
    await cli("task", "run", task_id)

    payload = json.loads((await cli("task", "results", task_id, "--json")).stdout)

    assert [one["capability_id"] for one in payload] == ["core.echo"]
    assert payload[0]["output"] == {"message": ECHO_MESSAGE}


async def test_results_of_a_task_that_does_not_exist_is_a_refusal(cli: Cli) -> None:
    result = await cli("task", "results", MISSING)

    assert result.exit_code == REFUSED
    assert "not_found" in result.stderr


async def test_show_of_a_task_without_a_plan_has_no_steps(cli: Cli) -> None:
    result = await cli("task", "show", await created(cli), "--json")

    assert json.loads(result.stdout)["steps"] == []


async def test_show_of_a_task_that_does_not_exist_is_a_refusal(cli: Cli) -> None:
    """And the message carries the id in the form it was typed: it is what goes in the next
    command, not ``UUID('…')``, which is Python's syntax for building one (review of M8.2)."""
    result = await cli("task", "show", MISSING)

    assert result.exit_code == REFUSED
    assert "not_found" in result.stderr
    assert MISSING in result.stderr
    assert "UUID(" not in result.stderr


async def test_plan_queues_the_task(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)

    result = await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    assert result.exit_code == 0
    assert TaskState.QUEUED.value in result.stdout


async def test_a_plan_that_is_not_json_never_reaches_ela(cli: Cli, tmp_path: Path) -> None:
    """The invocation is wrong, and nothing was sent: exit code 2, not 1."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")

    result = await cli("task", "plan", await created(cli), "--file", str(broken))

    assert result.exit_code == CONFIGURATION
    assert "not valid JSON" in result.stderr


async def test_a_plan_file_that_is_not_there_never_reaches_ela(cli: Cli, tmp_path: Path) -> None:
    result = await cli("task", "plan", await created(cli), "--file", str(tmp_path / "nope.json"))

    assert result.exit_code == CONFIGURATION
    assert "nope.json" in result.stderr


async def test_a_plan_that_cannot_be_a_graph_is_refused_by_ela(cli: Cli, tmp_path: Path) -> None:
    plan = echo_plan()
    plan["steps"][0]["dependencies"] = [MISSING]

    result = await cli("task", "plan", await created(cli), "--file", written(tmp_path, plan))

    assert result.exit_code == REFUSED
    assert "invalid" in result.stderr


async def test_run_walks_the_plan_and_says_where_it_stopped(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    result = await cli("task", "run", task_id)

    assert result.exit_code == 0
    assert "completed" in result.stdout
    assert TaskState.COMPLETED.value in result.stdout


async def test_run_of_a_task_with_no_plan_is_a_refusal(cli: Cli) -> None:
    result = await cli("task", "run", await created(cli))

    assert result.exit_code == REFUSED
    assert "conflict" in result.stderr


async def test_cancel_stops_the_task_and_records_the_reason(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    result = await cli("task", "cancel", task_id, "--reason", "non serve più")

    assert result.exit_code == 0
    assert TaskState.CANCELLED.value in result.stdout

    trail = await cli("audit", "tail", "--task", task_id, "--json")
    assert any("non serve più" in event["summary"] for event in json.loads(trail.stdout))


async def test_approve_needs_the_id_of_the_request(cli: Cli, tmp_path: Path) -> None:
    """No guessing: a "yes" is given to a request that was read (ADR 0024 §3)."""
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, note_plan()))
    await cli("task", "run", task_id)

    result = await cli("task", "approve", task_id)

    assert result.exit_code == CONFIGURATION
    assert "--approval" in result.stderr


async def test_deny_refuses_the_request_and_denies_the_task(cli: Cli, tmp_path: Path) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, note_plan()))
    await cli("task", "run", task_id)
    waiting = json.loads((await cli("approvals", "--json")).stdout)

    result = await cli("task", "deny", task_id, "--approval", waiting[0]["id"])

    assert result.exit_code == 0
    assert TaskState.DENIED.value in result.stdout


async def test_an_answer_to_an_unknown_request_is_a_refusal(cli: Cli) -> None:
    result = await cli("task", "approve", await created(cli), "--approval", MISSING)

    assert result.exit_code == REFUSED
    assert "not_found" in result.stderr


async def test_the_echoed_message_is_the_one_that_was_planned(cli: Cli, tmp_path: Path) -> None:
    """What the CLI sends is the file, byte for byte: the arguments arrive as they were written."""
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    detail = json.loads((await cli("task", "show", task_id, "--json")).stdout)

    assert detail["steps"][0]["arguments"] == {"message": ECHO_MESSAGE}
