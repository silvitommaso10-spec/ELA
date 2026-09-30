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
