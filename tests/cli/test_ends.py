"""What the command line says of an end (M13.1e, ADR 0059): the row ``reason``, who answered a no,
and the table ``why`` under the lists.

The CLI is on the Core, above every ceiling: the reason whole, and for a no the name with its role
beside it — the fixed name for the Core's token, ``<name> (console)`` or ``<name> (phone)`` for a
row of the registry, the id alone for an identity the registry does not know.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

import pytest

from ela.cli.tasks import RUN_LABELS
from ela.domain import ApprovalId, ApprovalStatus, TaskId
from tests.api.ends import (
    CONSOLE_NAME,
    PHONE_NAME,
    STOP_WORDS,
    Surfaces,
    asking,
    closing,
    failed_after_a_yes,
    no_from_the_command_line,
    no_from_the_console,
    no_from_the_phone,
    question_of,
    words,
)
from tests.api.planning import created
from tests.cli.support import plain

LOCAL_NAME = "the command line on the Core"


async def said(s: Surfaces, *arguments: str) -> str:
    result = await s.world.cli(*arguments)
    assert result.exit_code == 0, result.stdout
    return plain(result.stdout)


def row(output: str, label: str) -> str | None:
    """The value of the row ``label`` of a block of ``name  value`` lines, its spaces gathered."""
    for line in output.splitlines():
        if line.startswith(label + "  "):
            return words(line[len(label) :])
    return None


async def summary(s: Surfaces, task: str) -> str:
    return words((await closing(s, task))["summary"])


async def test_show_says_the_reason_under_the_state_and_who_answered(surfaces: Surfaces) -> None:
    s = surfaces
    task = await no_from_the_command_line(s)

    shown = await said(s, "task", "show", task)

    lines = [line.split("  ")[0] for line in shown.splitlines()]
    assert lines.index("reason") == lines.index("state") + 1
    assert row(shown, "reason") == await summary(s, task)
    assert row(shown, "answered by") == LOCAL_NAME


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (no_from_the_console, f"{CONSOLE_NAME} (console)"),
        (no_from_the_phone, f"{PHONE_NAME} (phone)"),
    ],
)
async def test_a_row_of_the_registry_is_its_name_with_its_role(
    surfaces: Surfaces, answer: Callable[[Surfaces], Awaitable[str]], expected: str
) -> None:
    task = await answer(surfaces)

    assert row(await said(surfaces, "task", "show", task), "answered by") == expected


async def test_an_identity_the_registry_does_not_know_is_its_id(surfaces: Surfaces) -> None:
    s = surfaces
    task = await asking(s, "una risposta di prima")
    unknown = str(uuid4())
    answered = await s.world.ela.approvals.respond(
        ApprovalId(UUID(await question_of(s, task))),
        status=ApprovalStatus.REJECTED,
        responded_by=unknown,
        now=s.world.ela.clock.now(),
    )
    await s.world.ela.engine.deny(TaskId(UUID(task)), approval=answered)

    assert row(await said(s, "task", "show", task), "answered by") == unknown


async def test_a_task_that_did_not_end_says_no_reason_and_nobody(surfaces: Surfaces) -> None:
    s = surfaces
    task = await asking(s, "una domanda")

    shown = await said(s, "task", "show", task)

    assert row(shown, "reason") == "—"
    assert row(shown, "answered by") is None


async def test_the_answers_of_deny_and_cancel_say_the_reason(surfaces: Surfaces) -> None:
    s = surfaces
    asked = await asking(s, "un no")
    denied = await said(s, "task", "deny", asked, "--approval", await question_of(s, asked))
    other = await asking(s, "da fermare")
    stopped = await said(s, "task", "cancel", other, "--reason", STOP_WORDS)

    assert row(denied, "reason") == await summary(s, asked)
    assert row(denied, "answered by") == LOCAL_NAME
    assert row(stopped, "reason") == await summary(s, other)
    assert STOP_WORDS in str(row(stopped, "reason"))


async def test_finished_and_list_say_the_why_in_a_table_of_their_own(surfaces: Surfaces) -> None:
    """Decision 3 (a''): the table of today does not change; under it, ``why``, a row per task
    with a reason — the id, the reason, who answered."""
    s = surfaces
    denied = await no_from_the_console(s)
    failed = await failed_after_a_yes(s)

    denied_reason = await summary(s, denied)
    failed_reason = await summary(s, failed)

    for output in (await said(s, "task", "finished"), await said(s, "task", "list")):
        lines = output.splitlines()
        assert "why" in lines
        under = lines[lines.index("why") + 1 :]
        assert words(under[0]) == "ID REASON ANSWERED BY"
        rows = {words(line).split(" ", 1)[0]: words(line) for line in under[1:]}
        assert rows[denied] == f"{denied} {denied_reason} {CONSOLE_NAME} (console)"
        assert rows[failed] == f"{failed} {failed_reason} —"


async def test_run_says_who_answered_a_no_and_nothing_more_for_the_rest(
    surfaces: Surfaces,
) -> None:
    """The row ``answered by`` is conditional: ``RUN_LABELS`` does not change, and the check of the
    guide's blocks of ``run`` (ADR 0055 §4) reads only those."""
    s = surfaces
    denied = await no_from_the_console(s)
    failed = await failed_after_a_yes(s)

    ran_denied = await said(s, "task", "run", denied)
    ran_failed = await said(s, "task", "run", failed)

    assert RUN_LABELS == ("outcome", "reason", "state", "steps handled", "stopped step")
    labels = [line.split("  ")[0] for line in ran_denied.splitlines()]
    assert labels == ["outcome", "reason", "answered by", "state", "steps handled", "stopped step"]
    assert row(ran_denied, "answered by") == f"{CONSOLE_NAME} (console)"
    assert row(ran_failed, "answered by") is None


async def test_plan_says_who_answered_the_planning_task_of_a_denied_task(
    surfaces: Surfaces,
) -> None:
    s = surfaces
    task = await created(s.world.client)
    body = (await s.world.client.post(f"/tasks/{task}/planning")).json()
    await s.world.client.post(
        f"/tasks/{body['planning_task']['id']}/deny", json={"approval_id": body["approval"]["id"]}
    )

    planned = await said(s, "task", "plan", task)

    assert row(planned, "reason") == await summary(s, task)
    assert row(planned, "answered by") == LOCAL_NAME


@pytest.mark.parametrize("name", ["show", "finished", "list"])
async def test_the_help_says_every_end_carries_its_why(surfaces: Surfaces, name: str) -> None:
    """The strong sentence of M13.1c, written here and not read from the code (ADR 0051 §1)."""
    helped = words(await said(surfaces, "task", name, "--help"))

    assert (
        "denied, failed, cancelled and expired always carry their why: the words of the "
        "transition that ended the task" in helped
    )
    assert "a no says who answered" in helped
