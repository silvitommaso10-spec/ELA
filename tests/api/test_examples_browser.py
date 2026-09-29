"""The six plans of M13.4 are plans ELA runs, with the guide's sites (ADR 0052).

Sent byte for byte, like every example (``test_examples.py``), to an ELA whose ``ELA_BROWSER_SITES``
is the line ``GETTING_STARTED.md`` §20 tells the reader to write — read from the guide by the last
test. The browser is the fake of ``ela.testing``, set for each plan to what the real site would do:
the pages are real in the proof by hand, and the real browser is asserted on local pages
(``tests/infrastructure/machine/test_browser.py``). What is asserted here is ELA's answer to each
plan — the question, the refusals, the outcome — and that the plans are the ones the guide runs.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Settings, build
from ela.testing.fakes import FakeBrowser, FakePage
from tests.api.support import AUTHORIZED, BASE
from tests.composition.support import create_schema, database_url, declare

EXAMPLES = Path(__file__).resolve().parents[2] / "docs" / "examples"
GUIDE = EXAMPLES.parent / "GETTING_STARTED.md"
DECLARED = ["example.com", "httpbin.org"]
"""The line of the guide, step 2 of §20 — read from it by the last test of this file."""


def plan(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    return loaded


@pytest.fixture
async def world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[AsyncClient, FakeBrowser]]:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(DECLARED))
    await create_schema(database_url(tmp_path))
    browser = FakeBrowser()
    ela = await build(Settings.load(), browser=browser)
    app: FastAPI = create_app(ela)
    try:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED
            ) as client,
        ):
            yield client, browser
    finally:
        await ela.aclose()


async def run(client: AsyncClient, name: str) -> tuple[str, dict[str, Any]]:
    task_id = (await client.post("/tasks", json={"text": name})).json()["id"]
    planned = await client.post(
        f"/tasks/{task_id}/plan",
        content=(EXAMPLES / name).read_bytes(),
        headers={"Content-Type": "application/json"},
    )
    assert planned.status_code == 200, planned.text
    return task_id, (await client.post(f"/tasks/{task_id}/run")).json()


async def test_a_read_asks_nothing_and_reads_the_title(
    world: tuple[AsyncClient, FakeBrowser],
) -> None:
    client, browser = world
    browser.page = FakePage(
        title="Example Domain", texts={"body > p:first-of-type": "This domain is for use in…"}
    )

    _, ran = await run(client, "browser-read.json")

    assert ran["outcome"] == "completed", ran
    assert browser.opened == ["https://example.com/"]
    assert (await client.get("/approvals")).json() == []


async def test_a_site_nobody_declared_is_denied_before_a_browser_starts(
    world: tuple[AsyncClient, FakeBrowser],
) -> None:
    client, browser = world

    _, ran = await run(client, "browser-read-outside.json")

    assert ran["outcome"] == "denied", ran
    assert "example.org" in ran["reason"] and "not within scope" in ran["reason"]
    assert browser.opened == []


async def test_a_page_that_goes_elsewhere_fails_and_the_browser_does_not_follow(
    world: tuple[AsyncClient, FakeBrowser],
) -> None:
    client, browser = world
    browser.page = FakePage(status=None, left="https://example.org/")

    _, ran = await run(client, "browser-left-site.json")

    assert ran["outcome"] == "failed", ran
    assert ran["reason"].startswith(
        "browser.left_site: the page of httpbin.org went to https://example.org,"
    )


async def test_a_slow_page_is_a_read_like_any_other(world: tuple[AsyncClient, FakeBrowser]) -> None:
    client, browser = world

    _, ran = await run(client, "browser-read-slow.json")

    assert ran["outcome"] == "completed", ran
    assert browser.opened == ["https://httpbin.org/delay/8"]


async def test_an_action_asks_and_its_question_names_everything(
    world: tuple[AsyncClient, FakeBrowser],
) -> None:
    client, browser = world

    task_id, ran = await run(client, "browser-act.json")

    assert ran["outcome"] == "waiting_approval", ran
    assert browser.opened == [], "nothing is opened before the yes"
    (question,) = (await client.get("/approvals")).json()
    assert question["target"] == "httpbin.org" and question["label"] == "site"
    assert question["address"] == "https://httpbin.org/forms/post"
    assert question["gestures"] == [
        "fills input[name=custname] with “ELA prova 7431”",
        "clicks form button",
    ]
    assert question["expect"] == "ELA prova 7431"
    assert question["timeout_seconds"] == 30
    assert "not your account" in question["does"]
    assert "ELA prova 7431" not in question["prompt"], "the prompt enters the audit"
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": question["id"]})
    again = (await client.post(f"/tasks/{task_id}/run")).json()
    assert again["outcome"] == "completed", again
    assert browser.fills == [("input[name=custname]", "ELA prova 7431")]


async def test_a_button_that_is_not_there_gets_no_gesture_after_the_yes(
    world: tuple[AsyncClient, FakeBrowser],
) -> None:
    client, browser = world
    browser.page = FakePage(counts={"#non-esiste": 0})

    task_id, _ = await run(client, "browser-act-missing.json")
    (question,) = (await client.get("/approvals")).json()
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": question["id"]})
    ran = (await client.post(f"/tasks/{task_id}/run")).json()

    assert ran["outcome"] == "failed", ran
    assert ran["reason"] == (
        "browser.element_missing: gesture 2 of 2 names no element on the page of httpbin.org; "
        "no gesture was made"
    )
    assert browser.fills == [] and browser.clicks == []


def test_the_sites_of_the_plans_are_the_line_the_guide_tells_you_to_write() -> None:
    section = GUIDE.read_text(encoding="utf-8").split("## 20. Il browser", 1)[1]
    line = re.search(r"^ELA_BROWSER_SITES=(\[.*\])$", section, re.M)
    assert line is not None
    assert json.loads(line.group(1)) == DECLARED
    used = {
        plan(path.name)["steps"][0]["arguments"]["site"] for path in EXAMPLES.glob("browser-*.json")
    }
    assert used - set(DECLARED) == {"example.org"}, "the one site nobody declared, on purpose"
