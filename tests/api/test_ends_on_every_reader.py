"""Every reader of ``docs/outcomes.txt`` that shows an ended task shows its why (M13.1e, decision C).

The readers are **derived from the file**, not listed here: every one has a way to render it in
:data:`RENDERERS`, or a line of «Le viste che non dicono la ragione» of ``docs/milestones/M13.1e.md``
that says why not — for the whole reader, or for one state it cannot reach. The world is closed both
ways: a reader with neither fails, and a line about a reader the file does not list is an answer to
nothing.

A rendering is the real one: **the page is served** by the application, with the identity the page
wants — the console from loopback, the phone enrolled through its page —, and **the command is
run**; the text a person reads is searched for the summary of the transition, whole, with its code
(no cut that takes the code away: the code is what one looks for). The tasks the phone reads are
created ``TRUSTED``, the ceiling the phone was enrolled with: what it shows of a task its ceiling
keeps on the Mac is :func:`test_under_the_ceiling_only_the_words_of_ela`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

import pytest

from ela.domain import TaskId, TaskState
from ela.tasks.ending import REASONED
from tests.api.ends import (
    CONSOLE_NAME,
    MISSING_BUTTON,
    PHONE_NAME,
    STOP_WORDS,
    Surfaces,
    asking,
    closing,
    ended,
    failed_after_a_yes,
    no_from_the_console,
    no_from_the_phone,
    page_text,
    question_of,
    stopped,
    task_of,
    words,
)
from tests.api.planning import created, said
from tests.api.reasons import later, run
from tests.cli.support import (  # noqa: F401 — the plain output of the CLI, as in tests/cli
    _output_without_a_terminal,
    plain,
)
from tests.docs.test_outcomes import generator, written
from tests.executive.planning import NO_PLAN, plan_of

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "milestones" / "M13.1e.md"
WHY_NOT = "## Le viste che non dicono la ragione"
LINE = re.compile(r"^- `([\w.]+)`(?: · ((?:`[A-Z_]+`(?:, )?)+))? — (.+)$", re.MULTILINE)

WRITE_PLAN = plan_of(
    {
        "name": "write",
        "goal": "write a file in the declared folder",
        "capability": "fs.write",
        "arguments": {
            "path": "ELA/fine.md",
            "body": "una fine scaduta\n",
            "overwrite": False,
            "purpose": "la prova di M13.1e",
        },
        "expected_result": "the file, with its text",
        "success_conditions": ["fs.file_exists", "fs.content_matches"],
    }
)
"""A plan the model could write whose one step asks — ``fs.write`` is ``HIGH`` —, so that a task
planned by the model can reach ``EXPIRED``: the question nobody answers."""


def why_not() -> dict[tuple[str, TaskState | None], str]:
    """The lines of the SPEC: ``(reader, None)`` for a whole reader, ``(reader, state)`` for a
    state it cannot reach."""
    section = SPEC.read_text(encoding="utf-8").split(WHY_NOT, 1)[1].split("\n## ", 1)[0]
    found: dict[tuple[str, TaskState | None], str] = {}
    for reader, states, why in LINE.findall(section):
        if not states:
            found[(reader, None)] = why
        for state in re.findall(r"`([A-Z_]+)`", states):
            found[(reader, TaskState(state))] = why
    return found


# ----------------------------------------------------------------------------------------
# How each reader is rendered, with a task in a given end
# ----------------------------------------------------------------------------------------

Rendered = tuple[str, str]
"""The task, and the text a person reads of it."""
Renderer = Callable[[Surfaces, TaskState], Awaitable[Rendered]]


async def command(s: Surfaces, *arguments: str) -> str:
    said_ = await s.world.cli(*arguments)
    assert said_.exit_code == 0, said_.stdout
    return words(plain(said_.stdout))


async def companion_home(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state, privacy="TRUSTED")
    return task, page_text((await s.phone.get("/companion/")).text)


async def console_home(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, page_text((await s.console.get("/console/")).text)


async def console_summary(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, page_text((await s.console.get("/console/task", params={"id": task})).text)


async def cli_show(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, await command(s, "task", "show", task)


async def cli_finished(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, await command(s, "task", "finished")


async def cli_list(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, await command(s, "task", "list")


async def cli_run(s: Surfaces, state: TaskState) -> Rendered:
    task = await ended(s, state)
    return task, await command(s, "task", "run", task)


async def answers_of(s: Surfaces, task: str) -> list[str]:
    return [str(one.id) for one in await s.world.ela.approvals.for_task(TaskId(UUID(task)))]


async def cli_answer(s: Surfaces, state: TaskState) -> Rendered:
    """``ela task deny`` answers with the task it denied; ``ela task approve`` repeated after the
    end answers with the task as it stands — failed after the yes, or stopped after it."""
    if state is TaskState.DENIED:
        task = await asking(s, "un no dalla riga di comando")
        return task, await command(
            s, "task", "deny", task, "--approval", await question_of(s, task)
        )
    if state is TaskState.FAILED:
        task = await failed_after_a_yes(s)
    else:
        assert state is TaskState.CANCELLED
        task = await asking(s, "un sì, poi fermato")
        yes = await question_of(s, task)
        await s.world.client.post(f"/tasks/{task}/approve", json={"approval_id": yes})
        await stopped_task(s, task)
    (yes,) = await answers_of(s, task)
    return task, await command(s, "task", "approve", task, "--approval", yes)


async def stopped_task(s: Surfaces, task: str) -> None:
    answer = await s.world.client.post(f"/tasks/{task}/cancel", json={"reason": STOP_WORDS})
    assert answer.status_code == 200, answer.text


async def cli_cancel(s: Surfaces, state: TaskState) -> Rendered:
    assert state is TaskState.CANCELLED
    task = await asking(s, "da fermare dalla riga di comando")
    return task, await command(s, "task", "cancel", task, "--reason", STOP_WORDS)


async def asked_for_a_plan(s: Surfaces) -> tuple[str, str]:
    """A task ELA was asked to plan, its planning task at the question: the task and the question."""
    task = await created(s.world.client)
    body = (await s.world.client.post(f"/tasks/{task}/planning")).json()
    assert body["outcome"] == "waiting_approval", body
    return task, str(body["approval"]["id"])


async def cli_plan(s: Surfaces, state: TaskState) -> Rendered:
    """``ela task plan <id>`` for a task whose planning ended — denied, failed, stopped — or, for a
    plan the model wrote, for a task that then expired at its own question: the plan is read again,
    with the task, by ``_detail``."""
    task, question = await asked_for_a_plan(s)
    child = str((await task_of(s, task))["planning_task_id"])
    if state is TaskState.DENIED:
        await s.world.client.post(f"/tasks/{child}/deny", json={"approval_id": question})
    elif state is TaskState.CANCELLED:
        await stopped_task(s, task)
    else:
        s.model.messages.prepare(said(NO_PLAN if state is TaskState.FAILED else WRITE_PLAN))
        await s.world.client.post(f"/tasks/{child}/approve", json={"approval_id": question})
        await s.world.client.post(f"/tasks/{task}/planning")
    if state is TaskState.EXPIRED:
        assert (await run(s.world, task))["outcome"] == "waiting_approval"
        await later(s.world, s.world.settings.core.approval_ttl.total_seconds() / 60 + 1)
    assert (await task_of(s, task))["state"] == state.value
    return task, await command(s, "task", "plan", task)


RENDERERS: Mapping[str, Renderer] = MappingProxyType(
    {
        "ela.api.companion.home": companion_home,
        "ela.api.console.home": console_home,
        "ela.api.console.summary": console_summary,
        "ela.cli.tasks.list_tasks": cli_list,
        "ela.cli.tasks.finished": cli_finished,
        "ela.cli.tasks.show": cli_show,
        "ela.cli.tasks.run": cli_run,
        "ela.cli.tasks.plan": cli_plan,
        "ela.cli.tasks.emit_answer": cli_answer,
        "ela.cli.tasks.cancel": cli_cancel,
    }
)


def readers() -> list[str]:
    return list(generator().readers_of(written()))


def cases() -> list[tuple[str, TaskState]]:
    """Every reader with a way to render it, in every end it can reach."""
    excused = why_not()
    return [
        (reader, state)
        for reader in sorted(RENDERERS)
        for state in sorted(REASONED)
        if (reader, state) not in excused
    ]


# ----------------------------------------------------------------------------------------
# The closure
# ----------------------------------------------------------------------------------------


def test_every_reader_of_the_file_is_rendered_or_says_why_not() -> None:
    whole = {reader for reader, state in why_not() if state is None}

    assert readers(), "the fingerprint lists no reader"
    assert sorted(set(readers()) - set(RENDERERS) - whole) == []
    assert set(RENDERERS).isdisjoint(whole), "a reader cannot both be rendered and say why not"


def test_every_line_of_why_not_is_about_a_reader_the_file_lists() -> None:
    named = {reader for reader, _ in why_not()}
    partial = {reader for reader, state in why_not() if state is not None}

    assert named <= set(readers())
    assert set(RENDERERS) <= set(readers())
    assert partial <= set(RENDERERS), "a state excused for a reader that is not rendered at all"


def test_a_reader_that_cannot_show_an_end_says_so_and_the_others_show_every_end() -> None:
    """The closure over the states: every rendered reader reaches every end it does not excuse."""
    reached = {reader for reader, _ in cases()}
    assert reached == set(RENDERERS)


# ----------------------------------------------------------------------------------------
# The rendering
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("reader", "state"), cases())
async def test_the_reader_shows_the_why_of_the_end(
    surfaces: Surfaces, reader: str, state: TaskState
) -> None:
    task, text = await RENDERERS[reader](surfaces, state)
    summary = (await closing(surfaces, task))["summary"]

    assert words(summary) in text, f"{reader} does not show the why of {state.value}: {text}"


# ----------------------------------------------------------------------------------------
# Who said no, and the ceiling (decision 2 of the review)
# ----------------------------------------------------------------------------------------


async def test_above_the_ceiling_the_name_with_the_role_beside_it(surfaces: Surfaces) -> None:
    s = surfaces
    from_the_phone = await no_from_the_phone(s)
    from_the_console = await no_from_the_console(s)

    phone = page_text((await s.phone.get("/companion/")).text)
    console = page_text(
        (await s.console.get("/console/task", params={"id": from_the_console})).text
    )

    assert f"ha risposto: {PHONE_NAME} (il telefono)" in phone
    assert f"Ha risposto {CONSOLE_NAME} (la console)" in console
    assert words((await closing(s, from_the_phone))["summary"]) in phone


async def test_under_the_ceiling_only_the_words_of_ela(surfaces: Surfaces) -> None:
    """Decision 2: under the ceiling the operation, the code and the role — never words somebody
    wrote: the message of an end, the words of a stop, the name of a device."""
    s = surfaces
    denied = await no_from_the_console(s)
    failed = await failed_after_a_yes(s)
    halted = await stopped(s)
    hidden = [(await closing(s, one))["payload"]["reason"] for one in (denied, failed, halted)]

    for page in (
        page_text((await s.phone.get("/companion/")).text),
        page_text((await s.away.get("/console/")).text),
    ):
        assert "deny_by_approval · ha risposto: la console" in page
        assert "fail · browser.element_missing" in page
        assert "cancel" in page
        assert CONSOLE_NAME not in page
        assert all(words(reason) not in page for reason in hidden), hidden
        assert STOP_WORDS not in page
        assert MISSING_BUTTON not in page


async def test_the_summary_from_away_says_the_words_of_ela_and_not_the_name(
    surfaces: Surfaces,
) -> None:
    s = surfaces
    denied = await no_from_the_console(s)

    away = page_text((await s.away.get("/console/task", params={"id": denied})).text)

    assert "Perché deny_by_approval" in away
    assert "Ha risposto la console" in away
    assert CONSOLE_NAME not in away
    assert "rejected by" not in away


def test_the_example_of_the_hand_test_is_a_button_example_com_does_not_have() -> None:
    plan = json.loads((ROOT / "docs" / "examples" / MISSING_BUTTON).read_text(encoding="utf-8"))
    (step,) = plan["steps"]

    assert step["required_capabilities"] == ["browser.act"]
    assert step["arguments"]["site"] == "example.com"
    assert step["arguments"]["click"] == "#non-esiste"
    assert step["arguments"]["fill"] == []
