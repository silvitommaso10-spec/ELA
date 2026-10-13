"""The routes of ELA's browser with the user's accounts (M13.9, ADR 0063 §8; decisions 18, 34
and 35).

``GET /browser`` says what the profile is — **looked at through its port at every request, never
remembered, and never by reading the folder**: usable or not and why, free or held and by whom,
with a window or without, linked to an account of the browser's maker or not.
``POST /browser/window`` turns the user's switch: a state of a running ELA, off at every start.
``POST /browser/open`` opens the window where the user signs in by hand, on a declared site or on
none — and writes who opened it. Its end is written by who waits for it.

The browser of the profile is the fake of ``ela.testing``: these are the routes, and what the
real binary does is the adapter's test.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.domain import ActorKind, AuditEvent, AuditEventType
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    SHUT_KILLED,
    SHUT_QUIT,
    SHUT_TOLD,
    BrowserFailed,
    BrowserStopped,
    BrowserUnsupported,
    ProfileBusy,
    ProfileUndeclared,
    ProfileUnsafe,
)
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower
from tests.api.support import AUTHORIZED, BASE
from tests.api.test_console import LOOPBACK, code_for, opened
from tests.composition.support import create_schema, database_url, declare

SITES = ["posta.example", "video.example"]
ROUTES = (
    ("GET", "/browser"),
    ("POST", "/browser/window"),
    ("POST", "/browser/open"),
    ("POST", "/browser/close"),
)
UNDECLARED = "no folder was declared for ELA's browser: write ELA_BROWSER_PROFILE_DIR"
UNSAFE = "the folder of ELA's browser is readable by others: 0755"


@dataclass(frozen=True)
class Browsed:
    """An ELA whose browser with the profile is a fake of the test's, its application, and the
    Core's client."""

    ela: Ela
    accounts: FakeAccountBrowser
    app: FastAPI
    client: AsyncClient

    async def events(self, kind: AuditEventType) -> list[AuditEvent]:
        return [event for event in await self.ela.audit.read() if event.event_type is kind]


@pytest.fixture
async def browsed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Browsed]:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(SITES))
    await create_schema(database_url(tmp_path))
    accounts = FakeAccountBrowser()
    ela = await build(Settings.load(), power=FakePower(), browser=FakeBrowser(), accounts=accounts)
    app = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield Browsed(ela, accounts, app, client)
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# The state, looked at
# ----------------------------------------------------------------------------------------


async def test_a_profile_nobody_holds_is_free_and_says_what_the_browser_says_of_itself(
    browsed: Browsed,
) -> None:
    answered = await browsed.client.get("/browser")

    assert answered.status_code == 200
    assert answered.json() == {
        "state": "free",
        "message": "",
        "window": False,
        "linked": False,
        "saved": 0,
        "profiles": 1,
        "sites": SITES,
    }


async def test_what_the_answer_may_carry_is_a_closed_set_of_fields(browsed: Browsed) -> None:
    """Nothing of the folder: not its path, not a file of it. A field added tomorrow is seen
    here."""
    said = (await browsed.client.get("/browser")).json()

    assert set(said) == {"state", "message", "window", "linked", "saved", "profiles", "sites"}
    assert str(browsed.ela.settings.persistence.db_url) not in json.dumps(said)


@pytest.mark.parametrize(
    ("raised", "state", "says"),
    [
        pytest.param(
            ProfileUndeclared(UNDECLARED), "profile_undeclared", UNDECLARED, id="no-folder"
        ),
        pytest.param(ProfileUnsafe(UNSAFE), "profile_unsafe", UNSAFE, id="an-unfit-folder"),
        pytest.param(
            BrowserUnsupported("Linux"), "unsupported_system", "this is Linux", id="linux"
        ),
        pytest.param(BrowserFailed("OSError"), "failed", "OSError", id="a-look-that-failed"),
    ],
)
async def test_a_profile_no_browser_can_start_on_says_why_and_reads_nothing_of_it(
    browsed: Browsed, raised: Exception, state: str, says: str
) -> None:
    """The state is the tools' own refusal, without its prefix — what a step would be told before
    its question — and the sentence is theirs. Where the folder cannot be used nothing is read
    from it: ``linked`` and ``saved`` are «not read», not «no» and «none»."""
    browsed.accounts.raising["occupied"] = raised
    browsed.accounts.raising["linked"] = AssertionError("the folder was read")
    browsed.accounts.raising["saved"] = AssertionError("the folder was read")

    said = (await browsed.client.get("/browser")).json()

    assert said["state"] == state and says in said["message"]
    assert said["linked"] is None and said["saved"] is None
    assert said["window"] is False and said["sites"] == SITES


