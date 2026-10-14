"""What the tools and the verifiers do with a page that is not inside its boundary, and with a
page that opened another (M13.4f, ADR 0064) — against a browser that records.

The adapter asks the boundary where the page is at every use of it, before and after, and raises
``LeftSite``; here is what the tools make of that, **at each of their steps**: ``browser.left_site``
with the origin alone, nothing of the page in the result, no other gesture — and the gestures
that were made counted as made. The verifiers answer the same code when their look finds the
page elsewhere, before the wait or after it. And a page that opened another is **said** — in the
result, and by the verifier with a code of its own when the text it waits for does not appear.

The real browsers are in ``tests/infrastructure/machine/test_the_boundary.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ela.domain import ExecutionResult, ExecutionStatus
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ,
    BROWSER_READ_AS_YOU,
)
from ela.ports import PageGone
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeVault,
)
from ela.tools.account import (
    AccountActTool,
    AccountActVerifier,
    AccountReadTool,
    AccountReadVerifier,
    LoginVerifier,
)
from ela.tools.browser import LEFT_SITE, BrowserActTool, BrowserReadTool
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_TEXT_MATCHES,
    BrowserActVerifier,
    BrowserReadVerifier,
)
from tests.tools.test_account_tools import (
    ACT,
    CLOCK,
    LOGIN,
    MARIO,
    READ,
    SITES,
    TYPED,
    USERNAME,
    asked,
    decision,
    login,
    page,
)
from tests.tools.test_verifiers import succeeded

ELSEWHERE = "https://fuori.example/percorso;sessione=1?chiave=1#frammento"
"""Where a page of these tests is found: on a site nobody declared — the boundary of a read with
the empty browser is every declared site —, at an address whose origin may be told, and
nothing else of it."""
ORIGIN = "https://fuori.example"
SECRET = "-".join(("what", "the", "other", "page", "shows"))


def nothing_of_that_page(result: ExecutionResult) -> str:
    """``browser.left_site``, with the origin and nothing else of the address; nothing of the
    page in the result."""
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None and result.error.code == LEFT_SITE
    said = result.model_dump_json()
    assert ORIGIN in result.error.message
    for part in ("percorso", "sessione", "chiave", "frammento", SECRET):
        assert part not in said
    assert "page" not in result.output, "a page that is elsewhere is not handed to the verifier"
    return result.error.message


def read_tool(browser: Any) -> Any:
    if isinstance(browser, FakeAccountBrowser):
        return AccountReadTool(SITES, browser, CLOCK, FakeIdGenerator()), BROWSER_READ_AS_YOU
    return BrowserReadTool(SITES, browser, CLOCK, FakeIdGenerator()), BROWSER_READ


def act_tool(browser: Any) -> Any:
    if isinstance(browser, FakeAccountBrowser):
        return AccountActTool(SITES, browser, CLOCK, FakeIdGenerator()), BROWSER_ACT_AS_YOU
    return BrowserActTool(SITES, browser, CLOCK, FakeIdGenerator()), BROWSER_ACT


BROWSERS = pytest.mark.parametrize("made", [FakeBrowser, FakeAccountBrowser])


# ----------------------------------------------------------------------------------------
# A read
# ----------------------------------------------------------------------------------------


@BROWSERS
@pytest.mark.parametrize("member", ["appeared", "text", "title"])
@pytest.mark.parametrize("when", ["before", "during"])
async def test_a_read_that_finds_the_page_elsewhere_carries_nothing_of_it(
    made: Any, member: str, when: str
) -> None:
    """At each use a read makes of its page, found elsewhere before the use or once it is done:
    what was read by then is thrown away with the rest."""
    browser = made(FakePage(texts={None: SECRET, "h1": SECRET}, title=SECRET))
    (browser.moves if when == "before" else browser.moves_during)[member] = ELSEWHERE
    tool, capability = read_tool(browser)

    result = await tool.execute(decision(capability), {**READ, "selector": "h1"}, FakeStop())

    nothing_of_that_page(result)
    assert result.output == {}
    assert browser.kept == [] and browser.closed == ["page-1"]


# ----------------------------------------------------------------------------------------
# An action
# ----------------------------------------------------------------------------------------

GESTURES_BEFORE = {"appeared": 0, "field": 0, "fill": 0, "click": 1, "left": 2}
"""How many gestures an action with one field has made when it reaches each use of its page."""


@BROWSERS
@pytest.mark.parametrize("member", sorted(GESTURES_BEFORE))
async def test_an_action_that_finds_the_page_elsewhere_makes_no_other_gesture(
    made: Any, member: str
) -> None:
    browser = made()
    browser.moves[member] = ELSEWHERE
    tool, capability = act_tool(browser)

    result = await tool.execute(decision(capability), ACT, FakeStop())

    done = GESTURES_BEFORE[member]
    said = nothing_of_that_page(result)
    assert result.output["gestures"] == done
    assert len(browser.fills) + len(browser.clicks) == done, "and none after it"
    assert ("no gesture was made" in said) is (done == 0)
    assert browser.kept == [] and browser.closed == ["page-1"]


@BROWSERS
@pytest.mark.parametrize(("member", "done"), [("fill", 1), ("click", 2)])
async def test_a_gesture_that_was_made_is_counted_when_the_page_is_found_elsewhere_after_it(
    made: Any, member: str, done: int
) -> None:
    """The page moved while the gesture was being made: the gesture happened, and the result
    says so — an action is not asked again on the word that nothing was done."""
    browser = made()
    browser.moves_during[member] = ELSEWHERE
    tool, capability = act_tool(browser)

    result = await tool.execute(decision(capability), ACT, FakeStop())

    said = nothing_of_that_page(result)
    assert result.output["gestures"] == done == len(browser.fills) + len(browser.clicks)
    assert f"{done} gesture" in said


@BROWSERS
@pytest.mark.parametrize("build", [read_tool, act_tool])
async def test_a_page_that_opened_elsewhere_says_nothing_of_itself_not_even_its_status(
    made: Any, build: Any
) -> None:
    """The opening asks the boundary where the page is, like every use after it: a page that
    answered an error elsewhere is ``browser.left_site`` and not ``browser.http_status`` — the
    status of a page nobody asked for is not said —, and no gesture is made on it."""
    browser = made(FakePage(address=ELSEWHERE, status=404, texts={None: SECRET, "h1": SECRET}))
    tool, capability = build(browser)
    arguments = {**READ, "selector": "h1"} if build is read_tool else ACT

    result = await tool.execute(decision(capability), arguments, FakeStop())

    nothing_of_that_page(result)
    assert "status" not in result.output and result.output.get("gestures", 0) == 0
    assert browser.fills == [] and browser.clicks == []
    assert browser.kept == [] and browser.closed == ["page-1"]


# ----------------------------------------------------------------------------------------
# A login
# ----------------------------------------------------------------------------------------

BEFORE_THE_VAULT = ("appeared", "field")


@pytest.mark.parametrize("member", [*BEFORE_THE_VAULT, "fill_secret", "click", "left", "landed"])
async def test_a_login_that_finds_the_page_elsewhere_types_nothing_more(
    tmp_path: Path, member: str
) -> None:
    """The one predicate, where the login had two comparisons of its own (decision 115)."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()
    browser.moves[member] = ELSEWHERE

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    said = nothing_of_that_page(result)
    typed = {"appeared": 0, "field": 0, "fill_secret": 0, "click": 2, "left": 3, "landed": 3}[
        member
    ]
    assert result.output["gestures"] == typed
    assert len(browser.secrets) + len(browser.clicks) == typed
    assert (vault.calls == []) is (member in BEFORE_THE_VAULT), "no password taken for nothing"
    assert TYPED not in said and USERNAME not in said
    assert browser.kept == []


