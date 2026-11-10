"""The question of a file from the browser, on the three surfaces that answer it (M13.13,
ADR 0066).

A download writes a file under the declared root; an upload gives a site one of the files there.
What the user must be able to read before saying yes is **which file** — resolved, with what
happens to it, as for ``fs.*`` — **and which site**, with what the yes does there; and, of a file
that leaves, **its size and its sha256 as they were when the question was asked**. The target of
the question stays the file, and the site, the sentence, the size and the fingerprint are four
fields of their own — ``site``, ``visits``, ``size``, ``digest`` —, shown by every surface that
offers a yes or the surface does not answer (ADR 0045 §11, closed over the fields in
``test_answering_surfaces.py`` and walked here with real questions).

They are the user's content, like the goal of a step: **under the ceiling**. And the sha256 is on
the surfaces and never in the sentence of the question, which is what enters the audit.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ela.api import create_app
from ela.cli.system import _questions
from ela.composition import Ela, Settings, build
from ela.ports import Field
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePage, FakePower
from ela.tools.browser_files import DOWNLOADS, LEAVES, UPLOADS, UPLOADS_AS_YOU
from tests.api.support import AUTHORIZED, BASE, queued
from tests.api.test_console import PHONE_PEER, TAILNET, code_for, opened
from tests.composition.support import create_schema, database_url, declare

LOOPBACK = "http://127.0.0.1"
GIVEN = b"il file della prova, con un testo neutro\n"
DIGEST = hashlib.sha256(GIVEN).hexdigest()
SITE = "carica.example"


def plan(capability: str, arguments: dict[str, Any], condition: str) -> dict[str, Any]:
    return {
        "goal": "portare un file",
        "steps": [
            {
                "id": "b4c2d7e1-5a3f-4b69-8d20-0000000000f1",
                "goal": "portare un file",
                "required_capabilities": [capability],
                "arguments": {**arguments, "purpose": "la prova"},
                "risk": "HIGH",
                "expected_result": "il file dov'era chiesto",
                "success_conditions": [condition],
                "requires_authorization": True,
            }
        ],
    }


def upload(capability: str = "browser.upload") -> dict[str, Any]:
    return plan(
        capability,
        {
            "site": SITE,
            "path": "/carica",
            "file": "ELA/da-caricare.txt",
            "file_field": "#file",
            "click": "#manda",
            "expect_text": "Ricevuto",
        },
        "browser.expect_visible",
    )


def download(capability: str = "browser.download") -> dict[str, Any]:
    return plan(
        capability,
        {"site": SITE, "path": "/file.bin", "file": "ELA/scaricato.bin", "overwrite": False},
        "browser.file_downloaded",
    )


@pytest.fixture
def browsers() -> tuple[FakeBrowser, FakeAccountBrowser]:
    """The two browsers of the ELA of these tests: what a test reads to know nothing started."""
    page = FakePage(fields={"#file": Field("file", "")}, download=GIVEN)
    return FakeBrowser(page), FakeAccountBrowser(page)


@pytest.fixture
async def ela(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    browsers: tuple[FakeBrowser, FakeAccountBrowser],
) -> AsyncIterator[Ela]:
    """An ELA with one declared site and one file under its declared root, on fake browsers."""
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps([SITE]))
    await create_schema(database_url(tmp_path))
    built = await build(
        Settings.load(), power=FakePower(), browser=browsers[0], accounts=browsers[1]
    )
    folder = tmp_path / "files" / "ELA"  # the root ``declare`` declared, and its scope
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "da-caricare.txt").write_bytes(GIVEN)
    try:
        yield built
    finally:
        await built.aclose()


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """The declared root, resolved as the tools resolve it."""
    return (tmp_path / "files").resolve()


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


@pytest.mark.parametrize(
    ("capability", "sentence"),
    [("browser.upload", UPLOADS), ("browser.upload_as_you", UPLOADS_AS_YOU)],
)
async def test_the_question_of_an_upload_names_the_file_the_site_the_size_and_the_fingerprint(
    client: AsyncClient, root: Path, capability: str, sentence: str
) -> None:
    asked = await question(client, upload(capability))
    resolved = str(root / "ELA" / "da-caricare.txt")

    assert asked["capability_id"] == capability
    assert (asked["target"], asked["label"], asked["does"]) == (resolved, "file", LEAVES)
    assert (asked["site"], asked["visits"]) == (SITE, sentence)
    assert (asked["size"], asked["digest"]) == (len(GIVEN), DIGEST)
    assert asked["address"] == f"https://{SITE}/carica" and asked["expect"] == "Ricevuto"
    assert asked["gestures"][0].startswith("gives #file the file")
    assert asked["gestures"][-1] == "clicks #manda"
    assert DIGEST not in asked["prompt"], "the sentence enters the audit: the fingerprint does not"


async def test_the_question_of_a_download_names_the_file_and_the_site_and_no_fingerprint(
    client: AsyncClient, root: Path
) -> None:
    asked = await question(client, download())
    resolved = str(root / "ELA" / "scaricato.bin")

    assert (asked["target"], asked["label"]) == (resolved, "file")
    assert "creates a new file" in asked["does"] and "download" in asked["does"]
    assert (asked["site"], asked["visits"]) == (SITE, DOWNLOADS)
    assert (asked["size"], asked["digest"]) == (None, ""), "nothing leaves: nothing to fingerprint"
    assert asked["address"] == f"https://{SITE}/file.bin"
    assert asked["gestures"] == ["goes to the address, which is the file"]


async def test_a_question_about_a_page_names_no_site_of_its_own_and_no_file(
    client: AsyncClient,
) -> None:
    """For every other browser call the site **is** the target: the four fields stay empty."""
    which = plan(
        "browser.act",
        {"site": SITE, "path": "/scrivi", "fill": [], "click": "#manda", "expect_text": "Mandato"},
        "browser.expect_visible",
    )

    asked = await question(client, which)

    assert (asked["target"], asked["label"]) == (SITE, "site")
    assert (asked["site"], asked["visits"], asked["size"], asked["digest"]) == ("", "", None, "")
    shown = _questions([asked])
    assert "sha256" not in shown and "on the site" not in shown and "size " not in shown


def row(shown: str, name: str) -> str | None:
    """The value of the row ``name`` of a question as the command line prints it, or ``None``."""
    found = re.search(rf"^{re.escape(name)} {{2,}}(.+)$", shown, re.MULTILINE)
    return None if found is None else found.group(1).strip()


async def test_the_command_line_shows_the_file_the_site_the_size_and_the_fingerprint(
    client: AsyncClient,
) -> None:
    shown = _questions([await question(client, upload())])

    assert "da-caricare.txt" in shown and LEAVES in shown
    assert row(shown, "site") == SITE, "the site has a row of its own, not a word of a sentence"
    assert row(shown, "on the site") == UPLOADS
    assert row(shown, "size") == f"{len(GIVEN)} bytes" and row(shown, "sha256") == DIGEST


async def test_the_command_line_shows_no_size_and_no_fingerprint_for_a_download(
    client: AsyncClient,
) -> None:
    shown = _questions([await question(client, download())])

    assert "scaricato.bin" in shown
    assert row(shown, "site") == SITE and row(shown, "on the site") == DOWNLOADS
    assert "sha256" not in shown and "size " not in shown


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_page_shows_the_file_the_site_the_size_and_the_fingerprint(
    client: AsyncClient, console: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    asked = await question(client, upload())
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert "da-caricare.txt" in page and "Il sito" in page and SITE in page
    assert "Sul sito" in page and "gives this site one file of yours" in page
    assert "Dimensione" in page and f"{len(GIVEN)} byte" in page
    assert "Impronta (sha256)" in page and DIGEST in page


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_a_page_shows_no_size_and_no_fingerprint_for_a_download(
    client: AsyncClient, console: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    asked = await question(client, download())
    browser = console if surface == "console" else phone

    page = (await browser.get(f"/{surface}/approval?id={asked['id']}")).text

    assert "scaricato.bin" in page and "Il sito" in page and "Sul sito" in page
    assert "Dimensione" not in page and "Impronta" not in page


@pytest.mark.parametrize("surface", ["console", "companion"])
async def test_the_file_and_its_fingerprint_are_the_user_s_content_and_stay_under_the_ceiling(
    client: AsyncClient, console_away: AsyncClient, phone: AsyncClient, surface: str
) -> None:
    """A task that must not leave the machine: the phone, and a console that is not at the Mac,
    are beyond its ceiling, and read neither the file, nor the site, nor the size, nor the
    fingerprint — as they read neither the goal nor the address."""
    asked = await question(client, upload(), privacy="LOCAL_ONLY")
    browser = console_away if surface == "console" else phone

    answered = await browser.get(f"/{surface}/approval?id={asked['id']}")
    page = answered.text

    assert answered.status_code == 200 and "browser.upload" in page, "the question's own page"
    assert "da-caricare.txt" not in page and SITE not in page
    assert "Il sito" not in page and "Sul sito" not in page
    assert "Dimensione" not in page and "Impronta" not in page and DIGEST not in page


async def test_the_console_at_the_mac_reads_the_file_of_a_task_that_stays_on_the_machine(
    client: AsyncClient, console: AsyncClient
) -> None:
    asked = await question(client, upload(), privacy="LOCAL_ONLY")

    page = (await console.get(f"/console/approval?id={asked['id']}")).text

    assert "da-caricare.txt" in page and SITE in page and DIGEST in page


# ----------------------------------------------------------------------------------------
# Outside the scope: the Guardian's, before any question and before any browser
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "which",
    [download(), download("browser.download_as_you"), upload(), upload("browser.upload_as_you")],
    ids=["download", "download_as_you", "upload", "upload_as_you"],
)
async def test_a_file_outside_the_scope_is_denied_before_any_question_and_no_browser_starts(
    client: AsyncClient,
    root: Path,
    browsers: tuple[FakeBrowser, FakeAccountBrowser],
    which: dict[str, Any],
) -> None:
    """The two criteria of the registration: a download outside the boundary is denied, not
    written and then deleted; a file outside the scope does not leave. The scope is the
    Guardian's, as for ``fs.*``: no question, no yes spent, no page."""
    (root / "fuori-dallo-scope").mkdir()
    (root / "fuori-dallo-scope" / "un-file.txt").write_bytes(GIVEN)
    which["steps"][0]["arguments"]["file"] = "fuori-dallo-scope/un-file.txt"
    which["steps"][0]["arguments"]["overwrite"] = True
    if which["steps"][0]["required_capabilities"][0].startswith("browser.upload"):
        del which["steps"][0]["arguments"]["overwrite"]
    task = await queued(client, which)

    ran = (await client.post(f"/tasks/{task}/run")).json()
    asked = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]

    assert ran["outcome"] == "denied", ran
    assert asked == [], "nobody is asked a yes for what the scope denies"
    for browser in browsers:
        assert browser.opened == [] and browser.given == [] and browser.downloads == []
    assert (root / "fuori-dallo-scope" / "un-file.txt").read_bytes() == GIVEN


async def test_a_site_nobody_declared_is_refused_by_the_tool_before_the_question(
    client: AsyncClient, browsers: tuple[FakeBrowser, FakeAccountBrowser]
) -> None:
    """Criterion 9. The scope of these capabilities is the file, so the Guardian does not look at
    the site: the tool does, before the question — no yes is spent, and the step says why."""
    which = upload()
    which["steps"][0]["arguments"]["site"] = "non-dichiarato.example"
    task = await queued(client, which)

    ran = (await client.post(f"/tasks/{task}/run")).json()
    asked = [one for one in (await client.get("/approvals")).json() if one["task_id"] == task]
    results = (await client.get(f"/tasks/{task}/results")).json()

    assert ran["outcome"] == "failed" and asked == []
    assert ran["task"]["end"]["reason_code"] == "browser.site_not_declared"
    assert results == [], "nothing ran: the step failed where its question would have been composed"
    assert browsers[0].opened == [] and browsers[0].given == []
