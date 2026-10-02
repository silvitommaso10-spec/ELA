"""The browser's verifiers look at the page, never at the tool's report of it (M13.4 form I).

A click sent is not a click that worked (§20): the action's verifier waits for the expected text on
the page. A read's verifier reads the page again, under the same selector. Both look **once** — the
page is released with the look — and a page that is gone is said to be gone, not verified. Every
failure speaks in sizes and origins, never with the page or an argument, which a failure carries
into the audit (§57).
"""

from __future__ import annotations

import asyncio

import pytest

from ela.domain import ExecutionResult, JsonMapping
from ela.permissions import BROWSER_ACT, BROWSER_READ
from ela.ports import BrowserFailed, BrowserStopped, Glanced
from ela.testing.fakes import FakeBrowser, FakePage, FakeStop
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_PAGE_GONE,
    BROWSER_TEXT_MATCHES,
    BROWSER_TEXT_MISMATCH,
    BrowserActVerifier,
    BrowserReadVerifier,
)
from ela.tools.verify import VERIFICATION_ARGUMENTS_INVALID, Verifier
from tests.tools.test_verifiers import succeeded


def result(capability: str, output: JsonMapping) -> ExecutionResult:
    return succeeded(capability, output=output)


async def opened(browser: FakeBrowser) -> str:
    """A page the tool handed to the verifier, as the tool does."""
    page = (await browser.open("https://example.com/", lambda url: True, FakeStop())).page
    await browser.keep(page)
    return page


# ----------------------------------------------------------------------------------------
# browser.read: the page shows, now, what the result says it read
# ----------------------------------------------------------------------------------------


async def test_a_read_is_verified_by_the_page_and_the_page_is_released() -> None:
    browser = FakeBrowser(FakePage(texts={"h1": "Example Domain"}))
    page = await opened(browser)
    verifier = BrowserReadVerifier(browser, 30.0)

    failures = await verifier.verify(
        [BROWSER_TEXT_MATCHES],
        {"selector": "h1"},
        result(BROWSER_READ, {"text": "Example Domain", "page": page}),
    )

    assert failures == ()
    assert browser.glances == [(page, "h1", None, 30.0)]
    assert (
        await verifier.verify(
            [BROWSER_TEXT_MATCHES],
            {"selector": "h1"},
            result(BROWSER_READ, {"text": "Example Domain", "page": page}),
        )
        != ()
    ), "one look: the page is gone after it"


async def test_a_result_that_says_what_the_page_does_not_show_fails_in_sizes() -> None:
    browser = FakeBrowser(FakePage(texts={None: "la pagina vera"}))
    page = await opened(browser)

    (failure,) = await BrowserReadVerifier(browser, 30.0).verify(
        [BROWSER_TEXT_MATCHES], {}, result(BROWSER_READ, {"text": "inventata", "page": page})
    )

    assert failure.code == BROWSER_TEXT_MISMATCH
    assert failure.details == {
        "condition": BROWSER_TEXT_MATCHES,
        "page_bytes": 14,
        "result_bytes": 9,
    }
    assert "vera" not in failure.message and "inventata" not in failure.message


async def test_a_page_that_changed_by_itself_fails_and_is_said() -> None:
    browser = FakeBrowser(FakePage(texts={None: "12:00"}, changes_to={None: "12:01"}))
    page = await opened(browser)

    (failure,) = await BrowserReadVerifier(browser, 30.0).verify(
        [BROWSER_TEXT_MATCHES], {}, result(BROWSER_READ, {"text": "12:00", "page": page})
    )

    assert failure.code == BROWSER_TEXT_MISMATCH


async def test_an_element_that_is_not_there_once_any_more_fails() -> None:
    browser = FakeBrowser(FakePage(texts={None: "x"}, changes_to={None: "x"}))
    page = await opened(browser)

    (failure,) = await BrowserReadVerifier(browser, 30.0).verify(
        [BROWSER_TEXT_MATCHES],
        {"selector": "h1"},
        result(BROWSER_READ, {"text": "x", "page": page}),
    )

    assert failure.code == BROWSER_TEXT_MISMATCH
    assert "not on the page exactly once" in failure.message


async def test_a_read_verifier_refuses_a_selector_that_is_not_a_text() -> None:
    (failure,) = await BrowserReadVerifier(FakeBrowser(), 30.0).verify(
        [BROWSER_TEXT_MATCHES], {"selector": 5}, result(BROWSER_READ, {"page": "page-1"})
    )

    assert failure.code == VERIFICATION_ARGUMENTS_INVALID


# ----------------------------------------------------------------------------------------
# browser.act: a click sent is not a click that worked
# ----------------------------------------------------------------------------------------


async def test_an_action_is_verified_by_the_text_appearing_on_the_page() -> None:
    browser = FakeBrowser(FakePage(shown=True))
    page = await opened(browser)

    failures = await BrowserActVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE], {"expect_text": "Grazie"}, result(BROWSER_ACT, {"page": page})
    )

    assert failures == ()
    assert browser.glances == [(page, None, "Grazie", 30.0)]


async def test_a_click_that_did_nothing_fails_without_the_expected_text() -> None:
    browser = FakeBrowser(FakePage(shown=False))
    page = await opened(browser)

    (failure,) = await BrowserActVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE],
        {"expect_text": "Grazie Tommaso"},
        result(BROWSER_ACT, {"page": page}),
    )

    assert failure.code == BROWSER_EXPECT_MISSING
    assert "within 30 s" in failure.message
    assert "may have arrived all the same" in failure.message
    assert "Grazie" not in failure.message and "Tommaso" not in failure.message
    assert failure.retryable is False


