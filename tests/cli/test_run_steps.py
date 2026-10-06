"""What ``ela task run`` prints of the steps of a run, on every branch (M6.3b, ADR 0051).

The row used to be ``steps executed``, and in ``waiting_approval`` it carried the step ELA had
stopped on to ask — a step that had not run (the proof by hand of M17.2b). It is ``steps handled``:
the steps the run handled, the ones the executor gave its answer about in this call.

The label is written here, :data:`STEPS`, and not read from :data:`~ela.cli.tasks.RUN_LABELS`: a
block built from the command's own constant would compare the command with itself, and the word
would be held by nothing. Every branch compares the whole block the command prints; one block — the
guide's §6 — is written out letter by letter. The branches are the ones of
``tests/api/test_run_steps.py``, reached through the command line; what a node does is done through
ELA's ports, because being a node is not something the command line can do (ADR 0024).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from ela.api.schemas import WorkResultIn
from ela.cli.output import EMPTY, GAP, fields
from ela.cli.tasks import RUN_LABELS
from ela.composition import Ela, Settings, build
from ela.domain import (
    DeviceId,
    DeviceRole,
    DeviceStatus,
    OperatingSystem,
    PerformanceClass,
    PowerSource,
    PrivacyLevel,
)
from ela.executive import RunOutcome
from ela.testing.fakes import FakeBrowser, FakeClock, FakePage, FakePower
from tests.api.support import EXAMPLES, echo_plan, note_plan
from tests.api.test_nodes_work import ENVELOPE
from tests.cli.support import Cli, plain
from tests.composition.support import create_schema, declare


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """The composition's world with the guide's sites (M14.1): the step that runs and fails is a
    gesture on a field the page does not have, since a call to the model that cannot be bounded is
    denied before its question (ADR 0057)."""
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["example.com", "httpbin.org"]))
    return Settings.load()


@pytest.fixture
async def ela(settings: Settings) -> AsyncIterator[Ela]:
    """ELA as ``build`` makes it, with a browser that opens nothing and a page with no
    ``#non-esiste`` — the story of ``browser-act-missing.json``."""
    await create_schema(settings.persistence.db_url)
    built = await build(
        settings, power=FakePower(), browser=FakeBrowser(FakePage(counts={"#non-esiste": 0}))
    )
    try:
        yield built
    finally:
        await built.aclose()


STEPS = "steps handled"
"""The label of the row, written out: the one place in the suite that holds the word itself."""

STOPPED = "stopped step"
"""The row M6.3c added (ADR 0054 §7), written out like :data:`STEPS`: what the step in progress had
done when a task was stopped — ``—`` in every branch here, none of which is a stop midway."""

LABELS = ("outcome", "reason", "state", STEPS, STOPPED)

DEFINITION = "A step is handled when the executor gave its answer about it in this call"
"""The sentence ``ela task run --help`` carries, the same as the schema's."""

FIRST_TASK_ECHO = "9c5b8f26-1a2b-4c3d-8e4f-000000000001"
FIRST_TASK_NOTE = "9c5b8f26-1a2b-4c3d-8e4f-000000000002"

WAITING_FOR_CONSENT = (
    "outcome        waiting_approval\n"
    "reason         —\n"
    "state          WAITING_APPROVAL\n"
    "steps handled  9c5b8f26-1a2b-4c3d-8e4f-000000000001, 9c5b8f26-1a2b-4c3d-8e4f-000000000002\n"
    "stopped step   —"
)
"""The guide's §6, and the first block of the proof by hand of §19, letter by letter."""


@dataclass(frozen=True)
class Printed:
    """What the run under test printed, and what the block must say."""

    stdout: str
    outcome: RunOutcome
    state: str
    steps: tuple[str, ...]
    reason: str | None = None
    """A fragment the reason must contain; ``None`` for the empty cell."""


Case = Callable[[Cli, Ela, Path], Awaitable[Printed]]


def plan_file(tmp_path: Path, plan: dict[str, Any]) -> str:
    path = tmp_path / f"plan-{uuid4().hex}.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return str(path)


def example(name: str) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return plan


async def planned(
    cli: Cli, tmp_path: Path, plan: dict[str, Any], *, privacy: str | None = None
) -> str:
    """A task created and planned through the command line; returns its id."""
    extra = ("--privacy", privacy) if privacy is not None else ()
    created = await cli("task", "create", "un task della prova", *extra, "--json")
    assert created.exit_code == 0, created.stdout
    task: str = json.loads(created.stdout)["id"]
    attached = await cli("task", "plan", task, "--file", plan_file(tmp_path, plan))
    assert attached.exit_code == 0, attached.stdout
    return task


async def run(cli: Cli, task: str) -> str:
    ran = await cli("task", "run", task)
    assert ran.exit_code == 0, ran.stdout
    return plain(ran.stdout)


async def answer_the_question(cli: Cli, task: str, verb: str) -> None:
    approval = json.loads((await cli("approvals", "--json")).stdout)[0]["id"]
    answered = await cli("task", verb, task, "--approval", approval)
    assert answered.exit_code == 0, answered.stdout


