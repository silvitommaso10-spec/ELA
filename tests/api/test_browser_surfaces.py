"""A question about the browser, on the three surfaces that answer it (M13.4 form H; ADR 0052 §7).

**Every surface that offers a yes shows** what ``browser.act`` would do: the whole address, the
gestures one per line — each field with the value the plan would type, then the click — and the text
the page must show after it — the rule H of ADR 0045 §11, closed over the fields in
``test_answering_surfaces.py`` and walked here with a real question. **None of them can be rewritten
by what it shows**: an ESC in a value and a U+202E in the expected text reach the command line, the
Command Center and the companion as characters a reader sees. And a read that asks — a step that
wants the question — names no expected text, because it has none.

The browser is the fake of ``ela.testing``, injected in ``build()``: a question opens no page
(decision 5), and the real one is not needed to ask.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.cli.system import _questions
from ela.composition import Ela, Settings, build
from ela.testing.fakes import FakeBrowser, FakePower
from tests.api.support import BASE, queued
from tests.composition.support import create_schema, declare

ESC = "\x1b"
RLO = "‮"
LOOPBACK = "http://127.0.0.1"
ADDRESS = "https://httpbin.org/forms/post"


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["httpbin.org"]))
    return Settings.load()


@pytest.fixture
async def ela(settings: Settings) -> AsyncIterator[Ela]:
    await create_schema(settings.persistence.db_url)
    built = await build(settings, power=FakePower(), browser=FakeBrowser())
    try:
        yield built
    finally:
        await built.aclose()


def plan(capability: str, arguments: dict[str, Any], condition: str) -> dict[str, Any]:
    return {
        "goal": "usare il browser",
        "steps": [
            {
                "id": "b4c2d7e1-5a3f-4b69-8d20-0000000000aa",
                "goal": "usare il browser",
                "required_capabilities": [capability],
                "arguments": {"site": "httpbin.org", "path": "/forms/post", **arguments},
                "risk": "HIGH" if capability == "browser.act" else "LOW",
                "expected_result": "la pagina",
                "success_conditions": [condition],
                "requires_authorization": True,
            }
        ],
    }


ACT = plan(
    "browser.act",
    {
        "fill": [["input[name=custname]", f"rosso{ESC}[31m"]],
        "click": "form button",
        "expect_text": f"abc{RLO}def",
        "purpose": "la prova",
    },
    "browser.expect_visible",
)
READ = plan("browser.read", {"purpose": "la prova"}, "browser.text_matches")


async def question(client: AsyncClient, which: dict[str, Any]) -> dict[str, Any]:
    task = await queued(client, which, privacy="TRUSTED")
    await client.post(f"/tasks/{task}/run")
    (waiting,) = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]
    return dict(waiting)


async def test_the_command_line_shows_every_fact_of_an_action_and_obeys_none(
    client: AsyncClient,
) -> None:
    asked = await question(client, ACT)

    shown = _questions([asked])

    assert "address" in shown and ADDRESS in shown
    assert '"fills input[name=custname] with “rosso\\x1b[31m”", "clicks form button"' in shown
    assert "expects" in shown and "abc\\u202edef" in shown
    assert ESC not in shown and RLO not in shown


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


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_page_shows_every_fact_of_an_action_and_obeys_nothing_it_shows(
    client: AsyncClient, console: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    asked = await question(client, ACT)
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert "Indirizzo" in page and ADDRESS in page
    assert "Gesti" in page and "rosso\\x1b[31m" in page and "clicks form button" in page
    assert "Testo atteso" in page and "abc\\u202edef" in page
    assert ESC not in page and RLO not in page


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_read_that_asks_shows_its_address_and_no_expected_text(
    client: AsyncClient, console: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    """A read has no text to expect: the question carries none, and no surface names one."""
    asked = await question(client, READ)
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert asked["address"] == ADDRESS
    assert asked["gestures"] == []
    assert asked["expect"] == ""
    assert ADDRESS in page
    assert "Testo atteso" not in page
    assert "expects " not in _questions([asked])