async def test_a_navigation_the_boundary_stopped_is_named_by_its_origin() -> None:
    browser = FakeBrowser(FakePage(shown=False, left="https://altrove.example/grazie?id=9"))
    page = await opened(browser)

    (failure,) = await BrowserActVerifier(browser, 30.0).verify(
        [BROWSER_EXPECT_VISIBLE], {"expect_text": "ok"}, result(BROWSER_ACT, {"page": page})
    )

    assert "https://altrove.example," in failure.message
    assert "id=9" not in failure.message


async def test_an_action_verifier_refuses_an_expectation_that_is_not_a_text() -> None:
    (failure,) = await BrowserActVerifier(FakeBrowser(), 30.0).verify(
        [BROWSER_EXPECT_VISIBLE], {"expect_text": ""}, result(BROWSER_ACT, {"page": "page-1"})
    )

    assert failure.code == VERIFICATION_ARGUMENTS_INVALID


# ----------------------------------------------------------------------------------------
# A page that is gone is gone, not verified
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("verifier", ["read", "act"])
async def test_a_page_that_is_gone_fails_and_is_not_retryable(verifier: str) -> None:
    """A restart between the tool and the look, which ``_resume`` does again (census C4)."""
    browser = FakeBrowser()
    checker = (
        BrowserReadVerifier(browser, 30.0)
        if verifier == "read"
        else BrowserActVerifier(browser, 30.0)
    )
    condition = BROWSER_TEXT_MATCHES if verifier == "read" else BROWSER_EXPECT_VISIBLE
    capability = BROWSER_READ if verifier == "read" else BROWSER_ACT

    (failure,) = await checker.verify(
        [condition], {"expect_text": "ok"}, result(capability, {"page": "page-99"})
    )

    assert failure.code == BROWSER_PAGE_GONE
    assert failure.retryable is False
    assert "what the tool reported is in the result" in failure.message


async def test_a_result_that_names_no_page_is_a_page_gone() -> None:
    (failure,) = await BrowserReadVerifier(FakeBrowser(), 30.0).verify(
        [BROWSER_TEXT_MATCHES], {}, result(BROWSER_READ, {"text": "x"})
    )

    assert failure.code == BROWSER_PAGE_GONE
    assert "names no page" in failure.message


async def test_a_stop_during_the_look_is_a_page_gone() -> None:
    browser = FakeBrowser()
    page = await opened(browser)
    browser.raising["glance"] = BrowserStopped("ELA is stopping")  # type: ignore[assignment]

    (failure,) = await BrowserReadVerifier(browser, 30.0).verify(
        [BROWSER_TEXT_MATCHES], {}, result(BROWSER_READ, {"text": "x", "page": page})
    )

    assert failure.code == BROWSER_PAGE_GONE


async def test_what_else_the_browser_raises_is_the_executor_s_to_name() -> None:
    """A verifier that cannot answer has not verified: ``verification.exception`` (ADR 0014 §4)."""
    browser = FakeBrowser()
    page = await opened(browser)
    browser.raising["glance"] = BrowserFailed("Error")  # type: ignore[assignment]

    with pytest.raises(BrowserFailed):
        await BrowserReadVerifier(browser, 30.0).verify(
            [BROWSER_TEXT_MATCHES], {}, result(BROWSER_READ, {"text": "x", "page": page})
        )


@pytest.mark.parametrize("which", ["read", "act"])
async def test_a_look_that_never_answers_is_bounded_and_is_a_doubt(which: str) -> None:
    """Found implementing, after the review of 2026-09-30, point 2: the look had no deadline of its
    own — the adapter cancels the deadline of a kept page when the look starts, and Playwright's
    calls have none —, so a page that never answered held the verification, and the ``run``, for
    ever. One deadline around the whole look, the wait for the text and a grace: past it the
    verifier raises, and the executor records ``verification.exception`` (ADR 0014 §4, §33). The
    guard is the test's, and never the one that fires."""

    class Unanswered(FakeBrowser):
        async def glance(
            self, page: str, *, selector: str | None, expect: str | None, seconds: float
        ) -> Glanced:
            await asyncio.Event().wait()
            raise AssertionError("never reached")

    browser = Unanswered()
    page = await opened(browser)
    verifier: Verifier
    if which == "read":
        verifier = BrowserReadVerifier(browser, 0.0, grace=0.0)
        conditions, arguments = [BROWSER_TEXT_MATCHES], {}
        output = result(BROWSER_READ, {"text": "x", "page": page})
    else:
        verifier = BrowserActVerifier(browser, 0.0, grace=0.0)
        conditions, arguments = [BROWSER_EXPECT_VISIBLE], {"expect_text": "Grazie"}
        output = result(BROWSER_ACT, {"gestures": 1, "page": page})

    guard = asyncio.timeout(10)
    async with guard:
        with pytest.raises(TimeoutError):
            await verifier.verify(conditions, arguments, output)
    assert not guard.expired()


def test_they_read_the_machine_and_say_what_they_can_report() -> None:
    assert BrowserReadVerifier.reads_the_machine is True
    assert BrowserActVerifier.reads_the_machine is True
    assert {BROWSER_TEXT_MISMATCH, BROWSER_PAGE_GONE} <= BrowserReadVerifier.failure_codes
    assert {BROWSER_EXPECT_MISSING, BROWSER_PAGE_GONE} <= BrowserActVerifier.failure_codes
