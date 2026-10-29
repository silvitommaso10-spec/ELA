"""A page a task keeps between two of its steps, on the two real browsers (M13.10, ADR 0065 §3).

Held, the page outlives the verifier's look and the deadline of a page nobody looks at; taken back,
it is judged by the boundary of the step that continues — in the gate too —, says what the gate
refused while it waited, and the second step's request carries what the site gave the first. The
room closes it when the task ends, and ELA's stop does — with nothing left on the machine.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    DecisionId,
    PermissionDecision,
    PermissionOutcome,
    PlanAuthor,
    PlanAuthorKind,
    PlanId,
    RiskLevel,
    StepId,
    Task,
    TaskId,
    TaskPlan,
    TaskState,
    TaskStep,
)
from ela.executive.pages import PageRoom
from ela.infrastructure.machine.account import AccountChrome
from ela.permissions import BROWSER_ACT, BROWSER_ACT_AS_YOU, BROWSER_READ, BROWSER_READ_AS_YOU
from ela.ports import CONTINUES, PROFILE_STEP, PROFILE_TASK, LeftSite
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuthorizationStore,
    FakeClock,
    FakeIdGenerator,
    FakeStop,
    FakeTaskPages,
    FakeTaskRepository,
)
from ela.tools.account import AccountActTool, AccountReadTool
from ela.tools.browser import BrowserActTool, BrowserReadTool, boundary
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine import test_the_boundary as bounded
from tests.infrastructure.machine.test_browser import Kept, Site, browsing, site

served = shell.served
nothing_left_behind = shell.nothing_left_behind
profile = account.profile
browser = bounded.browser
with_the_profile = bounded.with_the_profile
until = bounded.until

CLOCK = FakeClock()
TASK = TaskId(UUID(int=1))
FIRST, SECOND = StepId(UUID(int=11)), StepId(UUID(int=12))
BOUND = 60.0
"""The bound of each test: a wait that never ends fails with its line. Never a measure."""
FORM = (
    '<form method="post" action="/manda"><input id="t" name="t">'
    '<button id="go">go</button></form><a id="via" href="{to}">via</a>'
)


def decision(capability: str, step: StepId) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
        task_id=TASK,
        step_id=step,
    )


def the_two_tools(made: Any, sites: Any, pages: FakeTaskPages) -> tuple[Any, Any]:
    """The read and the action of the browser the fixture gave."""
    if isinstance(made, AccountChrome):
        return (
            AccountReadTool(sites, made, CLOCK, FakeIdGenerator(), pages=pages),
            AccountActTool(sites, made, CLOCK, FakeIdGenerator(), pages=pages),
        )
    return (
        BrowserReadTool(sites, made, CLOCK, FakeIdGenerator(), pages=pages),
        BrowserActTool(sites, made, CLOCK, FakeIdGenerator(), pages=pages),
    )


def capabilities(made: Any) -> tuple[str, str]:
    if isinstance(made, AccountChrome):
        return BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU
    return BROWSER_READ, BROWSER_ACT


async def test_two_steps_of_a_task_work_on_one_page_and_the_second_carries_the_first_s_cookie(
    browser: Any, served: list[Site]
) -> None:
    """Criterion 12: the site receives **one** request for the page, and what the second step
    sends carries the session cookie the site gave the first."""
    web = site(served, {"/": (200, {"Set-Cookie": "sessione=uno; Path=/"}, FORM.format(to="/"))})
    sites = browsing(web)
    pages = FakeTaskPages(continued={FIRST})
    read, act = the_two_tools(browser, sites, pages)
    reading, acting = capabilities(browser)

    async with asyncio.timeout(BOUND):
        first = await read.execute(
            decision(reading, FIRST),
            {"site": "sito0.example", "path": "/", "purpose": "la prova"},
            FakeStop(),
        )
        second = await act.execute(
            decision(acting, SECOND),
            {
                "site": "sito0.example",
                CONTINUES: True,
                "fill": [["#t", "ciao"]],
                "click": "#go",
                "expect_text": "Grazie",
                "purpose": "la prova",
            },
            FakeStop(),
        )
        await until(lambda: "POST /manda" in web.requests, "the form of the second step")

    assert first.error is None and second.error is None, (first.error, second.error)
    assert second.output["page"] == first.output["page"]
    assert web.requests == ["GET /", "POST /manda"]
    assert "sessione=uno" in web.cookies[1]
    assert web.bodies == ["t=ciao"]


async def test_a_held_page_outlives_the_look_and_the_deadline_of_a_page_nobody_looks_at(
    browser: Any, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>qui</p>")})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        await browser.keep(opened.page)
        await browser.hold(opened.page)
        kept: Kept = browser._kept  # noqa: SLF001 — the deadline the fixture gave the adapter
        kept.due.set()
        await asyncio.sleep(0.1)
        assert opened.page in browser._pages, "the deadline did not close it"  # noqa: SLF001

        glanced = await browser.glance(opened.page, selector="p", expect=None, seconds=1)

        assert glanced.text == "qui"
        assert opened.page in browser._pages, "nor did the look"  # noqa: SLF001
        assert await browser.where(opened.page) == web.origin + "/"
        await browser.close(opened.page)

    assert await browser.where(opened.page) is None


async def test_taken_back_the_page_is_judged_by_the_new_boundary_in_the_gate_too(
    browser: Any, served: list[Site]
) -> None:
    """Measure (g) of the SPEC: after the page is taken back, a navigation toward the site the
    new boundary admits leaves; with the old one it would not."""
    there = site(served, {"/": (200, {}, "<p>là</p>")})
    here = site(served, {"/": (200, {}, FORM.format(to=there.origin + "/"))})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(
            here.origin + "/", boundary(frozenset({here.origin})), FakeStop()
        )
        await browser.hold(opened.page)

        taken = await browser.resume(opened.page, boundary(frozenset({here.origin, there.origin})))
        await browser.click(opened.page, "#via")
        await until(lambda: there.requests, "the navigation the new boundary admits")

    assert taken.page == opened.page and taken.left is None and taken.waited is None
    assert taken.status == 200 and taken.address == here.origin + "/"
    assert there.requests == ["GET /"]


async def test_the_old_boundary_alone_keeps_the_navigation_from_leaving(
    browser: Any, served: list[Site]
) -> None:
    """The control of the test above: the same click, the page taken back with the boundary it
    was opened with, sends nothing to the other site."""
    there = site(served, {"/": (200, {}, "<p>là</p>")})
    here = site(served, {"/": (200, {}, FORM.format(to=there.origin + "/"))})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(
            here.origin + "/", boundary(frozenset({here.origin})), FakeStop()
        )
        await browser.hold(opened.page)
        await browser.resume(opened.page, boundary(frozenset({here.origin})))
        await browser.click(opened.page, "#via")
        said = await until(lambda: browser._pages[opened.page].refused, "the refusal")  # noqa: SLF001

    assert said == [there.origin + "/"]
    assert there.requests == []


async def test_what_the_gate_refused_while_the_page_waited_is_said_once_and_is_not_the_step_s(
    browser: Any, served: list[Site]
) -> None:
    there = site(served, {"/": (200, {}, "<p>là</p>")})
    later = f'<p>qui</p><script>setTimeout(() => location = "{there.origin}/via", 300)</script>'
    here = site(served, {"/": (200, {}, later)})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(
            here.origin + "/", boundary(frozenset({here.origin})), FakeStop()
        )
        await browser.hold(opened.page)
        await until(lambda: browser._pages[opened.page].refused, "the page moving by itself")  # noqa: SLF001

        taken = await browser.resume(opened.page, boundary(frozenset({here.origin})))

        assert taken.waited == there.origin + "/via"
        assert taken.address == here.origin + "/"
        assert await browser.left(opened.page) is None, "what :meth:`left` says is the step's"
    assert there.requests == []


async def test_a_page_outside_the_new_boundary_is_not_taken_back(
    browser: Any, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>qui</p>")})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        await browser.hold(opened.page)

        with pytest.raises(LeftSite) as refused:
            await browser.resume(opened.page, boundary(frozenset({"https://altro.example"})))

    assert refused.value.address == web.origin + "/" and refused.value.made is False


# ----------------------------------------------------------------------------------------
# Who closes it: the room at the task's end, the browser at ELA's stop
# ----------------------------------------------------------------------------------------


async def room_over(made: Any) -> tuple[PageRoom, dict[TaskId, asyncio.Event], asyncio.Event]:
    """The room, over the fakes of its three stores, with a plan whose second step continues."""
    repository = FakeTaskRepository()
    task = Task(id=TASK, created_at=CLOCK.now(), goal="una prova", state=TaskState.EXECUTING)
    await repository.add(task)

    def one(number: StepId, arguments: dict[str, object]) -> TaskStep:
        return TaskStep(
            id=number,
            created_at=CLOCK.now(),
            goal="un passo",
            required_capabilities=(BROWSER_READ,),
            arguments={"site": "sito0.example", "purpose": "una prova", **arguments},
            risk=RiskLevel.LOW,
            expected_result="fatto",
            requires_authorization=False,
        )

    await repository.add_plan(
        TaskPlan(
            id=PlanId(UUID(int=7)),
            created_at=CLOCK.now(),
            task_id=TASK,
            goal="una prova",
            steps=(one(FIRST, {"path": "/"}), one(SECOND, {CONTINUES: True})),
            author=PlanAuthor(by=PlanAuthorKind.HAND),
        )
    )
    ends: dict[TaskId, asyncio.Event] = {}
    stopping = asyncio.Event()

    async def never(seconds: float) -> None:
        await asyncio.Event().wait()

    room = PageRoom(
        repository=repository,
        approvals=FakeApprovalStore(),
        authorizations=FakeAuthorizationStore(),
        ends=lambda task: ends.setdefault(task, asyncio.Event()),
        stopping=stopping,
        clock=CLOCK,
        wait=never,
    )
    return room, ends, stopping


async def test_the_end_of_the_task_closes_the_page_and_leaves_no_process(
    browser: Any, served: list[Site]
) -> None:
    """Criterion 17, for every final state: the engine raises the same stop of the task for each
    of them, and the room hears it."""
    web = site(served, {"/": (200, {}, "<p>qui</p>")})
    room, ends, stopping = await room_over(browser)
    async with asyncio.timeout(BOUND):
        opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        assert await room.leave(TASK, FIRST, opened.page, browser, profile=False)
        await asyncio.sleep(0.05)
        assert shell.descendants(), "the browser runs while its page waits"

        ends[TASK].set()
        await until(lambda: opened.page not in browser._pages, "the room's closing")  # noqa: SLF001
        await until(lambda: not shell.started(), "every process of the browser gone")

    stopping.set()
    await room.stopped()


async def test_ela_s_stop_closes_a_page_that_waits_and_leaves_no_process(
    served: list[Site], profile: Path
) -> None:
    web = site(served, {"/": (200, {}, "<p>qui</p>")})
    stopping = asyncio.Event()
    made = bounded.empty(stopping)
    room, _, room_stopping = await room_over(made)
    async with asyncio.timeout(BOUND):
        opened = await made.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        assert await room.leave(TASK, FIRST, opened.page, made, profile=False)

        stopping.set()
        room_stopping.set()
        await room.stopped()
        assert await made.settle(lambda: asyncio.sleep(5)) == ()

    assert not made._pages and not shell.started()  # noqa: SLF001


@bounded.ON_A_MAC
async def test_a_page_held_on_the_profile_is_a_task_s_and_one_taken_back_a_step_s(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>qui</p>")})
    made = with_the_profile
    async with asyncio.timeout(BOUND):
        opened = await made.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        assert await made.occupied() == PROFILE_STEP
        await made.hold(opened.page)
        assert await made.occupied() == PROFILE_TASK

        await made.resume(opened.page, boundary(frozenset({web.origin})))
        assert await made.occupied() == PROFILE_STEP
        await made.close(opened.page)

    assert await made.occupied() is None
