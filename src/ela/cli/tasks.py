"""Tasks from the command line (spec §12, §14, §62, §65; ADR 0024 §3).

Every command is one call to the API and a rendering of the answer: the transitions are the Task
Engine's, the consent is the Guardian's, and nothing here decides anything. ``plan`` is the one
that may carry a file: with ``--file`` it sends a plan written by hand, as it stands — its shape is
the API's, unversioned, and a second place that knew it would be a second place to change —, and
without it it asks ELA's Planner (§13; M14.2, ADR 0058).
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import indent
from typing import Annotated, Any, Final, Literal

import typer

from ela.cli import client
from ela.cli.errors import CONFIGURATION, fail, handled
from ela.cli.output import Json, emit, fields, table
from ela.domain import Halt, listed, visible

__all__ = ["FINISHED_LIMIT", "RUN_LABELS", "app"]

app = typer.Typer(no_args_is_help=True, help="Create, read, plan, run and stop tasks.")

FINISHED_LIMIT: Final = 10
"""How many outcomes ``ela task finished`` shows when nobody says: **the CLI's own number**
(M17.2b, correction B). The CLI is a client and reads no constant of a page; a terminal has room for
a few more lines than a phone, and ``--limit`` is there for whoever wants another."""

RUN_LABELS: Final = ("outcome", "reason", "state", "steps handled", "stopped step")
"""The rows of ``ela task run``, in the order it prints them. ``steps handled`` was ``steps
executed``, and under ``waiting_approval`` it carried the step ELA had stopped on to ask, which had
not run (M6.3b, ADR 0051). ``stopped step`` says, for a task that was stopped, what the step in
progress had done (M6.3c, ADR 0054 §7). The guide's blocks of that output are checked against
these."""

HALT_WORDS: Final = {
    Halt.NOT_ACTED: "had not acted",
    Halt.ACTED_VERIFIED: "had acted; its verification passed",
    Halt.ACTED: "had acted; its effect was not verified",
    Halt.UNKNOWN: "may have acted: unknown",
    Halt.FINISHING: "still finishing",
}
"""What the line ``stopped step`` says for each value of :class:`~ela.domain.Halt` (M6.3c, ADR 0054
§7): what the verification did, never that an effect happened (ADR 0047 §9)."""


def halt_words(value: object) -> str | None:
    """The words for a ``halt`` as the API sends it; ``None`` — printed ``—`` — for none."""
    return None if value is None else HALT_WORDS[Halt(str(value))]


ROLE_WORDS: Final = {"CONSOLE": "console", "COMPANION": "phone"}
"""What the command line calls the role of who said no beside its name (M13.1e, ADR 0059). The
Core's token has a name that says it already, and is printed alone."""

WHY_HEADERS: Final = ("id", "reason", "answered by")
"""The table ``why`` under the lists: a row per task with a reason (M13.1e, decision 3 (a''))."""


def reason_of(payload: dict[str, Any]) -> str | None:
    """The why of a task's end, as the API sends it in ``end``; ``None`` for a task that did not end
    with one. Read with ``get``, as ``plan_author``: a payload written before M13.1e has no key."""
    end = payload.get("end")
    return None if end is None else str(end["reason"])


def answered_words(payload: dict[str, Any]) -> str | None:
    """Who said no, for the command line: on the Core, above every ceiling, the name with its role
    beside it — ``<name> (console)``, ``<name> (phone)`` —, the fixed name of the Core's token
    alone, and the id alone when the registry gave no name. ``None`` when nobody said no."""
    end = payload.get("end")
    answered = None if end is None else end.get("answered_by")
    if answered is None:
        return None
    name = answered["name"]
    if name is None:
        return visible(str(answered["identity"]), lines=False)
    role = ROLE_WORDS.get(str(answered["role"]))
    said = visible(str(name), lines=False)
    return said if role is None else f"{said} ({role})"


