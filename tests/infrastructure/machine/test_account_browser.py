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
from playwright.async_api import async_playwright

from ela.infrastructure.machine.account import (
    LAUNCH_ARGUMENTS,
    WINDOW_ARGUMENTS,
    AccountChrome,
    reports_in,
)
from ela.infrastructure.machine.browser import registry_folder
from ela.ports import (
    PROFILE_PROCESS,
    PROFILE_STEP,
    PROFILE_WINDOW,
    SHUT_QUIT,
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
judged = shell.judged

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


def processes() -> list[tuple[int, str]]:
    """Every process of this machine, with its arguments as the kernel has them."""
    said = subprocess.run(
        ["/bin/ps", "-ww", "-A", "-o", "pid=,args="], capture_output=True, text=True, check=False
    ).stdout
    table = []
    for line in said.splitlines():
        pid, _, arguments = line.strip().partition(" ")
        if pid.isdigit():
            table.append((int(pid), arguments))
    return table


def browsers_on(profile: Path) -> list[int]:
    """The processes of a browser on ``profile``: whatever was started with it as its folder —
    the main process, and its helpers. **Not the collector of crashes**: since decision 74 it
    keeps its database inside the folder, so it names the folder too, and it is a child of the
    system's that ends by itself a moment after its browser — what is promised when a close
    returns is that no browser is on the folder, and the fixture takes away, and asserts gone,
    whatever else still names it."""
    return [pid for pid, arguments in processes() if f"--user-data-dir={profile}" in arguments]


def collectors_of(profile: Path) -> list[str]:
    """The arguments of the collectors of crashes that write inside ``profile``."""
    wanted = f"--database={profile / 'Crashpad'}"
    return [arguments for _, arguments in processes() if wanted in arguments]


def rows(profile: Path, file: str, table: str) -> int:
    database = sqlite3.connect(
        f"{(profile / 'Default' / file).as_uri()}?mode=ro&immutable=1", uri=True
    )
    try:
        (count,) = database.execute(f"select count(*) from {table}").fetchone()  # noqa: S608
    finally:
        database.close()
    return int(count)


def cookies_in(profile: Path, which: str) -> int:
    """How many cookies one profile of the folder keeps on its disk."""
    database = sqlite3.connect(
        f"{(profile / which / 'Cookies').as_uri()}?mode=ro&immutable=1", uri=True
    )
    try:
        (count,) = database.execute("select count(*) from cookies").fetchone()
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
    left = profile / "Crashpad" / "pending" / "what-a-crash-left.dmp"
    left.parent.mkdir(parents=True)
    profile.chmod(0o700)
    left.write_bytes(b"memory of a process that fell")

    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    assert opened.status == 200 and await browser.text(opened.page, None) == "Ciao"
    assert not left.exists(), "what a crash left did not pass to this launch (decision 90)"
    assert len(browser._pages[opened.page].context.pages) == 1, "one page, not a blank one beside"
    arguments = arguments_of(profile)
    assert f"user-data-dir={profile}" in arguments
    for ours in LAUNCH_ARGUMENTS:
        assert ours.removeprefix("--") in arguments, ours
    assert "no-sandbox" not in arguments, "the sandbox is on: Playwright's default turns it off"
    assert any(argument.startswith("headless") for argument in arguments)
    assert profile.stat().st_mode & 0o777 == 0o700
    assert await browser.occupied() == PROFILE_STEP
    assert known(int(os.readlink(profile / "SingletonLock").rpartition("-")[2]))
    assert reports_in(profile).removeprefix("--") in arguments
    assert (profile / "Crashpad").is_dir() and collectors_of(profile), (
        "the collector of crashes that runs beside this browser writes inside the folder of "
        "the profile"
    )

    await browser.close(opened.page)

    assert await browser.occupied() is None
    assert browsers_on(profile) == [], "no process of that browser is left on the folder"


async def test_a_step_runs_on_the_profile_ela_prepares_whichever_was_used_last(
    browser: AccountChrome, profile: Path, served: list[Site]
) -> None:
    """Measured on 2026-10-11 (decision 79): with no name the browser opens the profile that was
    used last, and a step ran on one whose preferences ELA does not rewrite. Here a second
    profile is made and used last — by the driver itself, on the same binary and folder, as a
    user leaves one after adding it from the window —, and a step of ELA's leaves its cookie in
    ``Default`` all the same."""
    web = site(served, {"/": (200, KEPT, "<p>x</p>")})
    profile.mkdir(mode=0o700)
    async with async_playwright() as playwright:
        second = await playwright.chromium.launch_persistent_context(
            str(profile),
            channel="chromium",
            headless=True,
            args=["--use-mock-keychain", "--profile-directory=Profile 1", reports_in(profile)],
            env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home()), "LANG": "C.UTF-8"},
        )
        page = second.pages[0] if second.pages else await second.new_page()
        await page.goto(web.origin + "/")
        await second.close()
    state = json.loads((profile / "Local State").read_text(encoding="utf-8"))
    assert state["profile"]["last_used"] == "Profile 1", "the precondition: the second, last"
    assert cookies_in(profile, "Profile 1") == 1 and not (profile / "Default").exists()

    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.close(opened.page)

    assert cookies_in(profile, "Default") == 1, "the step ran on the profile ELA prepares"
    assert cookies_in(profile, "Profile 1") == 1, "and left the other as it was"
    assert await browser.profiles() == 2, "the browser's own list: the two, and no folder else"


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
<form method="post"><input name="method" value="x"><input id="named-post" type="password"></form>
<form method="post"><input id="overridden-field" type="password" formmethod="get">
  <button id="overriding" formmethod="get">b</button></form>
