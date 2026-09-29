"""Nothing of a page or of a browser call's arguments enters the audit (M13.4 form L, criterion 10).

The site is a target, and it stays — the privacy choice of ADR 0011, made with open eyes. Everything
else a browser call carries is the user's or the world's: the path and its query, a selector, a
value the plan types, the text an action waits for, the text of the page. Each carries a marker
here, and the tasks go through the branches where a message would carry something — a success, an
element that is not there, an error page, a page that changed, a text that never appears — and then
**no event of the audit contains a marker**. The log is never redacted, so the proof is on what is
written.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.testing.fakes import FakeBrowser, FakePage
from tests.api.support import AUTHORIZED, BASE, queued
from tests.composition.support import create_schema, database_url, declare

PATH = "/percorso-7431?chiave=query-7431"
SELECTOR = "#selettore-7431"
VALUE = "valore-7431"
EXPECT = "atteso-7431"
PAGE = "pagina-7431"
MARKERS = ("percorso-7431", "query-7431", "selettore-7431", "valore-7431", "atteso-7431", PAGE)


def plan(capability: str, arguments: dict[str, Any], condition: str) -> dict[str, Any]:
    return {
        "goal": "usare il browser",
        "steps": [
            {
                "id": "b4c2d7e1-5a3f-4b69-8d20-000000000099",
                "goal": "una pagina",
                "required_capabilities": [capability],
                "arguments": {
                    "site": "example.com",
                    "path": PATH,
                    "purpose": "la prova",
                    **arguments,
                },
                "risk": "HIGH" if capability == "browser.act" else "LOW",
                "expected_result": "una pagina",
                "success_conditions": [condition],
                "requires_authorization": capability == "browser.act",
            }
        ],
    }


READ = plan("browser.read", {"selector": SELECTOR}, "browser.text_matches")
ACT = plan(
    "browser.act",
    {"fill": [[SELECTOR, VALUE]], "click": "button", "expect_text": EXPECT},
    "browser.expect_visible",
)


@pytest.fixture
async def world(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> AsyncIterator[tuple[AsyncClient, Ela, FakeBrowser]]:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["example.com"]))
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
            yield client, ela, browser
    finally:
        await ela.aclose()


async def ran(client: AsyncClient, which: dict[str, Any]) -> str:
    """Run a task to its end: an action is asked, approved and run again."""
    task_id = await queued(client, which)
    first = (await client.post(f"/tasks/{task_id}/run")).json()
    if first["outcome"] != "waiting_approval":
        return str(first["outcome"])
    (approval,) = (await client.get("/approvals")).json()
    await client.post(f"/tasks/{task_id}/approve", json={"approval_id": approval["id"]})
    return str((await client.post(f"/tasks/{task_id}/run")).json()["outcome"])


async def test_no_event_of_the_audit_holds_the_page_or_an_argument(
    world: tuple[AsyncClient, Ela, FakeBrowser],
) -> None:
    client, ela, browser = world
    pages = [
        (READ, FakePage(title=PAGE, texts={SELECTOR: PAGE}), "completed"),
        (READ, FakePage(texts={SELECTOR: PAGE}, changes_to={SELECTOR: PAGE + " dopo"}), "failed"),
        (READ, FakePage(status=404, texts={SELECTOR: PAGE}), "failed"),
        (ACT, FakePage(title=PAGE, texts={None: PAGE}, shown=True), "completed"),
        (ACT, FakePage(counts={SELECTOR: 0}), "failed"),
        (ACT, FakePage(shown=False, texts={None: PAGE}), "failed"),
    ]

    outcomes = []
    for which, page, _ in pages:
        browser.page = page
        outcomes.append(await ran(client, which))

    assert outcomes == [expected for _, _, expected in pages]
    written = "\n".join(event.model_dump_json() for event in await ela.audit.read())
    assert "example.com" in written, "the site is a target, and it stays"
    for marker in MARKERS:
        assert marker not in written, f"{marker} reached the audit"
