"""The login form of a page, on the real browser with the profile (M13.10, ADR 0065 §4).

A page shaped as Hacker News's login page is (measure (e) of M13.10's SPEC): a form to sign in
and a form to sign up, each with a field for the name, a password field and an element that sends,
the second declaring ``new-password``. The adapter reads of each element only what it declares;
the rule picks the first form; the three selectors written from the facts count one each on the
page, and the look says how many elements a selector finds and the document's status.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ela.infrastructure.machine.account import AccountChrome
from ela.ports import FormField, PageForm
from ela.testing.fakes import FakeStop
from ela.tools.account import login_form_of
from ela.tools.browser import boundary
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine import test_the_boundary as bounded
from tests.infrastructure.machine.test_browser import Site, site

served = shell.served
nothing_left_behind = shell.nothing_left_behind
profile = account.profile
with_the_profile = bounded.with_the_profile
browser = bounded.browser

BOUND = 60.0
PAGE = """<title>Login</title>
<b>Login</b>
<form action="login" method="post">
  username: <input type="text" name="acct" autocorrect="off">
  password: <input type="password" name="pw" autocomplete="current-password">
  <input type="submit" value="login">
</form>
<a href="forgot">Forgot your password?</a>
<b>Create Account</b>
<form action="login" method="post">
  <input type="hidden" name="creating" value="t">
  username: <input type="text" name="acct">
  password: <input type="password" name="pw" autocomplete="new-password">
  <input type="submit" value="create account">
</form>
<input type="password" name="hidden" style="display: none">
"""
"""Hacker News's login page as measure (e) read it, with a password field in no form and with no
box beside it: what the rule must not count."""


@bounded.ON_A_MAC
async def test_the_adapter_reads_what_each_element_of_the_forms_declares_and_nothing_else(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    web = site(served, {"/login": (200, {}, PAGE)})
    async with asyncio.timeout(BOUND):
        opened = await with_the_profile.open(
            web.origin + "/login", boundary(frozenset({web.origin})), FakeStop()
        )
        forms = await with_the_profile.forms(opened.page)
        await with_the_profile.close(opened.page)

    text, password, submit = (
        FormField("input", "text", "acct", "", True),
        FormField("input", "password", "pw", "current-password", True),
        FormField("input", "submit", "", "", True),
    )
    assert forms == (
        PageForm((text, password, submit)),
        PageForm(
            (
                FormField("input", "hidden", "creating", "", False),
                text,
                FormField("input", "password", "pw", "new-password", True),
                submit,
            )
        ),
        PageForm((FormField("input", "password", "hidden", "", False),), in_a_form=False),
    )
    assert "t" not in {one.name for form in forms for one in form.fields}, "never a value"


@bounded.ON_A_MAC
async def test_the_three_selectors_written_from_the_facts_count_one_each_on_the_page(
    with_the_profile: AccountChrome, served: list[Site]
) -> None:
    web = site(served, {"/login": (200, {}, PAGE)})
    async with asyncio.timeout(BOUND):
        opened = await with_the_profile.open(
            web.origin + "/login", boundary(frozenset({web.origin})), FakeStop()
        )
        written = login_form_of(await with_the_profile.forms(opened.page))
        assert isinstance(written, dict), written
        counted = {
            role: await with_the_profile.count(opened.page, selector)
            for role, selector in written.items()
        }
        await with_the_profile.close(opened.page)

    assert counted == {"username_field": 1, "password_field": 1, "click": 1}


async def test_the_look_says_how_many_elements_a_selector_finds_and_the_document_s_status(
    browser: Any, served: list[Site]
) -> None:
    web = site(served, {"/": (403, {}, PAGE)})
    async with asyncio.timeout(BOUND):
        opened = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        glanced = await browser.glance(
            opened.page, selector='input[type="password" i]', expect=None, seconds=1
        )
        gone = await browser.open(web.origin + "/", boundary(frozenset({web.origin})), FakeStop())
        none = await browser.glance(gone.page, selector="#nothing-here", expect=None, seconds=1)

    assert (glanced.found, glanced.status) == (3, 403)
    assert (none.found, none.text) == (0, None)
