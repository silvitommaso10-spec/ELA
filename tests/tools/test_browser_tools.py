"""``browser.read`` and ``browser.act`` against a browser that records (M13.4, ADR 0052).

What is asserted here: what the tool decides — the address it composes, the boundary it hands over,
the question it names, every refusal before the question and before the first gesture — and what
comes back. The browser is :class:`~ela.testing.fakes.FakeBrowser`, which answers when the test
decides: a real one is asserted in ``tests/infrastructure/machine/test_browser.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import timedelta

import pytest

from ela.domain import (
    DecisionId,
    ExecutionStatus,
    JsonMapping,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import BROWSER_ACT, BROWSER_READ, FILLS_MAX, VALUE_MAX_LENGTH
from ela.ports import (
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    Field,
    Opened,
    PageGone,
    SiteUnreachable,
)
from ela.testing.fakes import FakeBrowser, FakeClock, FakeIdGenerator, FakePage
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.browser import (
    ACTS,
    BROWSER_TIMEOUT_SECONDS,
    ELEMENT_AMBIGUOUS,
    ELEMENT_MISSING,
    FAILED,
    HTTP_STATUS,
    LEFT_SITE,
    NOT_INSTALLED,
    OPENS,
    SECRET_FIELD,
    SITE,
    STOPPED,
    TEXT_MAX_BYTES,
    TIMEOUT,
    UNREACHABLE,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
)

CLOCK = FakeClock()
SITES = Browsing(sites=("example.com", "httpbin.org"))
READ = {"site": "example.com", "path": "/", "purpose": "la prova"}
ACT = {
    "site": "httpbin.org",
    "path": "/forms/post",
    "fill": [["input[name=custname]", "ELA prova 7431"]],
    "click": "form button",
    "expect_text": "ELA prova 7431",
    "purpose": "la prova",
}


def decision(capability: str) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH if capability == BROWSER_ACT else RiskLevel.LOW,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def read(browser: FakeBrowser, browsing: Browsing = SITES) -> BrowserReadTool:
    return BrowserReadTool(browsing, browser, CLOCK, FakeIdGenerator())


def act(browser: FakeBrowser, browsing: Browsing = SITES) -> BrowserActTool:
    return BrowserActTool(browsing, browser, CLOCK, FakeIdGenerator())


def with_(arguments: JsonMapping, **changed: object) -> dict[str, object]:
    return {**arguments, **changed}


# ----------------------------------------------------------------------------------------
# What they declare
# ----------------------------------------------------------------------------------------


def test_what_the_two_tools_declare() -> None:
    assert BrowserReadTool.idempotent is True
    assert BrowserActTool.idempotent is False
    assert BrowserReadTool.relocatable is False and BrowserActTool.relocatable is False
    assert BrowserReadTool.audit_numbers == {"status", "shown", "total"}
    assert BrowserActTool.audit_numbers == {"status", "gestures"}
    assert SECRET_FIELD not in BrowserReadTool.error_codes
    assert SECRET_FIELD in BrowserActTool.error_codes


# ----------------------------------------------------------------------------------------
# The question: what it names, and what is refused before it (form G)
# ----------------------------------------------------------------------------------------


async def test_the_question_of_an_action_names_the_site_the_address_the_gestures_and_the_yes() -> (
    None
):
    prospect = await act(FakeBrowser()).prospect(ACT)

    assert prospect.refusal is None and prospect.target is None
    visit = prospect.visit
    assert visit is not None
    assert visit.site == "httpbin.org" and visit.label == SITE
    assert visit.address == "https://httpbin.org/forms/post"
    assert visit.gestures == (
        "fills input[name=custname] with “ELA prova 7431”",
        "clicks form button",
    )
    assert visit.expect == "ELA prova 7431"
    assert visit.timeout_seconds == BROWSER_TIMEOUT_SECONDS
    assert visit.does == ACTS
    assert "not your account" in ACTS and "nor take back" in ACTS


async def test_the_question_of_a_read_says_what_a_read_does() -> None:
    prospect = await read(FakeBrowser()).prospect(with_(READ, selector="h1"))

    assert prospect.visit is not None
    assert prospect.visit.does == OPENS
    assert prospect.visit.gestures == () and prospect.visit.expect == ""
    assert prospect.visit.address == "https://example.com/"


async def test_the_origin_is_the_tool_s_dependency_and_https_is_the_default() -> None:
    local = Browsing(sites=("example.com",), origin=lambda site: "http://127.0.0.1:9")
    prospect = await read(FakeBrowser(), local).prospect(READ)

    assert prospect.visit is not None
    assert prospect.visit.address == "http://127.0.0.1:9/"
    assert Browsing(sites=()).origin("example.com") == "https://example.com"


@pytest.mark.parametrize(
    "changed",
    [
        {"site": "EXAMPLE.com"},
        {"site": 3},
        {"path": "forms"},
        {"path": "/" + "a" * 2048},
        {"fill": "no"},
        {"fill": [["only"]]},
        {"fill": [["#a", 1]]},
        {"fill": [["text=x", "v"]]},
        {"fill": [["#a", "v" * (VALUE_MAX_LENGTH + 1)]]},
        {"fill": [["#a", "v"]] * (FILLS_MAX + 1)},
        {"click": "//button"},
        {"click": None},
        {"expect_text": ""},
        {"expect_text": 5},
    ],
)
async def test_what_is_known_without_the_page_is_refused_before_the_question(
    changed: dict[str, object],
) -> None:
    browser = FakeBrowser()
    prospect = await act(browser).prospect(with_(ACT, **changed))

    assert prospect.visit is None
    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert browser.opened == [], "nothing is opened to find out"


async def test_what_the_question_refused_the_tool_refuses_again_and_opens_nothing() -> None:
    """The tool trusts neither the Guardian nor its own ``prospect`` (§28): ``execute`` checks the
    arguments again, and a plan that reaches it outside the grammar starts no browser."""
    browser = FakeBrowser()

    result = await act(browser).execute(decision(BROWSER_ACT), with_(ACT, path="forms/post"))

    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert browser.opened == [] and browser.closed == []


async def test_a_selector_of_a_read_is_refused_the_same_way() -> None:
    prospect = await read(FakeBrowser()).prospect(with_(READ, selector=">>"))

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID


async def test_a_browser_that_is_not_installed_refuses_before_the_question() -> None:
    prospect = await act(FakeBrowser(installed=False)).prospect(ACT)

    assert prospect.refusal is not None and prospect.refusal.code == NOT_INSTALLED
    assert "playwright install --only-shell chromium" in prospect.refusal.message


@pytest.mark.parametrize(
    ("capability", "arguments"), [(BROWSER_READ, READ), (BROWSER_ACT, ACT)], ids=["read", "act"]
)
async def test_the_run_does_not_ask_whether_the_browser_is_there(
    capability: str, arguments: JsonMapping
) -> None:
    """Decision 2 of the review of 2026-09-30: asking in ``execute`` was a browser more at every
    step. The question asked before the question; in the run, ``browser.not_installed`` comes from
    the launch that does the work (``test_what_the_browser_raises_has_a_code_of_its_own``)."""

    class Counting(FakeBrowser):
        asked = 0

        async def installed(self) -> bool:
            self.asked += 1
            return True

    browser = Counting(FakePage(texts={None: "testo"}, shown=True))
    tool = read(browser) if capability == BROWSER_READ else act(browser)

    result = await tool.execute(decision(capability), arguments)

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert browser.asked == 0
    assert len(browser.opened) == 1


@pytest.mark.parametrize(
    ("error", "code"),
    [(BrowserStopped("stop"), STOPPED), (BrowserFailed("Error"), FAILED)],
)
async def test_a_browser_that_cannot_say_whether_it_is_there_refuses_too(
    error: Exception, code: str
) -> None:
    browser = FakeBrowser()
    browser.raising["installed"] = error  # type: ignore[assignment]

    prospect = await read(browser).prospect(READ)

    assert prospect.refusal is not None and prospect.refusal.code == code


async def test_a_browser_that_does_not_answer_whether_it_is_there_is_bounded() -> None:
    class Hanging(FakeBrowser):
        async def installed(self) -> bool:
            await asyncio.Event().wait()
            return True

    tool = read(Hanging(), Browsing(sites=("example.com",), timeout_seconds=0))

    prospect = await tool.prospect(READ)

    assert prospect.refusal is not None and prospect.refusal.code == FAILED
    assert "did not start within" in prospect.refusal.message


# ----------------------------------------------------------------------------------------
# A read
# ----------------------------------------------------------------------------------------


async def test_a_read_composes_the_address_hands_the_declared_sites_and_keeps_the_page() -> None:
    browser = FakeBrowser(FakePage(title="Example Domain", texts={"h1": "Example Domain"}))

    result = await read(browser).execute(decision(BROWSER_READ), with_(READ, selector="h1"))

    assert result.status is ExecutionStatus.SUCCEEDED
    assert browser.opened == ["https://example.com/"]
    (allowed,) = browser.allowed
    assert allowed("https://httpbin.org/anything"), "a read may follow a declared site"
    assert not allowed("https://example.org/")
    assert result.output == {
        "address": "https://example.com/",
        "status": 200,
        "title": "Example Domain",
        "text": "Example Domain",
        "shown": 14,
        "total": 14,
        "page": "page-1",
    }
    assert browser.kept == ["page-1"] and browser.closed == []


async def test_a_read_of_the_whole_page_keeps_its_beginning() -> None:
    browser = FakeBrowser(FakePage(texts={None: "x" * (TEXT_MAX_BYTES + 10)}))

    result = await read(browser).execute(decision(BROWSER_READ), READ)

    assert result.output["shown"] == TEXT_MAX_BYTES
    assert result.output["total"] == TEXT_MAX_BYTES + 10


@pytest.mark.parametrize(
    ("page", "code", "said"),
    [
        (FakePage(status=None), UNREACHABLE, "gave no answer"),
        (FakePage(status=404), HTTP_STATUS, "answered 404"),
        (FakePage(left="https://example.org/altrove?q=1"), LEFT_SITE, "https://example.org,"),
        (FakePage(counts={"h1": 0}), ELEMENT_MISSING, "names no element"),
        (FakePage(counts={"h1": 3}), ELEMENT_AMBIGUOUS, "names 3 elements"),
    ],
)
async def test_what_the_page_refuses_closes_the_browser(
    page: FakePage, code: str, said: str
) -> None:
    browser = FakeBrowser(page)

    result = await read(browser).execute(decision(BROWSER_READ), with_(READ, selector="h1"))

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == code
    assert said in result.error.message
    assert "/altrove" not in result.error.message and "q=1" not in result.error.message
    assert browser.closed == ["page-1"] and browser.kept == []


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (BrowserNotInstalled("x"), NOT_INSTALLED),
        (SiteUnreachable("Error"), UNREACHABLE),
        (BrowserStopped("x"), STOPPED),
        (BrowserFailed("TargetClosedError"), FAILED),
        (PageGone("x"), FAILED),
    ],
)
async def test_what_the_browser_raises_has_a_code_of_its_own(error: Exception, code: str) -> None:
    browser = FakeBrowser()
    browser.raising["open"] = error  # type: ignore[assignment]

    result = await read(browser).execute(decision(BROWSER_READ), READ)

    assert result.error is not None and result.error.code == code
    assert browser.closed == [], "nothing was opened, so nothing is left to close"


async def test_a_page_that_is_still_at_work_after_the_time_is_closed_and_says_so() -> None:
    class Slow(FakeBrowser):
        async def text(self, page: str, selector: str | None) -> str:
            await asyncio.Event().wait()
            return ""

    browser = Slow()
    tool = read(browser, Browsing(sites=("example.com",), timeout_seconds=0))

    result = await tool.execute(decision(BROWSER_READ), READ)

    assert result.error is not None and result.error.code == TIMEOUT
    assert "still at work after 0 s" in result.error.message
    assert result.output == {}
    assert browser.closed == ["page-1"]


@pytest.mark.parametrize(
    ("capability", "arguments"), [(BROWSER_READ, READ), (BROWSER_ACT, ACT)], ids=["read", "act"]
)
async def test_a_page_that_never_opens_is_bounded_by_the_step_s_time(
    capability: str, arguments: JsonMapping
) -> None:
    """Review of 2026-09-30, point 2: the time of a step is the tool's — one deadline around all the
    work of the port, ``open`` included —, not a timeout of Playwright's on each call. A port that
    never answers is ``browser.timeout``; the guard is the test's, and never the one that fires."""

    class Unanswered(FakeBrowser):
        async def open(self, address: str, allowed: Callable[[str], bool]) -> Opened:
            await asyncio.Event().wait()
            raise AssertionError("never reached")

    browser = Unanswered()
    browsing = Browsing(sites=("example.com", "httpbin.org"), timeout_seconds=0)
    tool = read(browser, browsing) if capability == BROWSER_READ else act(browser, browsing)

    async with asyncio.timeout(10):
        result = await tool.execute(decision(capability), arguments)

    assert result.error is not None and result.error.code == TIMEOUT
    assert "still at work after 0 s" in result.error.message
    assert browser.closed == [], "no page came back, so there is none to close"


