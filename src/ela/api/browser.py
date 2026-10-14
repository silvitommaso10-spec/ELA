"""ELA's browser with the user's accounts, as the Core reaches it (M13.9, ADR 0063 §8; decisions
18, 34 and 35).

Four routes, the Core's. ``GET /browser`` says what the profile is: **looked at through its port
at every request, never remembered** — and never by opening the folder: this module is not handed
its path, and asks the port, which answers with facts (architecture rule 69). ``POST
/browser/window`` turns the user's switch: whether the browser of the next step has a window, a
state of a running ELA that is off at every start. ``POST /browser/open`` opens **the window where
the user signs in by hand**, on a declared site or on none. ``POST /browser/close`` ends the
browser a hand may be on (decision 80): the red button of that window closes the window and
leaves the browser running, and the profile stays held until the process ends.

**Of that window ELA reads nothing**: the port launches the binary alone and keeps the wait for
its end. What this module knows of it is that it was asked for.

**The audit**: an opening is written here, by the route that receives it, signed by who asked.
The end is written by who waits for the process — the user closes the window, or ELA stops, and no
route is asked. A close that told a process is written here too, signed by who asked: for a
browser ELA did not start nobody waits, and it is the only row there is.

The four functions under the routes are what a page calls too (architecture rule 55).
"""

from __future__ import annotations

import asyncio
from typing import Final

from fastapi import APIRouter

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import ApiError
from ela.api.schemas import (
    BrowserClosedOut,
    BrowserOpenedOut,
    BrowserOpenIn,
    BrowserOut,
    BrowserWindowIn,
    BrowserWindowOut,
    WaitingPageOut,
)
from ela.api.security import Identity
from ela.composition import Ela
from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS
from ela.domain import AuditEvent, AuditEventId, AuditEventType, visible
from ela.ports import PROFILE_STEP, PROFILE_TASK, BrowserError, BrowserStopped, ProfileBusy
from ela.tools.account import PROFILE_BUSY, STOP_A_TASK, look_at
from ela.tools.browser import (
    BROWSER_TIMEOUT_SECONDS,
    FAILED,
    NOT_INSTALLED,
    STOPPED,
    https_origin,
)

__all__ = [
    "FREE",
    "NOTHING",
    "SITE_UNDECLARED",
    "BrowserRefusedError",
    "browser_of",
    "router",
    "window_opened",
    "window_shut",
    "window_turned",
]

router = APIRouter(tags=["browser"])

SITE_UNDECLARED: Final = "browser.site_undeclared"
"""A window asked on a site that is not one of ``ELA_BROWSER_SITES``. The one code of these
routes that is theirs and not the tools'."""
FREE: Final = "free"
NOTHING: Final = "nothing"
"""What a close answers when no browser held the profile: nobody was told."""
PREFIX: Final = "browser."
A_STEP: Final = (
    "a step of ELA's is using its browser, and the command ends the browser where you sign in "
    f"by hand — to end a step, stop its task ({STOP_A_TASK} <id>)"
)
A_TASK: Final = (
    "a task of ELA's keeps a page on its browser between two of its steps, and the command ends "
    f"the browser where you sign in by hand — to end that page, stop the task ({STOP_A_TASK} "
    "<id>; `ela browser status` names it)"
)
"""What a close says when the profile is held by a page a task keeps (M13.10, ADR 0065 §3)."""
NOT_ELA_S: Final = (
    "the profile is held by a process that is not ELA's browser, or that ELA could not tell: "
    "ELA signals nothing it cannot name — it is yours to quit"
)
CLOSING_BUSY: Final = {PROFILE_STEP: A_STEP, PROFILE_TASK: A_TASK}
"""What a close says of a profile ELA itself holds: a step, or a page a task keeps."""
READ: Final = frozenset({None, PROFILE_BUSY})
"""The looks after which the folder is read for what the browser says of itself: a profile a
browser can start on — free, or held."""
ENDED: Final = READ | {NOT_INSTALLED}
"""The looks after which a browser may be ended: those, and a binary that is not installed any
more — nothing can be started then, and what is running can still be told to quit."""


class BrowserRefusedError(ApiError):
    """The window was not opened: the tools' own code is the first word — what a step with the
    profile would be refused with before its question —, and the sentence after it is theirs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


async def browser_of(ela: Ela) -> BrowserOut:
    """What the profile is now. The state is ``free``, who holds it — one of the port's three
    names —, or the tools' refusal without its prefix; ``linked`` and ``saved`` are what the
    browser says of itself, read again each time and ``None`` where nothing could be read; and
    whether a login could be given its window now is asked of the port the same way."""
    look = await look_at(ela.accounts, BROWSER_TIMEOUT_SECONDS, ela.pages)
    linked: bool | None = None
    saved: int | None = None
    profiles: int | None = None
    login_window: bool | None = None
    if look.code in READ:
        try:
            login_window = await ela.accounts.can_show()
        except BrowserError:
            login_window = None
        try:
            linked = await ela.accounts.linked()
        except BrowserError:
            linked = None
        try:
            saved = await ela.accounts.saved()
        except BrowserError:
            saved = None
        try:
            profiles = await ela.accounts.profiles()
        except BrowserError:
            profiles = None
    state = look.holder or (FREE if look.code is None else look.code.removeprefix(PREFIX))
    return BrowserOut(
        state=state,
        message=look.message,
        window=ela.window.shown,
        login_window=login_window,
        linked=linked,
        saved=saved,
        profiles=profiles,
        sites=ela.settings.browser.sites,
        waiting=tuple(
            WaitingPageOut(
                task=one.task,
                profile=one.profile,
                until=one.until,
                stop=f"{STOP_A_TASK} {one.task}",
            )
            for one in await ela.pages.waiting()
        ),
    )


def window_turned(ela: Ela, shown: bool) -> BrowserWindowOut:
    """Turn the user's switch. It opens nothing: it holds for the steps that start from now."""
    if shown:
        ela.window.show()
    else:
        ela.window.hide()
    return BrowserWindowOut(shown=ela.window.shown)