async def test_a_login_counts_what_it_typed_when_the_page_is_found_elsewhere_after_it(
    tmp_path: Path,
) -> None:
    """The username was typed, and the page was found elsewhere once it was: one gesture was
    made, and the result says one — never that nothing was typed."""
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page())
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    browser.moves_during["fill_secret"] = ELSEWHERE

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    said = nothing_of_that_page(result)
    assert result.output == {"status": 200, "gestures": 1}
    assert "1 gesture was made" in said and len(browser.secrets) == 1


async def test_a_login_on_a_page_that_opened_elsewhere_asks_the_vault_for_nothing(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page(address=ELSEWHERE))
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    vault.calls.clear()

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    nothing_of_that_page(result)
    assert result.output == {"gestures": 0}
    assert vault.calls == [] and browser.secrets == []


async def test_a_login_whose_page_ended_elsewhere_after_the_click_says_the_three_gestures(
    tmp_path: Path,
) -> None:
    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page(landed=ELSEWHERE))
    tool = await login(browser, vault, tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    said = nothing_of_that_page(result)
    assert result.output == {"status": 200, "gestures": 3}
    assert "3 gestures were made" in said


# ----------------------------------------------------------------------------------------
# The look of the verifier
# ----------------------------------------------------------------------------------------

VERIFIERS: dict[str, tuple[Any, Any, Any, str, dict[str, object]]] = {
    BROWSER_READ: (FakeBrowser, BrowserReadVerifier, BROWSER_TEXT_MATCHES, "text", {}),
    BROWSER_ACT: (FakeBrowser, BrowserActVerifier, BROWSER_EXPECT_VISIBLE, "x", ACT),
    BROWSER_READ_AS_YOU: (
        FakeAccountBrowser,
        AccountReadVerifier,
        BROWSER_TEXT_MATCHES,
        "text",
        {},
    ),
    BROWSER_ACT_AS_YOU: (FakeAccountBrowser, AccountActVerifier, BROWSER_EXPECT_VISIBLE, "x", ACT),
    BROWSER_LOGIN: (FakeAccountBrowser, LoginVerifier, BROWSER_EXPECT_VISIBLE, "x", LOGIN),
}


def inside(address: str) -> bool:
    return address.startswith("https://posta.example/")


async def handed(browser: Any) -> str:
    """A page a tool handed to its verifier, as the tool does: with the boundary of its step."""
    opened = await browser.open("https://posta.example/", inside, FakeStop())
    await browser.keep(opened.page)
    return str(opened.page)


@pytest.mark.parametrize("capability", sorted(VERIFIERS))
@pytest.mark.parametrize("when", ["before the wait", "after the wait"])
async def test_a_look_at_a_page_that_is_elsewhere_reads_nothing_and_says_left_site(
    capability: str, when: str
) -> None:
    """Criterion 4. Between the end of the tool and the look a page can move by itself, and so
    it can while the look waits for its text: the look says nothing of what the page shows —
    not even that the text appeared —, and the page is released."""
    from ela.tools.verifiers import BROWSER_LEFT_SITE

    made, verifier, condition, _, arguments = VERIFIERS[capability]
    browser = made(FakePage(texts={None: SECRET}, shown=True))
    page_ = await handed(browser)
    (browser.moves if when == "before the wait" else browser.moves_during)["glance"] = ELSEWHERE

    failures = await verifier(browser, 30.0).verify(
        [condition], arguments, succeeded(capability, output={"text": SECRET, "page": page_})
    )

    (failure,) = failures
    assert failure.code == BROWSER_LEFT_SITE == LEFT_SITE
    said = failure.model_dump_json()
    assert ORIGIN in failure.message
    for part in ("percorso", "chiave", SECRET):
        assert part not in said
    assert BROWSER_LEFT_SITE in verifier.failure_codes
    with pytest.raises(PageGone):
        await browser.text(page_, None)


@pytest.mark.parametrize("capability", [BROWSER_ACT, BROWSER_ACT_AS_YOU, BROWSER_LOGIN])
@pytest.mark.parametrize(
    ("another", "said", "unsaid"),
    [
        (("GET", "https://fuori.example/x?chiave=1"), "another page", "the form was not sent"),
        (("POST", "https://posta.example/send?chiave=1"), "the form was not sent", "chiave"),
        ((None, None), "another page", "the form was not sent"),
    ],
)
async def test_a_text_that_does_not_appear_on_a_page_that_opened_another_has_a_code_of_its_own(
    capability: str, another: tuple[str | None, str | None], said: str, unsaid: str
) -> None:
    """Decision 123. The page opened another page; ELA works on one, and from the other nothing
    was sent. Said in the place of ``browser.expect_missing`` — whose sentence, «what the click
    sent may have arrived all the same», is false here; for a form sent in another page, that
    the form was not sent. The origin of what that page asked for, never the rest of it."""
    from ela.ports import AnotherPage
    from ela.tools.verifiers import BROWSER_ANOTHER_PAGE

    made, verifier, condition, _, arguments = VERIFIERS[capability]
    browser = made(FakePage(shown=False, another=AnotherPage(*another)))
    page_ = await handed(browser)

    (failure,) = await verifier(browser, 30.0).verify(
        [condition], arguments, succeeded(capability, output={"page": page_})
    )

    assert failure.code == BROWSER_ANOTHER_PAGE != BROWSER_EXPECT_MISSING
    assert said in failure.message and unsaid not in failure.message
    assert "may have arrived" not in failure.message
    assert BROWSER_ANOTHER_PAGE in verifier.failure_codes


@pytest.mark.parametrize("capability", [BROWSER_ACT, BROWSER_ACT_AS_YOU, BROWSER_LOGIN])
async def test_a_text_that_appears_is_verified_whatever_the_page_tried_to_open(
    capability: str,
) -> None:
    """A step does not fail because a page tried to open another (decision 123)."""
    from ela.ports import AnotherPage

    made, verifier, condition, _, arguments = VERIFIERS[capability]
    browser = made(FakePage(shown=True, another=AnotherPage("GET", "https://fuori.example/x")))
    page_ = await handed(browser)

    failures = await verifier(browser, 30.0).verify(
        [condition], arguments, succeeded(capability, output={"page": page_})
    )

    assert failures == ()


async def test_a_second_factor_is_said_before_a_page_that_was_opened() -> None:
    from ela.ports import AnotherPage
    from ela.tools.account import BROWSER_SECOND_FACTOR

    browser = FakeAccountBrowser(
        FakePage(shown=False, second_factor=True, another=AnotherPage("GET", ELSEWHERE))
    )
    page_ = await handed(browser)

    (failure,) = await LoginVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE], LOGIN, succeeded(BROWSER_LOGIN, output={"page": page_})
    )

    assert failure.code == BROWSER_SECOND_FACTOR