# ----------------------------------------------------------------------------------------
# An action: every element before the first gesture, then the gestures (form H)
# ----------------------------------------------------------------------------------------


async def test_an_action_fills_then_clicks_on_its_own_site_and_keeps_the_page() -> None:
    browser = FakeBrowser()

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.status is ExecutionStatus.SUCCEEDED
    assert browser.opened == ["https://httpbin.org/forms/post"]
    (allowed,) = browser.allowed
    assert allowed("https://httpbin.org/post")
    assert not allowed("https://example.com/"), "a declared site is not the site of the question"
    assert browser.fills == [("input[name=custname]", "ELA prova 7431")]
    assert browser.clicks == ["form button"]
    assert result.output == {"status": 200, "gestures": 2, "page": "page-1"}
    assert browser.kept == ["page-1"]


async def test_an_action_with_no_field_is_one_click() -> None:
    browser = FakeBrowser()

    result = await act(browser).execute(decision(BROWSER_ACT), with_(ACT, fill=[]))

    assert result.output["gestures"] == 1 and browser.clicks == ["form button"]


@pytest.mark.parametrize(
    ("page", "code"),
    [
        (FakePage(counts={"form button": 0}), ELEMENT_MISSING),
        (FakePage(counts={"form button": 2}), ELEMENT_AMBIGUOUS),
        (FakePage(counts={"input[name=custname]": 0}), ELEMENT_MISSING),
        (FakePage(fields={"input[name=custname]": Field("password", "")}), SECRET_FIELD),
        (FakePage(fields={"input[name=custname]": Field("text", "cc-number")}), SECRET_FIELD),
        (FakePage(fields={"input[name=custname]": Field("text", "one-time-code")}), SECRET_FIELD),
    ],
)
async def test_a_page_that_is_not_the_plan_s_gets_no_gesture(page: FakePage, code: str) -> None:
    browser = FakeBrowser(page)

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.error is not None and result.error.code == code
    assert result.output == {"gestures": 0}
    assert result.error.message.endswith("no gesture was made")
    assert browser.fills == [] and browser.clicks == []
    assert "input[name=custname]" not in result.error.message
    assert "form button" not in result.error.message
    assert "ELA prova" not in result.error.message