<input id="alone" type="password">
<a id="link" href="/">c</a>
"""


SENDS = {
    "#posted": "post",
    "#post-button": "post",
    "#got": "get",
    "#unsaid": "get",
    "#capital": "post",
    "#named": "get",
    "#named-post": "post",
    "#overridden-field": "post",
    "#overriding": "get",
    "#alone": "",
    "#link": "",
}
"""How each element of :data:`FORMS` sends, by its selector."""


async def test_how_the_form_of_an_element_sends_is_read_from_the_attributes(
    browser: AccountChrome, served: list[Site]
) -> None:
    """``#named`` and ``#named-post``: a form with a field of its own called ``method`` answers
    ``form.method`` with that field — the adapter reads the attribute, so a form that posts is
    seen to post whatever its fields are called. ``#overriding``: a button that sends carries its
    own method over the form's; a field that is not one does not (``#overridden-field``).

    **One launch for every element of the page** (decision 76): each is a reading of an element
    of its own, which changes nothing of the page — none of them leans on another, and what is
    compared is the whole table, so a reading that is wrong is named by its selector."""
    web = site(served, {"/": (200, {}, FORMS)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    read = {selector: (await browser.field(opened.page, selector)).method for selector in SENDS}

    assert read == SENDS


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


async def planted(browser: AccountChrome, web: Site) -> None:
    """A worker in the profile, as the window leaves one: registered by a launch that lets it,
    **with nothing of ELA's attached** — the same binary on the same folder, prepared as the
    adapter prepares it, and no gate. *Through the gate a worker cannot be registered at all
    (M13.4f): the request for its script has no frame of the page, and is refused.*"""
    folder = await browser._folder()
    await browser._prepare(folder, driven=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(folder), **{**browser._launch(), "service_workers": "allow"}
        )
        try:
            page = context.pages[0]
            await page.goto(web.origin + "/register")
            await page.get_by_text("registered").wait_for(state="visible", timeout=20_000)
        finally:
            await context.close()


def worker_site(served: list[Site]) -> Site:
    return site(
        served,
        {
            "/register": (200, {}, REGISTERS),
            "/worker.js": (200, {"Content-Type": "text/javascript"}, WORKER),
            "/page": (200, {}, "<p>from the network</p>"),
        },
    )


async def test_a_launch_ela_drives_finds_no_worker_in_the_profile_and_the_gate_sees_the_request(
    browser: AccountChrome,
    profile: Path,
    served: list[Site],
    judged: list[tuple[str, str, bool]],
) -> None:
    """**Where the defence acts** (M13.4f, decision 136; ADR 0064): of a navigation a worker
    answers the gate is not told — the test after this one —, so before every launch ELA drives
    the workers of the profile are taken away, and new ones are blocked. A worker left by a
    launch that let it is not there for the page: the page is the network's, and **the gate was
    told of its request** and let it go — what the gate saw, kept as it decides, and not what
    the boundary was asked, which whoever holds the page asks too."""
    web = worker_site(served)
    await planted(browser, web)
    assert (profile / "Default" / "Service Worker").is_dir()

    opened = await browser.open(web.origin + "/page", everywhere, FakeStop())

    assert await browser.text(opened.page, None) == "from the network"
    assert ("GET", web.origin + "/page", True) in judged
    assert "GET /page" in web.requests


async def test_with_the_worker_left_the_page_is_the_worker_s_and_the_gate_is_never_told(
    browser: AccountChrome,
    served: list[Site],
    judged: list[tuple[str, str, bool]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative case, built: the same profile, launched without what ELA does to it — the
    worker not removed, and workers not blocked. The page is the worker's, and **the gate is
    never told** of the navigation. This is what the removal is for.

    The site receives the request for the page all the same — sent by the browser itself,
    beside its worker, with nobody asked: asserted beside the worker that asks another site
    (``test_the_boundary.py``), where it was measured in every round. A navigation that leaves
    without the boundary being asked is the thing the gate exists to prevent.

    *The boundary is asked all the same, by the opening*: about where the page is (ADR 0064
    §4), once the navigation is over — which is why what the gate was told is read from the
    gate, and not from a boundary that keeps what it was asked."""
    from ela.infrastructure.machine import account

    web = worker_site(served)
    await planted(browser, web)
    launch = browser._launch
    monkeypatch.setattr(browser, "_launch", lambda: {**launch(), "service_workers": "allow"})
    monkeypatch.setattr(account, "_prepared", lambda profile, *, driven: None)

    opened = await browser.open(web.origin + "/page", everywhere, FakeStop())

    assert await browser.text(opened.page, None) == "from the worker"
    told = [address for _, address, _ in judged]
    assert web.origin + "/page" not in told, "the gate was told of the navigation after all"


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
        seen.append((who, await browser.occupied(), browsers_on(profile)))

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
    assert browsers_on(profile) == []


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
        assert browsers_on(profile) == []
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
        reports_in(profile).removeprefix("--"),
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
    assert (profile / "Crashpad").is_dir() and collectors_of(profile), (
        "the window's collector writes inside the folder too"
    )

    stopping.set()
    grace = Grace()
    async with asyncio.timeout(30):
        killed = await browser.settle(grace)

    assert killed == (), "told, it left by itself: nothing was killed"
    assert not known(pid) and browsers_on(profile) == []
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
        assert not known(pid) and browsers_on(profile) == []
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)

    assert await chrome(profile).occupied() is None


