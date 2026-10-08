"""What a real ELA answers along the proof of M14.2, recorded once, for the tests of its script.

Decision 25 of the review of the proof (2026-10-08): the two FAILED of the first round were the
script's, and both passed the suite because its tests fed it answers written by hand — a key the
route does not have, an output that never comes from two commands. So every kind of the script that
reads the API is fed here by **the routes themselves**: ELA as ``build`` makes it, in this process,
with the cap and the key, and the real Anthropic adapter over the client double
(``tests/api/planning.py``) answering a plan and then «no plan». The commands of the guide are run
by the command line in this process too, and their output is what Tommaso reads. Three plannings,
as in steps 2, 4 and 5 of section 24: the note, a question to the model, and «no plan».

A negative case starts from one of these answers and changes it (:func:`changed`); nothing else is
written by hand.
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from tests.api.planning import NO_PLAN, NOTE_PLAN, asked, created, said, with_a_model
from tests.cli.support import plain
from tests.executive.planning import ASK_STEP, plan_of

QUESTION = "Fatti spiegare dal modello, in due frasi, che cos'è un grafo aciclico diretto."
"""The goal of step 4 of section 24: a plan with a ``model.complete`` step."""
LIGHT = "Spegni la luce della cucina."
"""The goal of step 5 of section 24: what no capability of the catalogue does."""


@dataclass(frozen=True)
class Real:
    """The answers of the routes and of the command line, in the order of the proof."""

    health: Any
    openapi: Any
    diagnostics: Any
    spend_start: Any
    task: str
    child: str
    waiting: Any
    """``GET /tasks/<task>`` while its planning task asks."""
    approvals: Any
    child_after_yes: Any
    planned_output: str
    """``ela task plan <task>`` after the yes: the plan the model wrote, attached."""
    planned: Any
    planning_child: Any
    results: Any
    run_output: str
    """``ela task run <task>``: the plan of the model, walked to its end."""
    asking_task: str
    asking_child: str
    asking: Any
    """``GET /tasks/<asking_task>``: a plan with a ``model.complete`` step, queued."""
    asking_results: Any
    refused_task: str
    refused_child: str
    refused_output: str
    """``ela task plan <refused_task>`` after the yes: «no plan», with its reason."""
    refused: Any
    refused_results: Any
    spend_end: Any


async def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Real:
    answers = said(NOTE_PLAN), said(plan_of(ASK_STEP)), said(NO_PLAN)
    async with with_a_model(monkeypatch, tmp_path, *answers) as (world, _):
        client = world.client

        async def get(path: str) -> Any:
            response = await client.get(path)
            assert response.status_code == 200, (path, response.text)
            return response.json()

        async def yes(body: dict[str, Any]) -> None:
            child = body["planning_task"]["id"]
            answered = await client.post(
                f"/tasks/{child}/approve", json={"approval_id": body["approval"]["id"]}
            )
            assert answered.status_code == 200, answered.text

        async def command(*words: str) -> str:
            result = await world.cli(*words)
            assert result.exit_code == 0, result.output
            return plain(result.stdout)

        health, openapi = await get("/health"), await get("/openapi.json")
        diagnostics, spend_start = await get("/diagnostics"), await get("/spend")
        task = await created(client)
        first = await asked(client, task)
        child = first["planning_task"]["id"]
        waiting, approvals = await get(f"/tasks/{task}"), await get("/approvals")
        await yes(first)
        child_after_yes = await get(f"/tasks/{child}")
        planned_output = await command("task", "plan", task)
        planned, planning_child = await get(f"/tasks/{task}"), await get(f"/tasks/{child}")
        results = await get(f"/tasks/{child}/results")
        run_output = await command("task", "run", task)
        asking_task = await created(client, QUESTION)
        third = await asked(client, asking_task)
        asking_child = third["planning_task"]["id"]
        await yes(third)
        await command("task", "plan", asking_task)
        asking = await get(f"/tasks/{asking_task}")
        asking_results = await get(f"/tasks/{asking_child}/results")
        refused_task = await created(client, LIGHT)
        second = await asked(client, refused_task)
        refused_child = second["planning_task"]["id"]
        await yes(second)
        refused_output = await command("task", "plan", refused_task)
        refused = await get(f"/tasks/{refused_task}")
        refused_results = await get(f"/tasks/{refused_child}/results")
        spend_end = await get("/spend")
        return Real(
            health=health,
            openapi=openapi,
            diagnostics=diagnostics,
            spend_start=spend_start,
            task=task,
            child=child,
            waiting=waiting,
            approvals=approvals,
            child_after_yes=child_after_yes,
            planned_output=planned_output,
            planned=planned,
            planning_child=planning_child,
            results=results,
            run_output=run_output,
            asking_task=asking_task,
            asking_child=asking_child,
            asking=asking,
            asking_results=asking_results,
            refused_task=refused_task,
            refused_child=refused_child,
            refused_output=refused_output,
            refused=refused,
            refused_results=refused_results,
            spend_end=spend_end,
        )


def record(tmp_path_factory: pytest.TempPathFactory) -> Real:
    """The answers, from a world that lives only while they are asked."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        return asyncio.run(recorded(monkeypatch, tmp_path_factory.mktemp("real")))


class Recorded:
    """An API that answers what the real one answered: by path, a copy each time."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers

    def get(self, path: str) -> Any:
        assert path in self.answers, f"the script asked {path}, which this test did not record"
        return copy.deepcopy(self.answers[path])

    def close(self) -> None:
        return None


def changed(answer: Any, **fields: Any) -> Any:
    """A real answer with some of its fields changed: where a negative case starts."""
    copied = copy.deepcopy(answer)
    copied.update(fields)
    return copied
