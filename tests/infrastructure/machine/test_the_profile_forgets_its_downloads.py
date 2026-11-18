"""The browser of the profile forgets the downloads it remembers, before every guided launch
(M13.13c, ADR 0073).

**The trigger, measured** (``docs/milestones/M13.13c.md``, the measures of decisions 104 and 114):
Chrome for Testing 153 falls at a new download when, at its launch, ``Default/History`` holds
downloads that completed — with ELA's tool from the second to the fourth download on a test
profile, with or without the window; with Playwright's own download, without ELA's door, at the
third or the seventh. The rows of the three tables of the downloads taken out before each launch,
it does not fall: zero crashes in sixty runs on new profiles, and the three profiles that had
already fallen work again. The browser puts the rows back by itself at its launch (measured; from
where is read, not measured): what ELA takes away is what the history holds **at the launch**.

What ELA does, and only that (decision 116): before a guided launch, with the folder free, the rows
of :data:`~ela.infrastructure.machine.account.DOWNLOAD_TABLES` deleted **without reading one**; no
other table; never through a link; nothing done when the tables are not the ones expected, and then
the launch goes on and the reason is said, with its type and never a path (decision 112). A history
that is not there — a new profile — is no error.

**The tests on the real binary** build the trigger as it was measured, completed downloads in the
history at the launch, and are red on the code before (``m13.13c/rossi-prima.txt`` in the workshop):
there the browser falls, and the system may write a crash report of Chrome for Testing — the one way
to show the defect on the binary, and only in that red run (decision 117). Green, nothing falls.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import sqlite3
import tempfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Final

import pytest
from playwright.async_api._context_manager import PlaywrightContextManager

from ela.infrastructure.machine import account as adapter
from ela.infrastructure.machine.account import DOWNLOAD_TABLES, HISTORY_FILE, AccountChrome
from ela.permissions import BROWSER_DOWNLOAD_AS_YOU
from ela.testing.fakes import FakeIdGenerator, FakeStop, FakeTaskPages
from ela.tools.browser_files import AccountDownloadTool
from tests.infrastructure.machine import test_account_browser as account
from tests.infrastructure.machine import test_the_boundary as bounds
from tests.infrastructure.machine.test_browser import CLOCK, decision
from tests.infrastructure.machine.test_the_files_of_a_page import SITE, browsing, root

profile = account.profile
nothing_left_behind = bounds.nothing_left_behind

FILE: Final = bytes(range(256)) * 8
"""2048 bytes, as the file of the measures."""
COOKIE: Final = "ela_accesso=1"
SENTINEL: Final = "https://sentinella.example/"
"""A row of another table of the history, ``urls``: it stays (decision 116)."""
SQLITE_DELETE: Final = 9
SQLITE_READ: Final = 20
SCHEMA: Final = frozenset({"sqlite_master", "sqlite_schema", "sqlite_temp_master"})


# ----------------------------------------------------------------------------------------------
# A site of the test, that gives a cookie and says whether it came back
# ----------------------------------------------------------------------------------------------


class Site:
    """Gives its file at any address, with a cookie that lasts a day; ``carried`` says, request
    by request, whether the cookie came with it."""

    def __init__(self) -> None:
        self.carried: list[bool] = []
        site = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                site.carried.append(COOKIE in (self.headers.get("Cookie") or ""))
                if self.path.startswith("/link"):
                    body = b'<!doctype html><a id="f" href="/file.bin" download>file</a>'
                    kind = "text/html"
                else:
                    body, kind = FILE, "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Set-Cookie", f"{COOKIE}; Max-Age=86400; Path=/")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://localhost:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def site() -> Iterator[Site]:
    made = Site()
    yield made
    made.server.shutdown()
    made.server.server_close()


def completed(profile: Path) -> int:
    """The completed downloads the history of a test profile holds, read on a copy: the
    precondition of the tests, read by the test and never by ELA."""
    history = profile.joinpath(*HISTORY_FILE)
    if not history.exists():
        return 0
    folder = Path(tempfile.mkdtemp())
    try:
        for one in history.parent.glob("History*"):
            shutil.copy(one, folder / one.name)
        with contextlib.closing(sqlite3.connect(folder / "History")) as database:
            (count,) = database.execute("select count(*) from downloads where state = 1").fetchone()
        return int(count)
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def sentinel_kept(profile: Path) -> bool:
    with contextlib.closing(sqlite3.connect(profile.joinpath(*HISTORY_FILE))) as database:
        found = database.execute("select count(*) from urls where url = ?", (SENTINEL,)).fetchone()
    return bool(found[0])


def sentinel_written(profile: Path) -> None:
    with contextlib.closing(sqlite3.connect(profile.joinpath(*HISTORY_FILE))) as database:
        database.execute(
            "insert into urls (url, title, visit_count, typed_count, last_visit_time, hidden) "
            "values (?, 'sentinella', 1, 0, 0, 0)",
            (SENTINEL,),
        )
        database.commit()


async def downloads(
    browser: AccountChrome, origin: str, under: Path, count: int, *, first: int = 1
) -> None:
    """``count`` downloads with the tool of ``browser.download_as_you``, one after the other on the
    same profile, each a launch of its own; each must succeed, and from the second the history
    holds completed downloads when it is asked for — the trigger, built."""
    tool = AccountDownloadTool(
        under,
        browsing(origin, 30),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    for number in range(first, first + count):
        if number > 1:
            assert completed(browser._profile) >= 1, "the trigger is not built"  # noqa: SLF001
        arguments = {
            "site": SITE,
            "path": f"/file-{number}.bin",
            "file": f"ELA/scaricati/{number:02d}.bin",
            "overwrite": False,
            "purpose": "la prova di M13.13c",
        }
        prospect = await tool.prospect(arguments)
        assert prospect.refusal is None, prospect.refusal
        result = await tool.execute(
            decision(BROWSER_DOWNLOAD_AS_YOU), arguments, FakeStop(), prospect.named or {}
        )
        assert result.error is None, f"download {number}: {result.error}"


# ----------------------------------------------------------------------------------------------
# The binary: the criteria of decision 105
# ----------------------------------------------------------------------------------------------


@bounds.ON_A_MAC
async def test_a_profile_that_had_ten_downloads_of_ela_downloads_the_next(
    profile: Path, site: Site, tmp_path: Path, nothing_left_behind: None
) -> None:
    """Criterion 1: on a profile that has had ten downloads of ELA's, the eleventh succeeds — and
    the files stay, a row of another table of the history stays, and the access to the site stays:
    its cookie comes back at every launch after the first."""
    browser = account.chrome(profile)
    under = root(tmp_path)
    await downloads(browser, site.origin, under, 1)
    sentinel_written(profile)

    await downloads(browser, site.origin, under, 10, first=2)

    assert sorted(path.name for path in (under / "ELA" / "scaricati").iterdir()) == [
        f"{number:02d}.bin" for number in range(1, 12)
    ]
    assert sentinel_kept(profile)
    assert site.carried[0] is False and all(site.carried[1:]), site.carried


@bounds.ON_A_MAC
async def test_a_profile_already_in_the_state_that_makes_the_browser_fall_works_again(
    profile: Path, site: Site, tmp_path: Path, nothing_left_behind: None
) -> None:
    """Criterion 2: a profile whose history already holds a completed download — made here by
    Playwright's own download, on the same binary with ELA's arguments, as the measure A7 did —
    works again with ELA: the ten downloads after it succeed. The state is built by a download
    and not by a crash, which would write a report of the system at every green run (decision
    117)."""
    browser = account.chrome(profile)
    profile.mkdir(mode=0o700, exist_ok=True)
    adapter._prepared(profile, driven=False)  # noqa: SLF001 — the window's preparation: no S1
    options = browser._launch()  # noqa: SLF001
    options["accept_downloads"] = True
    async with PlaywrightContextManager() as playwright:
        context = await playwright.chromium.launch_persistent_context(str(profile), **options)
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(site.origin + "/link")
        async with page.expect_download() as info:
            await page.click("#f")
        assert await (await info.value).failure() is None
        await context.close()
    assert completed(profile) >= 1, "the state is not built"

    await downloads(browser, site.origin, root(tmp_path), 10)


# ----------------------------------------------------------------------------------------------
# The operation: what it takes away, what it never reads, what it leaves
# ----------------------------------------------------------------------------------------------


def a_history(profile: Path) -> Path:
    """A history with the three tables of the downloads, each with a row, and ``urls`` with the
    sentinel: the shape of the binary's, for the columns the operation never names."""
    history = profile.joinpath(*HISTORY_FILE)
    history.parent.mkdir(parents=True, mode=0o700)
    with contextlib.closing(sqlite3.connect(history)) as database:
        database.executescript(
            "create table downloads (id integer primary key, guid text, target_path text,"
            " state integer);"
            "create table downloads_url_chains (id integer, chain_index integer, url text);"
            "create table downloads_slices (download_id integer, offset integer,"
            " received_bytes integer);"
            "create table urls (id integer primary key, url text);"
            "insert into downloads values (1, 'g', '/una/cartella/il-file', 1);"
            "insert into downloads_url_chains values (1, 0, 'https://sito.example/il-file');"
            "insert into downloads_slices values (1, 0, 10);"
            f"insert into urls (url) values ('{SENTINEL}');"
        )
    return history


