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
from ela.composition.system import WindowSwitch, while_the_user_signs_in, without_node_variables
from ela.domain import ActorKind, AuditEventType
from ela.infrastructure.machine import AccountChrome, PlaywrightBrowser
from ela.permissions import (
    BROWSER_ACT,
    BROWSER_ACT_AS_YOU,
    BROWSER_LOGIN,
    BROWSER_READ,
    BROWSER_READ_AS_YOU,
)
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    Browser,
    BrowserFailed,
    BrowserUnsupported,
    ProfileUndeclared,
    ProfileUnsafe,
)
from ela.testing.fakes import FakeAccountBrowser, FakeBrowser, FakePower, FakeStop
from ela.tools import PERCEPTION_CAPTURE_SCREEN, PERCEPTION_LISTEN, PERCEPTION_READ_SCREEN_TEXT
from ela.tools.listen import LISTEN_LOGIN_WINDOW_OPEN
from ela.tools.screen import SCREEN_LOGIN_WINDOW_OPEN
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
# Which tool holds which browser: a closed world, both ways (criterion 7)
# ----------------------------------------------------------------------------------------

EMPTY = frozenset({BROWSER_READ, BROWSER_ACT})
"""The capabilities of the empty browser: a visitor, on every page."""
WITH_THE_PROFILE = frozenset({BROWSER_READ_AS_YOU, BROWSER_ACT_AS_YOU, BROWSER_LOGIN})
"""The capabilities of the browser with the user's accounts."""


def holding_a_browser(tools: Any, verifiers: Any) -> dict[str, tuple[str, object]]:
    """Every tool and every verifier that holds a browser, by its name: the capability it is of,
    and the browser it holds."""
    return {
        one.name: (one.capability_id, one._browser)
        for one in (*tools.tools(), *verifiers.verifiers())
        if getattr(one, "_browser", None) is not None
    }


def misplaced(tools: Any, verifiers: Any, empty: object, accounts: object) -> list[str]:
    """The tools and verifiers that hold the wrong browser, or a browser nobody classified."""
    wrong: list[str] = []
    for name, (capability, browser) in holding_a_browser(tools, verifiers).items():
        if capability in EMPTY:
            right = browser is empty
        elif capability in WITH_THE_PROFILE:
            right = browser is accounts
        else:
            right = False
        if not right:
            wrong.append(name)
    return sorted(wrong)


async def test_no_tool_of_the_empty_browser_can_open_the_profile_and_none_of_its_own_can_miss_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The seventh criterion, as ELA is built: the two tools of the empty browser and their
    verifiers hold the empty browser — an object that has no folder —, the three of the profile
    hold the other, and **every** tool that holds a browser is one of these."""
    ela = await built(monkeypatch, tmp_path, {PROFILE: str(tmp_path / "state" / "profile")})
    try:
        held = holding_a_browser(ela.tools, ela.verifiers)

        assert {capability for capability, _ in held.values()} == EMPTY | WITH_THE_PROFILE
        assert len(held) == 2 * len(EMPTY | WITH_THE_PROFILE), "a tool and a verifier for each"
        assert misplaced(ela.tools, ela.verifiers, ela.browser, ela.accounts) == []
        assert ela.browser is not ela.accounts
        assert not isinstance(ela.browser, AccountChrome), "the empty browser has no profile"
        assert not hasattr(ela.browser, "_profile")
    finally:
        await ela.aclose()


def test_a_tool_of_the_empty_browser_handed_the_profile_is_found(tmp_path: Path) -> None:
    """The negative case, in both directions: registries built with the two browsers the wrong
    way round — what a slip of one argument in the composition would do."""
    from tests.tools.test_registry import _production

    empty, accounts = FakeBrowser(), FakeAccountBrowser()
    tools, verifiers, _ = _production(tmp_path)
    right = holding_a_browser(tools, verifiers)
    for one in (*tools.tools(), *verifiers.verifiers()):
        if one.name in right:
            one._browser = accounts if one.capability_id in EMPTY else empty

    assert misplaced(tools, verifiers, empty, accounts) == sorted(right)
    for one in (*tools.tools(), *verifiers.verifiers()):
        if one.name in right:
            one._browser = empty if one.capability_id in EMPTY else accounts
    assert misplaced(tools, verifiers, empty, accounts) == []


# ----------------------------------------------------------------------------------------
# While the user signs in by hand, ELA neither looks nor listens (decision 41)
# ----------------------------------------------------------------------------------------

LOOKS_OR_LISTENS = {
    PERCEPTION_CAPTURE_SCREEN: SCREEN_LOGIN_WINDOW_OPEN,
    PERCEPTION_READ_SCREEN_TEXT: SCREEN_LOGIN_WINDOW_OPEN,
    PERCEPTION_LISTEN: LISTEN_LOGIN_WINDOW_OPEN,
}
"""Every capability of ELA that looks at the screen or listens, with the code it refuses with
while the window is open. A closed world: a tool of ``perception.`` that is not here is found."""


async def would_refuse(ela: Ela) -> dict[str, str | None]:
    """What each tool of perception would refuse with now, asked as the executor asks before a
    question — by capability, ``None`` for a call that would go on."""
    found: dict[str, str | None] = {}
    for tool in ela.tools.tools():
        if str(tool.capability_id).startswith("perception."):
            refusal = (await tool.prospect({})).refusal
            found[tool.capability_id] = None if refusal is None else refusal.code
    return found


@pytest.mark.parametrize(
    ("holder", "says"),
    [
        pytest.param(PROFILE_WINDOW, "where you sign in by hand is open", id="the-window"),
        pytest.param(PROFILE_PROCESS, "ELA did not start", id="a-browser-left-on-the-folder"),
    ],
)
async def test_while_the_user_may_be_signing_in_no_capability_of_perception_would_start(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, holder: str, says: str
) -> None:
    """The window ELA opened — and a browser on the folder that ELA did not start now: a window
    left by an ELA that was killed is the same window, and the lock is all that names it."""
    accounts = FakeAccountBrowser(holder=holder)
    ela = await built(monkeypatch, tmp_path, {}, accounts=accounts)
    try:
        found = await would_refuse(ela)
        (capture,) = [
            one for one in ela.tools.tools() if one.capability_id == PERCEPTION_CAPTURE_SCREEN
        ]
        refusal = (await capture.prospect({})).refusal
    finally:
        await ela.aclose()

    assert found == LOOKS_OR_LISTENS
    assert refusal is not None and says in refusal.message


@pytest.mark.parametrize("holder", [PROFILE_STEP, None], ids=["a-step-of-ela-s", "nobody"])
async def test_a_profile_no_hand_is_on_refuses_nothing_of_perception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, holder: str | None
) -> None:
    """A step of ELA's own on the profile is no sign-in: nobody is typing a password there."""
    accounts = FakeAccountBrowser(holder=holder)
    ela = await built(monkeypatch, tmp_path, {}, accounts=accounts)
    try:
        found = await would_refuse(ela)
    finally:
        await ela.aclose()

    assert found == dict.fromkeys(LOOKS_OR_LISTENS)