def _answered_pairs(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    """The row ``answered by``, for a no and nothing else."""
    said = answered_words(payload)
    return [] if said is None else [("answered by", said)]


def _why(tasks: list[dict[str, Any]]) -> str:
    """The table ``why`` under a list: the tasks with a reason, their reason and who said no; an
    empty string when none of them has one, so that a list of live tasks stays as it was."""
    rows = [
        (one["id"], reason_of(one), answered_words(one))
        for one in tasks
        if reason_of(one) is not None
    ]
    return "" if not rows else f"\n\nwhy\n{table(WHY_HEADERS, rows)}"


TaskId = Annotated[str, typer.Argument(metavar="TASK_ID", help="the id of the task")]
Approval = Annotated[
    str, typer.Option("--approval", help="the id of the request you are answering")
]


def _task(payload: dict[str, Any]) -> str:
    return fields(_task_pairs(payload))


def _task_pairs(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    """The rows of a task: after its state, the why of its end — ``—`` for a task that did not end
    with one — and, for a no, who answered (M13.1e): the order of ``run``, the outcome, the why,
    the state."""
    return [
        ("id", payload["id"]),
        ("state", payload["state"]),
        ("reason", reason_of(payload)),
        *_answered_pairs(payload),
        ("goal", payload["goal"]),
        ("created", payload["created_at"]),
        ("deadline", payload["deadline"]),
        ("privacy", payload["max_privacy"]),
        ("plan", payload["plan_id"]),
    ]


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
    """The tasks ELA knows, in the order they were created.

    For a task that was stopped, `ela task show` says what the step in progress had done. Under the
    list, the table `why`: denied, failed, cancelled and expired always carry their why: the words
    of the transition that ended the task — the Guardian's reason, your no, the error, the words of
    the stop, the expiry —, and a no says who answered.
    """
    with client.connect() as api:
        payload = api.get("/tasks", client.query(state=state, limit=limit))
    emit(
        payload,
        as_json,
        table(
            ("id", "state", "created", "goal"),
            [(one["id"], one["state"], one["created_at"], one["goal"]) for one in payload],
        )
        + _why(payload),
    )


@app.command("finished")
@handled
def finished(
    limit: Annotated[
        int, typer.Option("--limit", min=1, help="at most this many; the CLI's own default")
    ] = FINISHED_LIMIT,
    as_json: Json = False,
) -> None:
    """The last tasks to reach a final state, the last first, and how many there are in all.

    Under the list, the table `why`: denied, failed, cancelled and expired always carry their why:
    the words of the transition that ended the task — the Guardian's reason, your no, the error, the
    words of the stop, the expiry —, and a no says who answered.
    """
    with client.connect() as api:
        payload = api.get("/tasks/finished", client.query(limit=limit))
    shown = payload["tasks"]
    title = f"the last {limit} to finish"
    if payload["total"] > len(shown):
        title = f"{title}, of {payload['total']}"
    emit(
        payload,
        as_json,
        "\n".join(
            [
                title,
                table(
                    ("id", "state", "finished", "stopped step", "goal"),
                    [
                        (
                            one["id"],
                            one["state"],
                            one["finished_at"],
                            halt_words(one["halt"]),
                            one["goal"],
                        )
                        for one in shown
                    ],
                )
                + _why(shown),
            ]
        ),
    )


@app.command("show")
@handled
def show(task_id: TaskId, as_json: Json = False) -> None:
    """A task and where each of its steps stands. No steps means: no plan yet.

    `reason`: denied, failed, cancelled and expired always carry their why: the words of the
    transition that ended the task — the Guardian's reason, your no, the error, the words of the
    stop, the expiry —, the same `ela task run` says; and a no says who answered, in `answered by`.
    """
    with client.connect() as api:
        payload = api.get(f"/tasks/{task_id}")
    emit(payload, as_json, _detail(payload))


def _detail(payload: dict[str, Any]) -> str:
    """What ``ela task show`` prints: the task, what its step in progress had done, who wrote its
    plan, its steps — and under them, step by step, what each is called with and what verifies it.

    The arguments and the conditions were only in ``--json`` until M14.2: a plan the model wrote is
    started by the user after seeing it (ADR 0058, decision I), and seeing it means these.
    """
    steps = table(
        ("step", "state", "risk", "capabilities", "goal"),
        [
            (one["id"], one["state"], one["risk"], one["required_capabilities"], one["goal"])
            for one in payload["steps"]
        ],
    )
    described = fields(
        [
            *_task_pairs(payload),
            ("stopped step", halt_words(payload["halt"])),
            ("author", author_words(payload.get("plan_author"))),
            *_planning_pairs(payload),
        ]
    )
    blocks = "".join(f"\n\n{_step_block(one)}" for one in payload["steps"])
    return f"{described}\n\n{steps}{blocks}"


def author_words(author: dict[str, Any] | None) -> str | None:
    """Who wrote the plan, as a line: ``MODEL claude-opus-5-5 (result …)`` for the model."""
    if author is None:
        return None
    if author["by"] != "MODEL":
        return str(author["by"])
    return f"MODEL {author['model']} (result {author['result_id']})"


def _planning_pairs(payload: dict[str, Any]) -> list[tuple[str, Any]]:
    """The planning task and the model's «no plan», for a task ELA was asked to plan."""
    pairs: list[tuple[str, Any]] = []
    if payload.get("planning_task_id"):
        pairs.append(("planning", payload["planning_task_id"]))
    if payload.get("no_plan"):
        pairs.append(("no plan", visible(payload["no_plan"], lines=False)))
    return pairs


def _step_block(one: dict[str, Any]) -> str:
    """One step under the table: its arguments, its conditions, what it waits for."""
    head = f"{', '.join(one['required_capabilities']) or '—'} — step {one['id']}"
    rows = fields(
        [
            ("arguments", visible(json.dumps(one["arguments"], ensure_ascii=False), lines=False)),
            ("conditions", one["success_conditions"]),
            ("after", one["dependencies"]),
            ("authorization", one["requires_authorization"]),
        ]
    )
    return f"{head}\n{indent(rows, '  ')}"


@app.command("results")
@handled
def results(task_id: TaskId, as_json: Json = False) -> None:
    """What the tools of this task produced (§63).

    The table says which step produced what and how it ended; under it, every result that has an
    output **or an error** shows it in full. Nothing is shortened: the answer of a model is the
    reason this command exists, and a truncated answer is not one — and neither is a failure
    whose code you have to go and read in the JSON (M13.1, rilievo 3).
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
        + indent("\n".join(filter(None, (_fields(_told(one)), *_streams(one)))), "  ")
        for one in payload
        if one["output"] or one.get("error")
    ]
    return "\n\n".join([listing, *blocks])


def _shown(value: Any) -> Any:
    """A value of a result as the reader sees it: text made visible, a list with its borders.

    A list of strings is rendered by :func:`~ela.domain.listed` and never joined with a comma: the
    arguments of a command — ``["a, b"]`` and ``["a", "b"]`` — are two different commands (M13.2
    dec. 12), and the proof with two real processes found them joined here. An empty list is
    ``[]`` — a program run with no argument — and not the dash of a value that is absent.
    """
    if isinstance(value, str):
        return visible(value, lines=True)
    if isinstance(value, list) and all(isinstance(one, str) for one in value):
        return listed(value)
    return value


STREAM_KEYS: Final = frozenset(
    {"head", "tail", "cut_after", "missing", "shown", "total", "replaced"}
)
"""What a stream of a command looks like in a result (M13.2 dec. 8): a head, a tail, and the cut."""


def _fields(rows: list[tuple[str, Any]]) -> str:
    return fields(rows) if rows else ""


def _is_stream(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == STREAM_KEYS


def _streams(one: dict[str, Any]) -> list[str]:
    """Each stream of a command: how much was kept, the head, **where** it was cut, the tail.

    The line between the two halves is this surface's own, in its own words (M13.2 dec. 8): in the
    result there is no invented text, the numbers say where the cut is. What the program printed
    passes the one rendering with its lines kept (dec. 13): an ESC it wrote reaches the reader as
    ``\\x1b``, and the terminal of whoever reads does not obey it.
    """
    blocks = []
    for name, value in one["output"].items():
        if not _is_stream(value):
            continue
        said = f"{name}  shown {value['shown']} of {value['total']} bytes"
        if value["replaced"]:
            said += f", {value['replaced']} sequences that were not text replaced"
        lines = [said]
        if value["head"]:
            lines.append(visible(value["head"], lines=True).rstrip("\n"))
        if value["missing"]:
            lines.append(
                f"— cut after {value['cut_after']} bytes: {value['missing']} bytes not shown —"
            )
            if value["tail"]:
                lines.append(visible(value["tail"], lines=True).rstrip("\n"))
        blocks.append("\n".join(lines))
    return blocks


def _told(one: dict[str, Any]) -> list[tuple[str, Any]]:
    """What a result says: its output, and — since M13.1 — **its error**.

    A FAILED row with no code and no message under it sent whoever read it to the JSON to find
    out what went wrong, which is the same defect as a reason row left empty: a diagnosis that
    lives where nobody looks is not a diagnosis. The error gets a block for the same reason the
    output has one.
    """
    rows: list[tuple[str, Any]] = [
        (name, _shown(value)) for name, value in one["output"].items() if not _is_stream(value)
    ]
    error = one.get("error")
    if error:
        rows.append(("error", error["code"]))
        if error.get("message"):
            rows.append(("message", error["message"]))
        rows.append(("retryable", error.get("retryable")))
    return rows


@app.command("plan")
@handled
def plan(
    task_id: TaskId,
    file: Annotated[
        Path | None,
        typer.Option("--file", help="a plan written by hand, as JSON; without it, ELA plans"),
    ] = None,
    as_json: Json = False,
) -> None:
    """Ask ELA for the plan of a task, or attach a plan written by hand with ``--file``.

    Without ``--file`` ELA's Planner writes it (M14.2, ADR 0058): the first call stops at the
    question of the planning task — the call to the model wants your yes, with its worst case —;
    after the yes, call it again, or run the planning task, and the plan is attached and the task
    queued. Nothing is started: the run is yours.

    With ``--file`` the file is sent as it stands: its shape belongs to the API, and is unversioned.
    """
    if file is None:
        with client.connect() as api:
            payload = api.post(f"/tasks/{task_id}/planning", {})
        emit(payload, as_json, _planning(payload))
        return
    try:
        body = json.loads(file.read_text(encoding="utf-8"))
    except OSError as unreadable:
        fail(CONFIGURATION, f"--file {file}: {unreadable.strerror or unreadable}")
    except ValueError as malformed:
        fail(CONFIGURATION, f"--file {file}: not valid JSON ({malformed})")
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/plan", body)
    emit(payload, as_json, _task(payload))


def _planning(payload: dict[str, Any]) -> str:
    """What ``ela task plan`` prints without ``--file``: where the planning stands, and what to do
    next — the question to answer, or the plan to read before running it."""
    task = payload["task"]
    planning = payload["planning_task"]
    pairs: list[tuple[str, Any]] = [
        ("task", f"{task['id']} — {task['state']}"),
        ("planning", None if planning is None else f"{planning['id']} — {planning['state']}"),
        ("outcome", payload["outcome"]),
        ("reason", payload["reason"]),
        *_answered_pairs(task),
    ]
    question = payload["approval"]
    if question is not None:
        pairs += [
            ("question", question["id"]),
            ("worst case", question["worst_case"] or None),
            ("left this month", question["left"] or None),
            (
                "next",
                f"ela task approve {question['task_id']} --approval {question['id']}, "
                f"then ela task plan {task['id']} again",
            ),
        ]
    if payload["no_plan"]:
        pairs.append(("no plan", visible(payload["no_plan"], lines=False)))
    pairs += [("problem", problem) for problem in payload["problems"]]
    said = fields(pairs)
    if payload["outcome"] == "planned":
        return f"{said}\n\n{_detail(task)}"
    return said


@app.command("run")
@handled
def run(task_id: TaskId, as_json: Json = False) -> None:
    """Walk the plan as far as it goes, and say where it stopped.

    The answer comes back when the run stops: the task closed, your consent is needed, no node was
    eligible, or a step went out to a node and has not come back. A long step keeps the command
    waiting, because the run is the request.

    ``steps handled`` lists the steps this run handled. A step is handled when the executor gave its
    answer about it in this call: it ran, it was closed from what a node delivered or a crash left,
    it failed, the Guardian denied it, or ELA stopped on it to ask for your consent. A step handed
    to a node, or waiting for one, is not handled. After ``waiting_approval``, ``denied`` and
    ``failed`` the last one is where the run stopped; ``—`` means the run handled no step.

    ``stopped step`` says, for a task that was stopped, what the step in progress had done: it had
    not acted, it had acted and its verification passed, it had acted and nothing verified its
    effect, nobody knows whether it acted, or it is still finishing. ``—`` when no step was in
    progress, and for every outcome but ``cancelled``.

    ``reason`` says why the run stopped when the outcome alone does not. Waiting for a node, which
    nodes were considered, why each was refused and — for a tool that is not installed — which tool.
    ``assigned``, which node is doing the work, under which assignment, and by when it is due: what
    you need in order to decide whether to wait. ``denied``, ``failed``, ``cancelled`` and
    ``expired`` always carry their why: the words of the transition that ended the task — the
    Guardian's reason, your no, the error, the words of the stop, the expiry —, the same at the run
    that ended it and at every run after. Empty for every other outcome: an outcome that explains
    itself does not need a sentence under it.
    """
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/run")
    emit(payload, as_json, _ran(payload))


def _ran(payload: dict[str, Any]) -> str:
    """What ``ela task run`` prints: the rows of :data:`RUN_LABELS`, in their order, and after the
    reason of a no who answered (M13.1e) — a row of its own, not one of :data:`RUN_LABELS`, so the
    guide's blocks of every other outcome stay what they are."""
    values = (
        payload["outcome"],
        payload["reason"],
        payload["task"]["state"],
        payload["steps"],
        halt_words(payload["halt"]),
    )
    rows = list(zip(RUN_LABELS, values, strict=True))
    return fields([*rows[:2], *_answered_pairs(payload["task"]), *rows[2:]])


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


def emit_answer(
    task_id: str, approval: str, verb: Literal["approve", "deny"], as_json: bool
) -> None:
    """The two answers, through their two routes. ``verb`` is a ``Literal`` and not a ``str``: the
    fingerprint of ``docs/outcomes.txt`` reads its values, and names only the routes it calls."""
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
    """Stop the task (§65). Stopping ELA is yours, always.

    The answer comes before the step in progress has closed: `ela task show` says whether it had
    acted.
    """
    with client.connect() as api:
        payload = api.post(f"/tasks/{task_id}/cancel", {"reason": reason})
    emit(payload, as_json, _task(payload))
