"""The question of a login, on the three surfaces that answer it (M13.9, ADR 0063 §9; decisions
15d and 31).

A ``browser.login`` asks to type a password of the user's vault into a page. What the user must
be able to read before saying yes is **which entry** — by its name — and **whose** — the
username, masked —: the question carries them in two fields of their own, ``entry`` and
``username``, and every surface that offers a yes shows both or does not answer (ADR 0045 §11,
closed over the fields in ``test_answering_surfaces.py`` and walked here with a real question).

They are the user's content, like the goal of a step: **under the ceiling**. And what no surface
ever receives: the whole username, the password, the id of the entry — the first two do not leave
the vault's adapter before a yes, and the third is the plan's.
"""

from __future__ import annotations

import json
import stat
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.cli.system import _questions
from ela.composition import Ela, Settings, build
from ela.ports import Secret
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakePower,
    FakeVault,
    FakeVaultEntry,
)
from tests.api.support import AUTHORIZED, BASE, queued
from tests.api.test_console import PHONE_PEER, TAILNET, code_for, opened
from tests.composition.support import create_schema, database_url, declare

LOOPBACK = "http://127.0.0.1"
WORD = "-".join(("SENTINEL", "of", "the", "word", "of", "the", "entry"))
USERNAME = "mario.rossi@example.com"
MASKED = "m…@example.com"
ENTRY = FakeVaultEntry(
    "11111111-2222-4333-8444-555555555555",
    "La posta di casa",
    ("https://posta.example/login",),
    USERNAME,
    WORD,
    MASKED,
)
NAMELESS = FakeVaultEntry(
    "22222222-3333-4444-8555-666666666666",
    "Il forum",
    ("https://forum.example/",),
    "",
    WORD,
    "",
)
WORD_FIELD = "_".join(("password", "field"))


def plan(site: str = "posta.example") -> dict[str, Any]:
    return {
        "goal": "entrare nella posta",
        "steps": [
            {
                "id": "b4c2d7e1-5a3f-4b69-8d20-0000000000ab",
                "goal": "entrare nella posta",
                "required_capabilities": ["browser.login"],
                "arguments": {
                    "site": site,
                    "path": "/login",
                    "username_field": "#user",
                    WORD_FIELD: "#word",
                    "click": "#go",
                    "expect_text": "Benvenuto",
                    "purpose": "la prova",
                },
                "risk": "HIGH",
                "expected_result": "la posta aperta",
                "success_conditions": ["browser.expect_visible"],
                "requires_authorization": True,
            }
        ],
    }


@pytest.fixture
async def ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Ela]:
    """An ELA whose vault is open on two entries, with the browser of the profile a fake."""
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    declare(
        monkeypatch,
        tmp_path,
        ELA_BROWSER_SITES=json.dumps(["posta.example", "forum.example"]),
        ELA_VAULT_PROGRAM=str(program),
    )
    await create_schema(database_url(tmp_path))
    vault = FakeVault([ENTRY, NAMELESS])
    built = await build(
        Settings.load(),
        power=FakePower(),
        browser=FakeBrowser(),
        accounts=FakeAccountBrowser(),
        vault=vault,
    )
    assert await built.vault.open(Secret(vault.key)) is None
    try:
        yield built
    finally:
        await built.aclose()


@pytest.fixture
def app(ela: Ela) -> FastAPI:
    return create_app(ela)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as http,
    ):
        yield http


async def question(
    client: AsyncClient, which: dict[str, Any], *, privacy: str = "TRUSTED"
) -> dict[str, Any]:
    task = await queued(client, which, privacy=privacy)
    ran = await client.post(f"/tasks/{task}/run")
    assert ran.json()["outcome"] == "waiting_approval", ran.text
    (waiting,) = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]
    return dict(waiting)