@pytest.mark.parametrize(
    "nothing_here",
    [ProfileUndeclared("no folder was declared"), BrowserUnsupported("Linux")],
    ids=["no-folder-declared", "not-a-mac"],
)
async def test_where_there_is_no_profile_there_is_no_window_to_wait_for(
    nothing_here: Exception,
) -> None:
    """ELA opens the window on a declared folder, on a Mac: where either is missing no window of
    ELA's can be open, and looking and listening go on as before M13.9."""
    accounts = FakeAccountBrowser(holder=PROFILE_WINDOW)
    accounts.raising["occupied"] = nothing_here

    assert await while_the_user_signs_in(accounts)() is None


@pytest.mark.parametrize(
    "doubt",
    [ProfileUnsafe("the folder is a link"), BrowserFailed("the lock could not be read")],
    ids=["an-unfit-folder", "a-look-that-failed"],
)
async def test_a_window_ela_cannot_look_for_is_a_doubt_and_a_doubt_refuses(
    doubt: Exception,
) -> None:
    """Fail-safe: a folder is declared, and ELA cannot say whether a hand is on it."""
    accounts = FakeAccountBrowser()
    accounts.raising["occupied"] = doubt

    reason = await while_the_user_signs_in(accounts)()

    assert reason is not None and "could not be read" in reason
    assert str(doubt) in reason


async def test_a_holder_ela_has_no_sentence_for_is_a_doubt_too() -> None:
    """Fail-safe: the one holder that lets ELA look and listen is a step of its own — nobody
    types a password into a page ELA drives. A holder the port comes to name and this table does
    not is not «nobody»: it is somebody ELA cannot say anything about."""
    accounts = FakeAccountBrowser(holder="a-holder-nobody-wrote-a-sentence-for")

    reason = await while_the_user_signs_in(accounts)()

    assert reason is not None and "a-holder-nobody-wrote-a-sentence-for" in reason


async def test_a_step_of_ela_s_own_is_no_hand_on_the_profile() -> None:
    accounts = FakeAccountBrowser(holder=PROFILE_STEP)

    assert await while_the_user_signs_in(accounts)() is None


async def test_the_question_looks_at_the_profile_each_time_it_is_asked() -> None:
    accounts = FakeAccountBrowser(holder=PROFILE_WINDOW)
    not_now = while_the_user_signs_in(accounts)

    open_, accounts.holder = await not_now(), None
    closed = await not_now()

    assert open_ is not None and closed is None


# ----------------------------------------------------------------------------------------
# The end of the sign-in window is told to the audit
# ----------------------------------------------------------------------------------------


async def test_the_end_of_a_sign_in_window_is_a_row_of_the_audit_signed_by_ela(ela: Ela) -> None:
    """A closing no route asked for — the user closed the window, ELA stopped — would be left
    without a row: who waits for the process writes it (ADR 0063 §8). The site if there was one,
    and how long the window stayed open, in whole seconds: never an address, and nothing of what
    was done in it — ELA does not know."""
    adapter = ela.accounts
    assert isinstance(adapter, AccountChrome)

    await adapter._ended("https://www.youtube.com/feed/you?tab=1", 12.9)
    await adapter._ended(None, 0.4)
    await adapter._ended("https://somebody@accounts.example:8443/signin", 3.0)

    closed = [
        event
        for event in await ela.audit.read()
        if event.event_type is AuditEventType.BROWSER_WINDOW_CLOSED
    ]
    assert [dict(event.payload) for event in closed] == [
        {"site": "www.youtube.com", "seconds": 12},
        {"site": None, "seconds": 0},
        {"site": "accounts.example", "seconds": 3},
    ]
    assert all(event.actor.kind is ActorKind.ELA for event in closed)
    assert all(event.task_id is None for event in closed), "a window is no task's"
    said = repr([(event.summary, event.payload) for event in closed])
    assert "feed" not in said
    assert "somebody" not in said and "8443" not in said, "the site: no name, and no port"


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
