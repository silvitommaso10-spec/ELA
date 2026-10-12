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
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, replace
from typing import ClassVar, Final

from ela.domain import ErrorMetadata, ExecutionResult, JsonMapping
from ela.permissions import (
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ_AS_YOU,
    ENTRY_MAX_LENGTH,
    EXPECT_MAX_LENGTH,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    AccountBrowser,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    Clock,
    IdGenerator,
    Opened,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
    Prospect,
    StopPoint,
    TaskStop,
)
from ela.tools.base import ARGUMENTS_INVALID, Outcome
from ela.tools.browser import (
    BROWSER_CODES,
    FAILED,
    FIRST_GESTURE,
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
    _secret,
    _selector,
    boundary,
    origin_of,
    place_of,
)
from ela.tools.vault import KEY_REFUSED, LOCKED, TIMEOUT, VAULT_CODES, VaultDoor, VaultProblem
from ela.tools.verifiers import (
    BROWSER_EXPECT_MISSING,
    BROWSER_EXPECT_VISIBLE,
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
    "BROWSER_ACT_AS_YOU_TOOL_NAME",
    "BROWSER_ACT_AS_YOU_VERIFIER_NAME",
    "BROWSER_LOGIN_TOOL_NAME",
    "BROWSER_LOGIN_VERIFIER_NAME",
    "BROWSER_READ_AS_YOU_TOOL_NAME",
    "BROWSER_READ_AS_YOU_VERIFIER_NAME",
    "BROWSER_SECOND_FACTOR",
    "ENTRY_FORGOTTEN",
    "LOGIN_FORM_GET",
    "LOGS_IN",
    "NOT_A_PASSWORD_FIELD",
    "PROFILE_BUSY",
    "PROFILE_UNDECLARED",
    "PROFILE_UNSAFE",
    "READS_AS_YOU",
    "AccountActTool",
    "AccountActVerifier",
    "AccountReadTool",
    "AccountReadVerifier",
    "LoginTool",
    "LoginVerifier",
    "ProfileLook",
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
ENTRY_FORGOTTEN: Final = "vault.entry_forgotten"
"""ELA does not know any more which entry the question named: it was started again between the
question and the yes. Nothing is typed, and the step is asked again."""
ACCOUNT_CODES: Final[frozenset[str]] = frozenset({PROFILE_UNDECLARED, PROFILE_UNSAFE, PROFILE_BUSY})

BROWSER_SECOND_FACTOR: Final = "browser.second_factor"
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
ACTS_AS_YOU: Final = (
    "fills in and clicks on this site in ELA's own browser, which keeps the sites you signed in "
    "to: where you are signed in it acts as you, on your account there — what it sends (a form, a "
    "message, an order) is sent in your name, and ELA cannot know it before it happens, nor take "
    "it back after"
)
LOGS_IN: Final = (
    "takes one password from your vault, types it into this page and sends the form: you are "
    "signed in to this site as you. ELA keeps the password nowhere — not in the plan, in this "
    "question, in the result or in a log —, and ELA's browser stays signed in there for as long "
    "as the site's cookie lasts"
)
"""Not «nowhere else»: after the click the form is sent again by the gate of the browser's
adapter, and the value passes through ELA's process once more (measured; decision 40)."""

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
REMEMBERED: Final = 256
"""How many questions a login tool remembers the entry of: the oldest goes first."""
NEW_OR_NOT_A_PASSWORD: Final = frozenset({"new-password", "one-time-code", "cc-number", "cc-csc"})
"""What a password field may not declare itself, for this tool as for every other: a password to
choose, a one-time code, a card."""


def _held(holder: str) -> str:
    return f"ELA's browser with your accounts is in use — {HELD_BY.get(holder, holder)}"


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


async def look_at(browser: AccountBrowser, seconds: float) -> ProfileLook:
    """Look at the profile through its port, within ``seconds``. Nothing is started, and the
    folder is not read from here: the port answers with facts."""
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
    if holder is not None:
        return ProfileLook(PROFILE_BUSY, _held(holder), holder)
    return ProfileLook()


UNASKED: Final = frozenset({UNSUPPORTED_SYSTEM, PROFILE_BUSY})
"""The refusals of the look whose sentence, before a question, ends by saying that none is
asked: the two a reader could take for something the yes would have fixed."""


class _OnTheProfile(_BrowserTool):
    """What the three tools share: the browser is the one with the profile, so the folder is
    looked at before the question and its refusals are named after the yes too."""

    _browser: AccountBrowser

    async def _installed(self) -> Outcome | None:
        """Before the question: the system, the folder, the binary, and who holds the folder.
        Nothing is started."""
        look = await look_at(self._browser, self._browsing.timeout_seconds)
        if look.code is None:
            return None
        unasked = ": no question is asked" if look.code in UNASKED else ""
        return Outcome(
            {}, look.code, f"{look.message}{unasked}", retryable=look.code == PROFILE_BUSY
        )

    async def _run(self, arguments: JsonMapping, stop: TaskStop) -> Outcome:
        """The run of the empty browser's tool — and what only a profile can refuse, found by the
        opening itself: the folder became held, or unfit, between the question and the yes. The
        yes is spent and nothing was started (ADR 0052 §7)."""
        nothing = {"gestures": 0} if self.acts else {}
        try:
            return await super()._run(arguments, stop)
        except ProfileBusy as busy:
            return Outcome(
                nothing,
                PROFILE_BUSY,
                f"{_held(busy.by)}: the yes was spent, and no browser was started",
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

    def _left(self, site: str, left: str) -> str:
        return (
            f"the page of {site} went to {left}, which is not the site the question named: the "
            "browser did not follow, and nothing was sent there"
        )


class AccountReadTool(_OnTheProfile, BrowserReadTool):
    """Opens one page of a declared site with the profile and reads its text (**MEDIUM**)."""

    error_codes: ClassVar[frozenset[str]] = BrowserReadTool.error_codes | ACCOUNT_CODES
    does: ClassVar[str] = READS_AS_YOU

    def __init__(
        self,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_READ_AS_YOU_TOOL_NAME,
    ) -> None:
        _BrowserTool.__init__(self, BROWSER_READ_AS_YOU, browsing, browser, clock, ids, name=name)

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

    def __init__(
        self,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        name: str = BROWSER_ACT_AS_YOU_TOOL_NAME,
    ) -> None:
        _BrowserTool.__init__(self, BROWSER_ACT_AS_YOU, browsing, browser, clock, ids, name=name)


@dataclass(frozen=True, slots=True)
class _Login(_Call):
    """A login that would start: the call, the entry the plan named — if it named one —, and the
    key this call is remembered by."""

    entry: str | None = None
    key: str = ""


class LoginTool(_OnTheProfile, _BrowserTool):
    """Takes one password from the vault and fills one login on a declared site (**HIGH**)."""

    error_codes: ClassVar[frozenset[str]] = (
        frozenset({ARGUMENTS_INVALID, *BROWSER_CODES, *ACCOUNT_CODES, *VAULT_CODES})
        | {NOT_A_PASSWORD_FIELD, LOGIN_FORM_GET, ENTRY_FORGOTTEN}
    ) - {KEY_REFUSED}
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {"status", "gestures", "page", ENDED_AT, ENDED_STATUS, PASSWORD_FIELD_STILL_THERE}
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
    ) -> None:
        super().__init__(BROWSER_LOGIN, browsing, browser, clock, ids, name=name)
        self._vault = vault
        self._found: dict[str, str | None] = {}

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
        expect, entry = arguments.get("expect_text"), arguments.get("entry")
        if not isinstance(expect, str) or not 0 < len(expect) <= EXPECT_MAX_LENGTH:
            return Outcome(
                {},
                ARGUMENTS_INVALID,
                f"expect_text must be a text of 1 to {EXPECT_MAX_LENGTH} characters",
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
            key=json.dumps(dict(arguments), sort_keys=True, default=str),
        )

    async def prospect(self, arguments: JsonMapping) -> Prospect:
        """What the question names: the site, the address, **the entry** — by its name and its
        username masked, in two fields of their own —, the fields, the click, the text awaited and
        the time. Before it, every refusal of the profile and of the vault, each with its code;
        none of them names an entry.
        """
        looked = self._shaped(arguments)
        if not isinstance(looked, Outcome):
            missing = await self._installed()
            if missing is not None:
                looked = missing
        if isinstance(looked, Outcome):
            return self._refused(looked.code or ARGUMENTS_INVALID, looked.message, looked.retryable)
        assert isinstance(looked, _Login)  # noqa: S101 — ``_gestures`` builds no other call
        found = await self._vault.find(looked.visit.site, looked.entry)
        if isinstance(found, VaultProblem):
            return self._refused(found.code, found.message, found.code in {LOCKED, TIMEOUT})
        self._remember(looked.key, found.id)
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
            )
        )

    def _refused(self, code: str, message: str, retryable: bool) -> Prospect:
        return Prospect(
            refusal=ErrorMetadata(
                code=code, message=message, tool_name=self.name, retryable=retryable
            )
        )

    def _remember(self, key: str, entry: str) -> None:
        """Which entry the question of this call named: what the yes covers. Kept in memory, for
        the questions that are waiting — a bounded number, the oldest first out.

        **One tool serves every task, and the key is the call.** Two questions for the same call
        that named **different** entries — the same plan asked twice, with the vault changed in
        between — leave ``None``: ELA cannot tell which of them a yes is for, and types neither
        (re-read of 2026-10-11)."""
        known = self._found.pop(key, entry)
        self._found[key] = entry if known == entry else None
        while len(self._found) > REMEMBERED:
            del self._found[next(iter(self._found))]

    async def _work(self, call: _Call, opened: Opened, done: list[int], stop: TaskStop) -> Outcome:
        """Every element and the form before anything is asked of the vault; the stop of the task;
        then one reading of the entry, and the three gestures."""
        assert isinstance(call, _Login) and call.click is not None  # noqa: S101
        site, page = call.visit.site, opened.page
        if origin_of(opened.address) != self._browsing.origin(site):
            return self._none_typed(
                LEFT_SITE,
                f"the page ELA opened is at {origin_of(opened.address)}, which is not the site "
                "the question named",
            )
        username, word = call.fills[0][0], call.fills[1][0]
        for selector, which in (
            (username, "username_field"),
            (word, "password_field"),
            (call.click, "click"),
        ):
            refused = await self._one(page, selector, which, site)
            if refused is not None:
                return self._none_typed(refused.code or FAILED, refused.message)
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
        entry = call.entry or self._found.get(call.key)
        if entry is None:
            return self._none_typed(ENTRY_FORGOTTEN, self._forgotten(call.key))
        taken = await self._vault.take(site, entry)
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
        await self._browser.fill_secret(page, username, taken.username)
        done[0] += 1
        if stop.is_set():
            return self._stopped(opened, done, site)
        await self._browser.fill_secret(page, word, taken.password)
        done[0] += 1
        del taken
        if stop.is_set():
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
        # What the page is now that the login was sent (decision 106): where it ended, with
        # which status, and whether the password field is still there — the three things that
        # tell a login the site refused from one it took. **In the result and nowhere else**:
        # the verifier's sentence, when the text does not appear, goes to the audit, and a path
        # is in no sentence of the audit (ADR 0052 §12).
        landed = await self._browser.landed(page)
        if origin_of(landed.address) != self._browsing.origin(site):
            # The gate is asked about the first address of a navigation and about its first
            # redirect, not about the rest of a chain (measured on 2026-10-12, ADR 0063 §11): a
            # page that ended on another site is found here, by where it is. It is not handed
            # to the verifier and nothing of it is told but its origin.
            return Outcome(
                {"status": opened.status, "gestures": done[0]},
                LEFT_SITE,
                f"after the login was sent the page of {site} ended at "
                f"{origin_of(landed.address)}, which is not the site the question named: ELA "
                "read nothing of that page" + self._after(done),
            )
        still = await self._browser.count(page, word)
        return Outcome(
            {
                "status": opened.status,
                "gestures": done[0],
                "page": page,
                ENDED_AT: place_of(landed.address),
                ENDED_STATUS: landed.status,
                PASSWORD_FIELD_STILL_THERE: still > 0,
            }
        )

    def _still_at_work(self, site: str, done: list[int]) -> str:
        """A time that ran out **after the click** is not a page still at work: the password was
        typed and the form was sent, and what the site did with it ELA does not know (decision
        111). Said as it is — and never asked again: a login sent twice is sent twice."""
        if done[0] == GESTURES_OF_A_LOGIN - 1:
            # Both values typed, and the third gesture not counted: the time ran out **inside
            # the click**, which waits for the navigation it starts. The form may have left.
            return (
                f"the two values were typed on the page of {site} and the click was asked, and "
                f"it had not returned after {self._browsing.timeout_seconds} s: ELA closed the "
                "browser and does not know whether the login was sent, nor how it ended"
                f"{self._after(done)}"
            )
        if done[0] < GESTURES_OF_A_LOGIN:
            return super()._still_at_work(site, done)
        return (
            f"the login was sent to {site}, and the page it led to was still arriving after "
            f"{self._browsing.timeout_seconds} s: ELA closed the browser and does not know how "
            f"it ended — the site may have signed you in{self._after(done)}"
        )

    def _forgotten(self, key: str) -> str:
        """Why the tool does not know which entry a yes is for — and the slate wiped, so that
        the next question for this call is the only one."""
        disagreed = key in self._found
        self._found.pop(key, None)
        if disagreed:
            return (
                "two questions for this same call named different entries of the vault, and ELA "
                "does not guess which one the yes was for: ask again"
            )
        return (
            "ELA was started again after it asked, and does not know any more which entry of "
            "the vault the question named: ask again"
        )

    def _none_typed(self, code: str, message: str, retryable: bool = False) -> Outcome:
        return Outcome({"gestures": 0}, code, message + SPENT, retryable=retryable)

    def _stopped(self, opened: Opened, done: list[int], site: str) -> Outcome:
        return Outcome(
            {"status": opened.status, "gestures": done[0]},
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

    conditions: ClassVar[frozenset[str]] = frozenset({BROWSER_EXPECT_VISIBLE})
    failure_codes: ClassVar[frozenset[str]] = COMMON_FAILURE_CODES | {
        BROWSER_EXPECT_MISSING,
        BROWSER_SECOND_FACTOR,
        BROWSER_PAGE_GONE,
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