async def test_a_browser_that_is_not_installed_says_the_command_that_installs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(SITES))
    await create_schema(database_url(tmp_path))
    ela = await build(
        Settings.load(),
        power=FakePower(),
        browser=FakeBrowser(),
        accounts=FakeAccountBrowser(installed=False),
    )
    app = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            said = (await client.get("/browser")).json()
    finally:
        await ela.aclose()

    assert said["state"] == "not_installed"
    assert "playwright install" in said["message"]
    assert said["linked"] is None and said["saved"] is None


@pytest.mark.parametrize(
    ("holder", "says"),
    [
        (PROFILE_STEP, "another step of ELA's is using it"),
        (PROFILE_WINDOW, "its window is open"),
        (PROFILE_PROCESS, "another process holds it"),
    ],
)
async def test_a_held_profile_says_who_holds_it_and_is_still_read(
    browsed: Browsed, holder: str, says: str
) -> None:
    browsed.accounts.holder = holder
    browsed.accounts.linked_answer, browsed.accounts.saved_answer = True, 2

    said = (await browsed.client.get("/browser")).json()

    assert said["state"] == holder and says in said["message"]
    assert (said["linked"], said["saved"]) == (True, 2), "a held folder is read all the same"


async def test_the_profile_is_looked_at_at_every_request(browsed: Browsed) -> None:
    """Derived, never remembered (decision 63 for ``linked``): what changed is in the next
    answer."""
    first = (await browsed.client.get("/browser")).json()
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.accounts.linked_answer = True
    second = (await browsed.client.get("/browser")).json()
    browsed.accounts.holder = None
    third = (await browsed.client.get("/browser")).json()

    assert [one["state"] for one in (first, second, third)] == ["free", "window", "free"]
    assert [one["linked"] for one in (first, second, third)] == [False, True, True]


async def test_a_fact_of_the_folder_that_cannot_be_read_is_not_read_and_the_state_stands(
    browsed: Browsed,
) -> None:
    """Between the look and the reading the folder may stop being readable: the state is what
    the look found, and the fact is «not read»."""
    browsed.accounts.raising["linked"] = BrowserFailed("PermissionError")
    browsed.accounts.raising["saved"] = ProfileUnsafe(UNSAFE)

    said = (await browsed.client.get("/browser")).json()

    assert said["state"] == "free"
    assert said["linked"] is None and said["saved"] is None


# ----------------------------------------------------------------------------------------
# With a window or without: the user's switch
# ----------------------------------------------------------------------------------------


async def test_the_switch_is_turned_by_the_route_and_read_back_by_the_state(
    browsed: Browsed,
) -> None:
    shown = await browsed.client.post("/browser/window", json={"shown": True})
    with_one = (await browsed.client.get("/browser")).json()
    hidden = await browsed.client.post("/browser/window", json={"shown": False})
    without = (await browsed.client.get("/browser")).json()

    assert (shown.status_code, shown.json()) == (200, {"shown": True})
    assert with_one["window"] is True
    assert (hidden.status_code, hidden.json()) == (200, {"shown": False})
    assert without["window"] is False
    assert browsed.ela.window.shown is False
    assert browsed.accounts.windows == [], "the switch opens nothing: it holds for the next step"


@pytest.mark.parametrize("body", [{}, {"shown": "sometimes"}, {"shown": True, "site": "x"}])
async def test_a_body_that_is_not_the_switch_turns_nothing(
    browsed: Browsed, body: dict[str, object]
) -> None:
    answered = await browsed.client.post("/browser/window", json=body)

    assert answered.status_code == 422
    assert browsed.ela.window.shown is False


# ----------------------------------------------------------------------------------------
# The window where the user signs in by hand
# ----------------------------------------------------------------------------------------


