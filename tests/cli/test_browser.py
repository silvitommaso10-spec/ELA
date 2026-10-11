"""``ela browser``: the state of ELA's browser with your accounts, its window, and the window
where you sign in by hand (M13.9, ADR 0063 §8; decisions 18 and 34).

``status`` prints what the profile is, looked at again at every call — and «not read» where the
folder could not be read, which is neither «no» nor «none». ``window show`` and ``window hide``
turn the user's switch and open nothing. ``open`` opens the window on a declared site or on none,
and a refusal is the tools' own, with exit 1.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from ela.api import create_app
from ela.cli import client
from ela.cli.app import app as ela_app
from ela.cli.errors import OK, REFUSED
from ela.composition import Ela, Settings, build
from ela.ports import PROFILE_WINDOW, ProfileUndeclared
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower
from tests.cli.support import LoopTransport
from tests.composition.support import create_schema, database_url, declare

SITES = ["posta.example", "video.example"]
UNDECLARED = "no folder was declared for ELA's browser: write ELA_BROWSER_PROFILE_DIR"


@dataclass(frozen=True)
class Browsed:
    """The command line pointed at an ELA whose browser with the profile is the test's."""

    ela: Ela
    accounts: FakeAccountBrowser
    transport: LoopTransport

    async def __call__(self, *arguments: str) -> Result:
        return await asyncio.to_thread(CliRunner().invoke, ela_app, list(arguments))

    def sent(self, path: str) -> list[dict[str, object]]:
        """The bodies of the requests the command made to ``path``."""
        return [
            json.loads(request.content)
            for request in self.transport.requests
            if request.url.path == path
        ]


@pytest.fixture
async def browsed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Browsed]:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(SITES))
    await create_schema(database_url(tmp_path))
    accounts = FakeAccountBrowser()
    ela = await build(Settings.load(), power=FakePower(), browser=FakeBrowser(), accounts=accounts)
    application = create_app(ela)
    transport = LoopTransport(application, asyncio.get_running_loop())
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with application.router.lifespan_context(application):
            yield Browsed(ela, accounts, transport)
    finally:
        await ela.aclose()


def row(output: str, name: str) -> str:
    """What the row ``name`` of ``ela browser status`` says."""
    (line,) = [one for one in output.splitlines() if one.startswith(name)]
    return line.removeprefix(name).strip()


# ----------------------------------------------------------------------------------------
# status
# ----------------------------------------------------------------------------------------


async def test_status_of_a_free_profile_says_every_fact_and_no_sentence(browsed: Browsed) -> None:
    result = await browsed("browser", "status")

    assert result.exit_code == OK, result.output
    said = result.output
    assert row(said, "state") == "free"
    assert row(said, "window") == "hidden"
    assert row(said, "linked to an account") == "no"
    assert row(said, "saved passwords") == "0"
    assert row(said, "sites") == "posta.example, video.example"
    assert len(said.strip().splitlines()) == 5, "a free profile has nothing to be told"


async def test_status_of_a_profile_that_cannot_be_used_says_why_and_reads_nothing(
    browsed: Browsed,
) -> None:
    """«Not read» is not «no»: where the folder could not be looked at, nobody knows whether the
    browser is linked to an account."""
    browsed.accounts.raising["occupied"] = ProfileUndeclared(UNDECLARED)

    result = await browsed("browser", "status")

    assert result.exit_code == OK, result.output
    assert row(result.output, "state") == "profile_undeclared"
    assert row(result.output, "linked to an account") == "not read"
    assert row(result.output, "saved passwords") == "not read"
    assert result.output.strip().splitlines()[-1] == UNDECLARED


async def test_status_says_a_linked_browser_and_a_shown_window(browsed: Browsed) -> None:
    browsed.accounts.linked_answer, browsed.accounts.saved_answer = True, 3
    browsed.accounts.holder = PROFILE_WINDOW
    browsed.ela.window.show()

    result = await browsed("browser", "status")

    assert row(result.output, "state") == "window"
    assert row(result.output, "window") == "shown"
    assert row(result.output, "linked to an account") == "yes"
    assert row(result.output, "saved passwords") == "3"
    assert "its window is open" in result.output.strip().splitlines()[-1]


async def test_status_as_json_is_the_api_s_own_answer(browsed: Browsed) -> None:
    result = await browsed("browser", "status", "--json")

    assert json.loads(result.output) == {
        "state": "free",
        "message": "",
        "window": False,
        "linked": False,
        "saved": 0,
        "sites": SITES,
    }


async def test_status_with_no_declared_site_says_so_with_a_dash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES="[]")
    await create_schema(database_url(tmp_path))
    ela = await build(
        Settings.load(), power=FakePower(), browser=FakeBrowser(), accounts=FakeAccountBrowser()
    )
    application = create_app(ela)
    transport = LoopTransport(application, asyncio.get_running_loop())
    monkeypatch.setattr(
        client, "connect", lambda: client.open_client(ela.settings.api, transport=transport)
    )
    try:
        async with application.router.lifespan_context(application):
            result = await asyncio.to_thread(CliRunner().invoke, ela_app, ["browser", "status"])
    finally:
        await ela.aclose()

    assert result.exit_code == OK, result.output
    assert row(result.output, "sites") == "—"


# ----------------------------------------------------------------------------------------
# window show, window hide
# ----------------------------------------------------------------------------------------


async def test_window_show_and_hide_turn_the_switch_and_open_nothing(browsed: Browsed) -> None:
    shown = await browsed("browser", "window", "show")
    while_shown = browsed.ela.window.shown
    hidden = await browsed("browser", "window", "hide")

    assert shown.exit_code == OK and "with a window from now" in shown.output
    assert while_shown is True
    assert hidden.exit_code == OK and "with no window from now" in hidden.output
    assert browsed.ela.window.shown is False
    assert browsed.sent("/browser/window") == [{"shown": True}, {"shown": False}]
    assert browsed.accounts.windows == []


# ----------------------------------------------------------------------------------------
# open
# ----------------------------------------------------------------------------------------


async def test_open_with_no_site_opens_the_window_and_says_what_ela_does_not_do(
    browsed: Browsed,
) -> None:
    result = await browsed("browser", "open")

    assert result.exit_code == OK, result.output
    assert result.output.strip() == (
        "the window is open: sign in, then quit that browser (Cmd-Q — closing the window alone "
        "leaves it running). ELA reads nothing of it"
    )
    assert browsed.sent("/browser/open") == [{}]
    assert browsed.accounts.windows == [None]


async def test_open_on_a_declared_site_names_it(browsed: Browsed) -> None:
    result = await browsed("browser", "open", "posta.example")

    assert result.exit_code == OK, result.output
    assert "the window is open on posta.example: " in result.output
    assert browsed.sent("/browser/open") == [{"site": "posta.example"}]
    assert browsed.accounts.windows == ["https://posta.example/"]


async def test_open_on_a_site_nobody_declared_exits_1_with_the_reason(browsed: Browsed) -> None:
    result = await browsed("browser", "open", "altrove.example")

    assert result.exit_code == REFUSED
    assert "browser.site_undeclared" in result.output
    assert browsed.accounts.windows == []


async def test_open_on_a_held_profile_exits_1_and_opens_nothing(browsed: Browsed) -> None:
    browsed.accounts.holder = PROFILE_WINDOW

    result = await browsed("browser", "open")

    assert result.exit_code == REFUSED
    assert "browser.profile_busy" in result.output and "its window is open" in result.output
    assert browsed.accounts.windows == []
