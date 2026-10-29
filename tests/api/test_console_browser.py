"""The sixth view of the Command Center: ``/console/browser`` (M13.9, ADR 0063 §10; decisions 12,
16e and 38).

«Il browser di ELA»: what the profile and the vault are, as ``GET /browser`` and ``GET /vault``
say them; the window that is turned on and off; the window where the user signs in by hand, opened
on a declared site or on none; and the vault that is closed. **It does not open it**: a key is not
pasted into a page.

What changes something is done from the Mac — a console under a narrower ceiling reads the states
and does one thing, the one that takes away: it closes the vault. Forms ``POST`` with the origin
check of the forms of a yes, and no JavaScript.
"""

from __future__ import annotations

import html
import json
import re
import shlex
import stat
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.composition.system import own_command
from ela.domain import ActorKind, AuditEvent, AuditEventType, TaskId
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_TASK,
    PROFILE_WINDOW,
    VAULT_LOCKED,
    BrowserFailed,
    ProfileUndeclared,
    Secret,
    WaitingPage,
)
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower, FakeVault
from tests.api.support import AUTHORIZED, BASE, outside_the_block
from tests.api.test_console import LOOPBACK, PHONE_PEER, TAILNET, code_for, opened
from tests.composition.support import create_schema, database_url, declare

SITES = ["posta.example", "video.example"]
UNDECLARED = "no folder was declared for the browser of ELA: write ELA_BROWSER_PROFILE_DIR"
WINDOW, OPEN, LOCK = "/console/browser/window", "/console/browser/open", "/console/browser/lock"
CLOSE = "/console/browser/close"


@dataclass(frozen=True)
class Viewed:
    """An ELA whose browser with the profile and whose vault are the test's, its application and
    the Core's client."""

    ela: Ela
    accounts: FakeAccountBrowser
    vault: FakeVault
    app: FastAPI
    client: AsyncClient
    program: Path

    async def events(self, kind: AuditEventType) -> list[AuditEvent]:
        return [event for event in await self.ela.audit.read() if event.event_type is kind]

    @asynccontextmanager
    async def console(self, *, away: bool = False) -> AsyncIterator[AsyncClient]:
        """A browser enrolled as a console: at the Mac, or on the tailnet under ``TRUSTED``."""
        base, peer = (TAILNET, PHONE_PEER) if away else (LOOPBACK, ("127.0.0.1", 123))
        async with opened(self.app, base, peer) as browser:
            entered = await browser.post(
                "/console/enroll",
                data={"code": await code_for(self.client), "name": "MacBook", "os": "MACOS"},
                headers={"Origin": base},
            )
            assert entered.status_code == 303, entered.text
            browser.headers["Origin"] = base
            yield browser

    async def page(self, console: AsyncClient) -> str:
        answered = await console.get("/console/browser")
        assert answered.status_code == 200, answered.text
        return outside_the_block(answered.text)


@pytest.fixture
async def viewed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Viewed]:
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    declare(
        monkeypatch,
        tmp_path,
        ELA_BROWSER_SITES=json.dumps(SITES),
        ELA_VAULT_PROGRAM=str(program),
    )
    await create_schema(database_url(tmp_path))
    accounts, vault = FakeAccountBrowser(), FakeVault(state=VAULT_LOCKED)
    ela = await build(
        Settings.load(),
        power=FakePower(),
        browser=FakeBrowser(),
        accounts=accounts,
        vault=vault,
    )
    app = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield Viewed(ela, accounts, vault, app, client, program)
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# What the view says
# ----------------------------------------------------------------------------------------