# ----------------------------------------------------------------------------------------
# A page that opened another is said in the result
# ----------------------------------------------------------------------------------------


@BROWSERS
@pytest.mark.parametrize(
    ("another", "said"),
    [(("GET", ELSEWHERE), ORIGIN), (("POST", ELSEWHERE), ORIGIN), ((None, None), None)],
)
async def test_the_result_of_a_step_says_that_its_page_opened_another(
    made: Any, another: tuple[str | None, str | None], said: str | None
) -> None:
    """Decision 123: always — a read that worked, an action whose click was made — and with the
    origin alone; for a page that had asked for nothing, that it had asked for nothing."""
    from ela.ports import AnotherPage
    from ela.tools.browser import ANOTHER_PAGE, ASKED_FOR_NOTHING

    for build, arguments in ((read_tool, READ), (act_tool, ACT)):
        browser = made(FakePage(another=AnotherPage(*another)))
        tool, capability = build(browser)

        result = await tool.execute(decision(capability), arguments, FakeStop())

        assert result.status is ExecutionStatus.SUCCEEDED, result.error
        assert result.output[ANOTHER_PAGE] == (said or ASKED_FOR_NOTHING)
        assert "chiave" not in result.model_dump_json()
        assert ANOTHER_PAGE in tool.output_keys and ANOTHER_PAGE not in tool.audit_numbers


