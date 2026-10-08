"""``ela task plan`` without ``--file``, and ``ela task show`` of a plan to read (M14.2, ADR 0058).

Without ``--file`` the command asks ELA's Planner: the first call stops at the question of the
planning task, and prints it with its worst case and the next command; after the yes, the same
command attaches the model's plan and prints it — who wrote it, every step's arguments and
conditions — because **the run is the user's, after reading it** (decision I). ``show`` prints the
same, for every plan: the arguments and the conditions were only in ``--json`` until M14.2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ela.cli.errors import REFUSED
from ela.executive.spending import CAP_VARIABLE
from ela.providers.anthropic.models import OPUS_5_5
from tests.api.planning import NO_PLAN, NOTE_PLAN, said, with_a_model
from tests.api.support import ECHO_MESSAGE, echo_plan
from tests.cli.support import Cli, plain
from tests.cli.test_tasks import created, written
from tests.executive.planning import GOAL, NO_PLAN_REASON, NOTE_BODY

WORST = "4.262144 USD, claude-opus-5-5, up to 983616 tokens in and 16384 out"


async def asked(cli: Cli) -> tuple[str, dict[str, Any]]:
    """A task and the first ``ela task plan`` of it, as JSON."""
    task_id = await created(cli, GOAL)
    result = await cli("task", "plan", task_id, "--json")
    assert result.exit_code == 0, result.output
    return task_id, json.loads(result.stdout)


async def test_without_a_cap_the_plan_says_it_was_denied_and_names_the_line(cli: Cli) -> None:
    task_id = await created(cli, GOAL)

    result = await cli("task", "plan", task_id)

    assert result.exit_code == 0, result.output
    out = plain(result.stdout)
    assert "denied" in out
    assert "deny_by_planning" in out
    assert CAP_VARIABLE in out


async def test_the_first_plan_prints_the_question_its_worst_case_and_what_to_do_next(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path) as (world, _):
        task_id = await created(world.cli, GOAL)

        result = await world.cli("task", "plan", task_id)

        assert result.exit_code == 0, result.output
        out = plain(result.stdout)
        assert "waiting_approval" in out
        assert WORST in out
        planning = json.loads((await world.cli("task", "show", task_id, "--json")).stdout)
        child = planning["planning_task_id"]
        assert f"ela task approve {child} --approval " in out
        assert f"then ela task plan {task_id} again" in out


async def test_after_the_yes_the_plan_is_printed_with_its_author_arguments_and_conditions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NOTE_PLAN)) as (world, _):
        task_id, first = await asked(world.cli)
        question = first["approval"]
        yes = await world.cli(
            "task",
            "approve",
            question["task_id"],
            "--approval",
            question["id"],
        )
        assert yes.exit_code == 0, yes.output

        result = await world.cli("task", "plan", task_id)

        assert result.exit_code == 0, result.output
        out = plain(result.stdout)
        assert "planned" in out
        assert "QUEUED" in out
        assert f"MODEL {OPUS_5_5} (result " in out
        assert NOTE_BODY in out
        assert "note.content_matches" in out
        assert "workspace.write_note" in out


async def test_a_no_plan_is_printed_with_the_models_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async with with_a_model(monkeypatch, tmp_path, said(NO_PLAN)) as (world, _):
        task_id, first = await asked(world.cli)
        question = first["approval"]
        await world.cli(
            "task",
            "approve",
            question["task_id"],
            "--approval",
            question["id"],
        )

        result = await world.cli("task", "plan", task_id)

        out = plain(result.stdout)
        assert "failed" in out
        assert NO_PLAN_REASON in out
        assert NO_PLAN_REASON in plain((await world.cli("task", "show", task_id)).stdout)


async def test_show_prints_a_plan_by_hand_with_its_author_and_what_each_step_is_called_with(
    cli: Cli, tmp_path: Path
) -> None:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))

    out = plain((await cli("task", "show", task_id)).stdout)

    assert "author" in out and "HAND" in out
    assert ECHO_MESSAGE in out
    assert "echo.message_matches" in out


async def test_a_plan_by_hand_with_a_step_the_executor_refuses_is_refused_by_the_command(
    cli: Cli, tmp_path: Path
) -> None:
    plan = echo_plan()
    plan["steps"][0]["success_conditions"] = []

    result = await cli("task", "plan", await created(cli), "--file", written(tmp_path, plan))

    assert result.exit_code == REFUSED
    assert "step 1 of 1 declares no success condition" in plain(result.stderr)
