"""The browser with the profile that lasts, **on the real Chrome for Testing** (M13.9, ADR 0063).

What only the binary can say: that a page opens on the declared folder with the sandbox on and
the keychain never touched; that what the profile must not keep is not kept — and what it exists
to keep, is —; that a worker left in the profile would answer without the gate, and is gone; that
one process at a time holds the folder; that ELA's stop and ELA's close do on this binary what
they do on the empty browser's, **and leave the folder where it is**; and that the window has
nothing attached.

**Reserved to a Mac with Chrome for Testing**: on any other system the adapter says
``browser.unsupported_system``, and that is the test of ``test_account_profile.py``. On a Mac
where the browser is not installed these fail, and say which command installs it.

Every test has a folder of its own under ``/tmp`` — a profile holds a socket, and a long path does
not fit in one —, and what a test leaves is found by that folder and taken away
(``tests/browser_leftovers.py``). Headless, except the two tests of the window. No login, to
anything: the pages are the test's, on ``127.0.0.1``. **The browser talks to Google by itself at
every launch** — measured, and declared —, here from a profile that holds nothing.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import signal
import sqlite3
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from ela.infrastructure.machine.account import (
    LAUNCH_ARGUMENTS,
    WINDOW_ARGUMENTS,
    AccountChrome,
)
from ela.infrastructure.machine.browser import registry_folder
from ela.ports import (
    PROFILE_STEP,
    PROFILE_WINDOW,
    BrowserFailed,
    BrowserStopped,
    ProfileBusy,
    Secret,
)
from ela.testing.fakes import FakeStop
from tests.browser_leftovers import named
from tests.infrastructure.machine import test_browser as shell
from tests.infrastructure.machine.test_browser import (
    Grace,
    Kept,
    Site,
    drivers,
    known,
    site,
    started,
)

# The two fixtures of the tests of the empty browser, under their own names: the servers a test
# made, closed after it; and — on every test here — a temporary folder of its own, with whatever
# the test left on the machine found by that folder, taken away, and asserted to be nothing.
served = shell.served
nothing_left_behind = shell.nothing_left_behind

SYSTEM = platform.system()
INSTALL = "uv run playwright install chromium"
pytestmark = pytest.mark.skipif(
    SYSTEM != "Darwin", reason="the browser with the profile is Chrome for Testing on a Mac"
)

SENTINEL = "-".join(("SENTINEL", "typed", "in", "the", "field"))
LOGIN = """
<form method="post" action="/in">
  <input id="user" name="user">
  <input id="word" name="word" type="password">
  <button id="go">Entra</button>
</form>
"""
KEPT = {"Set-Cookie": "kept=yes; Max-Age=3600; Path=/"}


def everywhere(address: str) -> bool:
    return True


@pytest.fixture
def profile(nothing_left_behind: None) -> Path:
    """The folder of this test's profile: inside the folder the leftovers are found by."""
    return Path(os.environ["TMPDIR"]) / "profile"


