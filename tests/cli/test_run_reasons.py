"""The ``reason`` row of ``ela task run`` for every end but ``completed`` (M13.1c, ADR 0055).

The same branches as ``tests/api/test_run_reasons.py`` (``tests/api/reasons.py``), the two calls
made through the command a person types: the row the run that closes the task prints and the row a
later run prints at the door are the same row, and it is not the ``—`` of an empty cell.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from ela.cli.output import EMPTY, GAP
from ela.cli.tasks import RUN_LABELS
from ela.domain import TaskId
from tests.api.reasons import (
    CASES,
    Builder,
    World,
    ending,
    said,
)

WIDTH = max(map(len, RUN_LABELS))


def row(printed: str, label: str) -> str:
    """The value of one row of ``ela task run``, read at the command's column."""
    for line in printed.splitlines():
        if line.startswith(label.ljust(WIDTH) + GAP):
            return line[WIDTH + len(GAP) :]
    raise AssertionError(f"no {label!r} row in {printed!r}")


async def ran(w: World, task: str) -> str:
    result = await w.cli("task", "run", task)
    assert result.exit_code == 0, result.output
    return result.stdout


@pytest.mark.parametrize("case", CASES, ids=[case.__name__ for case in CASES])
async def test_the_reason_row_is_the_same_at_the_end_and_at_the_door(
    case: Builder, world: World
) -> None:
    branch = await case(world)

    first = await ran(world, branch.task)
    if branch.taken:
        running: set[TaskId] = world.app.state.running
        running.add(TaskId(UUID(branch.task)))
        try:
            second = await ran(world, branch.task)
        finally:
            running.discard(TaskId(UUID(branch.task)))
    else:
        second = await ran(world, branch.task)

    assert row(first, "outcome") == row(second, "outcome") == branch.outcome.value
    assert row(first, "reason") != EMPTY
    assert row(second, "reason") == row(first, "reason")
    event = await ending(world, branch.task)
    assert row(first, "reason") == event["summary"]
    assert said(event) in row(first, "reason")