async def test_a_window_another_ela_left_is_seen_for_what_it_is_and_ended_by_the_command(
    profile: Path, served: list[Site]
) -> None:
    """Decisions 80 and 82, **with the system asked for real**: a second adapter on the folder —
    an ELA that did not start that window, as after the first was killed — finds the folder held
    because the command line of the process the lock names is ELA's own binary on it, and its
    command tells that process, which ends by itself. Everywhere else the system's answer is the
    test's: here it is the kernel's, of the real binary."""
    web = site(served, {"/": (200, {}, "<p>x</p>")})
    ended = Ended()
    first = chrome(profile, ended=ended)
    await first.window(web.origin + "/")
    pid = await on_the_folder(profile)
    async with asyncio.timeout(20):
        while "GET /" not in web.requests:  # up: a browser told to quit as it starts may not hear
            await asyncio.sleep(0.05)
    another = chrome(profile)

    assert await another.occupied() == PROFILE_PROCESS
    with pytest.raises(ProfileBusy) as busy:
        await another.open(web.origin + "/", everywhere, FakeStop())
    assert busy.value.by == PROFILE_PROCESS
    grace = Grace()
    async with asyncio.timeout(30):
        how = await another.shut(grace)
        await ended.heard.wait()

    assert how == SHUT_QUIT, "told, it ended by itself: the grace was never over"
    assert not known(pid) and browsers_on(profile) == []
    assert await another.occupied() is None and await first.occupied() is None
    first._stopping.set()
    assert await first.settle(Grace()) == ()


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


# ----------------------------------------------------------------------------------------
# A page with a window, and the fields read again (decisions 143 and 144 of 2026-10-13)
# ----------------------------------------------------------------------------------------


async def a_screen() -> bool:
    return True


async def test_a_page_asked_with_a_window_is_in_a_browser_that_has_one_with_the_switch_off(
    profile: Path, served: list[Site]
) -> None:
    """Decision 143, on the real browser: the switch is off, and the browser of this one page
    was not started without a window — with everything else a launch of ELA's has."""
    web = site(served, {"/": (200, {}, LOGIN)})
    browser = chrome(profile, on_a_screen=a_screen)

    opened = await browser.open_shown(web.origin + "/", everywhere, FakeStop())
    try:
        arguments = arguments_of(profile)
        found = await browser.count(opened.page, "#word")
    finally:
        await browser.close(opened.page)

    assert f"user-data-dir={profile}" in arguments
    assert not any(argument.startswith("headless") for argument in arguments), arguments
    for ours in LAUNCH_ARGUMENTS:
        assert ours.removeprefix("--") in arguments, ours
    assert "no-sandbox" not in arguments
    assert found == 1, "and it is a page like any other: the form is there"


