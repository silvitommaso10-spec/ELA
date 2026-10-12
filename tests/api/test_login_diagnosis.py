"""What a login that did not work leaves to read, and where (M13.9, decision 106).

The proof of 2026-10-12 ended on ``browser.expect_missing``, and nobody could say what the site
had answered. Now the step says three things that are true of the page as the tool left it —
where it had ended, the status of its document, whether the password field of the plan was
still there —, **in its result and nowhere else**: the result is the user's own content coming
back to the user, and the audit never carries it; a failure's sentence does go to the audit,
where the path of a page never goes (ADR 0052 §12).

One ELA on its real database, a login asked, approved, made and looked at, with the browser of
the profile a fake whose page ends where the test says.
"""

from __future__ import annotations

import json
import stat
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.composition import Ela, Settings, build
from ela.ports import Field, Secret
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePage, FakePower, FakeVault
from tests.api.support import AUTHORIZED, BASE, queued
from tests.api.test_login_surfaces import ENTRY, plan
from tests.composition.support import create_schema, database_url, declare

ENDED = "accedi-rifiutato"
"""A path the plan does not name: found in the audit, it would have come from the page."""
FORM = {
    "#user": Field("text", "username", "post"),
    "#word": Field("password", "current-password", "post"),
    "#go": Field("submit", "", "post"),
}


@pytest.fixture
async def ela(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Ela]:
    program = tmp_path / "bw"
    program.write_bytes(b"\xcf\xfa\xed\xfe a native program")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    declare(
        monkeypatch,
        tmp_path,
        ELA_BROWSER_SITES=json.dumps(["posta.example"]),
        ELA_VAULT_PROGRAM=str(program),
    )
    await create_schema(database_url(tmp_path))
    vault = FakeVault([ENTRY])
    refused = FakePage(
        fields=dict(FORM),
        shown=False,
        landed=f"https://posta.example/{ENDED}?why=bad&user=mario#form",
        landed_status=200,
    )
    built = await build(
        Settings.load(),
        power=FakePower(),
        browser=FakeBrowser(),
        accounts=FakeAccountBrowser(refused),
        vault=vault,
    )
    assert await built.vault.open(Secret(vault.key)) is None
    try:
        yield built
    finally:
        await built.aclose()


@pytest.fixture
async def client(ela: Ela) -> AsyncIterator[AsyncClient]:
    app = create_app(ela)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url=BASE, headers=AUTHORIZED) as http,
    ):
        yield http


async def test_a_login_that_did_not_work_says_what_the_page_was_in_its_result_and_not_in_the_audit(
    client: AsyncClient,
) -> None:
    task = await queued(client, plan(), privacy="TRUSTED")
    assert (await client.post(f"/tasks/{task}/run")).json()["outcome"] == "waiting_approval"
    (asked,) = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]
    approved = await client.post(f"/tasks/{task}/approve", json={"approval_id": asked["id"]})
    assert approved.status_code == 200, approved.text

    ran = (await client.post(f"/tasks/{task}/run")).json()
    results = (await client.get(f"/tasks/{task}/results")).json()
    audit = (await client.get("/audit", params={"task_id": task})).text

    assert ran["outcome"] == "failed" and "browser.expect_missing" in ran["reason"], ran
    (result,) = results
    assert result["status"] == "SUCCEEDED", "the tool did what it was asked: the look said no"
    assert result["output"]["ended_at"] == f"posta.example/{ENDED}"
    assert result["output"]["ended_status"] == 200
    assert result["output"]["password_field_still_there"] is True
    assert "why=bad" not in json.dumps(results), "the query of the address is in no result"
    assert "`ela task results`" in audit, "the audit says where to read it"
    assert ENDED not in audit and "ended_at" not in audit, "and holds nothing of it"
    assert ENDED not in ran["reason"]
