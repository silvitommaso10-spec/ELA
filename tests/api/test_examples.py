"""The example plans in ``docs/examples/`` are plans ELA really accepts (review of M8.2, M8.3).

An example that has drifted is worse than no example: it is the first thing somebody types, and
it fails in their hands with a message about a capability they have never heard of. So a file is
not quoted in a test — it is **sent**, byte for byte, and then walked as far as it goes.

``first-task.json``: two steps, one SAFE and one that asks for consent, a note on disk with the
text the file carries. ``ask-model.json`` (M8.3, ADR 0025 §8.4): one ``model.complete`` step,
walked on a machine with **no key**, which is what everybody who clones this repository has.

Both carry a ``_nota`` key that the API ignores (ADR 0025 §8.3), and the tests send it: a comment
a file relies on has to survive the trip, or it is a trap instead of an explanation.

``docs/GETTING_STARTED.md`` is the same round from the command line; ``tests/cli/`` walks it there.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from httpx import AsyncClient

from ela.composition import Ela
from ela.domain import TaskState
from ela.ports import PROVIDER_UNAVAILABLE

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
EXAMPLE = EXAMPLES / "first-task.json"
ASK_MODEL = EXAMPLES / "ask-model.json"
NOTE = "_nota"


def example_plan() -> dict[str, Any]:
    """The file as it is on disk. Nothing is patched in: that is the whole point."""
    plan: dict[str, Any] = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    return plan


def ask_model_plan() -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(ASK_MODEL.read_text(encoding="utf-8"))
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
    """The whole example: the SAFE step runs, the second stops and asks, and after the "yes"
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


# ----------------------------------------------------------------------------------------
# What the file says about itself, and what the API does with it (ADR 0025 §8)
# ----------------------------------------------------------------------------------------


def test_the_example_declares_the_risk_the_catalogue_declares(ela: Ela) -> None:
    """The debt of the first hand-run: the file said MEDIUM, §29 and the catalogue say LOW.

    Nothing behaves differently — the Guardian reads the catalogue, never the step (ADR 0011 §2)
    — but the Device Orchestrator *does* read the step, and ``ela task show`` prints it: a plan
    that declares a risk its capability does not have is a false statement that travels.
    """
    catalogue = {spec.id: spec.risk.value for spec in ela.capabilities.specs()}

    for step in example_plan()["steps"] + ask_model_plan()["steps"]:
        assert len(step["required_capabilities"]) == 1
        assert step["risk"] == catalogue[step["required_capabilities"][0]], step["goal"]


def test_the_step_that_asks_for_consent_asks_for_it_itself(ela: Ela) -> None:
    """And the reason the file explains: ``workspace.write_note`` is LOW and needs no grant of
    its own — the scope protects it — so it is the *step* that raises the bar (ADR 0025 §8.2)."""
    note_step = example_plan()["steps"][1]
    spec = next(
        one for one in ela.capabilities.specs() if one.id == note_step["required_capabilities"][0]
    )

    assert spec.requires_authorization is False
    assert spec.scope
    assert note_step["requires_authorization"] is True


def test_both_files_explain_themselves() -> None:
    """An example that cannot say why it is the way it is teaches the wrong thing by omission."""
    for plan in (example_plan(), ask_model_plan()):
        assert NOTE in plan
        assert plan[NOTE], "an empty explanation is not one"


async def test_a_plan_with_a_note_is_accepted_and_the_note_changes_nothing(
    client: AsyncClient,
) -> None:
    plan = example_plan()
    assert NOTE in plan

    with_note = (await client.post("/tasks", json={"text": "con nota"})).json()["id"]
    first = await client.post(f"/tasks/{with_note}/plan", json=plan)
    without = (await client.post("/tasks", json={"text": "senza nota"})).json()["id"]
    stripped = {key: value for key, value in plan.items() if key != NOTE}
    second = await client.post(f"/tasks/{without}/plan", json=stripped)

    assert first.status_code == second.status_code == 200
    of_first = (await client.get(f"/tasks/{with_note}")).json()["steps"]
    of_second = (await client.get(f"/tasks/{without}")).json()["steps"]
    assert of_first == of_second


async def test_an_unknown_key_inside_a_step_is_ignored_too(client: AsyncClient) -> None:
    """``StepIn`` declares the same thing as ``PlanIn``, so a note can sit on a step."""
    plan = example_plan()
    plan["steps"][0][NOTE] = "questo step non chiede niente a nessuno"
    task_id = (await client.post("/tasks", json={"text": "una cosa"})).json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)

    assert planned.status_code == 200, planned.text
    steps = (await client.get(f"/tasks/{task_id}")).json()["steps"]
    assert NOTE not in steps[0]


# ----------------------------------------------------------------------------------------
# ``ask-model.json``: the example for the day there is a key (ADR 0025 §8.4)
# ----------------------------------------------------------------------------------------


async def test_the_model_example_is_accepted_as_it_stands(client: AsyncClient) -> None:
    task_id = (await client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=ask_model_plan())

    assert planned.status_code == 200, planned.text
    assert planned.json()["state"] == TaskState.QUEUED.value


async def test_its_task_type_is_one_the_router_knows(client: AsyncClient) -> None:
    """A type outside the routing table fails with ``routing.unknown_task_type``, before the
    network (ADR 0022 §7): the example must not be the one that teaches that lesson."""
    declared = ask_model_plan()["steps"][0]["arguments"]["task_type"]

    types = (await client.get("/diagnostics")).json()["task_types"]

    assert declared in types


async def test_it_asks_for_consent_because_the_capability_does(client: AsyncClient) -> None:
    """The mirror of ``first-task.json``: here the catalogue raises the bar, not the step.

    The content leaves this machine (§29), so no plan can opt out of being asked.
    """
    plan = ask_model_plan()
    assert "requires_authorization" not in plan["steps"][0]
    task_id = (await client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=plan)

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "waiting_approval"
    approval = (await client.get("/approvals")).json()[0]
    assert approval["capability_id"] == plan["steps"][0]["required_capabilities"][0]


async def test_without_a_key_it_fails_cleanly_and_never_reaches_the_network(
    client: AsyncClient,
) -> None:
    """What everybody who clones this repository gets, and it must be a sentence and not a hang.

    That no socket was opened is not simulated: ``tests/conftest.py`` makes httpx's network
    transports unusable, so a real call would fail this test by itself (ADR 0020 §2).
    """
    task_id = (await client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=ask_model_plan())
    await client.post(f"/tasks/{task_id}/run")
    approval = (await client.get("/approvals")).json()[0]
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "failed"
    assert run["task"]["state"] == TaskState.FAILED.value
    results = (await client.get(f"/tasks/{task_id}/results")).json()
    # Two rows, and both are the point: ``model.complete`` cannot be run twice, so the executor
    # writes a STARTED record before it acts (ADR 0021 §1) and then the outcome that settles it.
    assert [one["status"] for one in results] == ["STARTED", "FAILED"]
    assert results[-1]["error"]["code"] == PROVIDER_UNAVAILABLE
    assert results[-1]["error"]["retryable"] is False
