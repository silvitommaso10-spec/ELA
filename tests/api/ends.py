"""Every end with a reason, on every surface (M13.1e, ADR 0059).

The world of ``tests/api/reasons.py`` — ELA as ``build`` makes it, the browser of ``ela.testing``,
the guide's sites — with a cap, a key and a model that answers what the test prepares
(``tests/api/planning.py``), and **a console and a phone enrolled through their own pages**: the no
of each surface that can answer a question is given as a person gives it, through the page or the
command line, and ``responded_by`` is what the identity resolved for that request. The console
reads from loopback, where every task is visible, and from the tailnet, where the ceiling the user
imposed holds; the phone always under its own.

Every end of :data:`~ela.tasks.ending.REASONED` is reached as production reaches it: the no, the
gesture on a button the page does not have, the stop, the question that expired at start-up.
"""

from __future__ import annotations

import html
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api.security import CONSOLE_COOKIE
from ela.domain import TaskState
from ela.testing.fakes import FakePage
from tests.api.planning import with_a_model
from tests.api.reasons import World, example, later, run
from tests.api.support import BASE, echo_plan, note_plan, queued
from tests.providers.support import FakeAnthropic

LOOPBACK = "http://127.0.0.1"
"""The Mac's browser at the Mac: both ends of the socket loopback, every task visible."""
TAILNET = "http://100.76.92.39"
"""The Mac on the tailnet: the console reads under the ceiling the user imposed."""
PHONE_PEER = ("100.70.98.26", 54536)
CONSOLE_NAME = "la console di prova"
PHONE_NAME = "il telefono di prova"
STOP_WORDS = "la prova di M13.1e"
MISSING_BUTTON = "browser-act-missing-here.json"
"""The example of the hand test (M13.1e): a click on a button example.com does not have."""


@dataclass(frozen=True)
class Surfaces:
    """One ELA, its CLI, and the two browsers that can answer a question."""

    world: World
    model: FakeAnthropic
    console: AsyncClient
    """The console, enrolled from loopback: it sees every task."""
    away: AsyncClient
    """The same console's cookie from the tailnet: the ceiling the user imposed, ``TRUSTED``."""
    phone: AsyncClient
    """The phone, enrolled ``TRUSTED``: it sees a task created ``TRUSTED`` and no other."""


def browser(app: FastAPI, base: str, peer: tuple[str, int] = ("127.0.0.1", 123)) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=peer), base_url=base)


async def enrol(
    client: AsyncClient, page: AsyncClient, path: str, role: str, name: str, system: str, base: str
) -> None:
    """A code minted by the Core for ``role``, presented by the browser with the name the user
    types at enrolment."""
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": role})
    assert minted.status_code == 201, minted.text
    answered = await page.post(
        path,
        data={"code": minted.json()["code"], "name": name, "os": system},
        headers={"Origin": base},
    )
    assert answered.status_code == 303, answered.text


@pytest.fixture
async def surfaces(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Surfaces]:
    async with opened_surfaces(monkeypatch, tmp_path) as built:
        yield built


