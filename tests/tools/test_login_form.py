"""The login form of a page, as the read with the profile finds it, and the login with no text to
wait for, as its verifier looks at it (M13.10, ADR 0065 §4).

The rule (decision 22 of the review of M13.10's SPEC): the password fields a login would fill —
of type password, visible, declaring neither a password to choose, nor a one-time code, nor a card
—, one of them; its form; the one text or e-mail field before it there; the one element of that
form that sends. The selectors are written from those facts, never from a position, and each is
counted on the page before it is written.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from ela.domain import DecisionId, PermissionDecision, PermissionOutcome, RiskLevel
from ela.permissions import BROWSER_LOGIN, BROWSER_READ_AS_YOU
from ela.ports import (
    BROWSER_LOGIN_FORM_GONE,
    LOGIN_FORM,
    LOGIN_FORM_AMBIGUOUS,
    LOGIN_FORM_NOT_FOUND,
    NAVIGATION,
    NO_LOGIN_FORM,
    FormField,
    PageForm,
    ToolStopped,
)
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeTaskPages,
    FakeVault,
)
from ela.tools.account import (
    LOGIN_FORM_STILL_THERE,
    PASSWORD_ITSELF,
    AccountReadTool,
    LoginVerifier,
    login_form_of,
)
from ela.tools.browser import HTTP_STATUS, Browsing, _selector
from ela.tools.verifiers import BROWSER_LEFT_SITE
from tests.tools.test_verifiers import succeeded

CLOCK = FakeClock()
SITES = Browsing(sites=("posta.example",))
READ = {"site": "posta.example", "path": "/login", "purpose": "la prova"}


def field(
    tag: str = "input",
    type: str = "text",  # noqa: A002 — the attribute's own name
    name: str = "",
    autocomplete: str = "",
    *,
    visible: bool = True,
) -> FormField:
    return FormField(tag=tag, type=type, name=name, autocomplete=autocomplete, visible=visible)


def password(autocomplete: str = "current-password", *, visible: bool = True) -> FormField:
    return field("input", "password", "pw", autocomplete, visible=visible)


SEND = field("input", "submit")
LOGIN = PageForm((field(name="acct"), password(), SEND))
SIGN_UP = PageForm(
    (field("input", "hidden", "creating"), field(name="acct"), password("new-password"), SEND)
)
"""The two forms of Hacker News's login page, as measure (e) of the SPEC read them."""


# ----------------------------------------------------------------------------------------
# The rule
# ----------------------------------------------------------------------------------------


def test_the_login_form_of_hacker_news_is_the_one_whose_field_is_not_a_new_password() -> None:
    found = login_form_of([LOGIN, SIGN_UP])

    scope = f"form:has({PASSWORD_ITSELF})"
    assert found == {
        "username_field": f'{scope} input[name="acct"]',
        "password_field": f"{scope} {PASSWORD_ITSELF}:visible",
        "click": f'{scope} input[type="submit" i]:visible',
    }


def test_the_selectors_written_are_selectors_the_tools_take() -> None:
    found = login_form_of([LOGIN, SIGN_UP])

    assert isinstance(found, dict)
    assert all(_selector(one, "a selector") is None for one in found.values())
    assert not any("nth" in one for one in found.values()), "never a position"


@pytest.mark.parametrize(
    ("forms", "code"),
    [
        ([], LOGIN_FORM_NOT_FOUND),
        ([SIGN_UP], LOGIN_FORM_NOT_FOUND),
        ([PageForm((field(name="acct"), password(visible=False), SEND))], LOGIN_FORM_NOT_FOUND),
        ([PageForm((field(name="acct"), password("one-time-code"), SEND))], LOGIN_FORM_NOT_FOUND),
        ([PageForm((field(name="n"), password("cc-csc"), SEND))], LOGIN_FORM_NOT_FOUND),
        ([LOGIN, LOGIN], LOGIN_FORM_AMBIGUOUS),
        ([PageForm((field(name="a"), password(), password(), SEND))], LOGIN_FORM_AMBIGUOUS),
        ([PageForm((password(), SEND))], LOGIN_FORM_NOT_FOUND),
        ([PageForm((field(name="a"), field(name="b"), password(), SEND))], LOGIN_FORM_AMBIGUOUS),
        ([PageForm((field(name="acct"), password()))], LOGIN_FORM_NOT_FOUND),
        ([PageForm((field(name="acct"), password(), SEND, SEND))], LOGIN_FORM_AMBIGUOUS),
        ([PageForm((field(name="acct"), password(), SEND), in_a_form=False)], LOGIN_FORM_NOT_FOUND),
    ],
    ids=[
        "no-form",
        "only-a-new-password",
        "a-hidden-password",
        "a-one-time-code",
        "a-card",
        "two-login-forms",
        "two-passwords-in-one-form",
        "no-field-for-the-name",
        "two-fields-for-the-name",
        "nothing-that-sends",
        "two-that-send",
        "a-password-in-no-form",
    ],
)
def test_a_page_with_no_one_login_form_says_why(forms: list[PageForm], code: str) -> None:
    assert login_form_of(forms) == code


