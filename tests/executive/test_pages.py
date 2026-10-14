"""The room of the pages a task keeps between two of its steps (M13.10, ADR 0065 §3).

One page per task, kept only when the step right after the one that leaves it continues, handed
to that step on the same browser, and closed by the room alone: when the task ends, when the same
task opens another page, when what the task waits for is over — the question, then the grant —,
and never by the room at ELA's stop, where the browsers close their own pages.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import UUID

import pytest

from ela.domain import (
    Approval,
    ApprovalId,
    ApprovalStatus,
    Authorization,
    AuthorizationId,
    CapabilityId,
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
from ela.executive.pages import WATCH_SECONDS, PageRoom
from ela.ports import CONTINUES, WaitingPage
from ela.testing.fakes import (
    FakeApprovalStore,
    FakeAuthorizationStore,
    FakeBrowser,
    FakeClock,
    FakeStop,
    FakeTaskRepository,
)

ACT = CapabilityId("browser.act")
READ = CapabilityId("browser.read")
FIRST, SECOND, THIRD = (StepId(UUID(int=n)) for n in (101, 102, 103))


def step(number: StepId, capability: CapabilityId, *, continues: bool = False) -> TaskStep:
    arguments: dict[str, object] = {"site": "sito.example", "purpose": "una prova"}
    if continues:
        arguments[CONTINUES] = True
    else:
        arguments["path"] = "/"
    return TaskStep(
        id=number,
        created_at=FakeClock().now(),
        goal="un passo",
        required_capabilities=(capability,),
        arguments=arguments,
        risk=RiskLevel.HIGH if capability == ACT else RiskLevel.LOW,
        expected_result="fatto",
        requires_authorization=capability == ACT,
    )


@dataclass
class World:
    """The room over the fakes of the three stores it reads, a browser, and the two stops."""

    clock: FakeClock = field(default_factory=FakeClock)
    repository: FakeTaskRepository = field(default_factory=FakeTaskRepository)
    approvals: FakeApprovalStore = field(default_factory=FakeApprovalStore)
    authorizations: FakeAuthorizationStore = field(default_factory=FakeAuthorizationStore)
    browser: FakeBrowser = field(default_factory=FakeBrowser)
    ends: dict[TaskId, asyncio.Event] = field(default_factory=dict)
    stopping: asyncio.Event = field(default_factory=asyncio.Event)
    waited: list[float] = field(default_factory=list)
    ticking: bool = False
    """``False``: a wait is over when the test sets :attr:`minute`, and the clock does not move by
    itself. ``True``: every wait is over at once, and the clock has moved by what was waited."""
    minute: asyncio.Event = field(default_factory=asyncio.Event)
    room: PageRoom = field(init=False)

    def __post_init__(self) -> None:
        self.room = PageRoom(
            repository=self.repository,
            approvals=self.approvals,
            authorizations=self.authorizations,
            ends=lambda task: self.ends.setdefault(task, asyncio.Event()),
            stopping=self.stopping,
            clock=self.clock,
            wait=self.wait,
        )

    async def wait(self, seconds: float) -> None:
        self.waited.append(seconds)
        if not self.ticking:
            await self.minute.wait()
            self.minute.clear()
            return
        self.clock.advance(timedelta(seconds=seconds))
        await asyncio.sleep(0)

    async def task(self, number: int, *steps: TaskStep) -> TaskId:
        task = Task(
            id=TaskId(UUID(int=number)),
            created_at=self.clock.now(),
            goal="una prova",
            state=TaskState.EXECUTING,
        )
        await self.repository.add(task)
        await self.repository.add_plan(
            TaskPlan(
                id=PlanId(UUID(int=1000 + number)),
                created_at=self.clock.now(),
                task_id=task.id,
                goal=task.goal,
                steps=steps,
                author=PlanAuthor(by=PlanAuthorKind.HAND),
            )
        )
        return task.id

    async def page(self) -> str:
        return (await self.browser.open("https://sito.example/", lambda url: True, FakeStop())).page

    async def asked(
        self, task: TaskId, number: StepId, status: ApprovalStatus, *, seconds: int = 3600
    ) -> Approval:
        approval = Approval(
            id=ApprovalId(UUID(int=500 + len(await self.approvals.for_task(task)))),
            created_at=self.clock.now(),
            task_id=task,
            step_id=number,
            capability_id=ACT,
            prompt="posso?",
            status=ApprovalStatus.PENDING,
            expires_at=self.clock.now() + timedelta(seconds=seconds),
        )
        await self.approvals.add(approval)
        if status is ApprovalStatus.PENDING:
            return approval
        return await self.approvals.respond(
            approval.id, status=status, responded_by="tommaso", now=self.clock.now()
        )

    async def granted(self, task: TaskId, number: StepId, *, seconds: int) -> Authorization:
        grant = Authorization(
            id=AuthorizationId(UUID(int=900)),
            created_at=self.clock.now(),
            capability_id=ACT,
            granted_by="tommaso",
            task_id=task,
            step_id=number,
            expires_at=self.clock.now() + timedelta(seconds=seconds),
            max_uses=1,
        )
        await self.authorizations.grant(grant)
        return grant


@pytest.fixture
def world() -> Iterator[World]:
    made = World()
    yield made
    made.stopping.set()


async def settled() -> None:
    """Let the room's own watch run what it can, with no clock involved."""
    for _ in range(20):
        await asyncio.sleep(0)


