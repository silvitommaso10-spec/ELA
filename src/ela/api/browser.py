"""ELA's browser with the user's accounts, as the Core reaches it (M13.9, ADR 0063 §8; decisions
18, 34 and 35).

Three routes, the Core's. ``GET /browser`` says what the profile is: **looked at through its port
at every request, never remembered** — and never by opening the folder: this module is not handed
its path, and asks the port, which answers with facts (architecture rule 69). ``POST
/browser/window`` turns the user's switch: whether the browser of the next step has a window, a
state of a running ELA that is off at every start. ``POST /browser/open`` opens **the window where
the user signs in by hand**, on a declared site or on none.

**Of that window ELA reads nothing**: the port launches the binary alone and keeps the wait for
its end. What this module knows of it is that it was asked for.

**The audit**: an opening is written here, by the route that receives it, signed by who asked.
The end is written by who waits for the process — the user closes the window, or ELA stops, and no
route is asked.

The three functions under the routes are what a page calls too (architecture rule 55).
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter

from ela.api.deps import ElaDep, IdentityDep
from ela.api.errors import ApiError
from ela.api.schemas import (
    BrowserOpenedOut,
    BrowserOpenIn,
    BrowserOut,
    BrowserWindowIn,
    BrowserWindowOut,
)
from ela.api.security import Identity
from ela.composition import Ela
from ela.domain import AuditEvent, AuditEventId, AuditEventType, visible
from ela.ports import BrowserError, ProfileBusy
from ela.tools.account import PROFILE_BUSY, look_at
from ela.tools.browser import BROWSER_TIMEOUT_SECONDS, FAILED, https_origin

__all__ = [
    "FREE",
    "SITE_UNDECLARED",
    "BrowserRefusedError",
    "browser_of",
    "router",
    "window_opened",
    "window_turned",
]

router = APIRouter(tags=["browser"])

SITE_UNDECLARED: Final = "browser.site_undeclared"
"""A window asked on a site that is not one of ``ELA_BROWSER_SITES``. The one code of these
routes that is theirs and not the tools'."""
FREE: Final = "free"
PREFIX: Final = "browser."
READ: Final = frozenset({None, PROFILE_BUSY})
"""The looks after which the folder is read for what the browser says of itself: a profile a
browser can start on — free, or held."""


class BrowserRefusedError(ApiError):
    """The window was not opened: the tools' own code is the first word — what a step with the
    profile would be refused with before its question —, and the sentence after it is theirs."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


async def browser_of(ela: Ela) -> BrowserOut:
    """What the profile is now. The state is ``free``, who holds it — one of the port's three
    names —, or the tools' refusal without its prefix; ``linked`` and ``saved`` are what the
    browser says of itself, read again each time and ``None`` where nothing could be read."""
    look = await look_at(ela.accounts, BROWSER_TIMEOUT_SECONDS)
    linked: bool | None = None
    saved: int | None = None
    if look.code in READ:
        try:
            linked = await ela.accounts.linked()
        except BrowserError:
            linked = None
        try:
            saved = await ela.accounts.saved()
        except BrowserError:
            saved = None
    state = look.holder or (FREE if look.code is None else look.code.removeprefix(PREFIX))
    return BrowserOut(
        state=state,
        message=look.message,
        window=ela.window.shown,
        linked=linked,
        saved=saved,
        sites=ela.settings.browser.sites,
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
