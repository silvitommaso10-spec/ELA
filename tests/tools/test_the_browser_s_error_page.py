"""The browser's own error page is not another site (M13.9b, ADR 0066), with the fakes.

When a site takes a request and answers nothing, the browser shows a page of its own,
``chrome-error://chromewebdata/``, and its protocol says which address it tried to reach — the
main frame's ``unreachableUrl`` (measured on 2026-11-02 on the two browsers: 50 rounds of 50, and
never on ``about:blank`` or a ``blob:``; ``docs/milestones/M13.9b.md``). **The boundary is asked
about that address**: inside it the site did not answer — no status, at the address asked —, outside
it is ``browser.left_site`` with the origin that was tried, never ``chrome-error://``.

And **the diagnosis is in the result** (answer 16 of the review at ``5808ae5``): a use on such a
page inside the boundary carries :data:`~ela.tools.browser.UNANSWERED`, the place the site did not
answer at; a verifier that sees the browser's page fails with the code of its condition, and says
that the text is the browser's.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from ela.domain import (
    DecisionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import BROWSER_ACT, BROWSER_LOGIN, BROWSER_READ
from ela.ports import Glanced, tried
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeTaskPages,
    FakeVault,
)
from ela.tools.account import BROWSER_LOGIN_FORM_GONE, LoginVerifier
from ela.tools.browser import LEFT_SITE, UNANSWERED, BrowserActTool, Browsing
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_TEXT_MATCHES,
    BROWSER_TEXT_MISMATCH,
    BrowserActVerifier,
    BrowserReadVerifier,
)
from tests.tools.test_account_tools import LOGIN, MARIO, asked, login, page
from tests.tools.test_verifiers import succeeded

ERROR_PAGE = "chrome-error://chromewebdata/"
"""Where the browser says its own page is, measured on the two browsers (2026-11-02)."""
CLOCK = FakeClock()
SITES = Browsing(sites=("example.com", "httpbin.org"))
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
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def act(browser: FakeBrowser) -> BrowserActTool:
    return BrowserActTool(SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())


# ----------------------------------------------------------------------------------------
# Where the browser tried to go: one function, the adapters' and the fakes'
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "unreachable", "said"),
    [
        (ERROR_PAGE, "https://posta.example/login", "https://posta.example/login"),
        ("https://posta.example/", "https://altro.example/", "https://posta.example/"),
        ("about:blank", None, "about:blank"),
        ("blob:https://posta.example/0a1b", None, "blob:https://posta.example/0a1b"),
        (ERROR_PAGE, None, ERROR_PAGE),
        (ERROR_PAGE, "", ERROR_PAGE),
    ],
)
def test_a_page_is_where_it_is_and_the_browser_s_own_page_is_where_it_tried_to_go(
    address: str, unreachable: str | None, said: str
) -> None:
    """A page of a site is where it is, whatever else is said of it; a page at no site is where
    the browser says it tried to go, when it says so — and where it is, when it does not:
    ``about:blank`` and a ``blob:`` carry no address that was not reached (measured)."""
    assert tried(address, unreachable) == said


# ----------------------------------------------------------------------------------------
# A gesture, and the login
# ----------------------------------------------------------------------------------------


async def test_a_click_the_site_does_not_answer_is_not_another_site_and_says_so() -> None:
    browser = FakeBrowser(
        FakePage(landed=ERROR_PAGE, unreachable="https://httpbin.org/post", landed_status=None)
    )

    result = await act(browser).execute(decision(BROWSER_ACT), ACT, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output[UNANSWERED] == "httpbin.org/post", "the place the site did not answer at"
    assert result.output["gestures"] == 2


async def test_the_browser_s_page_for_an_address_outside_is_left_site_with_that_origin() -> None:
    browser = FakeBrowser(
        FakePage(landed=ERROR_PAGE, unreachable="https://pagamenti.example/checkout")
    )

    result = await act(browser).execute(decision(BROWSER_ACT), ACT, FakeStop())

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://pagamenti.example," in result.error.message
    assert "chrome-error" not in result.error.message


async def test_a_page_that_answered_carries_nothing_of_the_browser_s_own() -> None:
    result = await act(FakeBrowser(FakePage())).execute(decision(BROWSER_ACT), ACT, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert UNANSWERED not in result.output


async def test_a_login_the_site_does_not_answer_is_told_where_it_was_asked(tmp_path: Path) -> None:
    """The case of M13.9's test, with the fakes: the login ends on the browser's own page, and is
    said at the address it asked, with no status — not ``browser.left_site``."""
    browser = FakeAccountBrowser(
        page(landed=ERROR_PAGE, unreachable="https://posta.example/login", landed_status=None)
    )
    tool = await login(browser, FakeVault([MARIO]), tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["ended_at"] == "posta.example/login"
    assert result.output["ended_status"] is None
    assert result.output[UNANSWERED] == "posta.example/login"


async def test_a_login_on_the_browser_s_page_for_another_site_is_left_site(tmp_path: Path) -> None:
    browser = FakeAccountBrowser(
        page(landed=ERROR_PAGE, unreachable="https://altro.example/x", landed_status=None)
    )
    tool = await login(browser, FakeVault([MARIO]), tmp_path)
    await asked(tool)

    result = await tool.execute(decision(BROWSER_LOGIN), LOGIN, FakeStop())

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://altro.example," in result.error.message


# ----------------------------------------------------------------------------------------
# The verifiers: the browser's page is not a page that shows what the step did
# ----------------------------------------------------------------------------------------


class OnTheBrowser_sPage(FakeBrowser):
    """A fake whose look finds the browser's own page, for the address ``unanswered``."""

    def __init__(self, page: FakePage, unanswered: str) -> None:
        super().__init__(page)
        self.unanswered_address = unanswered

    async def glance(
        self, page: str, *, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        return Glanced(
            text="This site can't be reached",
            shown=True,
            left=None,
            found=0,
            status=None,
            unanswered=self.unanswered_address,
        )


class OnTheBrowser_sPageToo(FakeAccountBrowser):
    """The same, for the browser of the profile."""

    async def glance(
        self, page: str, *, selector: str | None, expect: str | None, seconds: float
    ) -> Glanced:
        return Glanced(
            text="This site can't be reached",
            shown=True,
            left=None,
            found=0,
            status=None,
            unanswered="https://posta.example/login",
        )


def outcome(capability: str, text: str = "This site can't be reached") -> ExecutionResult:
    return succeeded(capability, output={"text": text, "page": "page-1"})


@pytest.mark.parametrize(
    ("verifier", "capability", "condition", "arguments", "code"),
    [
        (
            BrowserActVerifier,
            BROWSER_ACT,
            BROWSER_EXPECT_VISIBLE,
            {"expect_text": "This site"},
            BROWSER_EXPECT_MISSING,
        ),
        (BrowserReadVerifier, BROWSER_READ, BROWSER_TEXT_MATCHES, {}, BROWSER_TEXT_MISMATCH),
    ],
)
async def test_a_verifier_that_finds_the_browser_s_page_fails_and_says_whose_text_it_is(
    verifier: type, capability: str, condition: str, arguments: dict[str, str], code: str
) -> None:
    """Even when the text the step expects is on that page: it is the browser's, not the
    site's. Said with the origin alone — a failure goes to the audit."""
    browser = OnTheBrowser_sPage(FakePage(), "https://httpbin.org/post")

    (failure,) = await verifier(browser, 30.0).verify([condition], arguments, outcome(capability))

    assert failure.code == code
    assert "the browser's own" in failure.message
    assert "https://httpbin.org" in failure.message and "/post" not in failure.message


@pytest.mark.parametrize(
    ("condition", "arguments", "code"),
    [
        (BROWSER_EXPECT_VISIBLE, {"expect_text": "This site"}, BROWSER_EXPECT_MISSING),
        (BROWSER_LOGIN_FORM_GONE, {"password_field": "#word"}, "browser.http_status"),
    ],
)
async def test_the_login_s_verifier_that_finds_the_browser_s_page_fails_with_its_code(
    condition: str, arguments: dict[str, str], code: str
) -> None:
    browser = OnTheBrowser_sPageToo(page())

    (failure,) = await LoginVerifier(browser, 30.0).verify(
        [condition], arguments, outcome(BROWSER_LOGIN)
    )

    assert failure.code == code
    assert "the browser's own" in failure.message