async def test_a_field_holds_what_was_typed_until_a_key_lands_in_it(
    browser: AccountChrome, served: list[Site]
) -> None:
    """Decision 144. Whether a field still holds what a secret holds is the adapter's to say —
    it opens the secret to compare it, as it opened it to type it. A key, as the keyboard sends
    it to whatever has the focus in the page, lands in the field written last: after it that
    field holds something else, and the other still holds what was typed."""
    web = site(served, {"/": (200, {}, LOGIN)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "#user", Secret("mario"))
    await browser.fill_secret(opened.page, "#word", Secret(SENTINEL))

    before = (
        await browser.holds(opened.page, "#user", Secret("mario")),
        await browser.holds(opened.page, "#word", Secret(SENTINEL)),
    )
    await browser._pages[opened.page].page.keyboard.press("x")
    after = (
        await browser.holds(opened.page, "#user", Secret("mario")),
        await browser.holds(opened.page, "#word", Secret(SENTINEL)),
    )

    assert before == (True, True)
    assert after == (True, False)
    assert await browser.holds(opened.page, "#word", Secret(SENTINEL + "x")), (
        "the whole of what the field holds is compared, and that is what it holds now"
    )
    assert not await browser.holds(opened.page, "#word", Secret(SENTINEL[:-1]))


async def test_what_is_not_a_field_cannot_be_read_again_and_the_failure_names_its_type_alone(
    browser: AccountChrome, served: list[Site]
) -> None:
    """The secret is never handed to the engine to be compared — the field is read, and the
    comparison is made here —, so the engine has nothing of it to say: what leaves is the type
    of the engine's failure, as for every other use of a page."""
    web = site(served, {"/": (200, {}, '<p id="text">not a field</p>')})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())

    with pytest.raises(BrowserFailed) as failed:
        await browser.holds(opened.page, "#text", Secret(SENTINEL))

    assert str(failed.value) == "Error"
    error: BaseException | None = failed.value
    while error is not None:
        assert SENTINEL not in f"{error!s} {error!r} {error.args}"
        error = error.__cause__ or error.__context__


async def test_a_field_that_is_gone_holds_nothing_and_is_not_waited_for(
    browser: AccountChrome, served: list[Site]
) -> None:
    """Found by the re-read of 2026-10-13: a key pressed in the window may be the Return that
    sends the form, and then the page that comes has no such field. Reading it again must not
    wait for a field to appear — it would wait until the time of the tool ran out —: a field
    that is not there holds nothing of what was typed."""
    web = site(served, {"/": (200, {}, LOGIN)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "#word", Secret(SENTINEL))
    await browser._pages[opened.page].page.evaluate("document.querySelector('#word').remove()")

    async with asyncio.timeout(20):
        held = await browser.holds(opened.page, "#word", Secret(SENTINEL))

    assert held is False


async def test_a_field_that_holds_what_no_text_can_be_made_of_is_a_no_and_not_an_error(
    browser: AccountChrome, served: list[Site]
) -> None:
    """Found by the re-read: a page can put in its field half of a character — a lone surrogate
    —, which cannot be turned into bytes to be compared. It is a field that does not hold what
    was typed: an answer, and not an error that would carry the field in it. *Measured here, on
    2026-10-13*: this driver hands such a half over as a character of replacement, so the
    comparison never meets one on this road — and it does not rest on that
    (``test_account_profile.py`` hands it one)."""
    web = site(served, {"/": (200, {}, LOGIN)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "#user", Secret("mario"))
    await browser._pages[opened.page].page.evaluate(
        "document.querySelector('#user').value = 'mario' + String.fromCharCode(0xD800)"
    )

    assert await browser.holds(opened.page, "#user", Secret("mario")) is False


async def test_a_field_that_keeps_less_than_it_is_given_does_not_hold_what_was_typed(
    browser: AccountChrome, served: list[Site]
) -> None:
    """A limit that is declared, held here so that it is seen: a field with a length of its own
    keeps the beginning of what is typed into it, and the comparison is whole. A login on such a
    page ends ``browser.field_changed`` and is not sent (ADR 0063 §5; question 152 of M13.9)."""
    short = (
        '<form method="post" action="/in"><input id="word" type="password" maxlength="5"></form>'
    )
    web = site(served, {"/": (200, {}, short)})
    opened = await browser.open(web.origin + "/", everywhere, FakeStop())
    await browser.fill_secret(opened.page, "#word", Secret(SENTINEL))

    assert await browser.holds(opened.page, "#word", Secret(SENTINEL)) is False
    assert await browser.holds(opened.page, "#word", Secret(SENTINEL[:5])) is True