@pytest.fixture
async def console(app: FastAPI, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    minted = await client.post("/nodes/enrollments", json={"privacy": "TRUSTED", "role": "CONSOLE"})
    async with AsyncClient(
        transport=ASGITransport(app=app, client=("127.0.0.1", 123)), base_url=LOOPBACK
    ) as browser:
        entered = await browser.post(
            "/console/enroll",
            data={"code": minted.json()["code"], "name": "MacBook", "os": "MACOS"},
            headers={"Origin": LOOPBACK},
        )
        assert entered.status_code == 303, entered.text
        yield browser


@pytest.fixture
async def phone(app: FastAPI, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    minted = await client.post(
        "/nodes/enrollments", json={"privacy": "TRUSTED", "role": "COMPANION"}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as browser:
        entered = await browser.post(
            "/companion/enroll",
            data={"code": minted.json()["code"], "name": "iPhone", "os": "IOS"},
            headers={"Origin": BASE},
        )
        assert entered.status_code == 303, entered.text
        yield browser


def never_shown(text: str) -> None:
    assert WORD not in text, "the password"
    assert USERNAME not in text, "the whole username"
    assert ENTRY.id not in text, "the id of the entry"


async def test_the_question_of_a_login_carries_the_entry_and_the_masked_username(
    client: AsyncClient,
) -> None:
    asked = await question(client, plan())

    assert asked["capability_id"] == "browser.login"
    assert (asked["entry"], asked["username"]) == ("La posta di casa", MASKED)
    assert asked["gestures"] == [
        "types the username of that entry into #user",
        "types its password into #word",
        "clicks #go",
    ], "the gestures name the fields: which entry is a fact of its own"
    never_shown(json.dumps(asked, ensure_ascii=False))


async def test_an_entry_with_no_username_leaves_that_fact_absent_and_not_wrong(
    client: AsyncClient,
) -> None:
    asked = await question(client, plan("forum.example"))

    assert (asked["entry"], asked["username"]) == ("Il forum", "")
    assert "username" not in _questions([asked]).replace("types the username", "")


async def test_a_question_that_is_not_a_login_names_no_entry(client: AsyncClient) -> None:
    which = plan()
    step = which["steps"][0]
    step["required_capabilities"] = ["browser.act_as_you"]
    step["arguments"] = {
        "site": "posta.example",
        "path": "/scrivi",
        "fill": [],
        "click": "#manda",
        "expect_text": "Mandato",
        "purpose": "la prova",
    }

    asked = await question(client, which)

    assert (asked["entry"], asked["username"]) == ("", "")
    shown = _questions([asked])
    assert "entry " not in shown and "username " not in shown


async def test_the_command_line_shows_the_entry_and_the_masked_username(
    client: AsyncClient,
) -> None:
    shown = _questions([await question(client, plan())])

    assert "entry" in shown and "La posta di casa" in shown
    assert "username" in shown and MASKED in shown
    never_shown(shown)


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_page_shows_the_entry_and_the_masked_username(
    client: AsyncClient, console: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    asked = await question(client, plan())
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert "La voce" in page and "La posta di casa" in page
    assert "Nome utente" in page and MASKED in page
    never_shown(page)


@pytest.fixture
async def console_away(app: FastAPI, client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A console that is not at the Mac: on the tailnet, with the level ``TRUSTED``."""
    async with opened(app, TAILNET, PHONE_PEER) as browser:
        entered = await browser.post(
            "/console/enroll",
            data={"code": await code_for(client), "name": "MacBook", "os": "MACOS"},
            headers={"Origin": TAILNET},
        )
        assert entered.status_code == 303, entered.text
        yield browser


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_the_entry_is_the_user_s_content_and_stays_under_the_ceiling(
    client: AsyncClient, console_away: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    """A task that must not leave the machine: the phone, and a console that is not at the Mac,
    are beyond its ceiling, and read neither the name of the entry nor the masked username — as
    they read neither the goal nor the address."""
    asked = await question(client, plan(), privacy="LOCAL_ONLY")
    browser = console_away if surface == "console" else phone

    answered = await browser.get(f"/{surface}/approval?id={asked['id']}")
    page = answered.text

    assert answered.status_code == 200 and "browser.login" in page, "the question's own page"
    assert "La voce" not in page and "Nome utente" not in page
    assert "La posta di casa" not in page and MASKED not in page
    never_shown(page)


async def test_the_console_at_the_mac_reads_the_entry_of_a_task_that_stays_on_the_machine(
    client: AsyncClient, console: AsyncClient
) -> None:
    """The other side of the ceiling: at the Mac a console reads what stays on the Mac."""
    asked = await question(client, plan(), privacy="LOCAL_ONLY")

    page = (await console.get(f"/console/approval?id={asked['id']}")).text

    assert "La voce" in page and "La posta di casa" in page and MASKED in page