async def test_the_window_opens_on_no_site_and_who_opened_it_is_a_row_of_the_audit(
    browsed: Browsed,
) -> None:
    answered = await browsed.client.post("/browser/open", json={})

    assert (answered.status_code, answered.json()) == (200, {"site": None})
    assert browsed.accounts.windows == [None]
    (row,) = await browsed.events(AuditEventType.BROWSER_WINDOW_OPENED)
    assert row.actor.kind is ActorKind.USER
    assert row.task_id is None and row.capability_id is None
    assert dict(row.payload) == {"site": None}


async def test_the_window_opens_on_the_https_origin_of_a_declared_site(browsed: Browsed) -> None:
    answered = await browsed.client.post("/browser/open", json={"site": "posta.example"})

    assert (answered.status_code, answered.json()) == (200, {"site": "posta.example"})
    assert browsed.accounts.windows == ["https://posta.example/"]
    (row,) = await browsed.events(AuditEventType.BROWSER_WINDOW_OPENED)
    assert dict(row.payload) == {"site": "posta.example"}
    assert (await browsed.client.get("/browser")).json()["state"] == "window"


@pytest.mark.parametrize(
    "site", ["altrove.example", "posta.example/login", "https://posta.example"]
)
async def test_a_site_nobody_declared_opens_no_window(browsed: Browsed, site: str) -> None:
    """Inside the window the boundary of the sites is not there — they are the user's hands —,
    but where ELA opens it is a declared site or nowhere."""
    answered = await browsed.client.post("/browser/open", json={"site": site})

    assert answered.status_code == 409
    said = answered.json()["error"]
    assert said["code"] == "browser.refused"
    assert said["message"].startswith("browser.site_undeclared: ")
    assert "ELA_BROWSER_SITES" in said["message"]
    assert browsed.accounts.windows == []
    assert await browsed.events(AuditEventType.BROWSER_WINDOW_OPENED) == []


@pytest.mark.parametrize("body", [{"site": ""}, {"site": 7}, {"site": "posta.example", "x": 1}])
async def test_a_body_that_is_not_a_site_opens_no_window(
    browsed: Browsed, body: dict[str, object]
) -> None:
    answered = await browsed.client.post("/browser/open", json=body)

    assert answered.status_code == 422
    assert browsed.accounts.windows == []


@pytest.mark.parametrize("holder", [PROFILE_STEP, PROFILE_WINDOW, PROFILE_PROCESS])
async def test_a_held_profile_opens_no_second_window(browsed: Browsed, holder: str) -> None:
    """One process at a time on the profile (criterion 14): ELA launches nothing on a folder it
    found held — a second launch may kill the first."""
    browsed.accounts.holder = holder

    answered = await browsed.client.post("/browser/open", json={})

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith("browser.profile_busy: ")
    assert browsed.accounts.windows == []
    assert await browsed.events(AuditEventType.BROWSER_WINDOW_OPENED) == []


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (ProfileUndeclared(UNDECLARED), "browser.profile_undeclared"),
        (ProfileUnsafe(UNSAFE), "browser.profile_unsafe"),
        (BrowserUnsupported("Linux"), "browser.unsupported_system"),
        (BrowserFailed("OSError"), "browser.failed"),
    ],
)
async def test_a_profile_no_browser_can_start_on_opens_no_window_and_says_why(
    browsed: Browsed, raised: Exception, code: str
) -> None:
    browsed.accounts.raising["occupied"] = raised

    answered = await browsed.client.post("/browser/open", json={})

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith(f"{code}: ")
    assert browsed.accounts.windows == []


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (ProfileBusy(PROFILE_PROCESS), "browser.profile_busy"),
        (BrowserFailed("OSError"), "browser.failed"),
    ],
)
async def test_a_window_that_could_not_start_after_the_look_is_refused_and_not_written(
    browsed: Browsed, raised: Exception, code: str
) -> None:
    """Between the look and the launch the folder may become held, and a launch may fail: the
    refusal is the adapter's, and no opening is written for a window that is not there."""
    browsed.accounts.raising["window"] = raised

    answered = await browsed.client.post("/browser/open", json={"site": "posta.example"})

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith(f"{code}: ")
    assert await browsed.events(AuditEventType.BROWSER_WINDOW_OPENED) == []


# ----------------------------------------------------------------------------------------
# The profiles of the folder (decision 79), and the command that ends the window (decision 80)
# ----------------------------------------------------------------------------------------