async def test_a_click_that_starts_a_navigation_off_the_site_is_stopped_and_said() -> None:
    browser = FakeBrowser(FakePage(left_after_click="https://pagamenti.example/checkout"))

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://pagamenti.example," in result.error.message
    assert "the site the question named" in result.error.message
    assert result.error.message.endswith("2 gestures were made")
    assert result.output == {"status": 200, "gestures": 2}
    assert browser.closed == ["page-1"]


async def test_an_action_on_a_page_that_answers_an_error_makes_no_gesture() -> None:
    browser = FakeBrowser(FakePage(status=500))

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.error is not None and result.error.code == HTTP_STATUS
    assert browser.fills == [] and browser.clicks == []


async def test_a_stop_during_a_gesture_says_how_many_were_made() -> None:
    browser = FakeBrowser()
    browser.raising["click"] = BrowserStopped("ELA is stopping")  # type: ignore[assignment]

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.error is not None and result.error.code == STOPPED
    assert result.error.message.endswith("1 gesture was made")
    assert result.output == {"gestures": 1}


async def test_a_failure_during_a_gesture_is_named_by_its_type() -> None:
    browser = FakeBrowser()
    browser.raising["fill"] = BrowserFailed("TargetClosedError")  # type: ignore[assignment]

    result = await act(browser).execute(decision(BROWSER_ACT), ACT)

    assert result.error is not None and result.error.code == FAILED
    assert "BrowserFailed: TargetClosedError" in result.error.message
    assert result.error.message.endswith("no gesture was made")


async def test_a_timeout_before_the_first_gesture_says_none_was_made() -> None:
    class Slow(FakeBrowser):
        async def count(self, page: str, selector: str) -> int:
            await asyncio.Event().wait()
            return 1

    browser = Slow()

    result = await act(browser, Browsing(sites=("httpbin.org",), timeout_seconds=0)).execute(
        decision(BROWSER_ACT), ACT
    )

    assert result.error is not None and result.error.code == TIMEOUT
    assert result.error.message.endswith("no gesture was made")
    assert result.output == {"gestures": 0}
