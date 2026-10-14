"""The browser with the user's accounts, as ELA's tools reach it (§19, §57; M13.9, ADR 0063).

Three capabilities, beside the two of the empty browser and never instead of them:

* ``browser.read_as_you`` (**MEDIUM**) and ``browser.act_as_you`` (**HIGH**) are ``browser.read``
  and ``browser.act`` **on the browser with the profile that lasts** — the same arguments, the
  same grammars, the same checks before a gesture. What changes is the browser, the sentence the
  question shows, and the boundary of a read: the site the call names and no other, because a
  redirect between two declared sites would carry the credentials of the second into a read that
  named the first;
* ``browser.login`` (**HIGH**) takes one password from the vault and fills one login. **The value
  never comes from the plan, and never enters this module**: the tool asks the door of the vault
  for the entry, receives two :class:`~ela.ports.Secret`, and hands them to the browser's adapter
  — to nobody else, and into no outcome, message or event.

**Before the question** («it would start»), in this order and each with a code of its own: the
arguments; the system, the folder of the profile, the binary, and whether the folder is held; and,
for a login, the vault's program, the vault's state and the entry. A refusal born there costs no
yes, and never names an entry.

**After the yes** a login opens the page, looks at every element and at the form — the password
field must be a password field, of a form that sends with ``POST`` —, listens for the stop of its
task, and **only then** asks the vault: one reading, compared again with the site on that very
reading. What fails there has its code; the yes is spent, and nothing was typed.

**A login always has a window** (decisions 143 and 144 of the review of 2026-10-13): its page is
opened in a browser that has one whatever the user's switch says — a site may refuse a browser
that says it has none: measured on one site —, and where no window can be had the login does
not start, before the question and before the vault is asked. A window takes the keyboard —
measured: in two rounds of three the browser came in front, with the focus on the field just
written; no real key was pressed —: so right before the click the two fields are read again,
and a field that no longer holds what was typed stops the click.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import ClassVar, Final

from ela.domain import (
    ErrorMetadata,
    ExecutionResult,
    JsonMapping,
    JsonValue,
    PermissionDecision,
    TaskId,
)
from ela.permissions import (
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ_AS_YOU,
    ENTRY_MAX_LENGTH,
    EXPECT_MAX_LENGTH,
)
from ela.ports import (
    BROWSER_LOGIN_FORM_GONE,
    HELD,
    HELD_IN_PART,
    LOGIN_FORM,
    LOGIN_FORM_AMBIGUOUS,
    LOGIN_FORM_NOT_FOUND,
    NO_LOGIN_FORM,
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_TASK,
    PROFILE_WINDOW,
    AccountBrowser,
    BrowserError,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    Clock,
    FormField,
    IdGenerator,
    NoWindow,
    Opened,
    PageForm,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Prospect,
    StopPoint,
    TaskPages,
    TaskStop,
    WaitingPage,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome
from ela.tools.browser import (
    ANOTHER_PAGE,
    BROWSER_CODES,
    ELEMENT_AMBIGUOUS,
    ELEMENT_MISSING,
    FAILED,
    FIRST_GESTURE,
    HTTP_STATUS,
    LEFT_SITE,
    NOT_INSTALLED,
    SECRET_FIELD,
    STOPPED,
    UNSUPPORTED_SYSTEM,
    BrowserActTool,
    BrowserReadTool,
    Browsing,
    _BrowserTool,
    _Call,
    _Done,
    _secret,
    _selector,
    boundary,
    origin_of,
    place_of,
)
from ela.tools.vault import KEY_REFUSED, LOCKED, TIMEOUT, VAULT_CODES, VaultDoor, VaultProblem
from ela.tools.verifiers import (
    BROWSER_ANOTHER_PAGE,
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
    BROWSER_LEFT_SITE,
    BROWSER_PAGE_GONE,
    LOOK_GRACE_SECONDS,
    BrowserActVerifier,
    BrowserReadVerifier,
    _PageVerifier,
)
from ela.tools.verify import COMMON_FAILURE_CODES, VERIFICATION_ARGUMENTS_INVALID

__all__ = [
    "ACCOUNT_CODES",
    "ACTS_AS_YOU",
    "ACTS_ON_AS_YOU",
    "BROWSER_ACT_AS_YOU_TOOL_NAME",
    "BROWSER_ACT_AS_YOU_VERIFIER_NAME",
    "BROWSER_LOGIN_TOOL_NAME",
    "BROWSER_LOGIN_VERIFIER_NAME",
    "BROWSER_READ_AS_YOU_TOOL_NAME",
    "BROWSER_READ_AS_YOU_VERIFIER_NAME",
    "BROWSER_SECOND_FACTOR",
    "ENTRY_NOT_NAMED",
    "FIELD_CHANGED",
    "LOGIN_FORM_GET",
    "LOGIN_FORM_STILL_THERE",
    "LOGS_IN",
    "NAMED_ENTRY",
    "NOT_A_PASSWORD_FIELD",
    "NO_WINDOW",
    "PROFILE_BUSY",
    "PROFILE_UNDECLARED",
    "PROFILE_UNSAFE",
    "READS_AS_YOU",
    "READS_ON_AS_YOU",
    "STOP_A_TASK",
    "AccountActTool",
    "AccountActVerifier",
    "AccountReadTool",
    "AccountReadVerifier",
    "LoginTool",
    "LoginVerifier",
    "ProfileLook",
    "kept_on_the_profile",
    "login_form_of",
    "look_at",
]

BROWSER_READ_AS_YOU_TOOL_NAME: Final = "browser-read-as-you"
BROWSER_ACT_AS_YOU_TOOL_NAME: Final = "browser-act-as-you"
BROWSER_LOGIN_TOOL_NAME: Final = "browser-login"
BROWSER_READ_AS_YOU_VERIFIER_NAME: Final = "browser-read-as-you-verifier"
BROWSER_ACT_AS_YOU_VERIFIER_NAME: Final = "browser-act-as-you-verifier"
BROWSER_LOGIN_VERIFIER_NAME: Final = "browser-login-verifier"

PROFILE_UNDECLARED: Final = "browser.profile_undeclared"
"""No folder was declared for the browser to keep the user's sessions in."""
PROFILE_UNSAFE: Final = "browser.profile_unsafe"
"""The declared folder is open to others than its owner, or is not the owner's: ELA does not
narrow it by itself."""
PROFILE_BUSY: Final = "browser.profile_busy"
"""A process already holds the folder — a step of ELA's, the window, another browser —, and ELA
does not launch a second one on it. Retryable: what holds it ends."""
NOT_A_PASSWORD_FIELD: Final = "browser.not_a_password_field"  # noqa: S105 — a code
"""``password_field`` names a field that is not ``type="password"``: a password is not typed
where the page would show it."""
LOGIN_FORM_GET: Final = "browser.login_form_get"
"""The form of the password field does not send with ``POST``: sent with ``GET``, the password
would be in an address — in the history of the profile, and in what ELA remembers of a
navigation."""
ENTRY_NOT_NAMED: Final = "vault.entry_not_named"
"""The yes was given to a question that named no entry of the vault: a question composed before
ELA kept the entry with the yes (M13.10, decision 38 of its review). ELA does not look for one
again — the yes covers what the question named —: nothing is typed, and the step is asked again."""
NAMED_ENTRY: Final = "entry"
"""The key, in what the question of a login named (:attr:`~ela.ports.Prospect.named`), of the id of
the entry of the vault the question named (M13.10, ADR 0065): handed back with the yes."""
NO_WINDOW: Final = "browser.no_window"
"""A login wants a window, and ELA could not tell that one can be had — its process is not
inside a session of the screen, or the system did not say: a login does not start without one
(decision 143). Not retryable: nothing about a later attempt is different by itself."""
FIELD_CHANGED: Final = "browser.field_changed"
"""Right before the click, a field of the login form did not hold what ELA had typed in it — or
was not there any more: the window has the keyboard, and a key pressed in those seconds lands in
the form (decision 144; measured that the browser comes in front with the focus on the field,
not with a real key); and a page may itself change what is typed into its field. **ELA did not
click. Whether a key sent the form — a Return does, by itself — ELA does not know.** One case
has a sentence of its own (decision 152): a field that holds **only a beginning** of what was
typed — a page that keeps less than it is given —, said without saying how much."""
ACCOUNT_CODES: Final[frozenset[str]] = frozenset({PROFILE_UNDECLARED, PROFILE_UNSAFE, PROFILE_BUSY})