@BROWSERS
async def test_a_result_says_nothing_of_another_page_when_none_was_opened(made: Any) -> None:
    from ela.tools.browser import ANOTHER_PAGE

    tool, capability = read_tool(made())

    result = await tool.execute(decision(capability), READ, FakeStop())

    assert ANOTHER_PAGE not in result.output


async def test_a_step_that_failed_on_its_page_still_says_that_the_page_opened_another() -> None:
    """The page opened another and the element the plan names is not there: both are said."""
    from ela.ports import AnotherPage
    from ela.tools.browser import ANOTHER_PAGE, ELEMENT_MISSING

    browser = FakeBrowser(FakePage(counts={"#manda": 0}, another=AnotherPage("GET", ELSEWHERE)))
    tool, capability = act_tool(browser)

    result = await tool.execute(decision(capability), ACT, FakeStop())

    assert result.error is not None and result.error.code == ELEMENT_MISSING
    assert result.output[ANOTHER_PAGE] == ORIGIN


async def test_the_result_of_a_login_says_that_its_page_opened_another(tmp_path: Path) -> None:
    from ela.ports import AnotherPage
    from ela.tools.browser import ANOTHER_PAGE

    vault = FakeVault([MARIO])
    browser = FakeAccountBrowser(page(another=AnotherPage("POST", ELSEWHERE)))
    tool = await login(browser, vault, tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output[ANOTHER_PAGE] == ORIGIN
    assert ANOTHER_PAGE in tool.output_keys