# ----------------------------------------------------------------------------------------
# What is kept, and for whom
# ----------------------------------------------------------------------------------------


async def test_a_page_is_kept_when_the_step_right_after_continues_and_held_on_its_browser(
    world: World,
) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()

    kept = await world.room.leave(task, FIRST, page, world.browser, profile=False)

    assert kept is True
    assert world.browser.holding == [page]
    assert world.browser.closed == []


@pytest.mark.parametrize(
    "steps",
    [
        (step(FIRST, READ), step(SECOND, ACT)),
        (step(FIRST, READ),),
        (step(FIRST, READ), step(SECOND, READ), step(THIRD, ACT, continues=True)),
    ],
    ids=["the-next-opens-its-own", "the-last-step", "a-later-step-continues"],
)
async def test_a_page_is_not_kept_unless_the_step_right_after_continues(
    world: World, steps: tuple[TaskStep, ...]
) -> None:
    """The page goes to the step right after, and to no later one: a step in between that opens
    its own page would find the profile held by a page nobody will take."""
    task = await world.task(1, *steps)
    page = await world.page()

    assert await world.room.leave(task, FIRST, page, world.browser, profile=False) is False
    assert world.browser.holding == []
    assert await world.room.waiting() == ()


async def test_the_page_is_handed_to_the_step_that_continues_once_and_no_longer_kept(
    world: World,
) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    assert await world.room.take(task, world.browser) == page
    assert await world.room.take(task, world.browser) is None
    assert await world.room.waiting() == ()
    assert world.browser.closed == [], "the step that took it uses it, and closes it"