async def test_the_view_says_what_the_profile_and_the_vault_are_and_offers_its_forms(
    viewed: Viewed,
) -> None:
    async with viewed.console() as console:
        page = await viewed.page(console)

    assert "Il browser di ELA" in page and "Il vault" in page
    assert "free" in page and "senza finestra" in page
    assert "Collegato a un account" in page and "Password salvate" in page
    assert "locked" in page
    line = f"{viewed.program} unlock --raw | {shlex.quote(str(own_command()))} vault open"
    assert page.count(line) == 2, "in the vault's sentence, and once more alone: to copy whole"
    assert f'action="{WINDOW}"' in page and 'name="shown" value="1"' in page
    assert f'action="{OPEN}"' in page
    for site in ("", *SITES):
        assert f'name="site" value="{site}"' in page
    assert f'action="{LOCK}"' not in page, "a locked vault has nothing to close"
    assert f'action="{CLOSE}"' not in page, "and a free profile no browser to end"
    assert "Profili nella cartella" not in page, "one profile is nothing to be told"
    assert "<script" not in page


async def test_the_view_never_offers_to_open_the_vault(viewed: Viewed) -> None:
    """A key is not pasted into a page: no field could carry one, and no form reaches the route
    that takes it."""
    async with viewed.console() as console:
        locked = await viewed.page(console)
        assert await viewed.ela.vault.open(Secret(viewed.vault.key)) is None
        unlocked = await viewed.page(console)

    for page in (locked, unlocked):
        assert 'type="password"' not in page and 'name="key"' not in page
        assert "/vault/session" not in page
    assert viewed.vault.key not in unlocked


async def test_every_page_of_the_console_links_the_view(viewed: Viewed) -> None:
    async with viewed.console() as console:
        home = (await console.get("/console/")).text
        here = await viewed.page(console)

    assert 'href="/console/browser"' in home and 'href="/console/browser"' in here


async def test_a_profile_no_browser_can_start_on_says_why_and_offers_no_window(
    viewed: Viewed,
) -> None:
    viewed.accounts.raising["occupied"] = ProfileUndeclared(UNDECLARED)

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert "profile_undeclared" in page and UNDECLARED in page
    assert page.count("non letto") == 3, (
        "neither fact of the folder was read — not «no», not «0» —, nor whether a login could "
        "have its window"
    )
    assert f'action="{OPEN}"' not in page, "a window that can only be refused is not offered"
    assert f'action="{WINDOW}"' in page, "the switch is the user's whatever the profile is"


async def test_a_held_profile_says_who_holds_it_and_offers_no_second_window(
    viewed: Viewed,
) -> None:
    viewed.accounts.holder = PROFILE_WINDOW
    viewed.accounts.linked_answer, viewed.accounts.saved_answer = True, 2

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert "window" in page and "its window is open" in page
    assert f'action="{OPEN}"' not in page
    assert ">sì<" in page and ">2<" in page


@pytest.mark.parametrize("holder", [PROFILE_WINDOW, PROFILE_PROCESS])
async def test_a_profile_a_hand_may_be_on_offers_the_button_that_ends_the_browser(
    viewed: Viewed, holder: str
) -> None:
    """The red button of the window closes the window and leaves the browser running, and the
    state still says it is open: the page says so, beside the button that ends it (decision
    80)."""
    viewed.accounts.holder = holder

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert f'action="{CLOSE}"' in page and 'name="browser" value="close"' in page
    assert "pulsante rosso" in page


async def test_a_step_of_ela_s_offers_no_button_to_end_it(viewed: Viewed) -> None:
    viewed.accounts.holder = PROFILE_STEP

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert "step" in page and f'action="{CLOSE}"' not in page