async def a_node(ela: Ela) -> DeviceId:
    """A node enrolled through the ports, beating, idle and on the mains: built to win."""
    issued = await ela.enrollment.issue(PrivacyLevel.TRUSTED, DeviceRole.WORKER)
    enrolled = await ela.enrollment.enroll(
        issued.code,
        role=DeviceRole.WORKER,
        name="pc-windows",
        os=OperatingSystem.WINDOWS,
        capabilities=(),
        available_tools=tuple(tool.name for tool in ela.tools.tools()),
        performance=PerformanceClass.HIGH,
    )
    await ela.devices.heartbeat(
        enrolled.device.id, status=DeviceStatus.IDLE, power_source=PowerSource.AC
    )
    return enrolled.device.id


# ----------------------------------------------------------------------------------------
# The branches
# ----------------------------------------------------------------------------------------


async def completed(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    plan = echo_plan()
    task = await planned(cli, tmp_path, plan)
    return Printed(
        await run(cli, task), RunOutcome.COMPLETED, "COMPLETED", (plan["steps"][0]["id"],)
    )


async def completed_after_a_yes(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    task = await planned(cli, tmp_path, example("first-task.json"))
    await run(cli, task)
    await answer_the_question(cli, task, "approve")
    return Printed(await run(cli, task), RunOutcome.COMPLETED, "COMPLETED", (FIRST_TASK_NOTE,))


async def completed_with_nothing_to_handle(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    """The node takes the work and delivers it, the way its two routes do; the run that follows
    only closes the task."""
    node = await a_node(ela)
    task = await planned(cli, tmp_path, echo_plan(), privacy="TRUSTED")
    await run(cli, task)
    offer = await ela.assignments.next_for(node)
    assert offer is not None
    await ela.executor.begin(offer.id, node)
    delivery = WorkResultIn.model_validate({"assignment_id": str(offer.id), **ENVELOPE})
    await ela.executor.deliver(offer.id, node, delivery.envelope())
    return Printed(await run(cli, task), RunOutcome.COMPLETED, "COMPLETED", ())


async def waiting_approval(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    task = await planned(cli, tmp_path, example("first-task.json"))
    return Printed(
        await run(cli, task),
        RunOutcome.WAITING_APPROVAL,
        "WAITING_APPROVAL",
        (FIRST_TASK_ECHO, FIRST_TASK_NOTE),
    )


async def denied_by_the_guardian(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    plan = example("fs-outside-the-scope.json")
    task = await planned(cli, tmp_path, plan)
    return Printed(
        await run(cli, task),
        RunOutcome.DENIED,
        "DENIED",
        (plan["steps"][0]["id"],),
        reason="not within scope",
    )


async def denied_at_the_door(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    task = await planned(cli, tmp_path, note_plan())
    await run(cli, task)
    await answer_the_question(cli, task, "deny")
    # The words of the no at the door, since M13.1c (ADR 0055): the CLI's identity is ``local``'s.
    return Printed(
        await run(cli, task),
        RunOutcome.DENIED,
        "DENIED",
        (),
        reason="deny_by_approval: WAITING_APPROVAL -> DENIED (rejected by",
    )


async def failed_before_the_act(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    plan = example("fs-write.json")
    first = await planned(cli, tmp_path, plan)
    await run(cli, first)
    await answer_the_question(cli, first, "approve")
    await run(cli, first)
    again = await planned(cli, tmp_path, plan)
    return Printed(
        await run(cli, again),
        RunOutcome.FAILED,
        "FAILED",
        (plan["steps"][0]["id"],),
        reason="fs.overwrite_mismatch",
    )


async def failed_after_the_act(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    """A gesture on a field the page does not have (since M14.1: see the API's twin)."""
    plan = example("browser-act-missing.json")
    task = await planned(cli, tmp_path, plan)
    await run(cli, task)
    await answer_the_question(cli, task, "approve")
    return Printed(
        await run(cli, task),
        RunOutcome.FAILED,
        "FAILED",
        (plan["steps"][0]["id"],),
        reason="browser.element_missing",
    )


async def waiting_device(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    plan = echo_plan()
    first = plan["steps"][0]
    second = {**first, "id": "00000000-0000-4000-8000-0000000000b2"}
    second["required_capabilities"] = ["core.rm_rf"]
    second["dependencies"] = [first["id"]]
    plan["steps"].append(second)
    task = await planned(cli, tmp_path, plan)
    return Printed(
        await run(cli, task),
        RunOutcome.WAITING_DEVICE,
        "QUEUED",
        (first["id"],),
        reason="UNKNOWN_CAPABILITY",
    )


async def cancelled_at_the_door(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    task = await planned(cli, tmp_path, echo_plan())
    stopped = await cli("task", "cancel", task, "--reason", "fermato")
    assert stopped.exit_code == 0, stopped.stdout
    # The stop's words, never empty (decision 7 of the review of M6.3c): the door says what the
    # loop would.
    return Printed(await run(cli, task), RunOutcome.CANCELLED, "CANCELLED", (), reason="(fermato)")


async def expired_at_the_door(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    task = await planned(cli, tmp_path, note_plan())
    await run(cli, task)
    after = datetime.now(UTC) + ela.settings.core.approval_ttl + timedelta(minutes=1)
    later = await build(ela.settings, clock=FakeClock(after), power=FakePower())
    try:
        await later.engine.recover()
        await later.executor.close_every_open_step()
    finally:
        await later.aclose()
    # The words of the question that expired, since M13.1c (decision 2 of its review, ADR 0055).
    return Printed(
        await run(cli, task), RunOutcome.EXPIRED, "EXPIRED", (), reason="expire: WAITING_APPROVAL"
    )


async def assigned(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    await a_node(ela)
    plan = echo_plan()
    task = await planned(cli, tmp_path, plan, privacy="TRUSTED")
    return Printed(
        await run(cli, task),
        RunOutcome.ASSIGNED,
        "EXECUTING",
        (),
        reason=f"step {plan['steps'][0]['id']} assigned to node pc-windows",
    )


async def assigned_after_a_handled_step(cli: Cli, ela: Ela, tmp_path: Path) -> Printed:
    await a_node(ela)
    plan = note_plan()
    note = plan["steps"][0]
    note["requires_authorization"] = False
    echo = echo_plan()["steps"][0]
    echo["dependencies"] = [note["id"]]
    plan["steps"].append(echo)
    task = await planned(cli, tmp_path, plan, privacy="TRUSTED")
    return Printed(
        await run(cli, task),
        RunOutcome.ASSIGNED,
        "EXECUTING",
        (note["id"],),
        reason=f"step {echo['id']} assigned to node pc-windows",
    )


CASES: tuple[Case, ...] = (
    completed,
    completed_after_a_yes,
    completed_with_nothing_to_handle,
    waiting_approval,
    denied_by_the_guardian,
    denied_at_the_door,
    failed_before_the_act,
    failed_after_the_act,
    waiting_device,
    cancelled_at_the_door,
    expired_at_the_door,
    assigned,
    assigned_after_a_handled_step,
)


@pytest.mark.parametrize("case", CASES, ids=[case.__name__ for case in CASES])
async def test_the_run_prints_the_steps_it_handled(
    case: Case, cli: Cli, ela: Ela, tmp_path: Path
) -> None:
    printed = await case(cli, ela, tmp_path)
    lines = printed.stdout.rstrip("\n").splitlines()
    width = max(map(len, LABELS))
    reason_line = lines[1] if len(lines) > 1 else ""
    reason = reason_line[width + len(GAP) :]
    shown = reason if printed.reason is not None else None

    expected = fields(
        list(
            zip(
                LABELS,
                (printed.outcome.value, shown, printed.state, list(printed.steps), None),
                strict=True,
            )
        )
    )
    assert "\n".join(lines) == expected
    if printed.reason is not None:
        assert reason_line.startswith("reason".ljust(width) + GAP)
        assert printed.reason in reason


async def test_the_block_of_a_run_that_stops_to_ask_is_the_guides(cli: Cli, tmp_path: Path) -> None:
    """The guide's §6 letter by letter: the echo ran, the note is where ELA stopped to ask — two ids
    under a word that is true of both."""
    task = await planned(cli, tmp_path, example("first-task.json"))

    assert (await run(cli, task)).rstrip("\n") == WAITING_FOR_CONSENT


def test_the_command_prints_the_label_written_here() -> None:
    """The constant the guide's check reads is the word this module holds."""
    assert RUN_LABELS == LABELS


async def test_the_help_says_what_a_handled_step_is(cli: Cli) -> None:
    """Typer rewraps the docstring at the test's width, so the text is compared with its spaces
    made single; the double backticks are printed as they are.

    The help names what the user sees: the character the command prints in an empty cell, taken from
    :data:`~ela.cli.output.EMPTY` — the constant the command prints it with — and not written here
    by hand, so a cell that changed its character leaves the help stale and this test red (review of
    M6.3b, 2026-09-28)."""
    helped = await cli("task", "run", "--help")
    text = " ".join(plain(helped.stdout).split())

    assert helped.exit_code == 0
    assert DEFINITION in text
    assert f"``{EMPTY}`` means the run handled no step" in text
    assert "steps executed" not in text


async def test_the_help_says_that_an_end_always_carries_its_why(cli: Cli) -> None:
    """Decision F of M13.1c, the strong sentence, written here and not read from the code (the
    precedent of ADR 0051 §1): ``denied`` and ``failed`` — and, since decision 2 of its review,
    ``cancelled`` and ``expired`` — always carry their why, the same at every run."""
    helped = await cli("task", "run", "--help")
    text = " ".join(plain(helped.stdout).split())

    assert helped.exit_code == 0
    assert "``denied``, ``failed``, ``cancelled`` and ``expired`` always carry their why" in text
    assert "the same at the run that ended it and at every run after" in text
    assert "when this run received one" not in text