def test_the_field_for_the_name_is_the_one_before_the_password_and_an_email_counts() -> None:
    form = PageForm(
        (field("input", "email", "mail"), password(), field("input", "text", "after"), SEND)
    )

    found = login_form_of([form])

    assert isinstance(found, dict) and found["username_field"].endswith('input[name="mail"]')


@pytest.mark.parametrize(
    ("sender", "written"),
    [
        (field("button", "submit"), 'button[type="submit" i]:visible'),
        (field("button", ""), "button:not([type]):visible"),
        (field("input", "image"), 'input[type="image" i]:visible'),
    ],
    ids=["a-submit-button", "a-button-with-no-type", "an-image"],
)
def test_the_element_that_sends_is_written_by_what_it_declares(
    sender: FormField, written: str
) -> None:
    found = login_form_of([PageForm((field(name="acct"), password(), sender))])

    assert isinstance(found, dict) and found["click"].endswith(written)


def test_a_name_a_selector_cannot_carry_as_it_is_is_left_for_the_type() -> None:
    form = PageForm((field("input", "", 'na"me'), password(), SEND))

    found = login_form_of([form])

    assert isinstance(found, dict) and found["username_field"].endswith("input:not([type]):visible")
    assert '"me' not in found["username_field"]


# ----------------------------------------------------------------------------------------
# The read with the profile reports it, always
# ----------------------------------------------------------------------------------------


def decision(capability: str) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.MEDIUM,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


async def read(page: FakePage) -> Any:
    browser = FakeAccountBrowser(page)
    tool = AccountReadTool(SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())
    return await tool.execute(decision(BROWSER_READ_AS_YOU), READ, FakeStop()), browser


async def test_every_read_with_the_profile_reports_the_login_form_of_its_page() -> None:
    result, _ = await read(FakePage(forms=(LOGIN, SIGN_UP)))

    assert result.error is None
    assert result.output[LOGIN_FORM] == login_form_of([LOGIN, SIGN_UP])
    assert NO_LOGIN_FORM not in result.output


async def test_a_read_whose_page_has_no_login_form_says_why_and_still_reads() -> None:
    result, _ = await read(FakePage(forms=(SIGN_UP,)))

    assert result.error is None and result.output["text"] == "the text of the page"
    assert result.output[NO_LOGIN_FORM] == LOGIN_FORM_NOT_FOUND
    assert LOGIN_FORM not in result.output


async def test_a_selector_that_does_not_count_one_on_the_page_makes_the_form_ambiguous() -> None:
    written = login_form_of([LOGIN])
    assert isinstance(written, dict)

    result, _ = await read(FakePage(forms=(LOGIN,), counts={written["click"]: 2}))

    assert result.output[NO_LOGIN_FORM] == LOGIN_FORM_AMBIGUOUS


def test_the_login_form_is_in_no_audit_number_of_the_read() -> None:
    assert {LOGIN_FORM, NO_LOGIN_FORM} <= AccountReadTool.output_keys
    assert not {LOGIN_FORM, NO_LOGIN_FORM} & AccountReadTool.audit_numbers


async def test_a_read_that_did_not_work_reports_no_form() -> None:
    result, _ = await read(FakePage(status=500, forms=(LOGIN,)))

    assert result.error is not None
    assert LOGIN_FORM not in result.output and NO_LOGIN_FORM not in result.output


# ----------------------------------------------------------------------------------------
# A login with no text to wait for: the form gone
# ----------------------------------------------------------------------------------------

WORD_FIELD = "_".join(("password", "field"))
GONE_ARGUMENTS = {"site": "posta.example", WORD_FIELD: "#word", "username_field": "#user"}


async def looked(page: FakePage, *, moved: str | None = None) -> Any:
    browser = FakeAccountBrowser(page)
    opened = await browser.open(
        "https://posta.example/login",
        lambda url: url.startswith("https://posta.example"),
        FakeStop(),
    )
    await browser.click(opened.page, "#go")
    await browser.keep(opened.page)
    if moved is not None:
        browser.moves["glance"] = moved
    verifier = LoginVerifier(browser, 1.0)
    result = succeeded(BROWSER_LOGIN, output={"page": opened.page, "status": 200, "gestures": 3})
    return await verifier.verify((BROWSER_LOGIN_FORM_GONE,), GONE_ARGUMENTS, result)


async def test_a_login_whose_form_is_gone_on_a_page_that_answered_is_verified() -> None:
    failures = await looked(FakePage(counts_after_click={"#word": 0}, landed_status=200))

    assert failures == ()