async def test_a_page_a_task_keeps_says_which_task_until_when_and_offers_no_button_to_end_it(
    viewed: Viewed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M13.10, ADR 0065 §3 (decision 26): the console says which task keeps a page between two
    of its steps, until when, and the command that ends it — the task's stop, not the button
    that ends the browser where a hand may be."""
    task = TaskId(UUID(int=7))
    until = datetime(2026, 10, 14, 18, 30, tzinfo=UTC)

    async def waiting() -> tuple[WaitingPage, ...]:
        return (WaitingPage(task=task, profile=True, until=until),)

    monkeypatch.setattr(viewed.ela.pages, "waiting", waiting)
    viewed.accounts.holder = PROFILE_TASK

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert ">task<" in page and "Una pagina aspetta" in page
    assert f"il task {task}, sul browser con i tuoi account, fino a 2026-10-14T18:30" in page
    assert f"ela task cancel {task}" in page
    assert f'action="{CLOSE}"' not in page


async def test_the_view_says_when_the_folder_holds_more_than_one_profile(viewed: Viewed) -> None:
    viewed.accounts.profiles_answer = 2

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert "Profili nella cartella" in page and ">2<" in page
    assert "ELA ne prepara e ne usa uno solo" in page


# ----------------------------------------------------------------------------------------
# What the view does, from the Mac
# ----------------------------------------------------------------------------------------


async def test_the_switch_is_turned_from_the_page_and_the_page_says_it(viewed: Viewed) -> None:
    async with viewed.console() as console:
        shown = await console.post(WINDOW, data={"shown": "1"})
        while_shown = viewed.ela.window.shown
        with_one = await viewed.page(console)
        hidden = await console.post(WINDOW, data={"shown": "0"})
        without = await viewed.page(console)

    assert shown.status_code == 303 and shown.headers["location"] == "/console/browser"
    assert while_shown is True
    assert "con finestra" in with_one and 'name="shown" value="0"' in with_one
    assert hidden.status_code == 303 and viewed.ela.window.shown is False
    assert "senza finestra" in without and 'name="shown" value="1"' in without
    assert viewed.accounts.windows == [], "the switch opens nothing"


@pytest.mark.parametrize(
    ("site", "address"), [("posta.example", "https://posta.example/"), ("", None)]
)
async def test_the_window_is_opened_from_the_page_and_who_opened_it_is_written(
    viewed: Viewed, site: str, address: str | None
) -> None:
    async with viewed.console() as console:
        answered = await console.post(OPEN, data={"site": site})
        after = await viewed.page(console)

    assert answered.status_code == 303 and answered.headers["location"] == "/console/browser"
    assert viewed.accounts.windows == [address]
    (row,) = await viewed.events(AuditEventType.BROWSER_WINDOW_OPENED)
    assert row.actor.kind is ActorKind.USER
    assert dict(row.payload) == {"site": site or None}
    assert "window" in after and f'action="{OPEN}"' not in after


@pytest.mark.parametrize("holder", [PROFILE_WINDOW, PROFILE_PROCESS])
async def test_the_browser_is_ended_from_the_page_and_who_asked_is_written(
    viewed: Viewed, holder: str
) -> None:
    viewed.accounts.holder = holder

    async with viewed.console() as console:
        answered = await console.post(CLOSE, data={"browser": "close"})
        after = await viewed.page(console)

    assert answered.status_code == 303 and answered.headers["location"] == "/console/browser"
    assert len(viewed.accounts.shuts) == 1
    (row,) = await viewed.events(AuditEventType.BROWSER_CLOSE_ASKED)
    assert row.actor.kind is ActorKind.USER, "signed by the console that asked"
    assert "free" in after and f'action="{CLOSE}"' not in after


async def test_a_step_of_ela_s_is_not_ended_from_the_page_and_the_page_says_why(
    viewed: Viewed,
) -> None:
    viewed.accounts.holder = PROFILE_STEP

    async with viewed.console() as console:
        refused = await console.post(CLOSE, data={"browser": "close"})

    assert refused.status_code == 409
    assert "browser.profile_busy" in refused.text
    assert viewed.accounts.shuts == []


async def test_a_site_nobody_declared_opens_nothing_and_the_page_says_why(
    viewed: Viewed,
) -> None:
    async with viewed.console() as console:
        refused = await console.post(OPEN, data={"site": "altrove.example"})

    assert refused.status_code == 409
    assert "browser.site_undeclared" in refused.text
    assert viewed.accounts.windows == []


async def test_the_vault_is_closed_from_the_page_and_who_closed_it_is_written(
    viewed: Viewed,
) -> None:
    assert await viewed.ela.vault.open(Secret(viewed.vault.key)) is None
    viewed.vault.calls.clear()

    async with viewed.console() as console:
        before = await viewed.page(console)
        closed = await console.post(LOCK, data={"vault": "lock"})
        after = await viewed.page(console)

    assert "unlocked" in before and f'action="{LOCK}"' in before
    assert closed.status_code == 303 and closed.headers["location"] == "/console/browser"
    assert "lock" in viewed.vault.calls and viewed.ela.vault.forgets_at is None
    (row,) = await viewed.events(AuditEventType.VAULT_CLOSED)
    assert row.actor.kind is ActorKind.USER, "signed by the console that asked"
    assert f'action="{LOCK}"' not in after


@pytest.mark.parametrize(
    ("path", "fields"),
    [
        (WINDOW, {}),
        (WINDOW, {"shown": "sometimes"}),
        (OPEN, {}),
        (LOCK, {}),
        (LOCK, {"vault": "open"}),
        (CLOSE, {}),
        (CLOSE, {"browser": "open"}),
    ],
)
async def test_a_form_that_does_not_say_what_it_asks_changes_nothing(
    viewed: Viewed, path: str, fields: dict[str, str]
) -> None:
    """Each form of the view carries a field that names what it asks; a ``POST`` without it is
    not a request to guess."""
    assert await viewed.ela.vault.open(Secret(viewed.vault.key)) is None
    viewed.vault.calls.clear()
    if path == CLOSE:
        viewed.accounts.holder = PROFILE_WINDOW  # something to end, so that ending it would show

    async with viewed.console() as console:
        answered = await console.post(path, data=fields)

    assert answered.status_code == 422
    assert viewed.ela.window.shown is False and viewed.accounts.windows == []
    assert "lock" not in viewed.vault.calls and viewed.accounts.shuts == []


@pytest.mark.parametrize(
    ("path", "fields"),
    [
        (WINDOW, {"shown": "1"}),
        (OPEN, {"site": ""}),
        (LOCK, {"vault": "lock"}),
        (CLOSE, {"browser": "close"}),
    ],
)
async def test_a_post_without_the_origin_of_ela_is_refused(
    viewed: Viewed, path: str, fields: dict[str, str]
) -> None:
    if path == CLOSE:
        viewed.accounts.holder = PROFILE_WINDOW  # something to end, so that ending it would show
    async with viewed.console() as console:
        del console.headers["Origin"]
        refused = await console.post(path, data=fields)

    assert refused.status_code == 403
    assert viewed.ela.window.shown is False and viewed.accounts.windows == []
    assert "lock" not in viewed.vault.calls and viewed.accounts.shuts == []


# ----------------------------------------------------------------------------------------
# Under a narrower ceiling: the states, and the one thing that takes away
# ----------------------------------------------------------------------------------------


async def test_away_from_the_mac_the_view_says_the_states_and_keeps_the_rest_on_the_mac(
    viewed: Viewed,
) -> None:
    """The sites, the sentence of an unfit folder and the line with the vault's program are the
    Mac's: a console on the tailnet reads the words of the states and nothing that names a path
    or a site."""
    viewed.accounts.raising["occupied"] = ProfileUndeclared(UNDECLARED)

    async with viewed.console(away=True) as console:
        page = await viewed.page(console)

    assert "profile_undeclared" in page and "locked" in page
    assert UNDECLARED not in page
    assert str(viewed.program) not in page
    for site in SITES:
        assert site not in page
    assert f'action="{WINDOW}"' not in page and f'action="{OPEN}"' not in page
    assert "si usano dal Mac" in page


async def test_away_from_the_mac_a_free_profile_offers_no_window_and_names_no_site(
    viewed: Viewed,
) -> None:
    """The profile is free, and at the Mac the form would be there: away it is not, whatever the
    profile — and the sites it would have offered are not on the page."""
    async with viewed.console() as at_the_mac, viewed.console(away=True) as away:
        here = await viewed.page(at_the_mac)
        there = await viewed.page(away)

    assert f'action="{OPEN}"' in here and SITES[0] in here
    assert "free" in there
    assert f'action="{OPEN}"' not in there and f'action="{WINDOW}"' not in there
    for site in SITES:
        assert site not in there


async def test_away_from_the_mac_the_browser_of_the_mac_is_not_ended(viewed: Viewed) -> None:
    """What changes something on the Mac's screen is done at the Mac (decision 12): a window a
    hand may be typing in is not ended from a phone."""
    viewed.accounts.holder = PROFILE_WINDOW

    async with viewed.console(away=True) as console:
        page = await viewed.page(console)
        refused = await console.post(CLOSE, data={"browser": "close"})

    assert f'action="{CLOSE}"' not in page
    assert refused.status_code == 409 and "si usano dal Mac" in refused.text
    assert viewed.accounts.shuts == []
    assert await viewed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []


async def test_away_from_the_mac_nothing_is_turned_and_nothing_is_opened(viewed: Viewed) -> None:
    async with viewed.console(away=True) as console:
        turned = await console.post(WINDOW, data={"shown": "1"})
        opened_ = await console.post(OPEN, data={"site": ""})

    assert turned.status_code == 409 and opened_.status_code == 409
    assert "si usano dal Mac" in turned.text
    assert viewed.ela.window.shown is False and viewed.accounts.windows == []
    assert await viewed.events(AuditEventType.BROWSER_WINDOW_OPENED) == []


async def test_away_from_the_mac_the_vault_is_still_closed(viewed: Viewed) -> None:
    """Closing takes away, it does not widen: like the revocation of a policy, under any
    ceiling."""
    assert await viewed.ela.vault.open(Secret(viewed.vault.key)) is None
    viewed.vault.calls.clear()

    async with viewed.console(away=True) as console:
        before = await viewed.page(console)
        closed = await console.post(LOCK, data={"vault": "lock"})

    assert f'action="{LOCK}"' in before
    assert closed.status_code == 303
    assert "lock" in viewed.vault.calls and viewed.ela.vault.forgets_at is None


# ----------------------------------------------------------------------------------------
# A login always has a window: the view says it (decision 150 of the review of 2026-10-13)
# ----------------------------------------------------------------------------------------

A_LOGIN = "Un login"


def said_of_a_login(page: str) -> str:
    """What the view says in the row of a login, as a reader sees it."""
    plain = html.unescape(page)
    assert plain.count(A_LOGIN) == 1, "one row, beside the one of the switch"
    after = plain.split(A_LOGIN, 1)[1]
    return re.sub(r"<[^>]+>", " ", after.split("Collegato a un account", 1)[0]).strip()


async def test_the_view_says_that_a_login_has_a_window_whatever_the_switch_says(
    viewed: Viewed,
) -> None:
    """The view said «senza finestra» while a login would have one: the same fact ``GET
    /browser`` carries is a row of its own, beside the switch, and does not move with it."""
    async with viewed.console() as console:
        hidden = await viewed.page(console)
        viewed.ela.window.show()
        shown = await viewed.page(console)

    assert "senza finestra" in hidden and "senza finestra" not in shown
    for page in (hidden, shown):
        assert said_of_a_login(page) == "con finestra, qualunque cosa dica l'interruttore"


async def test_the_view_says_when_a_login_could_not_have_its_window(viewed: Viewed) -> None:
    viewed.accounts.screen = False

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert said_of_a_login(page) == (
        "con finestra — ed ELA non ha potuto dire di poterne aprire una adesso: un login non "
        "partirebbe"
    )


async def test_the_view_says_not_read_where_the_window_could_not_be_asked_about(
    viewed: Viewed,
) -> None:
    viewed.accounts.raising["can_show"] = BrowserFailed("the session could not be read")

    async with viewed.console() as console:
        page = await viewed.page(console)

    assert said_of_a_login(page) == "con finestra — se una si possa aprire: non letto"