async def test_a_page_of_the_other_browser_is_closed_and_not_handed_over(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    assert await world.room.take(task, FakeBrowser()) is None
    assert world.browser.closed == [page]


async def test_where_says_the_address_of_the_page_kept_on_that_browser_and_nothing_else(
    world: World,
) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    world.browser.moves["resume"] = "https://sito.example/dopo?segreto=1"
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    assert await world.room.where(task, world.browser) == "https://sito.example/"
    assert await world.room.where(task, FakeBrowser()) is None
    assert await world.room.where(TaskId(UUID(int=2)), world.browser) is None
    assert world.browser.holding == [page] and world.browser.closed == []


async def test_the_same_task_opening_another_page_closes_the_one_it_keeps(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    await world.room.release(task)

    assert world.browser.closed == [page]
    assert await world.room.take(task, world.browser) is None


async def test_a_task_keeps_one_page_and_a_second_one_closes_the_first(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    first, second = await world.page(), await world.page()
    await world.room.leave(task, FIRST, first, world.browser, profile=False)

    await world.room.leave(task, FIRST, second, world.browser, profile=False)

    assert world.browser.closed == [first]
    assert await world.room.take(task, world.browser) == second


async def test_two_tasks_with_the_same_plan_never_have_the_same_page(world: World) -> None:
    """The key is the task: two tasks whose plans have the same steps — the same ids, written by
    the same hand — each find their own page, and one that kept none finds none."""
    plan = (step(FIRST, READ), step(SECOND, ACT, continues=True))
    one, other, third = (
        await world.task(1, *plan),
        await world.task(2, *plan),
        await world.task(3, *plan),
    )
    mine, yours = await world.page(), await world.page()
    await world.room.leave(one, FIRST, mine, world.browser, profile=False)
    await world.room.leave(other, FIRST, yours, world.browser, profile=False)

    assert await world.room.take(third, world.browser) is None
    assert await world.room.take(other, world.browser) == yours
    assert await world.room.take(one, world.browser) == mine


# ----------------------------------------------------------------------------------------
# Who closes it, and when
# ----------------------------------------------------------------------------------------


async def test_the_end_of_the_task_closes_the_page_with_nobody_calling(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()
    assert world.browser.closed == []

    world.ends[task].set()
    await settled()

    assert world.browser.closed == [page]
    assert await world.room.waiting() == ()


async def test_at_ela_s_stop_the_room_closes_nothing_and_forgets(world: World) -> None:
    """The browsers close every page at the stop (ADR 0038 §11): a room that closed them too
    would be a second closer of the same page."""
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    world.stopping.set()
    await settled()
    await world.room.stopped()

    assert world.browser.closed == []
    assert await world.room.waiting() == ()
    assert await world.room.take(task, world.browser) is None


async def test_a_question_that_expires_closes_the_page_at_its_time_and_not_before(
    world: World,
) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    asked = await world.asked(task, SECOND, ApprovalStatus.PENDING, seconds=90)
    page = await world.page()
    world.ticking = True

    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()

    assert world.browser.closed == [page]
    assert asked.expires_at is not None and world.clock.now() >= asked.expires_at
    assert world.waited == [WATCH_SECONDS, 30], "a minute at a time, then what was left"


async def test_the_clock_says_when_and_not_the_time_of_the_loop(world: World) -> None:
    """A machine that slept: the clock moved by a night while the loop waited one minute. The
    page is closed at the end of that minute, whatever the loop counted."""
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    await world.asked(task, SECOND, ApprovalStatus.PENDING, seconds=3600)
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()
    assert world.waited == [WATCH_SECONDS] and world.browser.closed == []

    world.clock.advance(timedelta(hours=8))
    world.minute.set()
    await settled()

    assert world.browser.closed == [page]
    assert world.waited == [WATCH_SECONDS], "one minute of the loop, and a night of the clock"


async def test_after_the_yes_the_page_lives_as_long_as_the_grant(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    await world.asked(task, SECOND, ApprovalStatus.GRANTED, seconds=60)
    grant = await world.granted(task, SECOND, seconds=600)
    page = await world.page()
    await world.room.leave(task, FIRST, page, world.browser, profile=False)

    assert await world.room.waiting() == (
        WaitingPage(task=task, profile=False, until=grant.expires_at),
    )


async def test_a_grant_that_expires_closes_the_page(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    await world.asked(task, SECOND, ApprovalStatus.GRANTED)
    grant = await world.granted(task, SECOND, seconds=120)
    page = await world.page()
    world.ticking = True

    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()

    assert world.browser.closed == [page]
    assert grant.expires_at is not None and world.clock.now() >= grant.expires_at


async def test_a_no_closes_the_page_at_once(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    await world.asked(task, SECOND, ApprovalStatus.REJECTED)
    page = await world.page()

    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()

    assert world.browser.closed == [page]
    assert world.waited == [], "nothing is waited for"


async def test_a_yes_whose_grant_is_gone_closes_the_page(world: World) -> None:
    task = await world.task(1, step(FIRST, READ), step(SECOND, ACT, continues=True))
    await world.asked(task, SECOND, ApprovalStatus.GRANTED)
    page = await world.page()

    await world.room.leave(task, FIRST, page, world.browser, profile=False)
    await settled()

    assert world.browser.closed == [page]


async def test_a_task_that_waits_for_nothing_that_ends_keeps_its_page_until_it_ends(
    world: World,
) -> None:
    """No question asked yet — the step that continues asks none, or the run has not reached it
    —: nothing ends but the task, and the status says so with ``None``."""
    task = await world.task(1, step(FIRST, ACT), step(SECOND, READ, continues=True))
    page = await world.page()

    await world.room.leave(task, FIRST, page, world.browser, profile=True)
    await settled()

    assert await world.room.waiting() == (WaitingPage(task=task, profile=True, until=None),)
    assert world.waited == [WATCH_SECONDS] and world.browser.closed == []


def test_the_watch_looks_once_a_minute() -> None:
    assert WATCH_SECONDS == 60