BROWSER_SECOND_FACTOR: Final = "browser.second_factor"
LOGIN_FORM_STILL_THERE: Final = "browser.login_form_still_there"
"""The password field of the login is on the page still, after the login was sent."""
"""After the click the page asks for a one-time code: ELA takes none and types none."""
GESTURES_OF_A_LOGIN: Final = 3
"""The username typed, the password typed, the click: after the third the form has been sent."""
ENDED_AT: Final = "ended_at"
"""In the result of a login: where the page ended once the login had been sent — its host and
its path, never its query (decision 106)."""
ENDED_STATUS: Final = "ended_status"
"""The HTTP status of the document of that page; ``None`` when the site answered nothing to what
was sent. **Not** one of the numbers the audit takes from a result."""
PASSWORD_FIELD_STILL_THERE: Final = "_".join(("password", "field", "still", "there"))
"""Whether the password field the plan names was still on that page: the form again, or not."""

NOT_INSTALLED_MESSAGE: Final = (
    "the browser ELA keeps your sessions in is not installed on this machine: run "
    "`uv run playwright install chromium`"
)

READS_AS_YOU: Final = (
    "opens this page in ELA's own browser, which keeps the sites you signed in to: where you are "
    "signed in the site sees you, and what comes back is your own content; it fills in nothing "
    "and clicks nothing — but a site that acts when an address is opened acts as you"
)
"""What a yes to a read with the profile does (ADR 0063): «where you are signed in», because ELA
does not know, before it opens the page, whether there is a login on that site."""
READS_ON_AS_YOU: Final = (
    "opens no page: it reads the page the step right before it in this task left open, where that "
    "page is now, in ELA's own browser, which keeps the sites you signed in to: where you are "
    "signed in the site sees you, and what comes back is your own content; it fills in nothing "
    "and clicks nothing"
)
"""What a yes to a read with the profile that continues does (M13.10, ADR 0065 §3)."""
ACTS_AS_YOU: Final = (
    "fills in and clicks on this site in ELA's own browser, which keeps the sites you signed in "
    "to: where you are signed in it acts as you, on your account there — what it sends (a form, a "
    "message, an order) is sent in your name, and ELA cannot know it before it happens, nor take "
    "it back after"
)
ACTS_ON_AS_YOU: Final = (
    "opens no page: it fills in and clicks on the page the step right before it in this task left "
    "open, where that page is now, in ELA's own browser, which keeps the sites you signed in to: "
    "where you are signed in it acts as you, on your account there — what it sends (a form, a "
    "message, an order) is sent in your name, and ELA cannot know it before it happens, nor take "
    "it back after"
)
"""What a yes to an action with the profile that continues does (M13.10, ADR 0065 §3)."""
LOGS_IN: Final = (
    "takes one password from your vault, types it into this page and sends the form: you are "
    "signed in to this site as you. ELA keeps the password nowhere — not in the plan, in this "
    "question, in the result or in a log —, and ELA's browser stays signed in there for as long "
    "as the site's cookie lasts. While ELA signs in, a window of ELA's browser appears on your "
    "screen: do not type until it is gone"
)
"""Not «nowhere else»: after the click the browser sends the form, and the driver hands the
request — with its body — to its client in ELA's process (read in the driver's code; ADR 0063
§5). **The window is said here and in no other sentence** (decision 143): this is what the
question shows as what the yes does."""
NO_WINDOW_MESSAGE: Final = (
    "a login runs in a window of ELA's browser, and ELA could not tell that it can open one — "
    "it did not find itself inside a session of your screen: a login does not start without one"
)