def chrome(
    profile: Path, stopping: asyncio.Event | None = None, **options: object
) -> AccountChrome:
    return AccountChrome(
        asyncio.Event() if stopping is None else stopping,
        environment={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"},
        kept=Kept(),
        system=SYSTEM,
        profile=profile,
        shown=options.pop("shown", lambda: False),  # type: ignore[arg-type]
        **options,  # type: ignore[arg-type]
    )


@pytest.fixture
async def browser(profile: Path) -> AsyncIterator[AccountChrome]:
    made = chrome(profile)
    if not await made.installed():
        pytest.fail(f"Chrome for Testing is not installed on this machine: run `{INSTALL}`")
    yield made
    for page in list(made._pages):
        await made.close(page)


def arguments_of(profile: Path) -> list[str]:
    """The arguments of the browser's main process on ``profile``, as the kernel has them."""
    pids = named(profile.parent)
    if not pids:
        return []
    said = subprocess.run(
        ["/bin/ps", "-ww", "-o", "args=", "-p", ",".join(map(str, pids))],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    # The main process names the folder and no ``--type``; a process of the browser's own that
    # ended between the two questions to the kernel has no arguments left, and is nobody's.
    mains = [
        line
        for line in said.splitlines()
        if f"--user-data-dir={profile}" in line and "--type=" not in line
    ]
    assert len(mains) == 1, mains
    return mains[0].split(" --")[1:]


def rows(profile: Path, file: str, table: str) -> int:
    database = sqlite3.connect(
        f"{(profile / 'Default' / file).as_uri()}?mode=ro&immutable=1", uri=True
    )
    try:
        (count,) = database.execute(f"select count(*) from {table}").fetchone()  # noqa: S608
    finally:
        database.close()
    return int(count)


def holding(profile: Path, text: str) -> list[str]:
    """The files of the profile that hold ``text`` in the clear, in either of the two encodings
    a browser writes text in."""
    needles = (text.encode(), text.encode("utf-16le"))
    return sorted(
        str(found.relative_to(profile))
        for found in profile.rglob("*")
        if found.is_file() and any(needle in found.read_bytes() for needle in needles)
    )


# ----------------------------------------------------------------------------------------
# The binary, the folder, and what a launch is given
# ----------------------------------------------------------------------------------------


def test_the_binary_is_chrome_for_testing_of_the_lock_and_never_the_installed_chrome() -> None:
    """Where the adapter looks is the registry of Playwright, for the revision its lock names."""
    folder = registry_folder("chromium", os.environ, SYSTEM)

    assert folder is not None and "ms-playwright" in str(folder)
    assert "/Applications/" not in str(folder)


async def test_a_page_opens_on_the_declared_folder_with_the_sandbox_and_without_the_keychain(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>Ciao</p>")})

    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    assert opened.status == 200 and await browser.text(opened.page, None) == "Ciao"
    arguments = arguments_of(profile)
    assert f"user-data-dir={profile}" in arguments
    for ours in LAUNCH_ARGUMENTS:
        assert ours.removeprefix("--") in arguments, ours
    assert "no-sandbox" not in arguments, "the sandbox is on: Playwright's default turns it off"
    assert any(argument.startswith("headless") for argument in arguments)
    assert profile.stat().st_mode & 0o777 == 0o700
    assert await browser.occupied() == PROFILE_STEP
    assert known(int(os.readlink(profile / "SingletonLock").rpartition("-")[2]))

    await browser.close(opened.page)

    assert await browser.occupied() is None
    assert named(profile.parent) == [], "no process of that browser is left on the folder"


async def test_what_lasts_is_the_folder_a_cookie_with_an_end_is_found_by_the_next_launch(
    browser: AccountChrome, served: list[Site]
) -> None:
    """A browser per page, closed with it: what passes to the next is what the folder keeps. A
    cookie the site gave an end to is sent again; **a cookie of the session is not** — a login
    on a site that gives no other lasts for that step and no longer, and that is declared."""
    cookies = {"Set-Cookie": "kept=yes; Max-Age=3600; Path=/"}
    web = site(served, {"/": (200, cookies, "<p>x</p>"), "/s": (200, {}, "<p>y</p>")})

    first = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(first.page)
    second = await browser.open(web.origin + "/s", everywhere, FakeStop())
    await browser.close(second.page)

    assert web.cookies == ["", "kept=yes"]


async def test_a_cookie_of_the_session_does_not_pass_to_the_next_launch(
    browser: AccountChrome, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {"Set-Cookie": "session=yes; Path=/"}, "<p>x</p>")})

    first = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(first.page)
    second = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(second.page)

    assert web.cookies == ["", ""]


# ----------------------------------------------------------------------------------------
# What the profile does not keep
# ----------------------------------------------------------------------------------------


async def test_the_preferences_are_there_before_the_first_launch_and_rewritten_before_each(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    """Decision 22: written before every launch, **over the file the browser itself wrote**. A
    preference the browser or the user had changed does not survive the next launch."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    file = profile / "Default" / "Preferences"

    first = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(first.page)
    written = json.loads(file.read_text(encoding="utf-8"))
    assert written["credentials_enable_service"] is False
    assert written["signin"]["allowed"] is False
    assert len(written) > 5, "this is the browser's own file now, with everything else it keeps"

    written["credentials_enable_service"] = True
    written["signin"]["allowed"] = True
    written["autofill"]["profile_enabled"] = True
    file.write_text(json.dumps(written), encoding="utf-8")

    second = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(second.page)

    after = json.loads(file.read_text(encoding="utf-8"))
    assert after["credentials_enable_service"] is False
    assert after["signin"]["allowed"] is False
    assert after["autofill"]["profile_enabled"] is False
    assert await browser.linked() is False


async def test_after_a_login_no_password_is_left_in_the_browser(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    """Criterion 15: the form is sent with the password, and the profile holds none — the
    manager's tables are empty, and the sentinel is in the clear in no file of the folder."""
    web = site(served, {"/": (200, KEPT, LOGIN), "/in": (200, {}, "<p>Benvenuto</p>")})

    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "#user", Secret("mario"))
    await browser.fill_secret(opened.page, "#word", Secret(SENTINEL))
    await browser.click(opened.page, "#go")
    assert await browser.text(opened.page, None) == "Benvenuto"
    await browser.close(opened.page)

    assert web.bodies == [f"user=mario&word={SENTINEL}"], "the site received it"
    assert rows(profile, "Login Data", "logins") == 0
    assert rows(profile, "Login Data", "stats") == 0
    assert rows(profile, "Web Data", "autofill") == 0
    assert holding(profile, SENTINEL) == []
    assert await browser.saved() == 0


async def test_a_fill_that_fails_says_the_type_of_the_failure_and_nothing_of_the_value(
    browser: AccountChrome, served: list[Site]
) -> None:
    """Criterion 16: the engine's message names the call, with what was typed — and the engine's
    exception does not leave the adapter, not even as the context of the one that does."""
    web = site(served, {"/": (200, {}, '<p id="text">not a field</p>')})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    with pytest.raises(BrowserFailed) as failed:
        await browser.fill_secret(opened.page, "#text", Secret(SENTINEL))

    chain: list[BaseException] = []
    error: BaseException | None = failed.value
    while error is not None:
        chain.append(error)
        error = error.__cause__ or error.__context__
    assert len(chain) == 1, "nothing is chained to what leaves"
    assert SENTINEL not in f"{failed.value!s} {failed.value!r} {failed.value.args}"


# ----------------------------------------------------------------------------------------
# What the port says more than the empty browser's
# ----------------------------------------------------------------------------------------

FORMS = """
<form method="post"><input id="posted" type="password"><button id="post-button">a</button></form>
<form method="get"><input id="got" type="password"></form>
<form><input id="unsaid" type="password"></form>
<form method="POST"><input id="capital" type="password"></form>
<form method="get"><input name="method" value="post"><input id="named" type="password"></form>
<form method="post"><input id="overridden-field" type="password" formmethod="get">
  <button id="overriding" formmethod="get">b</button></form>
<input id="alone" type="password">
<a id="link" href="/">c</a>
"""


@pytest.mark.parametrize(
    ("selector", "method"),
    [
        ("#posted", "post"),
        ("#post-button", "post"),
        ("#got", "get"),
        ("#unsaid", "get"),
        ("#capital", "post"),
        ("#named", "get"),
        ("#overridden-field", "post"),
        ("#overriding", "get"),
        ("#alone", ""),
        ("#link", ""),
    ],
)
async def test_how_the_form_of_an_element_sends_is_read_from_the_attributes(
    browser: AccountChrome, served: list[Site], selector: str, method: str
) -> None:
    """``#named``: a form with a field of its own called ``method`` answers ``form.method`` with
    that field — the adapter reads the attribute. ``#overriding``: a button that sends carries its
    own method over the form's; a field that is not one does not (``#overridden-field``)."""
    web = site(served, {"/": (200, {}, FORMS)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    assert (await browser.field(opened.page, selector)).method == method


@pytest.mark.parametrize(
    ("page", "asks"),
    [
        ('<input autocomplete="one-time-code">', True),
        ('<input autocomplete="ONE-TIME-CODE section-x">', True),
        ('<input autocomplete="one-time-code" hidden>', False),
        ('<input autocomplete="current-password" type="password">', False),
        ("<p>Benvenuto</p>", False),
    ],
    ids=["a-code", "among-other-words", "hidden", "a-password", "no-field"],
)
async def test_the_look_says_whether_the_page_asks_for_a_one_time_code(
    browser: AccountChrome, served: list[Site], page: str, asks: bool
) -> None:
    """The one fact more of this port's look (decision 17). What it does not recognise is not
    said to be one: the verifier then says the awaited text is missing, which is true."""
    web = site(served, {"/": (200, {}, page)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.keep(opened.page)

    glanced = await browser.glance(opened.page, selector=None, expect=None, seconds=1.0)

    assert glanced.second_factor is asks
    assert await browser.occupied() is None, "the look releases the page, and the folder with it"


# ----------------------------------------------------------------------------------------
# The service workers (criterion 17)
# ----------------------------------------------------------------------------------------

WORKER = """
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (event) => {
  if (new URL(event.request.url).pathname === "/page") {
    const html = {headers: {"Content-Type": "text/html"}};
    event.respondWith(new Response("<p>from the worker</p>", html));
  }
});
"""
REGISTERS = """
<p id="state">registering</p>
<script>
navigator.serviceWorker.register("/worker.js").then(() => navigator.serviceWorker.ready)
  .then(() => { document.getElementById("state").textContent = "registered"; });
</script>
"""


async def planted(browser: AccountChrome, web: Site, monkeypatch: pytest.MonkeyPatch) -> None:
    """A worker in the profile, as the window leaves one: registered by a launch that lets it."""
    launch = browser._launch
    monkeypatch.setattr(browser, "_launch", lambda: {**launch(), "service_workers": "allow"})
    opened = await browser.open(web.origin + "/register", everywhere, FakeStop())
    async with asyncio.timeout(20):
        while await browser.text(opened.page, "#state") != "registered":
            await asyncio.sleep(0.05)
    await browser.close(opened.page)
    monkeypatch.undo()


def worker_site(served: list[Site]) -> Site:
    return site(
        served,
        {
            "/register": (200, {}, REGISTERS),
            "/worker.js": (200, {"Content-Type": "text/javascript"}, WORKER),
            "/page": (200, {}, "<p>from the network</p>"),
        },
    )


async def test_a_worker_left_in_the_profile_is_gone_before_a_page_and_the_gate_sees_the_request(
    browser: AccountChrome, profile: Path, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    web = worker_site(served)
    await planted(browser, web, monkeypatch)
    assert (profile / "Default" / "Service Worker").is_dir()
    at_the_gate: list[str] = []

    def admitted(address: str) -> bool:
        at_the_gate.append(address)
        return True

    opened = await browser.open(web.origin + "/page", admitted, FakeStop())

    assert await browser.text(opened.page, None) == "from the network"
    assert at_the_gate == [web.origin + "/page"]
    assert "GET /page" in web.requests


async def test_with_the_worker_left_the_page_is_the_worker_s_and_the_gate_is_never_asked(
    browser: AccountChrome, served: list[Site], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative case, built: the same profile, launched without what ELA does to it — the
    worker not removed, and workers not blocked. The page is the worker's, and **the boundary is
    never asked** about the navigation. This is what the removal is for.

    *Measured here on 2026-10-11, and not asserted*: the site received the request for the page
    all the same — sent by the browser itself, beside its worker, and not by the gate. A
    navigation that leaves without the boundary being asked is the thing the gate exists to
    prevent."""
    from ela.infrastructure.machine import account

    web = worker_site(served)
    await planted(browser, web, monkeypatch)
    launch = browser._launch
    monkeypatch.setattr(browser, "_launch", lambda: {**launch(), "service_workers": "allow"})
    monkeypatch.setattr(account, "_prepared", lambda profile, *, driven: None)
    at_the_gate: list[str] = []

    def admitted(address: str) -> bool:
        at_the_gate.append(address)
        return True

    opened = await browser.open(web.origin + "/page", admitted, FakeStop())

    assert await browser.text(opened.page, None) == "from the worker"
    assert at_the_gate == []


# ----------------------------------------------------------------------------------------
# One process at a time, and a closing that frees the folder
# ----------------------------------------------------------------------------------------


async def test_a_second_page_and_the_window_find_the_folder_held_and_start_nothing(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    before = started()

    with pytest.raises(ProfileBusy) as busy:
        await browser.open(web.origin + "/", everywhere, FakeStop())
    assert busy.value.by == PROFILE_STEP
    with pytest.raises(ProfileBusy):
        await browser.window(None)

    assert started() == before, "nothing was launched on a folder found held"
    assert web.requests == ["GET /"]
    await browser.close(opened.page)


async def test_two_openings_at_once_start_one_browser(
    browser: AccountChrome, served: list[Site]
) -> None:
    """Both look before either has a browser: the first to look is counted before the second
    looks, with no wait in between."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})

    results = await asyncio.gather(
        browser.open(web.origin + "/", everywhere, FakeStop()),
        browser.open(web.origin + "/", everywhere, FakeStop()),
        return_exceptions=True,
    )

    busy = [result for result in results if isinstance(result, ProfileBusy)]
    opened = [result for result in results if not isinstance(result, BaseException)]
    assert len(busy) == 1 and len(opened) == 1, results
    assert len(drivers()) == 1


async def test_whoever_asks_to_close_a_page_another_is_closing_returns_when_the_folder_is_free(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    """Criterion 28: on the empty browser the second call returns at once, and there it does not
    matter; here the step after would find the folder held."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    seen: list[tuple[str, str | None, list[int]]] = []

    async def closes(who: str) -> None:
        await browser.close(opened.page)
        seen.append((who, await browser.occupied(), named(profile.parent)))

    await asyncio.gather(closes("first"), closes("second"))

    assert sorted(seen) == [("first", None, []), ("second", None, [])]


# ----------------------------------------------------------------------------------------
# ELA's stop and ELA's close, on this binary
# ----------------------------------------------------------------------------------------


class RaisedWhileTheBrowserStarts(asyncio.Event):
    """ELA's stop, raised by the adapter's own second look at it: the one before a navigation."""

    def __init__(self) -> None:
        super().__init__()
        self.looks = 0

    def is_set(self) -> bool:
        self.looks += 1
        if self.looks >= 3:
            self.set()
        return super().is_set()


async def test_a_stop_of_ela_raised_while_the_profile_s_browser_starts_sends_nothing(
    profile: Path, served: list[Site]
) -> None:
    """Criterion 27: the property of M13.4c, held by this adapter on its own binary. The stop is
    raised while the browser starts — no navigation leaves, the page is closed by its opening,
    and the folder is free."""
    web = site(served, {"/": (200, {}, LOGIN)})
    stopping = RaisedWhileTheBrowserStarts()
    browser = chrome(profile, stopping)

    with pytest.raises(BrowserStopped):
        await browser.open(web.origin + "/", everywhere, FakeStop())

    assert web.requests == []
    assert await browser.settle(Grace()) == ()
    assert named(profile.parent) == []


async def test_a_profile_s_browser_that_does_not_close_is_killed_at_the_grace_and_keeps_its_folder(
    profile: Path, served: list[Site]
) -> None:
    """Criteria 29 and 31. The driver is frozen — an event —, so the closing ELA's stop begins
    never comes back; at the grace what the adapter started is killed and named. **The folder of
    the profile is there after, with what it held**: the adapter takes away only the temporary
    profiles Playwright names, never a folder somebody declared. And it is free.

    «What it held» is what a launch before had left: a browser that is killed has not written
    what it learned a moment ago — measured, a cookie set by the page of the killed browser is
    not found after —, and that is the browser's, not something the adapter takes away."""
    web = site(served, {"/": (200, KEPT, "<p>x</p>"), "/after": (200, {}, "<p>y</p>")})
    before_it = chrome(profile)
    first = await before_it.open(web.origin + "/", everywhere, FakeStop())
    await before_it.close(first.page)
    stopping = asyncio.Event()
    browser = chrome(profile, stopping)
    await browser.open(web.origin + "/after", everywhere, FakeStop())
    before = started()
    (driver,) = drivers()
    os.kill(driver, signal.SIGSTOP)
    grace = Grace()

    try:
        stopping.set()
        settling = asyncio.create_task(browser.settle(grace))
        await grace.asked.wait()
        assert not settling.done()
        grace.over.set()
        async with asyncio.timeout(30):
            killed = await settling

        assert killed.count("node") == 1 and len(killed) == len(before)
        assert [name for pid, name in before if known(pid)] == []
        assert (profile / "Default" / "Preferences").is_file(), "the folder is not a temporary one"
        assert named(profile.parent) == []
    finally:
        for pid, _ in before:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                continue

    again = chrome(profile)
    assert await again.occupied() is None, "the lock a killed browser left names nobody"
    opened = await again.open(web.origin + "/after", everywhere, FakeStop())
    await again.close(opened.page)
    assert web.cookies[-1] == "kept=yes", "and what it held is found by the launch after"


# ----------------------------------------------------------------------------------------
# The window: nothing attached, told at the stop, never left on the folder
# ----------------------------------------------------------------------------------------


class Ended:
    """Who is told that a window ended — in ELA, the audit."""

    def __init__(self) -> None:
        self.said: list[tuple[str | None, float]] = []
        self.heard = asyncio.Event()

    async def __call__(self, address: str | None, seconds: float) -> None:
        self.said.append((address, seconds))
        self.heard.set()


async def on_the_folder(profile: Path) -> int:
    """The window's main process, once it is on the folder: its lock names it."""
    async with asyncio.timeout(20):
        while not os.path.lexists(profile / "SingletonLock"):
            await asyncio.sleep(0.05)
    return int(os.readlink(profile / "SingletonLock").rpartition("-")[2])


async def test_the_window_has_nothing_attached_and_at_ela_s_stop_closes_by_itself(
    profile: Path, served: list[Site]
) -> None:
    """Criteria 13 and 32, the first way. The arguments, read back from the kernel, are the closed
    list — no driver under ELA, no pipe, no port. A cookie the site gives there is found by a
    step after: what the user does by hand in the window, ELA's pages inherit. At the stop the
    window is told, exits by itself, and the folder is free."""
    web = site(served, {"/": (200, KEPT, "<p>x</p>"), "/after": (200, {}, "<p>y</p>")})
    stopping, ended = asyncio.Event(), Ended()
    browser = chrome(profile, stopping, ended=ended)
    if not await browser.installed():
        pytest.fail(f"Chrome for Testing is not installed on this machine: run `{INSTALL}`")

    await browser.window(web.origin + "/")
    pid = await on_the_folder(profile)

    assert drivers() == [pid], "the window is the one thing ELA started: no driver beside it"
    arguments = arguments_of(profile)
    assert arguments[:-1] == [
        f"user-data-dir={profile}",
        *(argument.removeprefix("--") for argument in WINDOW_ARGUMENTS[:-1]),
    ]
    assert arguments[-1] == f"{WINDOW_ARGUMENTS[-1].removeprefix('--')} {web.origin}/"
    assert await browser.occupied() == PROFILE_WINDOW
    with pytest.raises(ProfileBusy) as busy:
        await browser.open(web.origin + "/", everywhere, FakeStop())
    assert busy.value.by == PROFILE_WINDOW
    async with asyncio.timeout(20):
        while "GET /" not in web.requests:
            await asyncio.sleep(0.05)

    stopping.set()
    grace = Grace()
    async with asyncio.timeout(30):
        killed = await browser.settle(grace)

    assert killed == (), "told, it left by itself: nothing was killed"
    assert not known(pid) and named(profile.parent) == []
    ((address, seconds),) = ended.said
    assert address == web.origin + "/" and seconds > 0

    after = chrome(profile)
    assert await after.occupied() is None
    opened = await after.open(web.origin + "/after", everywhere, FakeStop())
    await after.close(opened.page)
    assert web.cookies[-1] == "kept=yes"


async def test_a_window_that_does_not_close_is_killed_at_the_grace_and_never_left_on_the_folder(
    profile: Path, served: list[Site]
) -> None:
    """Criterion 32, the second way: a window that is frozen — an event — hears nothing. Within
    the grace it is waited for; at its end it is killed with its group, and named.

    **Frozen once it is up**, which the test builds by waiting for its page: measured on this
    system, a stopped process that has not yet said what it does with ``SIGTERM`` is ended by it
    at once — the kernel's doing, with none of its code run —, and a browser frozen as it starts
    is that. One that has its own handling of the signal stays stopped, and hears nothing."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    stopping = asyncio.Event()
    browser = chrome(profile, stopping)
    await browser.window(web.origin + "/")
    pid = await on_the_folder(profile)
    async with asyncio.timeout(20):
        while "GET /" not in web.requests:
            await asyncio.sleep(0.05)
    os.kill(pid, signal.SIGSTOP)
    grace = Grace()

    try:
        stopping.set()
        settling = asyncio.create_task(browser.settle(grace))
        await grace.asked.wait()
        await asyncio.sleep(0.2)
        assert not settling.done() and known(pid), "told and waited for, not killed yet"
        grace.over.set()
        async with asyncio.timeout(30):
            killed = await settling

        assert killed == ("Google Chrome for Testing",)
        assert not known(pid) and named(profile.parent) == []
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)

    assert await chrome(profile).occupied() is None


async def test_a_window_the_user_closes_is_told_and_the_folder_is_free(
    profile: Path, served: list[Site]
) -> None:
    """The window is closed by the user: here by the signal a quit sends. ELA learns it from the
    one thing it keeps — the wait for its end —, and says how long it lasted."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    ended = Ended()
    browser = chrome(profile, ended=ended)
    await browser.window(web.origin + "/")
    pid = await on_the_folder(profile)
    async with asyncio.timeout(20):
        while "GET /" not in web.requests:  # up: a browser told to quit as it starts may not hear
            await asyncio.sleep(0.05)

    os.kill(pid, signal.SIGTERM)
    async with asyncio.timeout(30):
        await ended.heard.wait()

    assert ended.said[0][0] == web.origin + "/"
    assert await browser.occupied() is None
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(opened.page)
