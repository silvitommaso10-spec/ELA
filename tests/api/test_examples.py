"""The example plans in ``docs/examples/`` are plans ELA really accepts (review of M8.2, M8.3).

An example that has drifted is worse than no example: it is the first thing somebody types, and
it fails in their hands with a message about a capability they have never heard of. So a file is
not quoted in a test — it is **sent**, byte for byte, and then walked as far as it goes.

``first-task.json``: two steps, one SAFE and one that asks for consent, a note on disk with the
text the file carries. ``ask-model.json`` (M8.3, ADR 0025 §8.4): one ``model.complete`` step,
walked on a machine with **no key and no cap**, which is what everybody who clones this repository
has — denied before its question since M14.1 (ADR 0057) —, and with a cap and a key, where it asks
and names what it may cost.
``speak-on-a-node.json`` (M12.4 dec. I): one ``voice.speak`` step with a long sentence, for the
proof by hand of ``GETTING_STARTED.md`` §12, where it is spoken by a node on another machine.

Both carry a ``_nota`` key that the API ignores (ADR 0025 §8.3), and the tests send it: a comment
a file relies on has to survive the trip, or it is a trap instead of an explanation.

``docs/GETTING_STARTED.md`` is the same round from the command line; ``tests/cli/`` walks it there.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from ela.composition import Ela
from ela.composition.settings import Settings
from ela.domain import TaskState
from ela.executive.spending import CAP_VARIABLE, month_of
from ela.ports import PROVIDER_UNAVAILABLE
from ela.tools import CREATES, OVERWRITES, READS
from ela.tools.settings import MAX_SPOKEN_CHARACTERS
from tests.api.reasons import example, opened
from tests.providers.support import SECRET

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
EXAMPLE = EXAMPLES / "first-task.json"
ASK_MODEL = EXAMPLES / "ask-model.json"
SPEAK_ON_A_NODE = EXAMPLES / "speak-on-a-node.json"
SPEAK_TO_THE_END = EXAMPLES / "speak-on-a-node-to-the-end.json"
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
    brought the echo of the measurement of the weights; twenty since M13.4, which brought the six of
    the browser; twenty-one since M6.3c, which brought the program that sleeps until it is stopped;
    twenty-two since the review of 2026-10-05 (decision Q), which gave §21 step 8 its own sentence;
    twenty-five since M14.1, which brought the three calls of §23 the first one does not make;
    twenty-six since M13.1e, which brought the button example.com does not have, for a failure after
    a yes with no call to the model.
    """
    found = sorted(EXAMPLES.glob("*.json"))
    assert len(found) == 26, [path.name for path in found]
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