HELD_BY: Final = {
    PROFILE_STEP: "another step of ELA's is using it",
    PROFILE_WINDOW: (
        "its window is open: quit that browser (Cmd-Q — closing the window alone leaves it "
        "running), or run `ela browser close`, and ask again"
    ),
    PROFILE_PROCESS: (
        "another process holds it — a browser somebody started on that folder, or a window of "
        "ELA's that outlived it: quit it, or run `ela browser close`"
    ),
}
SPENT: Final = "; the yes was spent, and nothing was typed"
UNNAMED: Final = "(an entry of your vault that has no name)"
"""What the question calls an entry the user never named: every surface that offers a yes shows
the entry and whose it is (ADR 0063 §9), and an empty name would have shown neither."""
NEW_OR_NOT_A_PASSWORD: Final = frozenset({"new-password", "one-time-code", "cc-number", "cc-csc"})
"""What a password field may not declare itself, for this tool as for every other: a password to
choose, a one-time code, a card."""

PASSWORD_ITSELF: Final = (
    'input[type="password" i]:not([autocomplete~="new-password" i])'
    ':not([autocomplete~="one-time-code" i]):not([autocomplete^="cc-" i])'
)
"""A password field a login would fill, by what it declares — the rule of decision 22 written as a
selector: of type password, and declaring itself neither a password to choose, nor a one-time code,
nor a card."""
SENDERS: Final = frozenset(
    {("input", "submit"), ("input", "image"), ("button", "submit"), ("button", "")}
)
"""The elements of a form that send it, by their tag and declared type: a button with no type
sends."""
TEXTS: Final = frozenset({"text", "email", ""})
"""The fields a username is typed in, by their declared type: an input with no type is text."""
_PLAIN_NAME: Final = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
"""A name a selector can carry as it is, with nothing to escape."""


def login_form_of(forms: Sequence[PageForm]) -> dict[str, str] | str:
    """The one login form of a page, as the three selectors a login fills and clicks — or the code
    that says why there is none (M13.10, ADR 0065 §4; decision 22 of the review of its SPEC).

    The rule counts the password fields ``browser.login`` would fill — of type ``password``,
    visible, declaring none of :data:`NEW_OR_NOT_A_PASSWORD` — and wants **one**; the form is the
    one that holds it, the field of the name is the one visible text or e-mail field before it in
    that form, the element that sends is the one of that form. **The selectors are written from
    the same facts**, never from a position: the password field by what it declares, the other two
    by their name or their type, each inside the form that holds that field. Each is counted on
    the page before it is written to a result — one, or the form is ambiguous."""
    wanted = [
        (form, index)
        for form in forms
        for index, one in enumerate(form.fields)
        if one.type == "password" and one.visible and not _not_a_login(one.autocomplete)
    ]
    if len(wanted) != 1:
        return LOGIN_FORM_AMBIGUOUS if wanted else LOGIN_FORM_NOT_FOUND
    form, index = wanted[0]
    if not form.in_a_form:
        return LOGIN_FORM_NOT_FOUND
    names = [
        one
        for one in form.fields[:index]
        if one.tag == "input" and one.type in TEXTS and one.visible
    ]
    senders = [one for one in form.fields if (one.tag, one.type) in SENDERS and one.visible]
    for found in (names, senders):
        if len(found) != 1:
            return LOGIN_FORM_AMBIGUOUS if found else LOGIN_FORM_NOT_FOUND
    scope = f"form:has({PASSWORD_ITSELF})"
    return {
        "username_field": f"{scope} {_written(names[0])}",
        "password_field": f"{scope} {PASSWORD_ITSELF}:visible",
        "click": f"{scope} {_written(senders[0])}",
    }


def _not_a_login(autocomplete: str) -> bool:
    tokens = autocomplete.split()
    return bool(set(tokens) & NEW_OR_NOT_A_PASSWORD) or any(t.startswith("cc-") for t in tokens)


def _written(one: FormField) -> str:
    """An element of the form by its name when it has a plain one, or by its type."""
    if _PLAIN_NAME.match(one.name):
        return f'{one.tag}[name="{one.name}"]'
    if one.type:
        return f'{one.tag}[type="{one.type}" i]:visible'
    return f"{one.tag}:not([type]):visible"


STOP_A_TASK: Final = "ela task cancel"
"""The command that ends a task, and with it the page it keeps: what the sentences of a page that
waits name (M13.10, decision 26 of the review of its SPEC)."""


def _held(holder: str, waiting: WaitingPage | None = None) -> str:
    if holder == PROFILE_TASK:
        return f"ELA's browser with your accounts is in use — {_kept(waiting)}"
    return f"ELA's browser with your accounts is in use — {HELD_BY.get(holder, holder)}"


def _kept(waiting: WaitingPage | None) -> str:
    """Who keeps the profile between two steps, until when, and how it ends (M13.10, ADR 0065 §3;
    decision 26 of the review of its SPEC)."""
    if waiting is None:
        return "a page a task keeps between two of its steps holds it, until that task ends"
    until = (
        "until that task ends"
        if waiting.until is None
        else f"until {waiting.until.isoformat(timespec='minutes')} at the latest"
    )
    return (
        f"task {waiting.task} keeps a page on it between two of its steps, {until}: "
        f"`{STOP_A_TASK} {waiting.task}` ends it"
    )


async def kept_on_the_profile(pages: TaskPages) -> WaitingPage | None:
    """The page a task keeps on the browser with the profile now, if any."""
    return next((one for one in await pages.waiting() if one.profile), None)


