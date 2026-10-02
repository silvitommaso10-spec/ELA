"""``stopped step``: what the step in progress had done, at the command line (M6.3c, ADR 0054 §7).

Three views render it — ``ela task run``, ``ela task show``, ``ela task finished`` — and each is
rendered here with every value of :class:`~ela.domain.Halt`. The value is the executor's to compute
(``tests/tasks/test_engine_stop.py``, ``tests/executive/test_stop.py``); what is tested here is what
the command line says of each, so the route is handed each value.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ela.cli.output import EMPTY
from ela.cli.tasks import HALT_WORDS, RUN_LABELS, halt_words
from ela.composition import Ela
from ela.domain import Halt
from tests.api.support import echo_plan
from tests.cli.support import Cli
from tests.cli.test_tasks import created, written


async def stopped(cli: Cli, tmp_path: Path) -> str:
    task_id = await created(cli)
    await cli("task", "plan", task_id, "--file", written(tmp_path, echo_plan()))
    answer = await cli("task", "cancel", task_id, "--reason", "ferma")
    assert answer.exit_code == 0, answer.output
    return task_id


def handed(ela: Ela, monkeypatch: pytest.MonkeyPatch, halt: Halt | None) -> None:
    async def said(task_id: object) -> Halt | None:
        return halt

    monkeypatch.setattr(ela.executor, "halt", said)


@pytest.mark.parametrize("halt", list(Halt), ids=str)
async def test_run_show_and_finished_say_what_the_step_had_done(
    cli: Cli, ela: Ela, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, halt: Halt
) -> None:
    task_id = await stopped(cli, tmp_path)
    handed(ela, monkeypatch, halt)

    run = await cli("task", "run", task_id)
    show = await cli("task", "show", task_id)
    finished = await cli("task", "finished")

    for answer in (run, show, finished):
        assert answer.exit_code == 0, answer.output
        assert HALT_WORDS[halt] in answer.stdout
    assert RUN_LABELS[-1] == "stopped step"
    assert "stopped step" in run.stdout and "stopped step" in show.stdout


async def test_no_step_at_work_is_the_empty_mark(
    cli: Cli, ela: Ela, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_id = await stopped(cli, tmp_path)

    run = await cli("task", "run", task_id)
    as_json = json.loads((await cli("task", "run", task_id, "--json")).stdout)

    line = next(row for row in run.stdout.splitlines() if row.startswith("stopped step"))
    assert line.split()[-1] == EMPTY
    assert as_json["halt"] is None
    assert not any(words in run.stdout for words in HALT_WORDS.values())


def test_every_value_has_its_words_and_none_says_an_effect_happened() -> None:
    assert set(HALT_WORDS) == set(Halt)
    assert len(set(HALT_WORDS.values())) == len(Halt)
    assert not any("happened" in words for words in HALT_WORDS.values())
    assert halt_words(None) is None
    assert all(halt_words(value.value) == HALT_WORDS[value] for value in Halt)