async def test_it_asks_for_consent_because_the_capability_does(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The mirror of ``first-task.json``: here the catalogue raises the bar, not the step.

    The content leaves this machine (§29), so no plan can opt out of being asked. On a machine with
    a cap and a key (M14.1): the question names the call's worst case and what the month has left
    (decision H) — no network is touched to say it.
    """
    async with opened(
        monkeypatch, tmp_path, ELA_SPENDING_CAP_USD="5", ELA_ANTHROPIC_API_KEY=SECRET
    ) as world:
        plan = ask_model_plan()
        assert "requires_authorization" not in plan["steps"][0]
        task_id = (await world.client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]
        await world.client.post(f"/tasks/{task_id}/plan", json=plan)

        run = (await world.client.post(f"/tasks/{task_id}/run")).json()

        assert run["outcome"] == "waiting_approval"
        approval = (await world.client.get("/approvals")).json()[0]
        assert approval["capability_id"] == plan["steps"][0]["required_capabilities"][0]
        assert approval["worst_case"] == (
            "4.065536 USD, claude-opus-5-5, up to 995904 tokens in and 4096 out"
        )
        month = month_of(datetime.now(UTC)).label
        assert approval["left"] == f"5 of 5 USD left in {month}"


@pytest.mark.parametrize(
    ("name", "worst"),
    [
        ("ask-model.json", "4.065536 USD, claude-opus-5-5, up to 995904 tokens in and 4096 out"),
        (
            "ask-model-balanced.json",
            "2.032768 USD, claude-sonnet-5-5, up to 995904 tokens in and 4096 out",
        ),
        (
            "ask-model-routine.json",
            "0.216384 USD, claude-haiku-4-5-20251001, up to 195904 tokens in and 4096 out",
        ),
        (
            "ask-model-long.json",
            "0.232768 USD, claude-haiku-4-5-20251001, up to 191808 tokens in and 8192 out",
        ),
    ],
)
async def test_the_four_calls_of_section_23_ask_with_the_worst_case_the_guide_prints(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str, worst: str
) -> None:
    """The four questions of the hand test of M14.1 (§23 steps 4–7): the same plan, the same route,
    the same price — the line ``ela approvals`` prints is the line the guide expects."""
    async with opened(
        monkeypatch, tmp_path, ELA_SPENDING_CAP_USD="30", ELA_ANTHROPIC_API_KEY=SECRET
    ) as world:
        task_id = (await world.client.post("/tasks", json={"text": name})).json()["id"]
        planned = await world.client.post(f"/tasks/{task_id}/plan", json=example(name))
        assert planned.status_code == 200, planned.text

        run = (await world.client.post(f"/tasks/{task_id}/run")).json()

        assert run["outcome"] == "waiting_approval", run
        (approval,) = (await world.client.get("/approvals")).json()
        assert approval["worst_case"] == worst
        assert guide_section_23_names(worst)


async def test_without_a_cap_it_is_denied_before_the_question_and_never_reaches_the_network(
    client: AsyncClient,
) -> None:
    """What everybody who clones this repository gets, and it must be a sentence and not a hang.

    No cap: no call that spends goes out (M14.1, decision B), and the reason names the line. No
    question is asked — a yes could not make it pass — and no row is written. That no socket was
    opened is not simulated: ``tests/conftest.py`` makes httpx's network transports unusable.
    """
    task_id = (await client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]
    await client.post(f"/tasks/{task_id}/plan", json=ask_model_plan())

    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert run["outcome"] == "denied"
    assert run["task"]["state"] == TaskState.DENIED.value
    assert run["reason"].startswith("deny_by_cap: EXECUTING -> DENIED (no monthly cap: ")
    assert CAP_VARIABLE in run["reason"]
    assert (await client.get("/approvals")).json() == []
    assert (await client.get(f"/tasks/{task_id}/results")).json() == []


async def test_with_a_cap_and_no_key_it_is_denied_as_a_call_nobody_can_bound(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A cap and no key on the Core: the route finds no usable provider, so the call has no worst
    case, and a call that cannot be bounded is not made (ADR 0057) — with the provider's code in
    the reason."""
    async with opened(monkeypatch, tmp_path, ELA_SPENDING_CAP_USD="5") as world:
        task_id = (await world.client.post("/tasks", json={"text": "chiedi una cosa"})).json()["id"]
        await world.client.post(f"/tasks/{task_id}/plan", json=ask_model_plan())

        run = (await world.client.post(f"/tasks/{task_id}/run")).json()

        assert run["outcome"] == "denied"
        assert f"this call cannot be bounded: {PROVIDER_UNAVAILABLE}: " in run["reason"]


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
# ``speak-on-a-node-to-the-end.json``: §21 step 8, a node left to speak (decision Q, 2026-10-05)
# ----------------------------------------------------------------------------------------


def the_sentence(path: Path) -> str:
    plan = json.loads(path.read_text(encoding="utf-8"))
    text: str = plan["steps"][0]["arguments"]["text"]
    return text


async def test_the_plan_of_the_stop_on_a_node_is_accepted_and_asks(client: AsyncClient) -> None:
    """Sent byte for byte, like every example: one ``voice.speak`` that asks every time."""
    plan = json.loads(SPEAK_TO_THE_END.read_text(encoding="utf-8"))
    task_id = (await client.post("/tasks", json={"text": "fai parlare il PC"})).json()["id"]

    planned = await client.post(f"/tasks/{task_id}/plan", json=plan)
    run = (await client.post(f"/tasks/{task_id}/run")).json()

    assert planned.status_code == 200, planned.text
    assert run["outcome"] == "waiting_approval"
    assert (await client.get("/approvals")).json()[0]["capability_id"] == "voice.speak"
    assert len(the_sentence(SPEAK_TO_THE_END)) <= MAX_SPOKEN_CHARACTERS


def test_a_sentence_written_for_one_proof_is_not_reused_by_one_that_asks_the_opposite() -> None:
    """Decision Q: the sentence of §12 asks whoever listens to press Ctrl-C, and on 2026-10-05 it
    was pressed on ``ela serve`` in §21, where the PC must be left to speak to the end. §21 has a
    sentence of its own, which gives whoever listens no instruction; §12 keeps its own."""
    assert "Ctrl-C" in the_sentence(SPEAK_ON_A_NODE)
    heard = the_sentence(SPEAK_TO_THE_END).lower()
    for asked in ("ctrl", "premi", "premere", "guarda", "guardare"):
        assert asked not in heard, asked


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
        "fail: EXECUTING -> FAILED (fs.overwrite_mismatch: 'ELA/prova.md' was declared as a new "
        "file and something is there now)"
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


def guide_section_23_names(worst: str) -> bool:
    """Whether §23 of the guide expects this worst case in the row ``ela approvals`` writes —
    whitespace aside, as the script of §23 compares."""
    guide = (EXAMPLES.parent / "GETTING_STARTED.md").read_text(encoding="utf-8")
    section = guide[guide.index("## 23. ") :]
    return " ".join(f"worst case {worst}".split()) in " ".join(section.split())
