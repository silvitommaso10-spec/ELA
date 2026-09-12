"""Tasks from the command line (spec §12, §14, §62, §65; ADR 0024 §3).

Every command is one call to the API and a rendering of the answer: the transitions are the Task
Engine's, the consent is the Guardian's, and nothing here decides anything. ``plan`` is the one
that carries a file, because the shape of a plan is the API's — temporary and unversioned until
the Planner (§13) exists — and a second place that knew it would be a second place to change.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import indent
from typing import Annotated, Any

import typer

from ela.cli import client
from ela.cli.errors import CONFIGURATION, fail, handled
from ela.cli.output import Json, emit, fields, table

__all__ = ["app"]

app = typer.Typer(no_args_is_help=True, help="Create, read, plan, run and stop tasks.")

TaskId = Annotated[str, typer.Argument(metavar="TASK_ID", help="the id of the task")]
Approval = Annotated[
    str, typer.Option("--approval", help="the id of the request you are answering")
]


def _task(payload: dict[str, Any]) -> str:
    return fields(
        [
            ("id", payload["id"]),
            ("state", payload["state"]),
            ("goal", payload["goal"]),
            ("created", payload["created_at"]),
            ("deadline", payload["deadline"]),
            ("privacy", payload["max_privacy"]),
            ("plan", payload["plan_id"]),
        ]
    )


@app.command("create")
@handled
def create(
    text: Annotated[str, typer.Argument(help="what you are asking ELA to do")],
    goal: Annotated[str | None, typer.Option("--goal", help="the goal, if not the text")] = None,
    deadline: Annotated[str | None, typer.Option("--deadline", help="ISO instant")] = None,
    privacy: Annotated[
        str | None,
        typer.Option(
            "--privacy", help="how far this task may travel: LOCAL_ONLY, TRUSTED, CLOUD_ALLOWED"
        ),
    ] = None,
    as_json: Json = False,
) -> None:
    """Create a task from what you asked. It has no plan yet, so nothing runs.

    ``--privacy`` is where this task's content may go (M12.2, D18): without it the task stays on
    this machine, which is the strictest answer and the old behaviour. It is declared **once** —
    widening a task later does not exist, you create a new one — and every placement of the task is
    judged against it, beside the level each node was enrolled with.
    """
    body: dict[str, Any] = {"text": text, "goal": goal, "deadline": deadline}
    if privacy is not None:
        body["max_privacy"] = privacy
    with client.connect() as api:
        payload = api.post("/tasks", body)
    emit(payload, as_json, _task(payload))


@app.command("list")
@handled
def list_tasks(
    state: Annotated[
        list[str] | None, typer.Option("--state", help="keep only these states; repeatable")
    ] = None,
    limit: Annotated[int | None, typer.Option("--limit", min=1, help="at most this many")] = None,
    as_json: Json = False,
) -> None:
    """The tasks ELA knows, in the order they were created."""
    with client.connect() as api:
        payload = api.get("/tasks", client.query(state=state, limit=limit))
    emit(
        payload,
        as_json,
        table(
            ("id", "state", "created", "goal"),
            [(one["id"], one["state"], one["created_at"], one["goal"]) for one in payload],
        ),
    )


@app.command("show")
@handled
def show(task_id: TaskId, as_json: Json = False) -> None:
    """A task and where each of its steps stands. No steps means: no plan yet."""
    with client.connect() as api:
        payload = api.get(f"/tasks/{task_id}")
    steps = table(
        ("step", "state", "risk", "capabilities", "goal"),
        [
            (one["id"], one["state"], one["risk"], one["required_capabilities"], one["goal"])
            for one in payload["steps"]
        ],
    )
    emit(payload, as_json, f"{_task(payload)}\n\n{steps}")


@app.command("results")
@handled
def results(task_id: TaskId, as_json: Json = False) -> None:
    """What the tools of this task produced (§63).

    The table says which step produced what and how it ended; under it, every result that has an
    output shows it in full. Nothing is shortened: the answer of a model is the reason this
    command exists, and a truncated answer is not one.
    """
    with client.connect() as api:
        payload = api.get(f"/tasks/{task_id}/results")
    emit(payload, as_json, _results(payload))


def _results(payload: list[dict[str, Any]]) -> str:
    listing = table(
        ("step", "capability", "status", "tool", "when"),
        [
            (
                one["step_id"],
                one["capability_id"],
                one["status"],
                one["tool_name"],
                one["created_at"],
            )
            for one in payload
        ],
    )
    blocks = [
        f"{one['capability_id']} — step {one['step_id']}\n"
        + indent(fields(list(one["output"].items())), "  ")
        for one in payload
        if one["output"]
    ]
    return "\n\n".join([listing, *blocks])


@app.command("plan")
@handled
def plan(
    task_id: TaskId,
    file: Annotated[Path, typer.Option("--file", help="the plan, as JSON")],
    as_json: Json = False,
) -> None:
    """Attach a plan written by hand and queue the task.

    The file is sent as it stands. Its shape belongs to the API and is temporary: the day ELA
    plans for itself, this is the endpoint that goes.
    """
    try:
        body = json.loads(file.read_text(encoding="utf-8"))
    except OSError as unreadable:
        fail(CONFIGURATION, f"--file {file}: {unreadable.strerror or unreadable}")
    except ValueError as malformed:
        fail(CONFIGURATION, f"--file {file}: not valid JSON ({malformed})")
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/plan", body)
    emit(payload, as_json, _task(payload))


@app.command("run")
@handled
def run(task_id: TaskId, as_json: Json = False) -> None:
    """Walk the plan as far as it goes, and say where it stopped.

    The answer comes back when the run stops: the task closed, your consent is needed, no node was
    eligible, or a step went out to a node and has not come back. A long step keeps the command
    waiting, because the run is the request.

    ``reason`` is filled in for the two outcomes that need it. Waiting for a node, it says which
    nodes were considered, why each was refused and — for a tool that is not installed — which tool.
    ``assigned``, it says which node is doing the work, under which assignment, and by when it is
    due (M12.2): what you need in order to decide whether to wait. Empty otherwise: an outcome that
    explains itself does not need a sentence under it.
    """
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/run")
    emit(
        payload,
        as_json,
        fields(
            [
                ("outcome", payload["outcome"]),
                ("reason", payload["reason"]),
                ("state", payload["task"]["state"]),
                ("steps executed", payload["steps"]),
            ]
        ),
    )


@app.command("approve")
@handled
def approve(task_id: TaskId, approval: Approval, as_json: Json = False) -> None:
    """Say yes to a request for consent. Read it first with `ela approvals`."""
    emit_answer(task_id, approval, "approve", as_json)


@app.command("deny")
@handled
def deny(task_id: TaskId, approval: Approval, as_json: Json = False) -> None:
    """Say no. A refusal is an answer, and it is yours as much as a yes is (§62)."""
    emit_answer(task_id, approval, "deny", as_json)


def emit_answer(task_id: str, approval: str, verb: str, as_json: bool) -> None:
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/{verb}", {"approval_id": approval})
    emit(payload, as_json, _task(payload))


@app.command("cancel")
@handled
def cancel(
    task_id: TaskId,
    reason: Annotated[str, typer.Option("--reason", help="why, for the audit trail")] = "",
    as_json: Json = False,
) -> None:
    """Stop the task (§65). Stopping ELA is yours, always."""
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/cancel", {"reason": reason})
    emit(payload, as_json, _task(payload))