@dataclass(frozen=True, slots=True)
class ProfileLook:
    """The profile as one look found it, with nothing started (M13.9, ADR 0063 §8).

    ``code`` is what a browser could not start for — the tools' own code, with ``message`` its
    sentence —, or ``None`` for a profile that is usable and free. ``holder`` is who holds it
    when the code is :data:`PROFILE_BUSY`. **One definition** for the tools, which refuse with
    it before their question, and for the routes, which say it as a state: the order — the
    system, the folder, the binary, who holds the folder — and the sentences are here.
    """

    code: str | None = None
    message: str = ""
    holder: str | None = None
    task: TaskId | None = None
    """The task that keeps a page on the profile between two of its steps, when the holder is
    :data:`PROFILE_TASK` (M13.10, ADR 0065 §3)."""


async def look_at(
    browser: AccountBrowser, seconds: float, pages: TaskPages | None = None
) -> ProfileLook:
    """Look at the profile through its port, within ``seconds``. Nothing is started, and the
    folder is not read from here: the port answers with facts — and, of a page a task keeps
    there, ``pages`` says which task, and until when."""
    try:
        async with asyncio.timeout(seconds):
            holder = await browser.occupied()
            installed = await browser.installed()
    except TimeoutError:
        return ProfileLook(
            FAILED, f"the browser did not say whether it can start within {seconds:g} s"
        )
    except BrowserStopped:
        return ProfileLook(STOPPED, "ELA was stopping: no browser was started")
    except BrowserUnsupported as system:
        return ProfileLook(
            UNSUPPORTED_SYSTEM,
            f"ELA's browser with your accounts runs on a Mac, and this is {system}",
        )
    except ProfileUndeclared as undeclared:
        return ProfileLook(PROFILE_UNDECLARED, str(undeclared))
    except ProfileUnsafe as unsafe:
        return ProfileLook(PROFILE_UNSAFE, str(unsafe))
    except BrowserFailed as failed:
        return ProfileLook(FAILED, f"whether the browser can start could not be read: {failed}")
    if not installed:
        return ProfileLook(NOT_INSTALLED, NOT_INSTALLED_MESSAGE)
    if holder is None:
        return ProfileLook()
    if holder == PROFILE_TASK and pages is not None:
        waiting = await kept_on_the_profile(pages)
        return ProfileLook(
            PROFILE_BUSY,
            _held(holder, waiting),
            holder,
            None if waiting is None else waiting.task,
        )
    return ProfileLook(PROFILE_BUSY, _held(holder), holder)


UNASKED: Final = frozenset({UNSUPPORTED_SYSTEM, PROFILE_BUSY})
"""The refusals of the look whose sentence, before a question, ends by saying that none is
asked: the two a reader could take for something the yes would have fixed."""


class _OnTheProfile(_BrowserTool):
    """What the three tools share: the browser is the one with the profile, so the folder is
    looked at before the question and its refusals are named after the yes too."""

    _browser: AccountBrowser
    profile: ClassVar[bool] = True

    async def _installed(self, task: TaskId | None = None) -> Outcome | None:
        """Before the question: the system, the folder, the binary, and who holds the folder.
        Nothing is started. **A page the same task keeps there is no refusal** (M13.10): the step
        continues on it, or the room closes it before this step opens another."""
        look = await look_at(self._browser, self._browsing.timeout_seconds, self._pages)
        if look.code is None or (look.task is not None and look.task == task):
            return None
        unasked = ": no question is asked" if look.code in UNASKED else ""
        return Outcome(
            {}, look.code, f"{look.message}{unasked}", retryable=look.code == PROFILE_BUSY
        )

    async def _ran(self, looked: _Call, stop: TaskStop) -> Outcome:
        """The run of the empty browser's tool — and what only a profile can refuse, found by the
        opening itself: the folder became held, or unfit, between the question and the yes. The
        yes is spent and nothing was started (ADR 0052 §7)."""
        nothing = {"gestures": 0} if self.acts else {}
        try:
            return await super()._ran(looked, stop)
        except ProfileBusy as busy:
            waiting = await kept_on_the_profile(self._pages) if busy.by == PROFILE_TASK else None
            return Outcome(
                nothing,
                PROFILE_BUSY,
                f"{_held(busy.by, waiting)}: the yes was spent, and no browser was started",
                retryable=True,
            )
        except ProfileUndeclared as undeclared:
            return Outcome(nothing, PROFILE_UNDECLARED, str(undeclared))
        except ProfileUnsafe as unsafe:
            return Outcome(nothing, PROFILE_UNSAFE, str(unsafe))
        except BrowserUnsupported as system:
            return Outcome(
                nothing,
                UNSUPPORTED_SYSTEM,
                f"ELA's browser with your accounts runs on a Mac, and this is {system}",
            )

    def _inside(self) -> str:
        """With the profile the boundary is the one site the call names, for a read too."""
        return "the site the question named"


class AccountReadTool(_OnTheProfile, BrowserReadTool):
    """Opens one page of a declared site with the profile and reads its text (**MEDIUM**)."""

    error_codes: ClassVar[frozenset[str]] = BrowserReadTool.error_codes | ACCOUNT_CODES
    output_keys: ClassVar[frozenset[str]] = BrowserReadTool.output_keys | {
        LOGIN_FORM,
        NO_LOGIN_FORM,
    }
    does: ClassVar[str] = READS_AS_YOU
    continuing: ClassVar[str] = READS_ON_AS_YOU

    def __init__(
        self,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_READ_AS_YOU_TOOL_NAME,
        pages: TaskPages,
    ) -> None:
        _BrowserTool.__init__(
            self, BROWSER_READ_AS_YOU, browsing, browser, clock, ids, name=name, pages=pages
        )

    async def _work(self, call: _Call, opened: Opened, done: _Done, stop: TaskStop) -> Outcome:
        """``browser.read``'s — and **the login form of the page, always** (M13.10, decision 43
        (ii) of the review of its SPEC): in a key of the result of its own, outside the audit and
        outside what a model is shown. No argument asks for it: a read the room makes for a login
        is a read like every other."""
        outcome = await super()._work(call, opened, done, stop)
        if not outcome.succeeded:
            return outcome
        found = login_form_of(await self._browser.forms(opened.page))
        if isinstance(found, dict):
            for selector in found.values():
                if await self._browser.count(opened.page, selector) != 1:
                    found = LOGIN_FORM_AMBIGUOUS
                    break
        said: JsonValue = dict(found) if isinstance(found, dict) else found
        key = LOGIN_FORM if isinstance(found, dict) else NO_LOGIN_FORM
        return replace(outcome, output={**outcome.output, key: said})

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        """``browser.read``'s — with **the site the call names as the whole boundary**, where the
        empty browser follows a redirect between declared sites (ADR 0063; proposal 4)."""
        looked = super()._gestures(arguments, site, address)
        if isinstance(looked, Outcome):
            return looked
        return replace(looked, allowed=boundary(frozenset({self._browsing.origin(site)})))


