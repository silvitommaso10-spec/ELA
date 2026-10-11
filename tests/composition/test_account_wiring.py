"""The browser with the user's accounts in the composition root (M13.9, ADR 0063).

``build`` binds the port to its adapter — Chrome for Testing on the folder of
``ELA_BROWSER_PROFILE_DIR``, with the closed environment of the empty browser —, and holds the
switch that says whether that browser has a window: the user's, off at every start. **Every
browser ``build`` makes is brought to rest by the close**, within one grace, and that is a closed
world. And nothing that makes the browser's driver write what it is told — ``DEBUG``,
``PWDEBUG`` — is left in ELA's environment.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import platform
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from ela.composition import Ela, Settings, build
from ela.composition.root import BROWSER_CLOSE_GRACE_SECONDS
from ela.composition.system import WindowSwitch, without_node_variables
from ela.infrastructure.machine import AccountChrome, PlaywrightBrowser
from ela.ports import Browser
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower, FakeStop
from ela.tools.terminal import CLOSED_PATH, LANGUAGE
from tests.composition.support import create_schema, database_url, declare
from tests.composition.test_node_variables import driver_of_this_process, environment_names

PROFILE = "ELA_BROWSER_PROFILE_DIR"


async def built(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, extra: dict[str, str], **named: Any
) -> Ela:
    declare(monkeypatch, tmp_path, **extra)
    await create_schema(database_url(tmp_path))
    return await build(Settings.load(), power=FakePower(), **named)


# ----------------------------------------------------------------------------------------
# The adapter, and what it is given
# ----------------------------------------------------------------------------------------


async def test_without_a_declared_folder_the_browser_is_built_on_none(ela: Ela) -> None:
    """ELA starts the same: the capabilities are there, and every call says which line to
    write. Nothing is started, and no folder is invented."""
    adapter = ela.accounts

    assert isinstance(adapter, AccountChrome)
    assert adapter._profile is None
    assert not adapter._drivers


async def test_the_profile_s_browser_is_chrome_on_the_declared_folder_with_the_closed_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile = tmp_path / "state" / "browser-profile"
    ela = await built(monkeypatch, tmp_path, {PROFILE: str(profile)})
    try:
        adapter = ela.accounts

        assert isinstance(adapter, AccountChrome)
        assert adapter._profile == profile
        assert adapter._environment == {
            "PATH": CLOSED_PATH,
            "HOME": str(Path.home()),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": LANGUAGE,
        }
        assert adapter._system == platform.system()
        assert adapter._stopping is ela.stopping
        empty = ela.browser
        assert isinstance(empty, PlaywrightBrowser) and not isinstance(empty, AccountChrome)
        assert adapter._environment == empty._environment
        assert adapter._kept.__qualname__ == empty._kept.__qualname__, "the same deadline of a page"
        assert not profile.exists(), "building ELA makes no folder: the first use does"
    finally:
        await ela.aclose()


# ----------------------------------------------------------------------------------------
# With a window or without: the user's switch
# ----------------------------------------------------------------------------------------


def test_the_switch_is_off_until_somebody_turns_it_on() -> None:
    switch = WindowSwitch()
    assert switch.shown is False

    switch.show()
    assert switch.shown is True
    switch.show()
    assert switch.shown is True

    switch.hide()
    assert switch.shown is False


async def test_the_adapter_asks_the_switch_at_every_launch_and_every_start_is_without_a_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 34: a state of a running ELA, which a route of the user's changes and no tool
    does; it holds from then on, and comes back to «without a window» at every start."""
    ela = await built(monkeypatch, tmp_path, {})
    try:
        adapter = ela.accounts
        assert isinstance(adapter, AccountChrome)
        assert ela.window.shown is False and adapter._launch()["headless"] is True

        ela.window.show()
        assert adapter._launch()["headless"] is False

        ela.window.hide()
        assert adapter._launch()["headless"] is True
        ela.window.show()
    finally:
        await ela.aclose()

    again = await build(Settings.load(), power=FakePower())
    try:
        assert again.window.shown is False
    finally:
        await again.aclose()


# ----------------------------------------------------------------------------------------
# Every browser build makes is brought to rest by the close (criterion 30)
# ----------------------------------------------------------------------------------------