async def test_the_state_says_how_many_profiles_of_the_browser_the_folder_holds(
    browsed: Browsed,
) -> None:
    """A second profile added from inside the window is one ELA neither prepares nor uses: the
    state says there is more than one, and what was saved in all of them is counted."""
    browsed.accounts.profiles_answer = 2
    browsed.accounts.saved_answer = 5

    said = (await browsed.client.get("/browser")).json()

    assert (said["profiles"], said["saved"]) == (2, 5)

    browsed.accounts.raising["profiles"] = BrowserFailed("PermissionError")
    assert (await browsed.client.get("/browser")).json()["profiles"] is None, "not read, not one"


@pytest.mark.parametrize("holder", [PROFILE_WINDOW, PROFILE_PROCESS])
@pytest.mark.parametrize("outcome", [SHUT_QUIT, SHUT_KILLED, SHUT_TOLD])
async def test_closing_tells_the_browser_a_hand_may_be_on_and_who_asked_is_a_row_of_the_audit(
    browsed: Browsed, holder: str, outcome: str
) -> None:
    """Written whenever a process was told — also when ELA cannot say what became of it —, with
    what held the profile when the command looked: the window ELA started, or a process it did
    not. For that one this is the only row there is."""
    browsed.accounts.holder = holder
    browsed.accounts.shut_answer = outcome

    answered = await browsed.client.post("/browser/close")

    assert (answered.status_code, answered.json()) == (200, {"outcome": outcome})
    assert len(browsed.accounts.shuts) == 1
    (row,) = await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED)
    assert row.actor.kind is ActorKind.USER
    assert row.task_id is None and row.capability_id is None
    assert dict(row.payload) == {"outcome": outcome, "held_by": holder}


async def test_a_browser_that_ended_frees_the_profile_for_the_state(browsed: Browsed) -> None:
    browsed.accounts.holder = PROFILE_WINDOW

    await browsed.client.post("/browser/close")

    assert (await browsed.client.get("/browser")).json()["state"] == "free"


async def test_a_binary_that_is_not_installed_any_more_does_not_stop_the_window_being_ended(
    browsed: Browsed,
) -> None:
    """The binary may go while a window of it runs — the lock's revision changed under a running
    ELA —: nothing can be started, and what is running can still be ended."""
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.accounts.installed_answer = False

    answered = await browsed.client.post("/browser/close")

    assert (answered.status_code, answered.json()) == (200, {"outcome": SHUT_QUIT})


async def test_a_stop_that_arrives_while_the_browser_is_ended_is_said_as_the_stop(
    browsed: Browsed,
) -> None:
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.accounts.raising["shut"] = BrowserStopped("ELA is stopping")

    answered = await browsed.client.post("/browser/close")

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith("browser.stopped: ")