async def window_opened(ela: Ela, identity: Identity, site: str | None) -> BrowserOpenedOut:
    """Open the window where the user signs in by hand. Refused before anything is launched for
    a site nobody declared and for a profile no browser can start on — held included: ELA
    launches nothing on a folder it found held."""
    if site is not None and site not in ela.settings.browser.sites:
        raise BrowserRefusedError(
            SITE_UNDECLARED,
            f"{visible(site, lines=False)} is not one of the sites ELA may visit: the window "
            "opens on a site of ELA_BROWSER_SITES, or on none",
        )
    look = await look_at(ela.accounts, BROWSER_TIMEOUT_SECONDS)
    if look.code is not None:
        raise BrowserRefusedError(look.code, look.message)
    try:
        await ela.accounts.window(None if site is None else f"{https_origin(site)}/")
    except ProfileBusy as busy:
        raise BrowserRefusedError(
            PROFILE_BUSY, f"the profile of ELA's browser became held ({busy.by}) as it opened"
        ) from None
    except BrowserError as failed:
        raise BrowserRefusedError(FAILED, f"the window could not be opened: {failed}") from None
    await ela.audit.append(
        AuditEvent(
            id=AuditEventId(ela.ids.new_uuid()),
            created_at=ela.clock.now(),
            event_type=AuditEventType.BROWSER_WINDOW_OPENED,
            actor=identity.actor,
            summary="browser: the sign-in window opened",
            payload={"site": site},
        )
    )
    return BrowserOpenedOut(site=site)


async def _the_grace() -> None:
    """The grace of ELA's own close, as the wait the adapter is handed: told, waited for, and
    killed only once it is over."""
    await asyncio.sleep(BROWSER_CLOSE_GRACE_SECONDS)


async def window_shut(ela: Ela, identity: Identity) -> BrowserClosedOut:
    """End the browser a hand may be on: the window ELA started, or a browser ELA did not start
    that is its own binary on the profile. **What it is and whether it may be told is the
    port's to say**: a step is not ended from here, and nothing that is not ELA's browser is
    signalled. Written, signed by who asked, when a process was told.

    Refused, with the tools' own code, for a profile no browser can be on — the look every
    route of the profile begins with.

    **The row is written once the browser has been told and waited for**, with what became of
    it and with what held the profile when the command looked — the window ELA started, or a
    process it did not. A signal is not taken back: a row that cannot be written is the audit's
    error, answered to who asked."""
    look = await look_at(ela.accounts, BROWSER_TIMEOUT_SECONDS)
    if look.code not in ENDED:
        raise BrowserRefusedError(look.code or FAILED, look.message)
    try:
        outcome = await ela.accounts.shut(_the_grace)
    except ProfileBusy as busy:
        raise BrowserRefusedError(PROFILE_BUSY, CLOSING_BUSY.get(busy.by, NOT_ELA_S)) from None
    except BrowserStopped:
        raise BrowserRefusedError(
            STOPPED, "ELA was stopping: its own close ends the window it started"
        ) from None
    except BrowserError as failed:
        raise BrowserRefusedError(FAILED, f"the browser could not be ended: {failed}") from None
    if outcome is None:
        return BrowserClosedOut(outcome=NOTHING)
    await ela.audit.append(
        AuditEvent(
            id=AuditEventId(ela.ids.new_uuid()),
            created_at=ela.clock.now(),
            event_type=AuditEventType.BROWSER_CLOSE_ASKED,
            actor=identity.actor,
            summary=f"browser: told to quit ({outcome})",
            payload={"outcome": outcome, "held_by": look.holder},
        )
    )
    return BrowserClosedOut(outcome=outcome)


@router.get("/browser")
async def browser(ela: ElaDep) -> BrowserOut:
    """What the profile is now: usable or not and why, free or held and by whom, with a window
    or without, and what the browser says of itself."""
    return await browser_of(ela)


@router.post("/browser/window")
async def window(body: BrowserWindowIn, ela: ElaDep) -> BrowserWindowOut:
    """With a window, or without: for the steps that start from now, until ELA stops."""
    return window_turned(ela, body.shown)


@router.post("/browser/open")
async def opened(body: BrowserOpenIn, ela: ElaDep, identity: IdentityDep) -> BrowserOpenedOut:
    """Open the window where the user signs in by hand, on a declared site or on none."""
    return await window_opened(ela, identity, body.site)


@router.post("/browser/close")
async def closed(ela: ElaDep, identity: IdentityDep) -> BrowserClosedOut:
    """End the browser a hand may be on: told, waited for, killed only past the grace."""
    return await window_shut(ela, identity)