def rows(history: Path) -> dict[str, int]:
    with contextlib.closing(sqlite3.connect(history)) as database:
        return {
            table: database.execute(f"select count(*) from {table}").fetchone()[0]  # noqa: S608
            for table in (*DOWNLOAD_TABLES, "urls")
        }


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    made = tmp_path / "profilo"
    made.mkdir(mode=0o700)
    return made


def test_a_guided_launch_takes_the_downloads_out_of_the_history_and_nothing_else(
    folder: Path,
) -> None:
    history = a_history(folder)

    assert adapter._prepared(folder, driven=True) is None  # noqa: SLF001

    assert rows(history) == {
        "downloads": 0,
        "downloads_url_chains": 0,
        "downloads_slices": 0,
        "urls": 1,
    }


def test_the_launch_of_the_window_leaves_the_history_as_it_is(folder: Path) -> None:
    """Decision 116: before a guided launch — the window is not one, and it does not download."""
    history = a_history(folder)

    adapter._prepared(folder, driven=False)  # noqa: SLF001

    assert rows(history) == {
        "downloads": 1,
        "downloads_url_chains": 1,
        "downloads_slices": 1,
        "urls": 1,
    }


def test_no_row_is_read_and_only_the_three_tables_are_deleted_from(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Decision 116: the rows are deleted without being read — the database says what each
    statement does, through its authorizer, and nothing reads a column of a table of the history."""
    a_history(folder)
    done: list[tuple[int, str | None]] = []
    connect = sqlite3.connect

    def watched(*args: Any, **options: Any) -> sqlite3.Connection:
        made = connect(*args, **options)

        def told(action: int, first: str | None, *_: object) -> int:
            done.append((action, first))
            return sqlite3.SQLITE_OK

        made.set_authorizer(told)
        return made

    monkeypatch.setattr(adapter.sqlite3, "connect", watched)

    adapter._prepared(folder, driven=True)  # noqa: SLF001

    deleted = {table for action, table in done if action == SQLITE_DELETE}
    read = {table for action, table in done if action == SQLITE_READ} - SCHEMA
    assert deleted == set(DOWNLOAD_TABLES), done
    assert read == set(), done


def test_a_profile_with_no_history_yet_is_no_error_and_gets_none(folder: Path) -> None:
    assert adapter._prepared(folder, driven=True) is None  # noqa: SLF001
    assert not folder.joinpath(*HISTORY_FILE).exists()


def test_a_history_that_is_a_link_is_not_followed_and_the_reason_has_no_path(
    folder: Path, tmp_path: Path
) -> None:
    elsewhere = a_history(tmp_path / "altrove")
    (folder / HISTORY_FILE[0]).mkdir(mode=0o700)
    folder.joinpath(*HISTORY_FILE).symlink_to(elsewhere)

    said = adapter._prepared(folder, driven=True)  # noqa: SLF001

    assert rows(elsewhere)["downloads"] == 1
    assert said is not None and str(tmp_path) not in said and "/" not in said


def test_tables_that_are_not_the_expected_ones_leave_everything_as_it_was(folder: Path) -> None:
    """One of the three is missing — a binary that changed them —: nothing is taken away, not even
    from the two that are there, and the reason is the type of what stopped it."""
    history = a_history(folder)
    with contextlib.closing(sqlite3.connect(history)) as database:
        database.execute("drop table downloads_slices")

    said = adapter._prepared(folder, driven=True)  # noqa: SLF001

    with contextlib.closing(sqlite3.connect(history)) as database:
        assert database.execute("select count(*) from downloads").fetchone()[0] == 1
        assert database.execute("select count(*) from downloads_url_chains").fetchone()[0] == 1
    assert said == "OperationalError"


async def test_the_reason_is_told_and_the_launch_is_not_refused(folder: Path) -> None:
    """Decision 112: the adapter tells who the composition named, and goes on."""
    a_history(folder)
    with contextlib.closing(sqlite3.connect(folder.joinpath(*HISTORY_FILE))) as database:
        database.execute("drop table downloads_slices")
    told: list[str] = []
    browser = AccountChrome(
        asyncio.Event(),
        environment={},
        kept=lambda: asyncio.sleep(0),
        system="Darwin",
        profile=folder,
        shown=lambda: False,
        closing=1.0,
        unforgotten=told.append,
    )

    await browser._prepare(folder, driven=True)  # noqa: SLF001

    assert told == ["OperationalError"]