async def test_the_grace_of_the_command_is_the_grace_of_ela_s_close(
    browsed: Browsed, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Told, waited for, and killed only once the grace is over — the same seconds ELA's own
    close gives a browser. The adapter is handed the wait, never the number."""
    import asyncio

    from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS

    browsed.accounts.holder = PROFILE_WINDOW
    await browsed.client.post("/browser/close")
    (grace,) = browsed.accounts.shuts
    waited: list[float] = []
    real = asyncio.sleep

    async def counted(seconds: float, *more: object) -> None:
        waited.append(seconds)
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", counted)
    await grace()

    assert waited == [BROWSER_CLOSE_GRACE_SECONDS]


async def test_closing_with_nothing_open_says_so_and_writes_nothing(browsed: Browsed) -> None:
    answered = await browsed.client.post("/browser/close")

    assert (answered.status_code, answered.json()) == (200, {"outcome": "nothing"})
    assert await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []


async def test_closing_does_not_end_a_step_of_ela_s(browsed: Browsed) -> None:
    browsed.accounts.holder = PROFILE_STEP

    answered = await browsed.client.post("/browser/close")

    assert answered.status_code == 409
    said = answered.json()["error"]["message"]
    assert said.startswith("browser.profile_busy: ") and "ela task stop" in said
    assert browsed.accounts.shuts == []
    assert await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []


async def test_closing_signals_nothing_that_is_not_ela_s_browser(browsed: Browsed) -> None:
    browsed.accounts.holder = PROFILE_PROCESS
    browsed.accounts.raising["shut"] = ProfileBusy(PROFILE_PROCESS)

    answered = await browsed.client.post("/browser/close")

    assert answered.status_code == 409
    said = answered.json()["error"]["message"]
    assert said.startswith("browser.profile_busy: ") and "not ELA's browser" in said
    assert await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []
    assert (await browsed.client.get("/browser")).json()["state"] == "process"


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (ProfileUndeclared(UNDECLARED), "browser.profile_undeclared"),
        (ProfileUnsafe(UNSAFE), "browser.profile_unsafe"),
        (BrowserUnsupported("Linux"), "browser.unsupported_system"),
        (BrowserFailed("OSError"), "browser.failed"),
        (BrowserStopped("ELA is stopping"), "browser.stopped"),
    ],
)
async def test_closing_on_a_profile_that_cannot_be_looked_at_says_why(
    browsed: Browsed, raised: Exception, code: str
) -> None:
    """The look every route of the profile begins with, and its codes: nothing is told on a
    folder ELA cannot say anything of."""
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.accounts.raising["occupied"] = raised

    answered = await browsed.client.post("/browser/close")

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith(f"{code}: ")
    assert browsed.accounts.shuts == []
    assert await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []


async def test_a_browser_that_could_not_be_ended_after_the_look_is_refused_and_not_written(
    browsed: Browsed,
) -> None:
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.accounts.raising["shut"] = BrowserFailed("OSError")

    answered = await browsed.client.post("/browser/close")

    assert answered.status_code == 409
    assert answered.json()["error"]["message"].startswith("browser.failed: ")
    assert await browsed.events(AuditEventType.BROWSER_CLOSE_ASKED) == []


# ----------------------------------------------------------------------------------------
# Whose routes these are
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_without_the_core_s_token_nothing_of_the_browser_answers(
    browsed: Browsed, method: str, path: str
) -> None:
    browsed.accounts.holder = PROFILE_WINDOW  # something to end, so that ending it would show
    async with AsyncClient(transport=ASGITransport(app=browsed.app), base_url=BASE) as nobody:
        answered = await nobody.request(method, path, json={})

    assert answered.status_code == 401
    assert browsed.accounts.windows == [] and browsed.ela.window.shown is False
    assert browsed.accounts.shuts == []


@pytest.mark.parametrize(("method", "path"), ROUTES)
async def test_a_console_s_cookie_is_not_the_core_s_token(
    browsed: Browsed, method: str, path: str
) -> None:
    """The routes are the Core's: a console reaches the browser through its own page."""
    async with opened(browsed.app, LOOPBACK) as browser:
        enrolled = await browser.post(
            "/console/enroll",
            data={"code": await code_for(browsed.client), "name": "MacBook", "os": "MACOS"},
            headers={"Origin": LOOPBACK},
        )
        assert enrolled.status_code == 303

        answered = await browser.request(method, path, json={"shown": True})

    assert answered.status_code == 401
    assert browsed.accounts.windows == [] and browsed.ela.window.shown is False


# ----------------------------------------------------------------------------------------
# A login always has a window (decision 143 of the review of 2026-10-13)
# ----------------------------------------------------------------------------------------


async def test_the_state_says_whether_a_login_could_have_its_window_now(browsed: Browsed) -> None:
    """Decision 143: ``browser.login`` starts with a window whatever the switch says, and does
    not start without one. The state says whether one can be had now — asked of the port at
    every request, like every other fact —, beside the switch and not in its place."""
    with_one = (await browsed.client.get("/browser")).json()
    browsed.accounts.screen = False
    without = (await browsed.client.get("/browser")).json()

    assert with_one["login_window"] is True and without["login_window"] is False
    assert with_one["window"] is False and without["window"] is False, "the switch is another"


async def test_a_window_nobody_could_ask_about_is_not_read_and_the_state_stands(
    browsed: Browsed,
) -> None:
    browsed.accounts.raising["can_show"] = BrowserFailed("the session could not be read")

    said = (await browsed.client.get("/browser")).json()

    assert said["state"] == "free" and said["login_window"] is None


async def test_a_profile_no_browser_can_start_on_is_not_asked_about_a_window(
    browsed: Browsed,
) -> None:
    browsed.accounts.raising["occupied"] = ProfileUndeclared(UNDECLARED)
    browsed.accounts.raising["can_show"] = AssertionError("nobody may ask")

    said = (await browsed.client.get("/browser")).json()

    assert said["state"] == "profile_undeclared" and said["login_window"] is None
