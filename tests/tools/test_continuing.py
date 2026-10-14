"""The tools of the browser that continue on the page their task keeps (M13.10, ADR 0065 §3).

A step that continues opens no page: it takes the one the step right before it left, on the same
browser, with **its own** boundary, and the question names where that page is now. A step that
works leaves its page to the room when the step after it continues, and to the verifier otherwise;
a step that opens a page closes the one its task keeps first. On the profile, a page another task
keeps is a ``browser.profile_busy`` that names the task; one the same task keeps is no refusal.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    DecisionId,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
    StepId,
    TaskId,
)
from ela.permissions import BROWSER_ACT, BROWSER_ACT_AS_YOU, BROWSER_READ, BROWSER_READ_AS_YOU
from ela.ports import CONTINUES, NAVIGATION, PROFILE_TASK, ProfileBusy, ToolStopped
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeTaskPages,
)
from ela.tools.account import (
    ACTS_ON_AS_YOU,
    PROFILE_BUSY,
    READS_ON_AS_YOU,
    STOP_A_TASK,
    AccountActTool,
    AccountReadTool,
)
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.browser import (
    ACTS_ON,
    LEFT_SITE,
    LEFT_WHILE_WAITING,
    NO_PAGE_TO_CONTINUE,
    READS_ON,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
)

CLOCK = FakeClock()
SITES = Browsing(sites=("sito.example", "altro.example"))
TASK, OTHER = TaskId(UUID(int=1)), TaskId(UUID(int=2))
BEFORE, NOW = StepId(UUID(int=11)), StepId(UUID(int=12))
OPEN_READ = {"site": "sito.example", "path": "/modulo", "purpose": "la prova"}
READ_ON = {"site": "sito.example", CONTINUES: True, "purpose": "la prova"}
ACT_ON = {
    "site": "sito.example",
    CONTINUES: True,
    "fill": [["#testo", "ciao"]],
    "click": "#manda",
    "expect_text": "ciao",
    "purpose": "la prova",
}
CALLS = {
    BROWSER_READ: READ_ON,
    BROWSER_ACT: ACT_ON,
    BROWSER_READ_AS_YOU: READ_ON,
    BROWSER_ACT_AS_YOU: ACT_ON,
}
SENTENCES = {
    BROWSER_READ: READS_ON,
    BROWSER_ACT: ACTS_ON,
    BROWSER_READ_AS_YOU: READS_ON_AS_YOU,
    BROWSER_ACT_AS_YOU: ACTS_ON_AS_YOU,
}
EVERY = pytest.mark.parametrize("capability", sorted(CALLS))


def decision(capability: str, task: TaskId = TASK, step: StepId = NOW) -> PermissionDecision:
    acts = capability in {BROWSER_ACT, BROWSER_ACT_AS_YOU}
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH if acts else RiskLevel.LOW,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
        task_id=task,
        step_id=step,
    )


def browser_for(capability: str, page: FakePage | None = None) -> FakeBrowser:
    if capability in {BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU}:
        return FakeAccountBrowser(page)
    return FakeBrowser(page)


def tool(capability: str, browser: FakeBrowser, pages: FakeTaskPages) -> Any:
    made = {
        BROWSER_READ: BrowserReadTool,
        BROWSER_ACT: BrowserActTool,
        BROWSER_READ_AS_YOU: AccountReadTool,
        BROWSER_ACT_AS_YOU: AccountActTool,
    }[capability]
    return made(SITES, browser, CLOCK, FakeIdGenerator(), pages=pages)


async def kept(browser: FakeBrowser, pages: FakeTaskPages, task: TaskId = TASK) -> str:
    """A page the step before left, kept by the room for ``task``."""
    opened = await browser.open("https://sito.example/modulo", lambda url: True, FakeStop())
    pages.continued.add(BEFORE)
    profile = isinstance(browser, FakeAccountBrowser)
    assert await pages.leave(task, BEFORE, opened.page, browser, profile=profile)
    pages.released.clear()
    return opened.page


# ----------------------------------------------------------------------------------------
# The shape of a call that continues
# ----------------------------------------------------------------------------------------


@EVERY
@pytest.mark.parametrize(
    "changed",
    [{"path": "/altro"}, {CONTINUES: False}, {CONTINUES: "true"}],
    ids=["with-a-path-too", "false", "not-a-boolean"],
)
async def test_a_step_opens_a_page_or_continues_and_never_both_or_a_half(
    capability: str, changed: dict[str, object]
) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    await kept(browser, pages)

    prospect = await tool(capability, browser, pages).prospect(
        {**CALLS[capability], **changed}, TASK
    )

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert "exactly one of the two" in prospect.refusal.message


# ----------------------------------------------------------------------------------------
# Before the question
# ----------------------------------------------------------------------------------------


@EVERY
async def test_without_a_page_of_its_task_no_question_is_asked(capability: str) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    await kept(browser, pages, OTHER)

    prospect = await tool(capability, browser, pages).prospect(CALLS[capability], TASK)

    assert prospect.refusal is not None and prospect.refusal.code == NO_PAGE_TO_CONTINUE
    assert prospect.refusal.message.endswith(": no question is asked")
    assert prospect.refusal.retryable is False


@EVERY
async def test_an_asker_that_knows_no_task_finds_no_page(capability: str) -> None:
    """The route of the policies does not pass the task (decision 25): a call that continues has
    no page to name there."""
    browser = browser_for(capability)
    pages = FakeTaskPages()
    await kept(browser, pages)

    prospect = await tool(capability, browser, pages).prospect(CALLS[capability])

    assert prospect.refusal is not None and prospect.refusal.code == NO_PAGE_TO_CONTINUE


@EVERY
async def test_the_question_says_the_step_continues_and_where_the_page_is_without_its_query(
    capability: str,
) -> None:
    browser = browser_for(capability, FakePage(address="https://sito.example/dopo;sid=7?chi=io"))
    pages = FakeTaskPages()
    await kept(browser, pages)

    prospect = await tool(capability, browser, pages).prospect(CALLS[capability], TASK)

    assert prospect.refusal is None and prospect.visit is not None
    assert prospect.visit.does == SENTENCES[capability]
    assert prospect.visit.address == "sito.example/dopo"
    assert browser.opened == ["https://sito.example/modulo"], "the question opens nothing"
    assert browser.resumed == [] and browser.closed == []


async def test_a_page_of_the_other_browser_is_no_page_to_continue_on() -> None:
    empty, accounts = FakeBrowser(), FakeAccountBrowser()
    pages = FakeTaskPages()
    await kept(empty, pages)

    prospect = await tool(BROWSER_READ_AS_YOU, accounts, pages).prospect(READ_ON, TASK)

    assert prospect.refusal is not None and prospect.refusal.code == NO_PAGE_TO_CONTINUE
    assert "with your accounts" in prospect.refusal.message


# ----------------------------------------------------------------------------------------
# After the yes
# ----------------------------------------------------------------------------------------


@EVERY
async def test_the_step_takes_the_page_back_with_its_own_boundary_and_opens_none(
    capability: str,
) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    page = await kept(browser, pages)

    result = await tool(capability, browser, pages).execute(
        decision(capability), CALLS[capability], FakeStop()
    )

    assert result.error is None, result.error
    assert browser.opened == ["https://sito.example/modulo"], "no page was opened"
    assert browser.resumed == [page]
    resumed_with = browser.allowed[-1]
    assert resumed_with("https://sito.example/x") and not resumed_with("https://fuori.example/")
    assert result.output["page"] == page
    assert browser.kept == [page], "handed to its verifier, as a page it had opened"


@pytest.mark.parametrize("capability", [BROWSER_ACT, BROWSER_ACT_AS_YOU])
async def test_the_gestures_are_made_on_the_page_the_task_kept(capability: str) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    await kept(browser, pages)

    await tool(capability, browser, pages).execute(decision(capability), ACT_ON, FakeStop())

    assert browser.fills == [("#testo", "ciao")] and browser.clicks == ["#manda"]


@EVERY
async def test_after_the_yes_without_a_page_nothing_is_done(capability: str) -> None:
    """ELA restarted between the question and the yes, or what the task waited for ran out."""
    browser = browser_for(capability)

    result = await tool(capability, browser, FakeTaskPages()).execute(
        decision(capability), CALLS[capability], FakeStop()
    )

    assert result.error is not None and result.error.code == NO_PAGE_TO_CONTINUE
    acts = capability in {BROWSER_ACT, BROWSER_ACT_AS_YOU}
    assert result.output == ({"gestures": 0} if acts else {})
    said = result.error.message
    assert said.endswith("the yes was spent, and nothing was done" if acts else "nothing was read")
    assert browser.opened == [] and browser.resumed == []


@EVERY
async def test_a_page_found_outside_the_step_s_site_gives_nothing_of_itself(
    capability: str,
) -> None:
    browser = browser_for(
        capability, FakePage(texts={None: "il testo segreto della pagina"}, title="un titolo")
    )
    pages = FakeTaskPages()
    page = await kept(browser, pages)
    browser.moves["resume"] = "https://fuori.example/dove?x=1"

    result = await tool(capability, browser, pages).execute(
        decision(capability), CALLS[capability], FakeStop()
    )

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://fuori.example" in result.error.message and "dove" not in result.error.message
    assert set(result.output) <= {"gestures", "stopped_at"}
    assert browser.fills == [] and browser.clicks == []
    assert page in browser.closed, "the page is the step's once taken, and goes with it"


@EVERY
async def test_a_navigation_refused_while_the_page_waited_is_said_and_fails_nothing(
    capability: str,
) -> None:
    browser = browser_for(capability, FakePage(waited="https://altro.example/rimando?t=9"))
    pages = FakeTaskPages()
    await kept(browser, pages)

    result = await tool(capability, browser, pages).execute(
        decision(capability), CALLS[capability], FakeStop()
    )

    assert result.error is None, result.error
    assert result.output[LEFT_WHILE_WAITING] == "https://altro.example"


@pytest.mark.parametrize("capability", [BROWSER_READ, BROWSER_READ_AS_YOU])
async def test_a_read_that_continues_listens_at_its_point_right_before_the_page_is_used(
    capability: str,
) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    page = await kept(browser, pages)

    with pytest.raises(ToolStopped):
        await tool(capability, browser, pages).execute(
            decision(capability), READ_ON, FakeStop(stopped=True)
        )

    assert browser.resumed == [] and page in browser.closed


@pytest.mark.parametrize("capability", [BROWSER_ACT, BROWSER_ACT_AS_YOU])
async def test_an_action_that_continues_listens_at_its_first_gesture(capability: str) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages()
    page = await kept(browser, pages)
    stop = FakeStop(stopped=True)

    with pytest.raises(ToolStopped):
        await tool(capability, browser, pages).execute(decision(capability), ACT_ON, stop)

    assert NAVIGATION not in stop.listened
    assert browser.fills == [] and page in browser.closed


# ----------------------------------------------------------------------------------------
# What a step leaves, and what it closes first
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("capability", [BROWSER_READ, BROWSER_READ_AS_YOU])
async def test_a_page_that_worked_goes_to_the_room_when_the_step_after_continues(
    capability: str,
) -> None:
    browser = browser_for(capability)
    pages = FakeTaskPages(continued={NOW})

    result = await tool(capability, browser, pages).execute(
        decision(capability), OPEN_READ, FakeStop()
    )

    page = result.output["page"]
    assert pages.offered == [(TASK, NOW, page)]
    assert browser.holding == [page] and browser.kept == []
    profile = capability == BROWSER_READ_AS_YOU
    assert pages.kept == {TASK: (page, browser, profile)}


async def test_a_page_that_worked_goes_to_the_verifier_when_nothing_continues_on_it() -> None:
    browser, pages = FakeBrowser(), FakeTaskPages()

    result = await tool(BROWSER_READ, browser, pages).execute(
        decision(BROWSER_READ), OPEN_READ, FakeStop()
    )

    assert pages.offered == [(TASK, NOW, result.output["page"])]
    assert browser.kept == [result.output["page"]] and browser.holding == []


async def test_a_page_that_did_not_work_is_offered_to_nobody() -> None:
    browser, pages = FakeBrowser(FakePage(status=500)), FakeTaskPages(continued={NOW})

    await tool(BROWSER_READ, browser, pages).execute(decision(BROWSER_READ), OPEN_READ, FakeStop())

    assert pages.offered == [] and browser.closed == ["page-1"]


async def test_a_step_that_opens_a_page_closes_the_one_its_task_keeps_first() -> None:
    browser = FakeBrowser()
    pages = FakeTaskPages()
    page = await kept(browser, pages)

    await tool(BROWSER_READ, browser, pages).execute(decision(BROWSER_READ), OPEN_READ, FakeStop())

    assert pages.released == [TASK]
    assert browser.closed[0] == page
    assert browser.opened[-1] == "https://sito.example/modulo"


# ----------------------------------------------------------------------------------------
# On the profile: whose page it is
# ----------------------------------------------------------------------------------------


async def test_a_page_another_task_keeps_on_the_profile_refuses_and_names_that_task() -> None:
    browser = FakeAccountBrowser()
    pages = FakeTaskPages(until=CLOCK.now() + timedelta(hours=1))
    opened = await browser.open("https://sito.example/", lambda url: True, FakeStop())
    pages.continued.add(BEFORE)
    await pages.leave(OTHER, BEFORE, opened.page, browser, profile=True)

    prospect = await tool(BROWSER_READ_AS_YOU, browser, pages).prospect(OPEN_READ, TASK)

    assert prospect.refusal is not None and prospect.refusal.code == PROFILE_BUSY
    said = prospect.refusal.message
    assert f"task {OTHER}" in said and f"{STOP_A_TASK} {OTHER}" in said
    assert "at the latest" in said and prospect.refusal.retryable is True


@pytest.mark.parametrize("call", [OPEN_READ, READ_ON], ids=["opens-another", "continues"])
async def test_a_page_the_same_task_keeps_on_the_profile_is_no_refusal(
    call: dict[str, object],
) -> None:
    browser = FakeAccountBrowser()
    pages = FakeTaskPages()
    opened = await browser.open("https://sito.example/", lambda url: True, FakeStop())
    pages.continued.add(BEFORE)
    await pages.leave(TASK, BEFORE, opened.page, browser, profile=True)
    assert await browser.occupied() == PROFILE_TASK

    prospect = await tool(BROWSER_READ_AS_YOU, browser, pages).prospect(call, TASK)

    assert prospect.refusal is None, prospect.refusal


async def test_after_the_yes_a_page_another_task_keeps_is_named_in_the_refusal() -> None:
    browser = FakeAccountBrowser()
    pages = FakeTaskPages()
    opened = await browser.open("https://sito.example/", lambda url: True, FakeStop())
    pages.continued.add(BEFORE)
    await pages.leave(OTHER, BEFORE, opened.page, browser, profile=True)
    browser.raising["open"] = ProfileBusy(PROFILE_TASK)

    result = await tool(BROWSER_READ_AS_YOU, browser, pages).execute(
        decision(BROWSER_READ_AS_YOU), OPEN_READ, FakeStop()
    )

    assert result.error is not None and result.error.code == PROFILE_BUSY
    assert f"task {OTHER}" in result.error.message
    assert "until that task ends" in result.error.message


# ----------------------------------------------------------------------------------------
# The edges of the way in
# ----------------------------------------------------------------------------------------


async def test_a_call_without_its_decision_runs_nothing() -> None:
    """``_run`` is never the way in: a call of the browser is a step of a task."""
    browser = FakeBrowser()
    made = tool(BROWSER_READ, browser, FakeTaskPages())

    outcome = await made._run(OPEN_READ, FakeStop())  # noqa: SLF001

    assert outcome.code == ARGUMENTS_INVALID and browser.opened == []


async def test_a_call_that_continues_with_no_task_in_its_decision_finds_no_page() -> None:
    browser = FakeBrowser()
    pages = FakeTaskPages()
    await kept(browser, pages)
    taskless = decision(BROWSER_READ).model_copy(update={"task_id": None})

    result = await tool(BROWSER_READ, browser, pages).execute(taskless, READ_ON, FakeStop())

    assert result.error is not None and result.error.code == NO_PAGE_TO_CONTINUE
    assert browser.resumed == []


async def test_a_login_never_continues() -> None:
    from ela.tools.account import LoginTool

    login = LoginTool(
        SITES, FakeAccountBrowser(), None, CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    )  # type: ignore[arg-type]

    looked = login._shaped({"site": "sito.example", CONTINUES: True})  # noqa: SLF001

    assert looked.code == ARGUMENTS_INVALID and "never continues" in looked.message


async def test_an_action_that_continues_with_gestures_that_are_not_a_call_is_refused() -> None:
    browser = FakeBrowser()
    pages = FakeTaskPages()
    await kept(browser, pages)

    prospect = await tool(BROWSER_ACT, browser, pages).prospect({**ACT_ON, "fill": "x"}, TASK)

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert "fill must be a list" in prospect.refusal.message


def test_a_wait_abandoned_after_it_ended_has_its_end_read() -> None:
    """The callback on a wait the tool stopped waiting for: an end that came anyway is read, so
    that nobody is told later of an exception never retrieved."""
    from ela.tools.browser import _retrieved

    loop = asyncio.new_event_loop()
    try:
        ended = loop.create_future()
        ended.set_exception(TimeoutError())
        _retrieved(ended)
        cancelled = loop.create_future()
        cancelled.cancel()
        _retrieved(cancelled)
    finally:
        loop.close()


async def test_a_page_of_a_task_the_room_no_longer_names_is_still_said_to_end_with_the_task() -> (
    None
):
    """The adapter says a task holds the profile, and the room has no page of it on the profile
    any more — it closed it a moment ago: the sentence says what it can."""
    browser = FakeAccountBrowser()
    browser.raising["open"] = ProfileBusy(PROFILE_TASK)

    result = await tool(BROWSER_READ_AS_YOU, browser, FakeTaskPages()).execute(
        decision(BROWSER_READ_AS_YOU), OPEN_READ, FakeStop()
    )

    assert result.error is not None and result.error.code == PROFILE_BUSY
    assert "a page a task keeps between two of its steps holds it" in result.error.message