async def test_a_login_that_leaves_the_form_on_the_page_fails_its_verification() -> None:
    (failure,) = await looked(FakePage(counts_after_click={"#word": 1}, landed_status=200))

    assert failure.code == LOGIN_FORM_STILL_THERE


@pytest.mark.parametrize("status", [403, 500, None], ids=["refused", "an-error", "no-answer"])
async def test_a_page_of_error_without_the_form_is_not_a_login(status: int | None) -> None:
    (failure,) = await looked(FakePage(counts_after_click={"#word": 0}, landed_status=status))

    assert failure.code == HTTP_STATUS


async def test_a_page_outside_the_site_is_not_a_login_either() -> None:
    (failure,) = await looked(
        FakePage(counts_after_click={"#word": 0}, landed_status=200),
        moved="https://altrove.example/",
    )

    assert failure.code == BROWSER_LEFT_SITE


async def test_a_read_that_fails_on_its_page_reports_no_form_either() -> None:
    """The selector of the read names two elements: the read fails in its own work, before any
    form is looked for."""
    browser = FakeAccountBrowser(FakePage(forms=(LOGIN,), counts={"#two": 2}))
    reading = AccountReadTool(SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())

    result = await reading.execute(
        decision(BROWSER_READ_AS_YOU), {**READ, "selector": "#two"}, FakeStop()
    )

    assert result.error is not None and result.error.code == "browser.element_ambiguous"
    assert LOGIN_FORM not in result.output and NO_LOGIN_FORM not in result.output


@pytest.mark.parametrize(
    "arguments",
    [
        {"site": "posta.example", "username_field": "#user"},
        {"site": "posta.example", WORD_FIELD: ""},
    ],
    ids=["no-password-field", "an-empty-one"],
)
async def test_a_form_gone_with_no_password_field_to_look_for_is_the_plan_s_error(
    arguments: dict[str, str],
) -> None:
    verifier = LoginVerifier(FakeAccountBrowser(), 1.0)
    result = succeeded(BROWSER_LOGIN, output={"page": "page-1", "status": 200, "gestures": 3})

    (failure,) = await verifier.verify((BROWSER_LOGIN_FORM_GONE,), arguments, result)

    assert failure.code == "verification.arguments_invalid"


async def test_a_form_gone_on_a_page_that_is_not_there_any_more_says_so() -> None:
    verifier = LoginVerifier(FakeAccountBrowser(), 1.0)
    result = succeeded(BROWSER_LOGIN, output={"status": 200, "gestures": 3})

    (failure,) = await verifier.verify((BROWSER_LOGIN_FORM_GONE,), GONE_ARGUMENTS, result)

    assert failure.code == "browser.page_gone"


async def test_a_page_that_asks_for_a_second_factor_is_not_a_form_gone() -> None:
    page = FakePage(counts_after_click={"#word": 0}, landed_status=200, second_factor=True)

    (failure,) = await looked(page)

    assert failure.code == "browser.second_factor"


# ----------------------------------------------------------------------------------------
# The login itself, at its two edges this milestone touched
# ----------------------------------------------------------------------------------------


async def test_a_login_whose_arguments_are_not_a_login_types_nothing(tmp_path: Path) -> None:
    from tests.tools.test_account_tools import LOGIN as A_LOGIN
    from tests.tools.test_account_tools import MARIO, login, page
    from tests.tools.test_account_tools import decision as login_decision

    browser = FakeAccountBrowser(page())
    tool = await login(browser, FakeVault([MARIO]), tmp_path)

    result = await tool.execute(login_decision(BROWSER_LOGIN), {**A_LOGIN, "click": ""}, FakeStop())

    assert result.error is not None and result.error.code == "arguments.invalid"
    assert browser.opened == [] and browser.secrets == []


async def test_a_login_stopped_while_it_awaits_its_fields_types_nothing_and_asks_no_vault(
    tmp_path: Path,
) -> None:
    from tests.tools.test_account_tools import LOGIN as A_LOGIN
    from tests.tools.test_account_tools import MARIO, asked, login, page
    from tests.tools.test_account_tools import decision as login_decision

    browser = FakeAccountBrowser(page())
    vault = FakeVault([MARIO])
    tool = await login(browser, vault, tmp_path)
    await asked(tool)
    browser.appear_later("#user")
    vault.calls.clear()

    # Stopped right after the navigation, which hears it and goes through: the stop is found
    # while the field of the name is awaited.
    with pytest.raises(ToolStopped):
        await tool.execute(login_decision(BROWSER_LOGIN), A_LOGIN, FakeStop(after=NAVIGATION))
    assert browser.waited == ["#user"]

    assert browser.secrets == [] and not any(call.startswith("take") for call in vault.calls)
