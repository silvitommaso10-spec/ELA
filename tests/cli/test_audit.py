"""``ela audit tail`` and ``ela audit verify``."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ela.cli.audit import DEFAULT_TAIL
from ela.cli.errors import REFUSED
from ela.composition import Ela
from tests.api.support import echo_plan, tamper_with_the_trail
from tests.cli.support import Cli
from tests.cli.test_tasks import created, written


async def ran(cli: Cli, tmp_path: Path, text: str = "una cosa") -> str:
    task_id = await created(cli, text)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan(), f"{task_id}.json"))
    await cli("task", "run", task_id)
    return task_id


async def test_tail_shows_the_last_entries_oldest_first(cli: Cli, tmp_path: Path) -> None:
    await ran(cli, tmp_path)

    result = await cli("audit", "tail", "-n", "3", "--json")
    everything = await cli("audit", "tail", "-n", "500", "--json")

    shown = json.loads(result.stdout)
    assert len(shown) == 3
    assert shown == json.loads(everything.stdout)[-3:]


async def test_tail_defaults_to_the_last_twenty(cli: Cli, tmp_path: Path) -> None:
    await ran(cli, tmp_path)

    shown = json.loads((await cli("audit", "tail", "--json")).stdout)
    everything = json.loads((await cli("audit", "tail", "-n", "500", "--json")).stdout)

    assert len(shown) == min(DEFAULT_TAIL, len(everything))


async def test_tail_renders_a_table(cli: Cli, tmp_path: Path) -> None:
    await ran(cli, tmp_path)

    result = await cli("audit", "tail")

    assert result.exit_code == 0
    assert result.stdout.splitlines()[0].split() == ["WHEN", "EVENT", "ACTOR", "TASK", "SUMMARY"]
    assert "ELA:ela" in result.stdout


async def test_tail_filters_by_task_and_by_instant(cli: Cli, tmp_path: Path) -> None:
    first = await ran(cli, tmp_path, "una")
    await ran(cli, tmp_path, "due")

    mine = json.loads((await cli("audit", "tail", "--task", first, "--json")).stdout)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    later = json.loads((await cli("audit", "tail", "--since", future, "--json")).stdout)

    assert {event["task_id"] for event in mine} == {first}
    assert later == []


async def test_tail_of_an_empty_trail_says_so(cli: Cli) -> None:
    result = await cli("audit", "tail")

    assert result.exit_code == 0
    assert result.stdout.strip() == "nothing to show"


async def test_verify_says_how_long_the_chain_is(cli: Cli, tmp_path: Path) -> None:
    await ran(cli, tmp_path)

    result = await cli("audit", "verify")

    assert result.exit_code == 0
    assert "entries" in result.stdout
    assert "head hash" in result.stdout


async def test_verify_in_json_is_the_summary_to_anchor(cli: Cli) -> None:
    summary = json.loads((await cli("audit", "verify", "--json")).stdout)

    assert summary == {"length": 0, "head_hash": "0" * 64}


async def test_a_tampered_trail_is_a_refusal_with_a_position(
    cli: Cli, ela: Ela, tmp_path: Path
) -> None:
    """The command exists for this answer: exit code 1, the API's code, and *where*."""
    await ran(cli, tmp_path)
    await tamper_with_the_trail(ela)

    result = await cli("audit", "verify")

    assert result.exit_code == REFUSED
    assert "tampered" in result.stderr