class AccountActTool(_OnTheProfile, BrowserActTool):
    """Fills fields on one page of a declared site with the profile and clicks (**HIGH**). A
    field that declares itself secret is refused, as by ``browser.act``."""

    error_codes: ClassVar[frozenset[str]] = BrowserActTool.error_codes | ACCOUNT_CODES
    does: ClassVar[str] = ACTS_AS_YOU
    continuing: ClassVar[str] = ACTS_ON_AS_YOU

    def __init__(
        self,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_ACT_AS_YOU_TOOL_NAME,
        pages: TaskPages,
    ) -> None:
        _BrowserTool.__init__(
            self, BROWSER_ACT_AS_YOU, browsing, browser, clock, ids, name=name, pages=pages
        )


@dataclass(frozen=True, slots=True)
class _Login(_Call):
    """A login that would start: the call, and the entry — the one the plan named, or, after the
    yes, the one the question named (M13.10)."""

    entry: str | None = None


class LoginTool(_OnTheProfile, _BrowserTool):
    """Takes one password from the vault and fills one login on a declared site (**HIGH**)."""

    error_codes: ClassVar[frozenset[str]] = (
        frozenset({ARGUMENTS_INVALID, *BROWSER_CODES, *ACCOUNT_CODES, *VAULT_CODES})
        | {NOT_A_PASSWORD_FIELD, LOGIN_FORM_GET, ENTRY_NOT_NAMED, NO_WINDOW, FIELD_CHANGED}
    ) - {KEY_REFUSED}
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "status",
            "gestures",
            "page",
            ENDED_AT,
            ENDED_STATUS,
            PASSWORD_FIELD_STILL_THERE,
            ANOTHER_PAGE,
        }
    )
    audit_numbers: ClassVar[frozenset[str]] = frozenset({"status", "gestures"})
    """The status of the page of the form and how many gestures were made: never a selector, an
    entry, a username or the page."""
    idempotent: ClassVar[bool] = False
    """**Not idempotent**: a login sent twice is sent twice, and a password taken twice is taken
    twice. A retry that finds a started record without an outcome never types again."""
    does: ClassVar[str] = LOGS_IN
    acts: ClassVar[bool] = True
    stop_point: ClassVar[StopPoint] = StopPoint(here=FIRST_GESTURE, on_a_node=None)
    """Before the first gesture — and **before the vault is asked for the password**: a stopped
    task takes none."""

    def __init__(
        self,
        browsing: Browsing,
        browser: AccountBrowser,
        vault: VaultDoor,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_LOGIN_TOOL_NAME,
        pages: TaskPages,
    ) -> None:
        super().__init__(BROWSER_LOGIN, browsing, browser, clock, ids, name=name, pages=pages)
        self._vault = vault

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        username, word, click = (
            arguments.get("username_field"),
            arguments.get("password_field"),
            arguments.get("click"),
        )
        for selector, which in (
            (username, "username_field"),
            (word, "password_field"),
            (click, "click"),
        ):
            refused = _selector(selector, which)
            if refused is not None:
                return refused
        expect, entry = arguments.get("expect_text", ""), arguments.get("entry")
        if not isinstance(expect, str) or len(expect) > EXPECT_MAX_LENGTH:
            # Optional since M13.10 (decision 31): absent, the verifier looks for the form gone.
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                f"expect_text, when given, must be a text of 1 to {EXPECT_MAX_LENGTH} characters",
            )
        if entry is not None and (
            not isinstance(entry, str) or not 0 < len(entry) <= ENTRY_MAX_LENGTH
        ):
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                f"entry must be the id of an entry of the vault, of 1 to {ENTRY_MAX_LENGTH} "
                "characters",
            )
        assert isinstance(username, str) and isinstance(word, str)  # noqa: S101 — ``_selector``
        assert isinstance(click, str)  # noqa: S101 — ``_selector`` said so
        gestures = (
            f"types the username of the entry of your vault into {username}",
            f"types its password into {word}",
            f"clicks {click}",
        )
        return _Login(
            visit=self._visit(site, address, gestures, expect),
            fills=((username, ""), (word, "")),
            click=click,
            selector=None,
            allowed=boundary(frozenset({self._browsing.origin(site)})),
            entry=entry,
        )

    async def _installed(self, task: TaskId | None = None) -> Outcome | None:
        """What every tool of the profile looks at before its question — and whether a window
        can be had, which only a login needs: asked last, of a profile a browser can start on."""
        missing = await super()._installed(task)
        if missing is not None:
            return missing
        try:
            async with asyncio.timeout(self._browsing.timeout_seconds):
                possible = await self._browser.can_show()
        except BrowserStopped:
            return Outcome({}, STOPPED, "ELA was stopping: no browser was started")
        except (TimeoutError, BrowserError):
            # Whether a window can be had could not be read: a doubt, and a doubt is not a yes.
            possible = False
        if possible:
            return None
        return Outcome({}, NO_WINDOW, f"{NO_WINDOW_MESSAGE}: no question is asked")

    async def _opened(self, call: _Call, stop: TaskStop) -> Opened:
        """The page of a login, opened **with a window whatever the switch says**."""
        return await self._browser.open_shown(call.visit.address, call.allowed, stop)

    async def _decided(
        self,
        decision: PermissionDecision,
        arguments: JsonMapping,
        stop: TaskStop,
        named: JsonMapping,
    ) -> Outcome:
        """The login of **the entry the question named** (M13.10, ADR 0065): the plan's, when it
        named one, or the one the executor hands back with the yes — never one found again after
        the yes, which is what a restart would otherwise make of it. A yes to a question that
        named none is :data:`ENTRY_NOT_NAMED`, and nothing is typed."""
        looked = self._shaped(arguments)
        if isinstance(looked, Outcome):
            return looked
        assert isinstance(looked, _Login)  # noqa: S101 — ``_gestures`` builds no other call
        entry = looked.entry
        if entry is None:
            said = named.get(NAMED_ENTRY)
            entry = said if isinstance(said, str) and said else None
        if entry is None:
            return self._none_typed(
                ENTRY_NOT_NAMED,
                "the question this yes answered named no entry of the vault, and ELA does not "
                "look for one again: ask again",
            )
        return await self._ran(self._of(replace(looked, entry=entry), decision), stop)

    async def _ran(self, looked: _Call, stop: TaskStop) -> Outcome:
        """The run of every tool of the profile — and the one thing only a page asked with a
        window can be refused for, by the opening itself: the session of the screen went away
        between the question and the yes. Nothing was started, and the vault was not asked."""
        try:
            return await super()._ran(looked, stop)
        except NoWindow:
            return self._none_typed(NO_WINDOW, NO_WINDOW_MESSAGE)

    async def prospect(self, arguments: JsonMapping, task: TaskId | None = None) -> Prospect:
        """What the question names: the site, the address, **the entry** — by its name and its
        username masked, in two fields of their own —, the fields, the click, the text awaited and
        the time. Before it, every refusal of the profile and of the vault, each with its code;
        none of them names an entry. A login never continues: a page its task keeps is closed
        when it opens its own (M13.10).
        """
        looked = self._shaped(arguments)
        if not isinstance(looked, Outcome):
            missing = await self._installed(task)
            if missing is not None:
                looked = missing
        if isinstance(looked, Outcome):
            return self._refused(looked.code or ARGUMENTS_INVALID, looked.message, looked.retryable)
        assert isinstance(looked, _Login)  # noqa: S101 — ``_gestures`` builds no other call
        found = await self._vault.find(looked.visit.site, looked.entry)
        if isinstance(found, VaultProblem):
            return self._refused(found.code, found.message, found.code in {LOCKED, TIMEOUT})
        username, word = looked.fills[0][0], looked.fills[1][0]
        gestures = (
            f"types the username of that entry into {username}",
            f"types its password into {word}",
            f"clicks {looked.click}",
        )
        return Prospect(
            visit=replace(
                looked.visit,
                gestures=gestures,
                entry=found.name or UNNAMED,
                username=found.username,
            ),
            # What the yes will cover, handed back with it (M13.10, ADR 0065): kept beside the
            # approval, shown by no surface, and in no event of the audit.
            named={NAMED_ENTRY: found.id},
        )

    def _refused(self, code: str, message: str, retryable: bool) -> Prospect:
        return Prospect(
            refusal=ErrorMetadata(
                code=code, message=message, tool_name=self.name, retryable=retryable
            )
        )

    async def _work(self, call: _Call, opened: Opened, done: _Done, stop: TaskStop) -> Outcome:
        """Every element and the form before anything is asked of the vault — each element
        **awaited** when it is not there yet (M13.10: one rule, an element is awaited when it is
        needed) —; the stop of the task; then one reading of the entry, and the three gestures."""
        assert isinstance(call, _Login) and call.click is not None  # noqa: S101
        site, page = call.visit.site, opened.page
        # Where the page is, the browser's adapter asks the boundary at every use of it — the
        # first one below, and each one after (M13.4f, ADR 0064 §4): the two comparisons this
        # tool made by itself until then are that one predicate.
        username, word = call.fills[0][0], call.fills[1][0]
        for selector, which in (
            (username, "username_field"),
            (word, "password_field"),
            (call.click, "click"),
        ):
            found = await self._awaited(page, selector, stop, done, which)
            if found is None:
                # Stopped while an element was awaited: nothing is typed, and the vault is not
                # asked — the point of the tool, heard here.
                stop.listen(FIRST_GESTURE)
            elif found > 1:
                return self._none_typed(
                    ELEMENT_AMBIGUOUS, f"{which} names {found} elements on the page of {site}"
                )
        secret = await self._browser.field(page, word)
        if secret.type != "password":
            return self._none_typed(
                NOT_A_PASSWORD_FIELD,
                f"password_field names a field that is not a password field, on the page of "
                f"{site}: a password is not typed where the page would show it",
            )
        tokens = set(secret.autocomplete.split())
        if tokens & NEW_OR_NOT_A_PASSWORD or any(one.startswith("cc-exp") for one in tokens):
            return self._none_typed(
                SECRET_FIELD,
                f"password_field names a field that declares itself a new password, a one-time "
                f"code or a card, on the page of {site}: ELA does not fill it",
            )
        name = await self._browser.field(page, username)
        if _secret(name.type, name.autocomplete):
            return self._none_typed(
                SECRET_FIELD,
                f"username_field names a field that declares itself a password, a one-time code "
                f"or a card, on the page of {site}: ELA does not fill it",
            )
        button = await self._browser.field(page, call.click)
        if secret.method != "post" or button.method == "get":
            return self._none_typed(
                LOGIN_FORM_GET,
                f"the login form of the page of {site} does not send with POST: sent with GET, "
                "the password would be in an address",
            )
        if stop.is_set():
            # A task that is stopped by now is heard before the vault is asked: no password is
            # taken for a step that will type nothing.
            stop.listen(FIRST_GESTURE)
        assert call.entry is not None  # noqa: S101 — ``_decided`` names it, or the step ends there
        taken = await self._vault.take(site, call.entry)
        if isinstance(taken, VaultProblem):
            return self._none_typed(taken.code, taken.message, taken.code in {LOCKED, TIMEOUT})
        # The reading took its seconds — the door, the program, the vault —, and the world went
        # on meanwhile: the field is looked at again before anything the vault gave is typed.
        again = await self._browser.field(page, word)
        if again.type != "password" or again.method != "post":
            del taken
            return self._none_typed(
                NOT_A_PASSWORD_FIELD,
                f"the page of {site} changed its password field, or the form it is in, while "
                "the vault was asked: a password is not typed where the page would show it",
            )
        try:
            # The point of the tool: the last instant before its first gesture — after the vault
            # has answered, so that a stop given while it was asked is heard here, and nothing
            # is typed (ADR 0054 §3; re-read of 2026-10-11).
            stop.listen(FIRST_GESTURE)
        except BaseException:
            del taken
            raise
        await self._gesture(done, self._browser.fill_secret(page, username, taken.username))
        if stop.is_set():
            return self._stopped(opened, done, site)
        await self._gesture(done, self._browser.fill_secret(page, word, taken.password))
        # The window has the keyboard, and a key pressed since the first field was written
        # lands in the form (decision 144; measured on 2026-10-13 that the browser comes in
        # front with the focus on the field written last — not with a real key): the two fields
        # are read again here, right before the click. The comparison is the adapter's.
        try:
            held = await self._browser.holds(page, username, taken.username)
            if held == HELD:
                held = await self._browser.holds(page, word, taken.password)
        finally:
            del taken
        if held == HELD_IN_PART:
            # The comparison stays whole (decision 152): a login is not sent with less than the
            # vault gave. But this case is told apart, and by no number: how much the field
            # kept is something of what was typed.
            return Outcome(
                {"status": opened.status, "gestures": done.made},
                FIELD_CHANGED,
                f"right before the click, a field of the login form on the page of {site} held "
                "only a beginning of what ELA had typed in it — the page keeps less than it is "
                f"given —: ELA did not click{self._after(done)}",
            )
        if held != HELD:
            return Outcome(
                {"status": opened.status, "gestures": done.made},
                FIELD_CHANGED,
                f"right before the click, a field of the login form on the page of {site} did "
                "not hold what ELA had typed in it — a key pressed while its window had the "
                "keyboard lands there, and a page may change what is typed —: ELA did not "
                f"click, and does not know whether a key sent the form{self._after(done)}",
            )
        if stop.is_set():
            return self._stopped(opened, done, site)
        # What the count says the instant before the click is asked: a time that runs out with
        # two gestures counted ran out **inside the click** if this is set, and while the two
        # fields were being read again if it is not.
        done.click_asked = True
        await self._gesture(done, self._browser.click(page, call.click))
        left = await self._browser.left(page)
        if left is not None:
            return Outcome(
                {"status": opened.status, "gestures": done.made},
                LEFT_SITE,
                self._left(site, origin_of(left)) + self._after(done),
            )
        # What the page is now that the login was sent (decision 106): where it ended, with
        # which status, and whether the password field is still there — the three things that
        # tell a login the site refused from one it took. **In the result and nowhere else**:
        # the verifier's sentence, when the text does not appear, goes to the audit, and a path
        # is in no sentence of the audit (ADR 0052 §12).
        # A page that ended on another site after the click is found by the predicate, at
        # this use or at the one before it: it is not handed to the verifier, and nothing of
        # it is told but its origin (``_elsewhere``).
        landed = await self._browser.landed(page)
        still = await self._browser.count(page, word)
        return Outcome(
            {
                "status": opened.status,
                "gestures": done.made,
                "page": page,
                ENDED_AT: place_of(landed.address),
                ENDED_STATUS: landed.status,
                PASSWORD_FIELD_STILL_THERE: still > 0,
            }
        )

    def _still_at_work(self, site: str, done: _Done) -> str:
        """A time that ran out **after the click** is not a page still at work: the password was
        typed and the form was sent, and what the site did with it ELA does not know (decision
        111). Said as it is — and never asked again: a login sent twice is sent twice."""
        if done.made == GESTURES_OF_A_LOGIN - 1 and not done.click_asked:
            # Both values typed, and the click not asked yet: the time ran out while the two
            # fields were being read again (decision 144). ELA did not click — and a key
            # pressed in the window, which has the keyboard, may have sent the form by itself.
            return (
                f"the two values were typed on the page of {site}, and the two fields were "
                f"being read again before the click when the {self._browsing.timeout_seconds} s "
                "ran out: ELA closed the browser. ELA did not click, and does not know whether "
                f"a key sent the form{self._after(done)}"
            )
        if done.made == GESTURES_OF_A_LOGIN - 1:
            # Both values typed, and the third gesture not counted: the time ran out **inside
            # the click**, which waits for the navigation it starts. The form may have left.
            return (
                f"the two values were typed on the page of {site} and the click was asked, and "
                f"it had not returned after {self._browsing.timeout_seconds} s: ELA closed the "
                "browser and does not know whether the login was sent, nor how it ended"
                f"{self._after(done)}"
            )
        if done.made < GESTURES_OF_A_LOGIN:
            return super()._still_at_work(site, done)
        return (
            f"the login was sent to {site}, and the page it led to was still arriving after "
            f"{self._browsing.timeout_seconds} s: ELA closed the browser and does not know how "
            f"it ended — the site may have signed you in{self._after(done)}"
        )

    def _timed_out(self, site: str, done: _Done) -> Outcome:
        """A time that runs out while an element of the form is awaited: nothing was typed and
        the vault was not asked, and the refusal says it as every refusal of a login before its
        first gesture does."""
        if done.waiting is not None:
            return self._none_typed(
                ELEMENT_MISSING,
                f"{done.waiting} names no visible element on the page of {site} within the "
                f"{self._browsing.timeout_seconds} s of the step",
            )
        return super()._timed_out(site, done)

    def _elsewhere(self, site: str, address: str, done: _Done, opened: Opened | None) -> Outcome:
        """Before the first gesture a login that finds its page elsewhere has typed nothing, and
        says so as every refusal of its own does; after it, as every action."""
        if done.made:
            return super()._elsewhere(site, address, done, opened)
        return self._none_typed(
            LEFT_SITE,
            f"the page of {site} is at {origin_of(address)}, which is not {self._inside()}: ELA "
            "read nothing of that page",
        )

    def _none_typed(self, code: str, message: str, retryable: bool = False) -> Outcome:
        return Outcome({"gestures": 0}, code, message + SPENT, retryable=retryable)

    def _stopped(self, opened: Opened, done: _Done, site: str) -> Outcome:
        return Outcome(
            {"status": opened.status, "gestures": done.made},
            STOPPED,
            f"the task was stopped on the page of {site}{self._after(done)}, and no other gesture "
            "followed",
        )


