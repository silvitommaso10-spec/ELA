"""How ``build`` wires the browser (M13.4 forms E, J, K; ADR 0052).

The sites of ``ELA_BROWSER_SITES`` reach the catalogue and the tools, and the placeholder of the
factories never does. The origin of a site is ``https`` — the one seam a test of the real browser
replaces, held here —; the browser of the Core is Playwright's, with the closed environment of a
command of the terminal, started nothing until a page is asked for; and the node builds neither
the tools nor the port (form A), though its process imports the module (C12).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from ela.composition import Ela, Settings, build
from ela.infrastructure.machine import PlaywrightBrowser
from ela.permissions import BROWSER_ACT, BROWSER_READ, UNDECLARED_SITES
from ela.testing.fakes import FakeBrowser
from ela.tools import BROWSER_TIMEOUT_SECONDS
from ela.tools.terminal import CLOSED_PATH, LANGUAGE
from tests.composition.support import create_schema, database_url, declare


async def test_the_declared_sites_reach_the_catalogue_and_the_placeholder_never_does(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path, ELA_BROWSER_SITES=json.dumps(["example.com"]))
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load())
    try:
        read = ela.capabilities.get(BROWSER_READ).scope
        act = ela.capabilities.get(BROWSER_ACT).scope
        browsing = ela.tools.get(BROWSER_READ)._browsing  # type: ignore[attr-defined]  # noqa: SLF001
    finally:
        await ela.aclose()

    assert read == act == ("example.com",)
    assert UNDECLARED_SITES[0] not in read
    assert browsing.sites == ("example.com",)
    assert browsing.origin("example.com") == "https://example.com", "the seam is https here"


async def test_no_site_declared_is_an_empty_scope_and_not_the_placeholder(ela: Ela) -> None:
    assert ela.capabilities.get(BROWSER_READ).scope == ()
    assert ela.capabilities.get(BROWSER_ACT).scope == ()


async def test_the_browser_of_the_core_is_playwright_with_the_closed_environment(
    ela: Ela,
) -> None:
    browser = ela.tools.get(BROWSER_ACT)._browser  # type: ignore[attr-defined]  # noqa: SLF001

    assert isinstance(browser, PlaywrightBrowser)
    assert browser._environment == {  # noqa: SLF001
        "PATH": CLOSED_PATH,
        "HOME": str(Path.home()),
        "TMPDIR": tempfile.gettempdir(),
        "LANG": LANGUAGE,
    }
    assert browser._pages == {}, "nothing starts until a page is asked for"  # noqa: SLF001
    assert browser._stopping is ela.stopping, "the stop signal of ADR 0038 §11"  # noqa: SLF001
    assert browser._launch()["handle_sigint"] is False  # noqa: SLF001 — M5-bis


async def test_a_page_handed_to_the_verifier_waits_the_tool_s_time_and_no_more(
    ela: Ela, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Form I: the adapter closes a kept page nobody looked at when the tool's own time is up —
    the composition's deadline, the tool's thirty seconds, and not a number of the adapter's."""
    browser = ela.tools.get(BROWSER_ACT)._browser  # type: ignore[attr-defined]  # noqa: SLF001
    waited: list[float] = []

    async def sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    await browser._kept()  # noqa: SLF001

    assert waited == [BROWSER_TIMEOUT_SECONDS]


async def test_the_same_browser_serves_the_tools_and_the_verifiers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    fake = FakeBrowser()
    ela = await build(Settings.load(), browser=fake)
    try:
        tools = {ela.tools.get(cid)._browser for cid in (BROWSER_READ, BROWSER_ACT)}  # type: ignore[attr-defined]  # noqa: SLF001
        verifiers = {
            ela.verifiers.get(cid)._browser
            for cid in (BROWSER_READ, BROWSER_ACT)  # type: ignore[attr-defined]  # noqa: SLF001
        }
    finally:
        await ela.aclose()

    assert tools == verifiers == {fake}


async def test_a_closing_that_passed_its_limit_is_said_where_ela_s_close_says_its_kill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """M13.9d, decision 80: the two browsers are given ELA's one limit, and what a closing of
    theirs that passed it killed is written by ``said`` — the standard error of ``ela serve`` —,
    in the form of the line of ELA's close and with its phrase, :data:`KILLED`."""
    from ela.api import server
    from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS, KILLED, killed_at_a_closing

    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    lines: list[str] = []
    names = ("node", "Google Chrome for Testing", "Google Chrome for Testing")
    ela = await build(Settings.load(), said=lines.append)
    try:
        empty = ela.tools.get(BROWSER_ACT)._browser  # type: ignore[attr-defined]  # noqa: SLF001
        for browser in (empty, ela.accounts):
            assert browser._limit == BROWSER_CLOSE_GRACE_SECONDS  # type: ignore[attr-defined]  # noqa: SLF001
            browser._told(names)  # type: ignore[attr-defined]  # noqa: SLF001
    finally:
        await ela.aclose()

    assert lines == [killed_at_a_closing(names)] * 2
    assert lines[0] == (
        f"ela: a browser of a step did not close within {BROWSER_CLOSE_GRACE_SECONDS} s: "
        "ELA killed what it had started — 2 Google Chrome for Testing, 1 node"
    )
    assert KILLED in server.killed(names)


async def test_downloads_not_forgotten_are_said_where_a_kill_is_said(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """M13.13c, decision 112: before a launch of the browser of the profile, downloads that could
    not be forgotten are said by ``said`` — the standard error of ``ela serve`` —, with the type of
    what stopped it and never a path, and the launch goes on."""
    from ela.composition.root import history_kept

    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    lines: list[str] = []
    ela = await build(Settings.load(), said=lines.append)
    try:
        ela.accounts._unforgotten("OperationalError")  # type: ignore[attr-defined]  # noqa: SLF001
    finally:
        await ela.aclose()

    assert lines == [history_kept("OperationalError")]
    assert lines[0] == (
        "ela: the downloads the browser of the profile remembers were not forgotten before a "
        "launch (OperationalError): the launch goes on"
    )


async def test_with_nobody_to_say_it_to_a_kill_is_said_nowhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``build`` with no ``said`` — every caller but ``ela serve`` —: the browsers are told, and
    nothing is written, and nothing raises."""
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load())
    try:
        ela.tools.get(BROWSER_ACT)._browser._told(("node",))  # type: ignore[attr-defined]  # noqa: SLF001
    finally:
        await ela.aclose()


async def test_with_nobody_to_say_it_downloads_not_forgotten_are_said_nowhere(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """M13.13c: ``build`` with no ``said`` — every caller but ``ela serve`` —: the browser of the
    profile is told why the downloads were not forgotten, and nothing is written, and nothing
    raises."""
    declare(monkeypatch, tmp_path)
    await create_schema(database_url(tmp_path))
    ela = await build(Settings.load())
    try:
        ela.accounts._unforgotten("OperationalError")  # type: ignore[attr-defined]  # noqa: SLF001
    finally:
        await ela.aclose()

    assert "not forgotten" not in capsys.readouterr().err
