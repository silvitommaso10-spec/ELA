"""The example plans in ``docs/examples/`` are plans ELA really accepts (review of M8.2, M8.3).

An example that has drifted is worse than no example: it is the first thing somebody types, and
it fails in their hands with a message about a capability they have never heard of. So a file is
not quoted in a test — it is **sent**, byte for byte, and then walked as far as it goes.

``first-task.json``: two steps, one SAFE and one that asks for consent, a note on disk with the
text the file carries. ``ask-model.json`` (M8.3, ADR 0025 §8.4): one ``model.complete`` step,
walked on a machine with **no key**, which is what everybody who clones this repository has.
``speak-on-a-node.json`` (M12.4 dec. I): one ``voice.speak`` step with a long sentence, for the
proof by hand of ``GETTING_STARTED.md`` §12, where it is spoken by a node on another machine.

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
from ela.composition.settings import Settings
from ela.domain import TaskState
from ela.ports import PROVIDER_UNAVAILABLE
from ela.tools import CREATES, OVERWRITES, READS
from ela.tools.settings import MAX_SPOKEN_CHARACTERS

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
EXAMPLE = EXAMPLES / "first-task.json"
ASK_MODEL = EXAMPLES / "ask-model.json"
SPEAK_ON_A_NODE = EXAMPLES / "speak-on-a-node.json"
COMPANION = EXAMPLES / "companion.json"
ECHO = EXAMPLES / "echo.json"
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


def test_every_example_explains_itself() -> None:
    """An example that cannot say why it is the way it is teaches the wrong thing by omission.

    Closed over the folder since M12.5: a fourth file arrived, and a list of three would have let
    a fifth arrive unexplained. Seven since M13.1, which brought the three of the filesystem;
    thirteen since M13.2, which brought the six of the terminal; fourteen since M13.3, which
    brought the echo of the measurement of the weights.
    """
    found = sorted(EXAMPLES.glob("*.json"))
    assert len(found) == 14, [path.name for path in found]
    for path in found:
        plan = json.loads(path.read_text(encoding="utf-8"))
        assert NOTE in plan, path.name
        assert plan[NOTE], "an empty explanation is not one"


async def test_the_plan_of_the_companion_is_accepted_and_asks_twice(client: AsyncClient) -> None:
    """The plan of the hand test of M12.5, sent byte for byte: two steps that both ask, and no
    model key anywhere — the proof is made on one machine, with the iPhone answering."""
    plan = json.loads(COMPANION.read_text(encoding="utf-8"))
    created = await client.post(
        "/tasks", json={"text": "la prova del companion", "max_privacy": "TRUSTED"}
    )
    task_id = created.json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)

    assert planned.status_code == 200, planned.text
    ran = await client.post(f"/tasks/{task_id}/run")
    assert ran.status_code == 200, ran.text
    assert ran.json()["task"]["state"] == TaskState.WAITING_APPROVAL.value
    waiting = (await client.get("/approvals")).json()
    assert len(waiting) == 1
    assert waiting[0]["capability_id"] == "workspace.write_note"


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


# ----------------------------------------------------------------------------------------
# ``speak-on-a-node.json``: the proof by hand of a node on a PC (M12.4 dec. I)
# ----------------------------------------------------------------------------------------


def speak_on_a_node_plan() -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(SPEAK_ON_A_NODE.read_text(encoding="utf-8"))
    return plan


async def test_the_node_example_is_accepted_as_it_stands(client: AsyncClient) -> None:
    task_id = (await client.post("/tasks", json={"text": "fai parlare il PC"})).json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=speak_on_a_node_plan())

    assert planned.status_code == 200, planned.text
    assert planned.json()["state"] == TaskState.QUEUED.value


def test_its_sentence_is_long_and_still_one_ela_may_say() -> None:
    """Long on purpose — the guide has somebody watch a process tree and press Ctrl-C while it
    is spoken — and never past the ceiling, or the proof would stop at ``arguments.invalid``."""
    text = speak_on_a_node_plan()["steps"][0]["arguments"]["text"]

    assert 400 <= len(text) <= MAX_SPOKEN_CHARACTERS


async def test_it_asks_for_consent_every_time(client: AsyncClient) -> None:
    """The first ``run`` stops and asks: that is the step of the guide the approval answers."""
    task_id = (await client.post("/tasks", json={"text": "fai parlare il PC"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=speak_on_a_node_plan())

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "waiting_approval"
    approval = (await client.get("/approvals")).json()[0]
    assert approval["capability_id"] == "voice.speak"


# ----------------------------------------------------------------------------------------
# ``echo.json``: the work of the measurement of the weights (M13.3, GETTING_STARTED §17)
# ----------------------------------------------------------------------------------------


async def test_the_echo_of_the_measurement_runs_without_a_question(client: AsyncClient) -> None:
    """The shortest work that travels, sent byte for byte: ``SAFE``, so it is repeated ten times
    with nobody asked — and on the Core alone, without ``--privacy``, it completes here."""
    plan = json.loads(ECHO.read_text(encoding="utf-8"))
    task_id = (await client.post("/tasks", json={"text": "un'eco"})).json()["id"]
    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)
    assert planned.status_code == 200, planned.text

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "completed", run
    assert plan["steps"][0]["required_capabilities"] == ["core.echo"]


# ----------------------------------------------------------------------------------------
# The three plans of M13.1: the filesystem outside the workspace (ADR 0045)
# ----------------------------------------------------------------------------------------


def results_of(response: Any) -> list[dict[str, Any]]:
    listed: list[dict[str, Any]] = response.json()
    return listed


def fs_plan(name: str) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return plan


async def asked(client: AsyncClient, plan: dict[str, Any], text: str) -> dict[str, Any]:
    """Send a plan, run it once, and return the question it stopped on."""
    task_id = (await client.post("/tasks", json={"text": text})).json()["id"]
    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)
    assert planned.status_code == 200, planned.text
    await client.post(f"/tasks/{task_id}/run")
    waiting = (await client.get("/approvals")).json()
    assert len(waiting) == 1, waiting
    question: dict[str, Any] = waiting[0]
    question["task_id"] = task_id
    return question


async def say_yes(client: AsyncClient, question: dict[str, Any]) -> dict[str, Any]:
    await client.post(f"/tasks/{question['task_id']}/approve", json={"approval_id": question["id"]})
    run: dict[str, Any] = (await client.post(f"/tasks/{question['task_id']}/run")).json()
    return run


async def test_the_write_example_asks_and_says_it_creates_a_file(
    client: AsyncClient, settings: Settings
) -> None:
    """The first step of the proof by hand: the question names the **resolved** path (dec. G)."""
    question = await asked(client, fs_plan("fs-write.json"), "scrivi fuori dalla workspace")

    assert question["capability_id"] == "fs.write"
    assert question["risk"] == "HIGH"
    assert question["target"] == str(settings.filesystem.root / "ELA" / "prova.md")
    assert question["does"] == CREATES


async def test_the_write_example_leaves_the_file_the_note_promises(
    client: AsyncClient, settings: Settings
) -> None:
    question = await asked(client, fs_plan("fs-write.json"), "scrivi fuori dalla workspace")

    run = await say_yes(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    written = settings.filesystem.root / "ELA" / "prova.md"
    assert written.read_text(encoding="utf-8").startswith("# M13.1")
    assert not str(written).startswith(str(settings.workspace.workspace_dir))


async def test_the_write_example_spends_its_yes_and_every_record_names_it(
    client: AsyncClient,
) -> None:
    """M13.1b: the audit says *with which authorization* the write happened (§32).

    Until M13.1b this was null on both result rows and on ``TOOL_EXECUTED``, and the grant stayed
    unspent for its hour: the ``HIGH`` row was missing from ``CONSUMING_RULES``. What the proof by
    hand of ``GETTING_STARTED.md`` §15 asks the user to see with ``--json``.
    """
    question = await asked(client, fs_plan("fs-write.json"), "scrivi fuori dalla workspace")
    await say_yes(client, question)

    task_id = question["task_id"]
    results = results_of(await client.get(f"/tasks/{task_id}/results"))
    events = (await client.get("/audit", params={"task_id": task_id})).json()
    (granted,) = [e for e in events if e["event_type"] == "AUTHORIZATION_GRANTED"]
    (executed,) = [e for e in events if e["event_type"] == "TOOL_EXECUTED"]

    assert [r["status"] for r in results] == ["STARTED", "SUCCEEDED"]
    assert granted["authorization_id"] is not None
    assert [r["authorization_id"] for r in results] == [granted["authorization_id"]] * 2
    assert executed["authorization_id"] == granted["authorization_id"]
    assert executed["payload"]["uses"] == 1


async def test_the_same_plan_sent_again_is_refused_before_anybody_is_asked(
    client: AsyncClient, settings: Settings
) -> None:
    """**The blocker the proof by hand found**, and the shape of its repair (ADR 0045 §6-bis).

    The plan asserts «nothing is there». After the first run something is, so the call would be
    refused the instant it ran — and a question is composed only for what would succeed now. The
    task fails without asking, and the file that was there is the file that is still there.
    """
    first = await asked(client, fs_plan("fs-write.json"), "scrivi fuori dalla workspace")
    await say_yes(client, first)

    task_id = (await client.post("/tasks", json={"text": "riscrivi lo stesso file"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=fs_plan("fs-write.json"))
    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["task"]["state"] == TaskState.FAILED.value, run
    assert (await client.get("/approvals")).json() == [], "nobody is asked what is already lost"
    events = (await client.get("/audit")).json()
    assert "BELL_RUNG" not in [event["event_type"] for event in events]
    # Nothing ran, so there is no result to carry the error — and the reason must still reach a
    # person: `ela task run` shows it (M13.1, rilievo 3).
    assert results_of(await client.get(f"/tasks/{task_id}/results")) == []
    assert run["reason"] == (
        "fs.overwrite_mismatch: 'ELA/prova.md' was declared as a new file and something is "
        "there now"
    )
    assert (
        settings.filesystem.root.joinpath("ELA", "prova.md")
        .read_text(encoding="utf-8")
        .startswith("# M13.1")
    )


async def test_a_plan_that_declares_the_overwrite_is_asked_and_says_so(
    client: AsyncClient,
) -> None:
    """And the way to really overwrite: the plan asserts what is true, so the question exists."""
    await say_yes(client, await asked(client, fs_plan("fs-write.json"), "scrivi"))
    plan = fs_plan("fs-write.json")
    plan["steps"][0]["arguments"]["overwrite"] = True

    question = await asked(client, plan, "sovrascrivi davvero")

    assert question["does"] == OVERWRITES
    run = await say_yes(client, question)
    assert run["task"]["state"] == TaskState.COMPLETED.value, run


async def test_the_read_example_puts_the_content_in_the_result_and_not_in_the_audit(
    client: AsyncClient,
) -> None:
    """dec. P: the bytes go into the result, and so does their size; the audit keeps the path.

    Until M13.1b this docstring said the audit kept «the path and the size», and the body checked
    only the path: no event has ever carried the size of a read that succeeded. The size is
    ``bytes``, in the result beside the content; ``TOOL_EXECUTED`` has its fixed keys and nothing
    else. A read that *fails* is another matter, and carries sizes on purpose (ADR 0045 §8).
    """
    await say_yes(client, await asked(client, fs_plan("fs-write.json"), "scrivi"))

    question = await asked(client, fs_plan("fs-read.json"), "rileggi")
    assert question["capability_id"] == "fs.read"
    assert question["risk"] == "MEDIUM"
    assert question["does"] == READS, "a read is never told it overwrites anything"
    run = await say_yes(client, question)

    assert run["task"]["state"] == TaskState.COMPLETED.value, run
    results = (await client.get(f"/tasks/{question['task_id']}/results")).json()
    assert results[-1]["output"]["content"].startswith("# M13.1")
    content = results[-1]["output"]["content"]
    assert results[-1]["output"]["bytes"] == len(content.encode("utf-8"))
    trail = json.dumps((await client.get("/audit")).json())
    assert "Questo file sta fuori dalla workspace" not in trail
    assert "ELA/prova.md" in trail
    read = (await client.get("/audit", params={"task_id": question["task_id"]})).json()
    (executed,) = [e for e in read if e["event_type"] == "TOOL_EXECUTED"]
    assert set(executed["payload"]) == {
        "status",
        "result_id",
        "targets",
        "duration_ms",
        "device",
        "uses",
    }, "a key beyond the fixed ones is a channel nobody decided to open"
    assert executed["error"] is None


async def test_the_plan_outside_the_scope_is_denied_without_asking_anybody(
    client: AsyncClient, ela: Ela, settings: Settings
) -> None:
    """The step of the proof by hand that proves itself by an **absence** (dec. R).

    A defence that denies before the question is proved by the bell that does not ring, not by
    the denial that appears: if the question existed, the iPhone would have buzzed.
    """
    task_id = (await client.post("/tasks", json={"text": "fuori dallo scope"})).json()["id"]
    planned = await client.post(f"/tasks/{task_id}/plan", json=fs_plan("fs-outside-the-scope.json"))
    assert planned.status_code == 200, planned.text

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["task"]["state"] == TaskState.DENIED.value, run
    assert (await client.get("/approvals")).json() == [], "nobody is asked what is refused anyway"
    events = (await client.get("/audit")).json()
    kinds = [event["event_type"] for event in events]
    assert "BELL_RUNG" not in kinds, "the phone must not buzz for a denial"
    decided = [event for event in events if event["event_type"] == "PERMISSION_DECIDED"][-1]
    assert decided["payload"]["rule"] == "SCOPE"
    assert not (settings.filesystem.root / "altrove").exists()


def test_the_paths_of_the_examples_are_the_scope_the_guide_tells_you_to_write() -> None:
    """``ELA_FS_SCOPE=ELA`` in ``GETTING_STARTED.md``, and the plans walk the same folder.

    An example whose path fell outside the scope of the guide would be denied in the reader's
    hands, with a message about a boundary they thought they had written correctly.
    """
    guide = (EXAMPLES.parent / "GETTING_STARTED.md").read_text(encoding="utf-8")

    assert "ELA_FS_SCOPE=ELA" in guide
    assert fs_plan("fs-write.json")["steps"][0]["arguments"]["path"].startswith("ELA/")
    assert fs_plan("fs-read.json")["steps"][0]["arguments"]["path"].startswith("ELA/")
    assert not fs_plan("fs-outside-the-scope.json")["steps"][0]["arguments"]["path"].startswith(
        "ELA/"
    )