# ----------------------------------------------------------------------------------------
# The verifiers
# ----------------------------------------------------------------------------------------


class AccountReadVerifier(BrowserReadVerifier):
    """``browser.read_as_you``: the page shows, now, what the result says it read."""

    def __init__(
        self,
        browser: AccountBrowser,
        seconds: float,
        *,
        grace: float = LOOK_GRACE_SECONDS,
        name: str = BROWSER_READ_AS_YOU_VERIFIER_NAME,
    ) -> None:
        _PageVerifier.__init__(self, BROWSER_READ_AS_YOU, browser, seconds, grace=grace, name=name)


class AccountActVerifier(BrowserActVerifier):
    """``browser.act_as_you``: a click sent is not a click that worked — the page says."""

    def __init__(
        self,
        browser: AccountBrowser,
        seconds: float,
        *,
        grace: float = LOOK_GRACE_SECONDS,
        name: str = BROWSER_ACT_AS_YOU_VERIFIER_NAME,
    ) -> None:
        _PageVerifier.__init__(self, BROWSER_ACT_AS_YOU, browser, seconds, grace=grace, name=name)


class LoginVerifier(_PageVerifier):
    """``browser.login``: the page shows the text the plan awaits after a login — or it asks for
    a second factor, and that has a code of its own (decision 17).

    ELA takes no one-time code and types none: when the page shows a field that asks for one, the
    failure says so — «do it by hand in ELA's window» — instead of saying that a text is missing.
    **The recognition is partial**, like that of the secret fields: a site that does not declare
    its field is answered with the missing text, which is true.
    """

    conditions: ClassVar[frozenset[str]] = frozenset(
        {BROWSER_EXPECT_VISIBLE, BROWSER_LOGIN_FORM_GONE}
    )
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {
        BROWSER_EXPECT_MISSING,
        BROWSER_SECOND_FACTOR,
        BROWSER_PAGE_GONE,
        BROWSER_LEFT_SITE,
        BROWSER_ANOTHER_PAGE,
        LOGIN_FORM_STILL_THERE,
        HTTP_STATUS,
    }

    def __init__(
        self,
        browser: AccountBrowser,
        seconds: float,
        *,
        grace: float = LOOK_GRACE_SECONDS,
        name: str = BROWSER_LOGIN_VERIFIER_NAME,
    ) -> None:
        super().__init__(BROWSER_LOGIN, browser, seconds, grace=grace, name=name)

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        if condition == BROWSER_LOGIN_FORM_GONE:
            return await self._gone_form(condition, arguments, result)
        expect = arguments.get("expect_text")
        if not isinstance(expect, str) or not expect:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "expect_text must be a text",
                retryable=False,
            )
        glanced = await self._glanced(condition, result, selector=None, expect=expect)
        if isinstance(glanced, ErrorMetadata):
            return glanced
        if glanced.shown:
            return None
        if glanced.second_factor:
            return self._failure(
                condition,
                BROWSER_SECOND_FACTOR,
                "the site asks for a second factor: do it by hand in ELA's window — ELA takes no "
                "one-time code, and typed none",
                retryable=False,
            )
        another = self._opened_another(condition, glanced, "login")
        if another is not None:
            return another
        return self._failure(
            condition,
            BROWSER_EXPECT_MISSING,
            "the text the plan expects did not appear on the page within "
            f"{self._seconds:g} s after the login was sent: the site may have refused it, or "
            "signed you in all the same. Where the page had ended, the status of its document "
            "and whether the password field was still there are in the result of this step "
            "(`ela task results`), and in no other place",
            retryable=False,
        )

    async def _gone_form(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        """The login form is gone (M13.10): the page on the step's site — a page elsewhere is
        refused by the look itself —, no element left for the password field's selector, and
        the document below 400. Looked at once, on the page as it is now: no text is awaited."""
        word = arguments.get("password_field")
        if not isinstance(word, str) or not word:
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "password_field must be a selector",
                retryable=False,
            )
        glanced = await self._glanced(condition, result, selector=word, expect=None)
        if isinstance(glanced, ErrorMetadata):
            return glanced
        if glanced.second_factor:
            return self._failure(
                condition,
                BROWSER_SECOND_FACTOR,
                "the site asks for a second factor: do it by hand in ELA's window — ELA takes no "
                "one-time code, and typed none",
                retryable=False,
            )
        if glanced.found != 0:
            return self._failure(
                condition,
                LOGIN_FORM_STILL_THERE,
                "the password field of the login is on the page still, after the login was sent: "
                "the site may have refused it",
                retryable=False,
            )
        if glanced.status is None or glanced.status >= 400:
            said = "no status" if glanced.status is None else f"the status {glanced.status}"
            return self._failure(
                condition,
                HTTP_STATUS,
                f"the page the login ended on has {said}: a page of error or of refusal without "
                "the form is not a login",
                retryable=False,
            )
        return None