class Graced(FakeAccountBrowser):
    """A browser that waits the grace it is given, and says so."""

    def __init__(self, name: str, order: list[str]) -> None:
        super().__init__()
        self._name = name
        self._order = order

    async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
        self._order.append(f"{self._name} settling")
        await super().settle(grace)
        await grace()
        self._order.append(f"{self._name} settled")
        return (self._name,)


def resting(ela: Ela) -> dict[str, Any]:
    """Every field of ELA that holds a browser — whatever implements the port: what the close
    must bring to rest."""
    return {
        field.name: getattr(ela, field.name)
        for field in dataclasses.fields(ela)
        if isinstance(getattr(ela, field.name), Browser)
    }


def unsettled(ela: Ela) -> list[str]:
    """The browsers ELA holds that its close did not ask to settle."""
    return sorted(name for name, browser in resting(ela).items() if not browser.settled)


async def test_the_close_brings_to_rest_every_browser_ela_was_built_with(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The closed world: whatever field of ``Ela`` can be settled, is. A browser added to the
    composition tomorrow and not to the close is found here by its name."""
    empty, accounts = FakeBrowser(), FakeAccountBrowser()
    ela = await built(monkeypatch, tmp_path, {}, browser=empty, accounts=accounts)
    assert resting(ela) == {"browser": empty, "accounts": accounts}
    assert unsettled(ela) == ["accounts", "browser"]

    await ela.aclose()

    assert unsettled(ela) == []


async def test_a_browser_built_and_not_waited_for_is_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The negative case: one browser more on ``Ela`` than its close knows of."""

    @dataclasses.dataclass(frozen=True, slots=True)
    class Wider(Ela):
        third: FakeBrowser = dataclasses.field(default_factory=FakeBrowser)

    ela = await built(
        monkeypatch, tmp_path, {}, browser=FakeBrowser(), accounts=FakeAccountBrowser()
    )
    wider = Wider(**{f.name: getattr(ela, f.name) for f in dataclasses.fields(ela)})

    await wider.aclose()

    assert unsettled(wider) == ["third"]


async def test_the_two_browsers_are_settled_together_within_one_grace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Decision 59: the window is waited for «within the same grace» as the pages. Both are
    asked before either has finished, the grace is counted once, and who closes ELA is told once
    of everything that was killed."""
    from ela.composition import root

    order: list[str] = []
    counted: list[int] = []
    over = root._over

    async def one_grace(seconds: int, hurry: object) -> bool:
        counted.append(seconds)
        return await over(0, None)

    monkeypatch.setattr(root, "_over", one_grace)
    ela = await built(
        monkeypatch,
        tmp_path,
        {},
        browser=Graced("empty", order),
        accounts=Graced("accounts", order),
    )
    told: list[tuple[tuple[str, ...], bool]] = []

    await ela.aclose(killed=lambda names, hurried: told.append((names, hurried)))

    assert order[:2] == ["empty settling", "accounts settling"], "both asked before either ends"
    assert counted == [BROWSER_CLOSE_GRACE_SECONDS], "one grace, for both"
    assert told == [(("empty", "accounts"), False)]


@pytest.mark.parametrize("failing", ["browser", "accounts"])
async def test_a_browser_that_cannot_be_settled_does_not_keep_the_other_nor_the_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failing: str
) -> None:
    class Failing(FakeAccountBrowser):
        async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            await super().settle(grace)
            raise RuntimeError("a browser that could not be settled")

    browsers = {"browser": FakeAccountBrowser(), "accounts": FakeAccountBrowser()}
    browsers[failing] = Failing()
    ela = await built(monkeypatch, tmp_path, {}, **browsers)

    with pytest.raises(RuntimeError, match="could not be settled"):
        await ela.aclose()

    assert unsettled(ela) == []
    assert int(ela.database.pool.checkedin()) == 0  # type: ignore[attr-defined]


async def test_a_browser_that_fails_does_not_end_the_close_while_the_other_is_still_settling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """«When this returns nothing of a browser runs any more» holds for both: one that fails at
    once is given back only when the other has been brought to rest."""
    release = asyncio.Event()
    finished: list[bool] = []

    class Failing(FakeBrowser):
        async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            raise RuntimeError("a browser that could not be settled")

    class Slow(FakeAccountBrowser):
        async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            await release.wait()
            finished.append(True)
            return ()

    ela = await built(monkeypatch, tmp_path, {}, browser=Failing(), accounts=Slow())
    closing = asyncio.ensure_future(ela.aclose())
    ended, _ = await asyncio.wait({closing}, timeout=0.5)
    assert not ended, "the close waits for the browser that is still settling"

    release.set()
    with pytest.raises(RuntimeError, match="could not be settled"):
        await closing

    assert finished == [True]
    assert int(ela.database.pool.checkedin()) == 0  # type: ignore[attr-defined]


async def test_a_grace_somebody_asked_for_does_not_run_on_behind_a_close_that_is_over(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A browser that asked for the grace and then closed by itself: when ELA's close returns the
    count of the grace is over too — five seconds running behind it would hold the loop open."""

    class Asking(FakeBrowser):
        async def settle(self, grace: Callable[[], Awaitable[None]]) -> tuple[str, ...]:
            asyncio.ensure_future(grace())
            await asyncio.sleep(0)
            return ()

    ela = await built(monkeypatch, tmp_path, {}, browser=Asking(), accounts=FakeAccountBrowser())
    before = asyncio.all_tasks()

    await ela.aclose()
    for _ in range(5):
        await asyncio.sleep(0)

    left = [task for task in asyncio.all_tasks() - before if not task.done()]
    assert left == [], left


# ----------------------------------------------------------------------------------------
# What makes the driver write: out of ELA's environment (decision 22)
# ----------------------------------------------------------------------------------------


def test_every_variable_that_makes_the_driver_talk_is_removed_by_its_prefix() -> None:
    """``NODE_`` as before; and ``DEBUG`` and ``PWDEBUG``, with which the driver writes on its
    stderr the value of every ``fill`` (measure 7). By the prefix, never by a list of names: the
    names are kept, never the values."""
    environment = {
        "NODE_TLS_REJECT_UNAUTHORIZED": "0",
        "DEBUG": "pw:api",
        "DEBUG_FILE": "/somewhere/a-log-7431",
        "DEBUG_COLORS": "no",
        "PWDEBUG": "1",
        "PWDEBUG_ANYTHING": "x",
        "MY_DEBUG": "stays",
        "NOT_NODE_OPTIONS": "stays",
        "PATH": "/usr/bin",
    }

    removed = without_node_variables(environment)

    assert removed == (
        "DEBUG",
        "DEBUG_COLORS",
        "DEBUG_FILE",
        "NODE_TLS_REJECT_UNAUTHORIZED",
        "PWDEBUG",
        "PWDEBUG_ANYTHING",
    )
    assert environment == {"MY_DEBUG": "stays", "NOT_NODE_OPTIONS": "stays", "PATH": "/usr/bin"}
    assert all("7431" not in name for name in removed)


async def test_the_core_removes_them_before_anything_is_built_and_keeps_the_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEBUG", "pw:api")
    monkeypatch.setenv("PWDEBUG", "console")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/somewhere")

    ela = await built(
        monkeypatch, tmp_path, {}, browser=FakeBrowser(), accounts=FakeAccountBrowser()
    )
    try:
        removed = set(ela.removed_from_environment)
    finally:
        await ela.aclose()

    assert {"DEBUG", "PWDEBUG", "NODE_EXTRA_CA_CERTS"} <= removed
    assert not {"DEBUG", "PWDEBUG", "NODE_EXTRA_CA_CERTS"} & set(os.environ)


async def test_the_driver_of_the_core_does_not_receive_what_would_make_it_write_a_fill(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Criterion 16, with the real driver — the empty browser's, which every machine of the suite
    has: with ``DEBUG=pw:api`` in the environment of whoever starts ELA, the driver the Core
    starts does not have it. It is the same driver, started the same way, for the profile."""
    monkeypatch.setenv("DEBUG", "pw:api")
    monkeypatch.setenv("PWDEBUG", "1")
    ela = await built(monkeypatch, tmp_path, {})
    browser = ela.browser
    try:
        opened = await browser.open("about:blank", lambda url: True, FakeStop())
        try:
            names = environment_names(driver_of_this_process())
        finally:
            await browser.close(opened.page)
    finally:
        await ela.aclose()

    assert "PATH" in names, "the reading found the driver's environment"
    assert not {name for name in names if name.startswith(("DEBUG", "PWDEBUG", "NODE_"))}