@asynccontextmanager
async def opened_surfaces(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[Surfaces]:
    """The world of :func:`surfaces`, for a recording that lives longer than one test
    (``tests/docs/real_ends.py``)."""
    async with with_a_model(monkeypatch, tmp_path) as (world, model), AsyncExitStack() as stack:
        console = await stack.enter_async_context(browser(world.app, LOOPBACK))
        away = await stack.enter_async_context(browser(world.app, TAILNET, PHONE_PEER))
        phone = await stack.enter_async_context(browser(world.app, BASE))
        await enrol(
            world.client, console, "/console/enroll", "CONSOLE", CONSOLE_NAME, "MACOS", LOOPBACK
        )
        cookie = console.cookies.get(CONSOLE_COOKIE)
        assert cookie is not None
        away.cookies.set(CONSOLE_COOKIE, cookie)
        await enrol(world.client, phone, "/companion/enroll", "COMPANION", PHONE_NAME, "IOS", BASE)
        yield Surfaces(world, model, console, away, phone)


# ----------------------------------------------------------------------------------------
# Reading what a surface shows
# ----------------------------------------------------------------------------------------


def words(text: str) -> str:
    """``text`` with its spaces gathered: a page wraps where it likes, and a line of the CLI is
    aligned with spaces nobody chose."""
    return " ".join(text.split())


def page_text(page: str) -> str:
    """What a person reads on a page: the tags out, the entities back, the spaces gathered."""
    return words(html.unescape(re.sub(r"<[^>]+>", " ", page)))


async def task_of(s: Surfaces, task: str) -> dict[str, Any]:
    answer = await s.world.client.get(f"/tasks/{task}")
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


async def question_of(s: Surfaces, task: str) -> str:
    pending = [
        one for one in (await s.world.client.get("/approvals")).json() if one["task_id"] == task
    ]
    assert pending, f"task {task} asks nothing"
    approval: str = pending[0]["id"]
    return approval


# ----------------------------------------------------------------------------------------
# The ends, as production reaches them
# ----------------------------------------------------------------------------------------


async def asking(s: Surfaces, goal: str, *, privacy: str | None = None) -> str:
    """A task stopped at its question: the note of ``note_plan``, which asks before it writes."""
    task = await queued(s.world.client, note_plan(), goal, privacy=privacy)
    assert (await run(s.world, task))["outcome"] == "waiting_approval"
    return task


async def no_from_the_command_line(s: Surfaces, *, privacy: str | None = None) -> str:
    """The no of ``ela task deny``: the Core's token, the identity of ``LOCAL_USER``."""
    task = await asking(s, "il no dalla riga di comando", privacy=privacy)
    said = await s.world.cli("task", "deny", task, "--approval", await question_of(s, task))
    assert said.exit_code == 0, said.stdout
    return task


async def the_console_says_no(s: Surfaces, task: str) -> None:
    """The «Rifiuta» of the console, from loopback, to the question of ``task``."""
    answered = await s.console.post(
        "/console/answer",
        data={"id": await question_of(s, task), "answer": "no"},
        headers={"Origin": LOOPBACK},
    )
    assert answered.status_code == 303, answered.text


async def the_phone_says_no(s: Surfaces, task: str) -> None:
    """The «No» of the phone to the question of ``task``."""
    answered = await s.phone.post(
        "/companion/answer",
        data={"id": await question_of(s, task), "answer": "no"},
        headers={"Origin": BASE},
    )
    assert answered.status_code == 303, answered.text


async def no_from_the_console(s: Surfaces, *, privacy: str | None = None) -> str:
    """The «Rifiuta» of the console, from loopback."""
    task = await asking(s, "il no dalla console", privacy=privacy)
    await the_console_says_no(s, task)
    return task


async def no_from_the_phone(s: Surfaces) -> str:
    """The «No» of the phone: the task ``TRUSTED``, or the phone could not see what it answers."""
    task = await asking(s, "il no dal telefono", privacy="TRUSTED")
    await the_phone_says_no(s, task)
    return task


async def failed_after_a_yes(s: Surfaces, *, privacy: str | None = None) -> str:
    """The example of the hand test: the yes, the page opens, the button is not there."""
    s.world.browser.page = FakePage(counts={"#non-esiste": 0})
    task = await queued(
        s.world.client, example(MISSING_BUTTON), "un bottone che non c'è", privacy=privacy
    )
    assert (await run(s.world, task))["outcome"] == "waiting_approval"
    yes = await s.world.client.post(
        f"/tasks/{task}/approve", json={"approval_id": await question_of(s, task)}
    )
    assert yes.status_code == 200, yes.text
    assert (await run(s.world, task))["outcome"] == "failed"
    return task


async def stopped(s: Surfaces, *, privacy: str | None = None) -> str:
    """A task in the queue, stopped with words of the user's."""
    task = await queued(s.world.client, echo_plan(), "da fermare", privacy=privacy)
    answer = await s.world.client.post(f"/tasks/{task}/cancel", json={"reason": STOP_WORDS})
    assert answer.status_code == 200, answer.text
    return task


async def expired(s: Surfaces, *, privacy: str | None = None) -> str:
    """A question nobody answered, expired by the start-up on a clock past its life."""
    task = await asking(s, "una domanda scaduta", privacy=privacy)
    await later(s.world, s.world.settings.core.approval_ttl.total_seconds() / 60 + 1)
    return task


Ending = Callable[..., Awaitable[str]]

ENDS: Mapping[TaskState, Ending] = MappingProxyType(
    {
        TaskState.DENIED: no_from_the_command_line,
        TaskState.FAILED: failed_after_a_yes,
        TaskState.CANCELLED: stopped,
        TaskState.EXPIRED: expired,
    }
)
"""One way to each end of ``REASONED``; a test holds its keys equal to the set, so a new end
without a way to it stops the suite instead of skipping a case."""


async def ended(s: Surfaces, state: TaskState, *, privacy: str | None = None) -> str:
    task = await ENDS[state](s, privacy=privacy)
    reached = (await task_of(s, task))["state"]
    assert reached == state.value, f"{state.value} was not reached: {reached}"
    return task


async def closing(s: Surfaces, task: str) -> dict[str, Any]:
    """The audit event of the transition that put the task in its state, by ``new_state``."""
    state = (await task_of(s, task))["state"]
    audit = (await s.world.client.get("/audit", params={"task_id": task})).json()
    found = [event for event in audit if event["payload"].get("new_state") == state]
    assert found, f"no audit event put {task} in {state}"
    event: dict[str, Any] = found[-1]
    return event


async def device_of(s: Surfaces, name: str) -> str:
    """The id the registry gave the browser enrolled with ``name``."""
    found = [one for one in (await s.world.client.get("/devices")).json() if one["name"] == name]
    assert len(found) == 1, found
    identity: str = found[0]["id"]
    return identity
