"""``browser.read`` and ``browser.act`` (spec §19): one page of a declared site, in ELA's own empty
browser (M13.4, ADR 0052).

**Every decision is here, and the adapter executes it to the letter** (M13.4 form K). The address is
composed — the origin of the site, then the path — and never read from a string of the plan, so the
target the Guardian judged and the host the browser goes to cannot be two. Where the main frame may
go is a function of this module, handed to the adapter (:func:`boundary`): the declared sites for a
read, **the site of the question and no other** for an action (decision 13). Which element, which
value, and every refusal are decided here, in the gate.

**What can be known without opening the page is refused before the question** (form G, decision 5):
the grammar of the site, of the path and of the selectors, the shape of the gestures and their
limits, and whether the browser the lock names is installed. Opening the page would be a visit the
audit does not record, so everything else is found after the yes — and never with an effect other
than the one approved: before the first gesture every element is there exactly once, and none
declares itself secret (form H).

**A secret field is refused, and the refusal does not protect the secret** (decision 6): it comes
after the yes, when the value is already in the plan, in the question and on the phone. It protects
the truth of this module's sentence — «the site sees a visitor, not your account» — and, for a card,
§30 until M14.1. Both recognitions are partial: a password in an ordinary text field passes.

**A page read is kept for the verifier**, under an opaque identifier in the result: the tool's word
about *which* page, never about what it shows (form I). Every other ending closes the browser.
"""

from __future__ import annotations

import asyncio
import re
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Final
from urllib.parse import urlsplit

from ela.domain import CapabilityId, ErrorMetadata, JsonMapping, JsonValue
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_READ,
    EXPECT_MAX_LENGTH,
    FILLS_MAX,
    PATH_MAX_LENGTH,
    PATH_PATTERN,
    SELECTOR_MAX_LENGTH,
    SITE_PATTERN,
    VALUE_MAX_LENGTH,
)
from ela.ports import (
    NAVIGATION,
    Browser,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    BrowserUnsupported,
    Clock,
    IdGenerator,
    Opened,
    PageGone,
    Prospect,
    SiteUnreachable,
    StopPoint,
    TaskStop,
    ToolStopped,
    Visit,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome, Tool

__all__ = [
    "ACTS",
    "BROWSER_ACT_TOOL_NAME",
    "BROWSER_CODES",
    "BROWSER_READ_TOOL_NAME",
    "BROWSER_TIMEOUT_SECONDS",
    "ELEMENT_AMBIGUOUS",
    "ELEMENT_MISSING",
    "FAILED",
    "HTTP_STATUS",
    "LEFT_SITE",
    "NOT_INSTALLED",
    "OPENS",
    "SECRET_AUTOCOMPLETE",
    "SELECTOR_EXAMPLES",
    "SELECTOR_GRAMMAR",
    "SITE",
    "SECRET_FIELD",
    "STOPPED",
    "TEXT_MAX_BYTES",
    "TIMEOUT",
    "UNREACHABLE",
    "UNSUPPORTED_SYSTEM",
    "BrowserActTool",
    "BrowserReadTool",
    "Browsing",
    "boundary",
    "cut",
    "https_origin",
    "origin_of",
]

BROWSER_READ_TOOL_NAME: Final = "browser-read"
BROWSER_ACT_TOOL_NAME: Final = "browser-act"

BROWSER_TIMEOUT_SECONDS: Final = 30
"""How long a browser step has to open, look and act — and the verifier to see its text appear
(decision 8). **A decision, not a median**: a local page is read in 18 ms and ``example.com`` in 119
(M3), and the real time is the site's, as a program decides a command's (ADR 0047 §7). Thirty
seconds are a hundred times the slowest cold read measured over the network (333 ms), and a ceiling
to how
long a run stays hanging. The question shows it; no argument changes it."""

TEXT_MAX_BYTES: Final = 65536
"""How much of a page's text a read keeps: **the beginning**, cut on a character (form I). A
decision — the terminal's ceiling per stream (ADR 0047 §8) —, not a measure."""

NOT_INSTALLED: Final = "browser.not_installed"
"""The browser the lock names is not on this machine: refused before the question, from its
executable; and in the run, from the launch that does the work."""
UNSUPPORTED_SYSTEM: Final = "browser.unsupported_system"
"""ELA does not know where the browser would be on this system: refused before the question, like
:data:`NOT_INSTALLED`, and not called that — installing would not change the answer."""
NOT_INSTALLED_MESSAGE: Final = (
    "the browser ELA uses is not installed on this machine: run "
    "`uv run playwright install --only-shell chromium`"
)
UNREACHABLE: Final = "browser.unreachable"
"""The page did not answer."""
HTTP_STATUS: Final = "browser.http_status"
"""The page answered with a status of 400 or more: an error page is not the information asked, and
not the form to fill."""
LEFT_SITE: Final = "browser.left_site"
"""A navigation of the main frame went outside the boundary, and was not sent (form F)."""
ELEMENT_MISSING: Final = "browser.element_missing"
"""A selector finds no element on the page."""
ELEMENT_AMBIGUOUS: Final = "browser.element_ambiguous"
"""A selector finds more than one element: which one would be a guess."""
SECRET_FIELD: Final = "browser.secret_field"
"""A field to fill declares itself a password, a one-time code or a card (decision 6)."""
TIMEOUT: Final = "browser.timeout"
"""The step was still at work after :data:`BROWSER_TIMEOUT_SECONDS`, and ELA closed the browser."""
STOPPED: Final = "browser.stopped"
"""ELA was stopping, and closed the browser. Not :data:`TIMEOUT`: the time had not run out."""
FAILED: Final = "browser.failed"
"""Anything else the engine raised, by its type's name: poor, and said (form J)."""

BROWSER_CODES: Final[frozenset[str]] = frozenset(
    {
        NOT_INSTALLED,
        UNSUPPORTED_SYSTEM,
        UNREACHABLE,
        HTTP_STATUS,
        LEFT_SITE,
        ELEMENT_MISSING,
        ELEMENT_AMBIGUOUS,
        SECRET_FIELD,
        TIMEOUT,
        STOPPED,
        FAILED,
    }
)

SITE: Final = "site"
"""What the target of the two capabilities is called, in the tools' own word (M13.2 dec. 12)."""
FIRST_GESTURE: Final = "the first gesture"
"""Where ``browser.act`` listens for the stop of its task: a field filled, or the click (M6.3c)."""

OPENS: Final = (
    "opens this address in ELA's own browser, which is empty — no cookies, no logins: the site "
    "sees a visitor, not you — and reads the page; it fills in nothing and clicks nothing"
)
"""What a yes to a read does, said by the capability (ADR 0045 §6): asked only when a step asks."""
ACTS: Final = (
    "fills in and clicks on this site, in ELA's own browser, which is empty — no cookies, no "
    "logins: the site sees a visitor, not your account —; what it sends (a form, a message, an "
    "order) ELA cannot know before it happens, nor take back after"
)
"""What a yes to an action does (form G): it **can** send, always — said of the capability, never
guessed from the argument —, and the browser holds nothing of the user's (form C)."""

SECRET_AUTOCOMPLETE: Final[frozenset[str]] = frozenset(
    {"current-password", "new-password", "one-time-code", "cc-number", "cc-csc"}
)
"""The ``autocomplete`` tokens a field declares itself secret with (decision 6), beside
``type="password"`` and every ``cc-exp`` token. A site that does not declare its fields passes:
the recognition is partial, and the question — which shows the values — is what remains."""

SELECTOR_EXAMPLES: Final = ('input[name="custname"]', 'button:has-text("Submit order")')
"""Two selectors as the grammar wants them: an attribute, and a text that Playwright's CSS finds."""

SELECTOR_GRAMMAR: Final = (
    "a selector is CSS as Playwright reads it, pseudo-classes included — "
    f"{SELECTOR_EXAMPLES[0]}, {SELECTOR_EXAMPLES[1]} —, with no prefix such as text= or xpath=, "
    "no '>>' and no quotes at its start; it must name exactly one element on the page"
)
"""The grammar of a selector, written once (decision 44 of the review of M14.3's second round): the
refusal of :func:`_selector` says it, and so do the tools of a guided session to their model — who
chooses writes, and who gives the tool says the grammar."""

_ENGINE_SWITCH: Final = re.compile(r"^\s*(?:[\"']|//|\.\.|[\w-]+(?::[\w-]+)*=)")
"""The start of a selector that would make Playwright choose another engine (form H): quotes are
text, ``//`` and ``..`` are XPath, ``name=`` is the engine ``name``. ``>>`` chains engines and is
refused apart."""


def origin_of(url: str) -> str:
    """``scheme://host[:port]`` of ``url``, lower-cased: what the boundary compares, and what a
    refusal names — never the path, and never a user or a password written before the host."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:  # a port that is not a number: the origin is what can be said of it
        port = None
    host = parts.hostname or ""
    return f"{parts.scheme.lower()}://{host}" + ("" if port is None else f":{port}")


def https_origin(site: str) -> str:
    """The origin of a site in production: ``https`` and the site, nothing else (form E)."""
    return f"https://{site}"


def boundary(origins: frozenset[str]) -> Callable[[str], bool]:
    """Whether a navigation of the main frame to ``url`` may be sent: its origin is one of these
    (form F). ``http`` against ``https`` is another origin, and so is another port."""

    def allowed(url: str) -> bool:
        return origin_of(url) in origins

    return allowed


def cut(text: str) -> tuple[str, int, int]:
    """The beginning of ``text`` that fits :data:`TEXT_MAX_BYTES`, on a character, with the bytes
    kept and the bytes there were."""
    data = text.encode()
    kept = data[:TEXT_MAX_BYTES].decode(errors="ignore")
    return kept, len(kept.encode()), len(data)


@dataclass(frozen=True, slots=True)
class Browsing:
    """What the composition hands the two tools, once (M13.4).

    ``sites`` is ``ELA_BROWSER_SITES`` — the same tuple the catalogue's scope is —; ``origin`` gives
    the origin of a site, ``https`` in production (:func:`https_origin`) and a local server in the
    tests of the real browser: the seam is here, in the gate, and ``build()`` is held to ``https``
    by a test of its wiring (form E).
    """

    sites: tuple[str, ...]
    origin: Callable[[str], str] = https_origin
    timeout_seconds: int = BROWSER_TIMEOUT_SECONDS


@dataclass(frozen=True, slots=True)
class _Call:
    """A browser call that would start: the facts of the question, and what the page needs."""

    visit: Visit
    fills: tuple[tuple[str, str], ...]
    click: str | None
    selector: str | None
    allowed: Callable[[str], bool]


class _BrowserTool(Tool):
    """What the two browser tools share: the checks before the question, and the page's life."""

    relocatable: ClassVar[bool] = False
    """**Not relocatable** (form A): the browser does not travel, and a page opened from another
    machine is another visit — another address, another hour."""
    does: ClassVar[str]
    acts: ClassVar[bool]

    def __init__(
        self,
        capability_id: CapabilityId,
        browsing: Browsing,
        browser: Browser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str,
    ) -> None:
        super().__init__(capability_id, clock, ids, name=name)
        self._browsing = browsing
        self._browser = browser

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What this call would do, and what the question names (form G): the shape and the
        grammar, then whether the shell is there — asked here, before the question, and **not in
        the run**, where the launch that does the work says it (decision 2 of the review of
        2026-09-30: asking there cost a browser more at every step)."""
        looked = self._shaped(arguments)
        if not isinstance(looked, Outcome):
            missing = await self._installed()
            if missing is not None:
                looked = missing
        if isinstance(looked, Outcome):
            return Prospect(
                refusal=ErrorMetadata(
                    code=looked.code or ARGUMENTS_INVALID,
                    message=looked.message,
                    tool_name=self.name,
                    retryable=looked.retryable,
                )
            )
        return Prospect(visit=looked.visit)

    async def _installed(self) -> Outcome | None:
        """Whether the shell is there, from its executable and without starting it (form G)."""
        try:
            async with asyncio.timeout(self._browsing.timeout_seconds):
                installed = await self._browser.installed()
        except TimeoutError:
            return Outcome(
                {},
                FAILED,
                "the browser did not say whether it is installed within "
                f"{self._browsing.timeout_seconds} s",
            )
        except BrowserStopped:
            return Outcome({}, STOPPED, "ELA was stopping: no browser was started")
        except BrowserUnsupported as system:
            return Outcome(
                {},
                UNSUPPORTED_SYSTEM,
                f"ELA does not know where the browser would be on this system ({system}), so it "
                "cannot say whether it is there: no question is asked",
            )
        except BrowserFailed as failed:
            return Outcome(
                {}, FAILED, f"whether the browser is installed could not be read: {failed}"
            )
        if not installed:
            return Outcome({}, NOT_INSTALLED, NOT_INSTALLED_MESSAGE)
        return None

    def _shaped(self, arguments: JsonMapping) -> Outcome | _Call:
        site, path = arguments.get("site"), arguments.get("path")
        if not isinstance(site, str) or re.fullmatch(SITE_PATTERN, site) is None:
            return Outcome({}, ARGUMENTS_INVALID, "site must be a host name, such as example.com")
        if (
            not isinstance(path, str)
            or len(path) > PATH_MAX_LENGTH
            or re.fullmatch(PATH_PATTERN, path) is None
        ):
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                "path must begin with / and hold only the characters of a URL",
            )
        address = self._browsing.origin(site) + path
        return self._gestures(arguments, site, address)

    @abstractmethod
    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        """The part of the call only one of the two capabilities has."""

    def _visit(self, site: str, address: str, gestures: tuple[str, ...], expect: str) -> Visit:
        return Visit(
            site=site,
            label=SITE,
            does=self.does,
            address=address,
            gestures=gestures,
            expect=expect,
            timeout_seconds=self._browsing.timeout_seconds,
        )

    async def _run(self, arguments: JsonMapping, stop: TaskStop) -> Outcome:
        looked = self._shaped(arguments)
        if isinstance(looked, Outcome):
            return looked
        site = looked.visit.site
        done = [0]
        opened: Opened | None = None
        try:
            async with asyncio.timeout(self._browsing.timeout_seconds):
                opened = await self._browser.open(looked.visit.address, looked.allowed, stop)
                outcome = await self._on_the_page(looked, opened, done, stop)
        except ToolStopped:
            # Stopped before the point (M6.3c): what was opened is closed, and the call leaves
            # without acting — the executor records it.
            if opened is not None:
                await self._browser.close(opened.page)
            raise
        except TimeoutError:
            outcome = Outcome(
                self._partial(done),
                TIMEOUT,
                f"the page of {site} was still at work after {self._browsing.timeout_seconds} s: "
                f"ELA closed the browser{self._after(done)}",
            )
        except BrowserNotInstalled:
            outcome = Outcome({}, NOT_INSTALLED, NOT_INSTALLED_MESSAGE)
        except SiteUnreachable as away:
            outcome = Outcome({}, UNREACHABLE, f"the page of {site} did not answer: {away}")
        except BrowserStopped:
            outcome = Outcome(
                self._partial(done),
                STOPPED,
                f"ELA stopped while the page of {site} was open{self._after(done)}",
            )
        except (BrowserFailed, PageGone) as failed:
            outcome = Outcome(
                self._partial(done),
                FAILED,
                f"the browser failed on the page of {site}: {type(failed).__name__}"
                f"{': ' + str(failed) if str(failed) else ''}{self._after(done)}",
            )
        if opened is not None:
            if outcome.succeeded:
                await self._browser.keep(opened.page)
            else:
                await self._browser.close(opened.page)
        return outcome

    async def _on_the_page(
        self, call: _Call, opened: Opened, done: list[int], stop: TaskStop
    ) -> Outcome:
        """What happens once the page is open: the refusals of the page, then the work."""
        site = call.visit.site
        if opened.left is not None:
            return Outcome({}, LEFT_SITE, self._left(site, origin_of(opened.left)))
        if opened.status is None:
            return Outcome({}, UNREACHABLE, f"the page of {site} gave no answer")
        if opened.status >= 400:
            return Outcome(
                {"status": opened.status},
                HTTP_STATUS,
                f"the page of {site} answered {opened.status}",
            )
        return await self._work(call, opened, done, stop)

    @abstractmethod
    async def _work(self, call: _Call, opened: Opened, done: list[int], stop: TaskStop) -> Outcome:
        """What the capability does on a page that answered, on its own site."""

    async def _one(self, page: str, selector: str, which: str, site: str) -> Outcome | None:
        """``None`` when ``selector`` finds exactly one element; the refusal otherwise."""
        found = await self._browser.count(page, selector)
        if found == 1:
            return None
        if found == 0:
            return Outcome({}, ELEMENT_MISSING, f"{which} names no element on the page of {site}")
        return Outcome(
            {}, ELEMENT_AMBIGUOUS, f"{which} names {found} elements on the page of {site}"
        )

    def _left(self, site: str, left: str) -> str:
        where = "a declared site" if not self.acts else "the site the question named"
        return (
            f"the page of {site} went to {left}, which is not {where}: the browser did not follow, "
            "and nothing was sent there"
        )

    def _partial(self, done: list[int]) -> dict[str, JsonValue]:
        return {"gestures": done[0]} if self.acts else {}

    def _after(self, done: list[int]) -> str:
        if not self.acts:
            return ""
        if done[0] == 0:
            return "; no gesture was made"
        return "; 1 gesture was made" if done[0] == 1 else f"; {done[0]} gestures were made"


class BrowserReadTool(_BrowserTool):
    """Opens one page of a declared site and reads its text (§19, **LOW**)."""

    error_codes: ClassVar[frozenset[str]] = frozenset({ARGUMENTS_INVALID, *BROWSER_CODES}) - {
        SECRET_FIELD
    }
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"address", "status", "title", "text", "shown", "total", "page"}
    )
    audit_numbers: ClassVar[frozenset[str]] = frozenset({"status", "shown", "total"})
    """Numbers, and only numbers (ADR 0047 §10): never the address, the title or the text."""
    idempotent: ClassVar[bool] = True
    """**Idempotent**: reading again leaves the world as reading once — a declared limit, since a
    page with a token in its query may act on a GET (decision 4). A read killed halfway is repaired
    by reading again, and a grant is not at stake: the row is LOW."""
    does: ClassVar[str] = OPENS
    acts: ClassVar[bool] = False
    stop_point: ClassVar[StopPoint] = StopPoint(here=NAVIGATION, on_a_node=None)
    """The visit is the effect: the adapter listens right before the navigation (M6.3c)."""

    def __init__(
        self,
        browsing: Browsing,
        browser: Browser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_READ_TOOL_NAME,
    ) -> None:
        super().__init__(BROWSER_READ, browsing, browser, clock, ids, name=name)

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        selector = arguments.get("selector")
        if selector is not None:
            refused = _selector(selector, "selector")
            if refused is not None:
                return refused
        origins = frozenset(self._browsing.origin(one) for one in self._browsing.sites)
        return _Call(
            visit=self._visit(site, address, (), ""),
            fills=(),
            click=None,
            selector=selector if isinstance(selector, str) else None,
            allowed=boundary(origins),
        )

    async def _work(self, call: _Call, opened: Opened, done: list[int], stop: TaskStop) -> Outcome:
        site = call.visit.site
        if call.selector is not None:
            refused = await self._one(opened.page, call.selector, "the selector", site)
            if refused is not None:
                return refused
        text, shown, total = cut(await self._browser.text(opened.page, call.selector))
        return Outcome(
            {
                "address": opened.address,
                "status": opened.status,
                "title": await self._browser.title(opened.page),
                "text": text,
                "shown": shown,
                "total": total,
                "page": opened.page,
            }
        )


class BrowserActTool(_BrowserTool):
    """Fills fields on one page of a declared site and clicks (§19, **HIGH**)."""

    error_codes: ClassVar[frozenset[str]] = frozenset({ARGUMENTS_INVALID, *BROWSER_CODES})
    output_keys: ClassVar[frozenset[str]] = frozenset({"status", "gestures", "page"})
    audit_numbers: ClassVar[frozenset[str]] = frozenset({"status", "gestures"})
    """The status of the page of the form, and how many gestures were made: never a selector, a
    value or the page (ADR 0047 §10)."""
    idempotent: ClassVar[bool] = False
    """**Not idempotent**: a submission sent twice is sent twice. The executor writes a STARTED
    record before the first gesture, and a retry that finds it without an outcome closes the step as
    interrupted and **never clicks again** (ADR 0021 §2)."""
    does: ClassVar[str] = ACTS
    acts: ClassVar[bool] = True
    stop_point: ClassVar[StopPoint] = StopPoint(here=FIRST_GESTURE, on_a_node=None)
    """Before the first gesture (decision 2 of M6.3c); the navigation before it is listened to
    without being this tool's point, and after it no gesture follows a stop (decision 5)."""

    def __init__(
        self,
        browsing: Browsing,
        browser: Browser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_ACT_TOOL_NAME,
    ) -> None:
        super().__init__(BROWSER_ACT, browsing, browser, clock, ids, name=name)

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        fill, click, expect = (
            arguments.get("fill"),
            arguments.get("click"),
            arguments.get("expect_text"),
        )
        if not isinstance(fill, list | tuple) or len(fill) > FILLS_MAX:
            return Outcome(
                {}, ARGUMENTS_INVALID, f"fill must be a list of at most {FILLS_MAX} pairs"
            )
        fills: list[tuple[str, str]] = []
        for index, pair in enumerate(fill, start=1):
            if (
                not isinstance(pair, list | tuple)
                or len(pair) != 2
                or not all(isinstance(one, str) for one in pair)
            ):
                return Outcome(
                    {}, ARGUMENTS_INVALID, f"fill {index} must be a pair [selector, value]"
                )
            selector, value = str(pair[0]), str(pair[1])
            refused = _selector(selector, f"the selector of fill {index}")
            if refused is not None:
                return refused
            if len(value) > VALUE_MAX_LENGTH:
                return Outcome(
                    {},
                    ARGUMENTS_INVALID,
                    f"the value of fill {index} is longer than {VALUE_MAX_LENGTH} characters",
                )
            fills.append((selector, value))
        refused = _selector(click, "click")
        if refused is not None:
            return refused
        if not isinstance(expect, str) or not 0 < len(expect) <= EXPECT_MAX_LENGTH:
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                f"expect_text must be a text of 1 to {EXPECT_MAX_LENGTH} characters",
            )
        assert isinstance(click, str)  # noqa: S101 — ``_selector`` said so
        gestures = (
            *(f"fills {selector} with “{value}”" for selector, value in fills),
            f"clicks {click}",
        )
        return _Call(
            visit=self._visit(site, address, gestures, expect),
            fills=tuple(fills),
            click=click,
            selector=None,
            allowed=boundary(frozenset({self._browsing.origin(site)})),
        )

    async def _work(self, call: _Call, opened: Opened, done: list[int], stop: TaskStop) -> Outcome:
        """Every element before the first gesture, then the gestures, in order (form H).

        The stop of the task is listened to right before the first gesture — the point — and
        looked at before every other one: a gesture never follows a stop (M6.3c, decision 5)."""
        site, page = call.visit.site, opened.page
        total = len(call.fills) + 1
        for index, (selector, _) in enumerate(call.fills, start=1):
            which = f"gesture {index} of {total}"
            refused = await self._one(page, selector, which, site)
            if refused is not None:
                return self._none_made(refused)
            declared = await self._browser.field(page, selector)
            if _secret(declared.type, declared.autocomplete):
                return self._none_made(
                    Outcome(
                        {},
                        SECRET_FIELD,
                        f"{which} names a field that declares itself a password, a one-time code "
                        f"or a card, on the page of {site}: ELA does not fill it",
                    )
                )
        assert call.click is not None  # noqa: S101 — an action always clicks
        refused = await self._one(page, call.click, f"gesture {total} of {total}", site)
        if refused is not None:
            return self._none_made(refused)
        stop.listen(FIRST_GESTURE)
        for selector, value in call.fills:
            if done[0] and stop.is_set():
                return self._stopped(opened, done, site)
            await self._browser.fill(page, selector, value)
            done[0] += 1
        if done[0] and stop.is_set():
            return self._stopped(opened, done, site)
        await self._browser.click(page, call.click)
        done[0] += 1
        left = await self._browser.left(page)
        if left is not None:
            return Outcome(
                {"status": opened.status, "gestures": done[0]},
                LEFT_SITE,
                self._left(site, origin_of(left)) + self._after(done),
            )
        return Outcome({"status": opened.status, "gestures": done[0], "page": page})

    def _none_made(self, refused: Outcome) -> Outcome:
        return Outcome({"gestures": 0}, refused.code, refused.message + "; no gesture was made")

    def _stopped(self, opened: Opened, done: list[int], site: str) -> Outcome:
        """The task was stopped after the first gesture: no other one is made (M6.3c)."""
        return Outcome(
            {"status": opened.status, "gestures": done[0]},
            STOPPED,
            f"the task was stopped on the page of {site}{self._after(done)}, and no other gesture "
            "followed",
        )


def _selector(selector: object, which: str) -> Outcome | None:
    """``None`` for a selector the tool hands to the browser as it stands; the refusal otherwise.

    A selector is Playwright's, pseudo-classes included, and the question shows it as it is; what
    would make Playwright choose another engine is refused (form H).
    """
    if not isinstance(selector, str) or not 0 < len(selector) <= SELECTOR_MAX_LENGTH:
        return Outcome(
            {},
            ARGUMENTS_INVALID,
            f"{which} must be a text of 1 to {SELECTOR_MAX_LENGTH} characters",
        )
    if ">>" in selector or _ENGINE_SWITCH.match(selector) is not None or "\n" in selector:
        return Outcome(
            {},
            ARGUMENTS_INVALID,
            f"{which} would choose another engine than the one the question shows: "
            f"{SELECTOR_GRAMMAR}",
        )
    return None


def _secret(declared_type: str, autocomplete: str) -> bool:
    """Whether a field declares itself secret: a password, a one-time code, a card (decision 6)."""
    if declared_type == "password":
        return True
    tokens = set(autocomplete.split())
    return bool(tokens & SECRET_AUTOCOMPLETE) or any(one.startswith("cc-exp") for one in tokens)
