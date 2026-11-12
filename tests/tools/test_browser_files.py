"""The files from the browser (M13.13, ADR 0066), with the fakes: **a download is judged as
an ``fs.write``, an upload as an ``fs.read``, and the question names the file**.

Four capabilities, all ``HIGH``: ``browser.download`` and ``browser.upload`` on the empty browser,
``browser.download_as_you`` and ``browser.upload_as_you`` on the browser with the profile — their
own, because a consent is not inherited (ADR 0034). The scope is ``ELA_FS_SCOPE`` on ``file``; the
site is the boundary of the tool, and one that is not declared is refused **before the question**
(X11).

* **Every refusal before the question**, with no yes spent (ADR 0045 §6-bis): the form, the site,
  the browser, the root, and the file with the classification ``fs`` shares — a download refuses
  what ``fs.write`` refuses, with ``overwrite`` an assertion both ways; an upload what ``fs.read``
  refuses, and a file over the 50 MiB Playwright gives a page (answer 20).
* **An upload**: the question names the resolved path, the size and the sha256; after the yes ELA
  reads the bytes itself again — a file changed meanwhile does not leave (``browser.file_changed``)
  —, gives the page **the bytes and the name**, never the path, as the first gesture, and the page
  holds a file from then on.
* **A download**: the browser writes under a name the site does not choose, in the folder of the
  target; the file takes the plan's name, and **600** — also when it replaces one.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from ela.domain import (
    DecisionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
    StepId,
    TaskId,
)
from ela.permissions import (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
    production_catalogue,
)
from ela.ports import (
    DOWNLOAD_GESTURE,
    BrowserFailed,
    BrowserNotInstalled,
    BrowserStopped,
    Downloaded,
    GivenFile,
    SiteUnreachable,
    ToolStopped,
)
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeTaskPages,
)
from ela.tools import browser_files
from ela.tools.base import ARGUMENTS_INVALID
from ela.tools.browser import (
    DOWNLOAD_REFUSED,
    ELEMENT_AMBIGUOUS,
    FAILED,
    LEFT_SITE,
    NOT_INSTALLED,
    STOPPED,
    TIMEOUT,
    UNREACHABLE,
    BrowserActTool,
    Browsing,
)
from ela.tools.browser_files import (
    DOWNLOAD_NOT_STARTED,
    FILE_CHANGED,
    FILE_DOWNLOADED,
    FILE_MISMATCH,
    FILE_TOO_LARGE,
    FILE_UNREADABLE,
    NOT_A_FILE_FIELD,
    SITE_NOT_DECLARED,
    UPLOAD_MAX_BYTES,
    AccountDownloadTool,
    AccountFileDownloadedVerifier,
    AccountUploadTool,
    AccountUploadVerifier,
    BrowserDownloadTool,
    BrowserUploadTool,
    FileDownloadedVerifier,
    UploadVerifier,
)
from ela.tools.fs import (
    ELA_S_OWN,
    HARD_LINK,
    IO_ERROR,
    NO_ROOT,
    OVERWRITE_MISMATCH,
    FsReadTool,
    FsWriteTool,
)
from ela.tools.paths import (
    PATH_INVALID,
    PATH_IS_DIRECTORY,
    PATH_MISSING,
    PATH_OUTSIDE_ROOT,
    PATH_SYMLINK,
)
from tests.tools.test_verifiers import succeeded

CLOCK = FakeClock()
SITES = Browsing(sites=("httpbin.org", "testpages.eviltester.com"))
BYTES = b"il file della prova, con un testo neutro\n"
DOWNLOAD = {
    "site": "httpbin.org",
    "path": "/bytes/1024",
    "file": "ELA/prova/scaricato.bin",
    "overwrite": False,
    "purpose": "la prova",
}
UPLOAD = {
    "site": "testpages.eviltester.com",
    "path": "/pages/files/file-upload/",
    "file": "ELA/prova/da-caricare.txt",
    "file_field": "#fileinput",
    "click": "input[name=upload]",
    "expect_text": "Upload successful!",
    "purpose": "la prova",
}


def decision(capability: str) -> PermissionDecision:
    return PermissionDecision(
        id=DecisionId(FakeIdGenerator().new_uuid()),
        created_at=CLOCK.now(),
        capability_id=capability,  # type: ignore[arg-type]
        risk=RiskLevel.HIGH,
        outcome=PermissionOutcome.ALLOWED,
        reason="allowed for this test",
        expires_at=CLOCK.now() + timedelta(minutes=5),
    )


def root(tmp_path: Path) -> Path:
    made = tmp_path / "root"
    (made / "ELA" / "prova").mkdir(parents=True)
    return made


def download(
    browser: FakeBrowser,
    folder: Path,
    *,
    profile: bool = False,
    protected: dict[str, Path] | None = None,
) -> BrowserDownloadTool | AccountDownloadTool:
    kind = AccountDownloadTool if profile else BrowserDownloadTool
    return kind(  # type: ignore[arg-type]
        folder,
        SITES,
        browser,
        CLOCK,
        FakeIdGenerator(),
        protected={} if protected is None else protected,
        pages=FakeTaskPages(),
    )


def upload(
    browser: FakeBrowser, folder: Path, *, profile: bool = False
) -> BrowserUploadTool | AccountUploadTool:
    kind = AccountUploadTool if profile else BrowserUploadTool
    return kind(folder, SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())  # type: ignore[arg-type]


def with_(arguments: dict[str, Any], **changed: Any) -> dict[str, Any]:
    return {**arguments, **changed}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ----------------------------------------------------------------------------------------
# The catalogue
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "capability", [BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU, BROWSER_UPLOAD, BROWSER_UPLOAD_AS_YOU]
)
def test_the_four_are_high_their_scope_is_the_file_and_none_continues(capability: str) -> None:
    spec = production_catalogue(fs_scope="ELA", sites=("httpbin.org",)).get(capability)  # type: ignore[arg-type]

    assert spec.risk is RiskLevel.HIGH and spec.requires_authorization
    assert spec.scope == ("ELA",) and spec.scoped_arguments == ("file",)
    assert "continues" not in spec.input_schema["properties"]
    assert "file" in spec.input_schema["required"] and "path" in spec.input_schema["required"]


# ----------------------------------------------------------------------------------------
# Before the question, with no yes spent
# ----------------------------------------------------------------------------------------


async def test_a_site_that_is_not_declared_is_refused_before_the_question(tmp_path: Path) -> None:
    tool = download(FakeBrowser(), root(tmp_path))

    prospect = await tool.prospect(with_(DOWNLOAD, site="altro.example"))

    assert prospect.refusal is not None and prospect.refusal.code == SITE_NOT_DECLARED


@pytest.mark.parametrize(
    ("file", "leads_to", "code"),
    [
        ("../fuori.bin", None, PATH_INVALID),
        ("ELA/prova", None, PATH_IS_DIRECTORY),
        ("ELA/link.bin", "ELA/prova/vero.bin", PATH_SYMLINK),
        ("ELA/link.bin", "../elsewhere", PATH_OUTSIDE_ROOT),
    ],
)
async def test_a_download_refuses_what_fs_write_refuses(
    tmp_path: Path, file: str, leads_to: str | None, code: str
) -> None:
    """**With the code ``fs.write`` gives**, asked of ``fs.write`` itself on the same disk: the
    codes written here are what it answers, and the day it answers another this says so. *Three of
    the codes the red test of 2026-11-03 expected were wrong*: a path with ``..`` is refused by
    the grammar, and a link that leads outside the root is outside the root."""
    folder = root(tmp_path)
    if leads_to is not None:
        (folder / "ELA" / "prova" / "vero.bin").write_bytes(b"c'era")
        (folder / "ELA" / "link.bin").symlink_to(folder / leads_to)
    as_a_write = await FsWriteTool(folder, CLOCK, FakeIdGenerator(), protected={}).prospect(
        {"path": file, "body": "", "overwrite": False}
    )

    prospect = await download(FakeBrowser(), folder).prospect(with_(DOWNLOAD, file=file))

    assert prospect.refusal is not None and prospect.refusal.code == code
    assert as_a_write.refusal is not None and as_a_write.refusal.code == code


@pytest.mark.parametrize(("there", "overwrite"), [(True, False), (False, True)])
async def test_overwrite_is_an_assertion_on_the_world_both_ways(
    tmp_path: Path, there: bool, overwrite: bool
) -> None:
    folder = root(tmp_path)
    if there:
        (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(b"c'era")

    prospect = await download(FakeBrowser(), folder).prospect(with_(DOWNLOAD, overwrite=overwrite))

    assert prospect.refusal is not None and prospect.refusal.code == OVERWRITE_MISMATCH


@pytest.mark.parametrize("profile", [False, True], ids=["empty", "as-you"])
@pytest.mark.parametrize("what", ["ela_s_own", "hard_link"])
async def test_a_download_refuses_what_ela_uses_to_exist_and_a_file_with_two_names(
    tmp_path: Path, profile: bool, what: str
) -> None:
    """A download is a write (M13.14, ADR 0068): the list of the places no write reaches, and a
    file with more than one name, refused before the question and before the gesture — the
    browser never opened, nothing arrived."""
    folder = root(tmp_path)
    landing = folder / "ELA" / "prova" / "scaricato.bin"
    protected: dict[str, Path] = {}
    arguments = DOWNLOAD
    if what == "ela_s_own":
        protected["the database"] = folder / "ELA" / "prova"
        code = ELA_S_OWN
    else:
        landing.write_bytes(b"c'era")
        os.link(landing, folder / "ELA" / "secondo.bin")
        arguments = with_(DOWNLOAD, overwrite=True)
        code = HARD_LINK
    browser = (FakeAccountBrowser if profile else FakeBrowser)(FakePage(download=BYTES))
    tool = download(browser, folder, profile=profile, protected=protected)

    asked = await tool.prospect(arguments)
    result = await tool.execute(
        decision(BROWSER_DOWNLOAD_AS_YOU if profile else BROWSER_DOWNLOAD), arguments, FakeStop()
    )

    assert asked.refusal is not None and asked.refusal.code == code
    assert result.error is not None and result.error.code == code
    assert code in tool.error_codes
    assert browser.opened == [] and browser.downloads == []
    assert not landing.exists() or landing.read_bytes() == b"c'era"


async def test_without_a_root_nothing_is_asked(tmp_path: Path) -> None:
    prospect = await download(FakeBrowser(), tmp_path / "missing").prospect(DOWNLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == NO_ROOT


@pytest.mark.parametrize(
    ("make", "code"),
    [
        ("missing", PATH_MISSING),
        ("directory", PATH_IS_DIRECTORY),
        ("link", PATH_SYMLINK),
        ("link outside", PATH_OUTSIDE_ROOT),
    ],
)
async def test_an_upload_refuses_what_fs_read_refuses(tmp_path: Path, make: str, code: str) -> None:
    """With the code ``fs.read`` gives, asked of ``fs.read`` itself on the same disk."""
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "da-caricare.txt"
    if make == "directory":
        target.mkdir()
    elif make == "link":
        (folder / "ELA" / "vero.txt").write_bytes(BYTES)
        target.symlink_to(folder / "ELA" / "vero.txt")
    elif make == "link outside":
        (tmp_path / "vero.txt").write_bytes(BYTES)
        target.symlink_to(tmp_path / "vero.txt")
    as_a_read = await FsReadTool(folder, CLOCK, FakeIdGenerator()).prospect(
        {"path": UPLOAD["file"]}
    )

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == code
    assert as_a_read.refusal is not None and as_a_read.refusal.code == code


async def test_bytes_that_are_not_text_are_uploaded(tmp_path: Path) -> None:
    """Answer 19: what ``fs.read`` refuses is its root and its classification — the refusal of a
    text that is not UTF-8 stays ``fs.read``'s, whose text enters a result. A PDF is uploaded."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(b"%PDF-1.7\n\xff\xfe\x00 binario")

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is None


async def test_a_file_over_the_limit_a_page_takes_is_refused_before_the_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Answer 20: Playwright gives a page at most 50 MiB as bytes, and a question is composed only
    for what would succeed now. A sparse file: **its size is asked of the disk, and not one byte of
    it is read** — the reading of this test says who asked for it."""
    folder = root(tmp_path)
    with (folder / "ELA" / "prova" / "da-caricare.txt").open("wb") as big:
        big.truncate(UPLOAD_MAX_BYTES + 1)
    read: list[Path] = []
    monkeypatch.setattr(browser_files, "read_bytes", lambda target: read.append(target) or b"")

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == FILE_TOO_LARGE
    assert read == [], "a file over the limit was read to learn its size"


# ----------------------------------------------------------------------------------------
# The question
# ----------------------------------------------------------------------------------------


async def test_the_question_of_a_download_names_the_file_and_the_site(tmp_path: Path) -> None:
    folder = root(tmp_path)

    prospect = await download(FakeBrowser(), folder).prospect(DOWNLOAD)

    assert prospect.target is not None and prospect.visit is not None
    assert prospect.target.resolved == str(folder / "ELA" / "prova" / "scaricato.bin")
    assert prospect.target.exists is False and "download" in prospect.target.does
    assert prospect.visit.site == "httpbin.org"
    assert prospect.visit.address == "https://httpbin.org/bytes/1024"


async def test_the_question_of_an_upload_names_the_path_the_size_and_the_imprint(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.target is not None
    assert prospect.target.resolved == str(folder / "ELA" / "prova" / "da-caricare.txt")
    assert (prospect.target.size, prospect.target.digest) == (len(BYTES), digest(BYTES))
    assert prospect.named == {"size": len(BYTES), "digest": digest(BYTES)}


# ----------------------------------------------------------------------------------------
# The upload
# ----------------------------------------------------------------------------------------


async def asked_and_run(
    tool: Any, arguments: dict[str, Any], capability: str, *, changed: bytes | None = None
) -> ExecutionResult:
    prospect = await tool.prospect(arguments)
    assert prospect.refusal is None, prospect.refusal
    if changed is not None:
        target = Path(prospect.target.resolved)
        target.write_bytes(changed)
    return await tool.execute(decision(capability), arguments, FakeStop(), prospect.named or {})


@pytest.mark.parametrize(
    ("profile", "capability"), [(False, BROWSER_UPLOAD), (True, BROWSER_UPLOAD_AS_YOU)]
)
async def test_an_upload_gives_the_page_the_bytes_and_the_name_first_and_then_clicks(
    tmp_path: Path, profile: bool, capability: str
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = (FakeAccountBrowser if profile else FakeBrowser)(
        FakePage(fields={"#fileinput": _file_field()})
    )

    result = await asked_and_run(upload(browser, folder, profile=profile), UPLOAD, capability)

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert browser.given == [("#fileinput", GivenFile("da-caricare.txt", "text/plain", BYTES))]
    assert browser.clicks == ["input[name=upload]"]
    assert result.output["gestures"] == 2
    assert str(folder) not in repr(browser.given), "the page never receives the path"


@pytest.mark.parametrize(
    "changed",
    [BYTES + b"cambiato", BYTES[:-1] + bytes([BYTES[-1] ^ 1])],
    ids=["longer", "the same size, one bit of it"],
)
async def test_a_file_changed_between_the_question_and_the_yes_does_not_leave(
    tmp_path: Path, changed: bytes
) -> None:
    """By its size **or** by its sha256: a file of the same length is another file."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))

    result = await asked_and_run(upload(browser, folder), UPLOAD, BROWSER_UPLOAD, changed=changed)

    assert result.error is not None and result.error.code == FILE_CHANGED
    assert browser.given == [] and browser.opened == [], "nothing was opened, nothing given"


async def test_a_field_that_is_not_a_file_field_receives_nothing(tmp_path: Path) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _text_field()}))

    result = await asked_and_run(upload(browser, folder), UPLOAD, BROWSER_UPLOAD)

    assert result.error is not None and result.error.code == NOT_A_FILE_FIELD
    assert browser.given == [] and result.output.get("gestures") == 0


async def test_an_upload_without_a_click_gives_the_file_and_ends(tmp_path: Path) -> None:
    """For a page that uploads when the file is given (answer 22): ``click`` is optional."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    arguments = {key: value for key, value in UPLOAD.items() if key != "click"}

    result = await asked_and_run(upload(browser, folder), arguments, BROWSER_UPLOAD)

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert browser.clicks == [] and result.output["gestures"] == 1


async def test_a_stop_before_the_file_gives_nothing_and_counts_no_gesture(tmp_path: Path) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    prospect = await tool.prospect(UPLOAD)
    from ela.ports import NAVIGATION

    stop = FakeStop(after=NAVIGATION)  # stopped right after the page opened, before the file

    with pytest.raises(ToolStopped):
        await tool.execute(decision(BROWSER_UPLOAD), UPLOAD, stop, prospect.named or {})

    assert browser.given == []
    assert stop.listened[-1] == "the first gesture", "giving the file is the tool's point"


# ----------------------------------------------------------------------------------------
# The download
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("profile", "capability"), [(False, BROWSER_DOWNLOAD), (True, BROWSER_DOWNLOAD_AS_YOU)]
)
async def test_a_download_ends_under_the_plan_s_name_with_600(
    tmp_path: Path, profile: bool, capability: str
) -> None:
    folder = root(tmp_path)
    browser = (FakeAccountBrowser if profile else FakeBrowser)(FakePage(download=BYTES))

    result = await asked_and_run(download(browser, folder, profile=profile), DOWNLOAD, capability)

    target = folder / "ELA" / "prova" / "scaricato.bin"
    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert target.read_bytes() == BYTES and stat.S_IMODE(target.stat().st_mode) == 0o600
    assert result.output["file"] == "ELA/prova/scaricato.bin"
    assert (result.output["size"], result.output["digest"]) == (len(BYTES), digest(BYTES))
    assert os.listdir(target.parent) == ["scaricato.bin"], "nothing else in the folder"


async def test_a_download_that_replaces_a_file_leaves_it_600_too(tmp_path: Path) -> None:
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "scaricato.bin"
    target.write_bytes(b"c'era")
    target.chmod(0o644)
    browser = FakeBrowser(FakePage(download=BYTES))

    result = await asked_and_run(
        download(browser, folder), with_(DOWNLOAD, overwrite=True), BROWSER_DOWNLOAD
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert target.read_bytes() == BYTES and stat.S_IMODE(target.stat().st_mode) == 0o600


async def test_a_download_that_does_not_start_writes_nothing(tmp_path: Path) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=None))

    result = await asked_and_run(download(browser, folder), DOWNLOAD, BROWSER_DOWNLOAD)

    assert result.error is not None and result.error.code == DOWNLOAD_NOT_STARTED
    assert os.listdir(folder / "ELA" / "prova") == []


async def test_a_download_with_a_click_downloads_from_the_page_the_path_opens(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))

    result = await asked_and_run(
        download(browser, folder), with_(DOWNLOAD, path="/links", click="a#file"), BROWSER_DOWNLOAD
    )

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert browser.opened == ["https://httpbin.org/links"]
    assert browser.downloads == [("a#file", str(folder / "ELA" / "prova"))]


def test_the_point_of_a_download_is_the_gesture_that_starts_it() -> None:
    assert BrowserDownloadTool.stop_point.here == DOWNLOAD_GESTURE
    assert Downloaded("a-guid").name == "a-guid"


# ----------------------------------------------------------------------------------------
# A download nobody asked for, said by every tool of the browser
# ----------------------------------------------------------------------------------------


async def test_a_download_nobody_asked_for_is_said_with_its_origin_and_fails_nothing() -> None:
    browser = FakeBrowser(FakePage(download_refused="https://httpbin.org/bytes/16"))
    act = BrowserActTool(SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())
    arguments = {
        "site": "httpbin.org",
        "path": "/forms/post",
        "fill": [],
        "click": "form button",
        "expect_text": "x",
        "purpose": "la prova",
    }

    result = await act.execute(decision("browser.act"), arguments, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert result.output[DOWNLOAD_REFUSED] == "https://httpbin.org"


# ----------------------------------------------------------------------------------------
# The verifier
# ----------------------------------------------------------------------------------------


async def test_the_verifier_finds_the_file_the_result_says(tmp_path: Path) -> None:
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "scaricato.bin"
    target.write_bytes(BYTES)
    said = {"file": "ELA/prova/scaricato.bin", "size": len(BYTES), "digest": digest(BYTES)}

    failures = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert failures == ()


async def test_the_verifier_fails_in_sizes_on_another_file(tmp_path: Path) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(b"un altro")
    said = {"file": "ELA/prova/scaricato.bin", "size": len(BYTES), "digest": digest(BYTES)}

    (failure,) = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert digest(BYTES) not in failure.message, "sizes, not hashes (ADR 0045 §8)"
    assert str(len(BYTES)) in failure.message


async def test_the_verifier_fails_on_a_file_that_is_not_there(tmp_path: Path) -> None:
    folder = root(tmp_path)
    said = {"file": "ELA/prova/scaricato.bin", "size": len(BYTES), "digest": digest(BYTES)}

    (failure,) = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert failure.code == PATH_MISSING, "judged with the classification fs shares, then read"


def _file_field() -> Any:
    from ela.ports import Field

    return Field("file", "")


def _text_field() -> Any:
    from ela.ports import Field

    return Field("text", "")


# ----------------------------------------------------------------------------------------
# Every way a download can fall
# ----------------------------------------------------------------------------------------

TASK = TaskId(UUID("00000000-0000-4000-8000-00000000d0d0"))
STEP = StepId(UUID("00000000-0000-4000-8000-00000000d0d1"))


def of_a_task(capability: str) -> PermissionDecision:
    return decision(capability).model_copy(update={"task_id": TASK, "step_id": STEP})


@pytest.mark.parametrize(
    "wrong",
    [{"file": 7}, {"file": ""}, {"overwrite": "no"}, {"click": ">> x"}, {"continues": True}],
    ids=[
        "a file that is no text",
        "no file",
        "an overwrite that is no boolean",
        "a click",
        "continues",
    ],
)
async def test_a_download_whose_shape_is_wrong_is_refused_before_the_question_and_after_the_yes(
    tmp_path: Path, wrong: dict[str, Any]
) -> None:
    browser = FakeBrowser(FakePage(download=BYTES))
    tool = download(browser, root(tmp_path))
    arguments = with_(DOWNLOAD, **wrong)

    prospect = await tool.prospect(arguments)
    result = await tool.execute(decision(BROWSER_DOWNLOAD), arguments, FakeStop())

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert browser.opened == [] and browser.downloads == []


async def test_a_file_that_appears_between_the_question_and_the_yes_is_not_replaced(
    tmp_path: Path,
) -> None:
    """``overwrite`` is an assertion on the world after the yes too: nothing is opened."""
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    tool = download(browser, folder)
    prospect = await tool.prospect(DOWNLOAD)
    assert prospect.refusal is None
    (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(b"arrivato intanto")

    result = await tool.execute(decision(BROWSER_DOWNLOAD), DOWNLOAD, FakeStop())

    assert result.error is not None and result.error.code == OVERWRITE_MISMATCH
    assert browser.opened == [] and browser.downloads == []
    assert (folder / "ELA" / "prova" / "scaricato.bin").read_bytes() == b"arrivato intanto"


async def test_a_download_closes_first_the_page_its_task_keeps(tmp_path: Path) -> None:
    pages = FakeTaskPages()
    tool = BrowserDownloadTool(
        root(tmp_path),
        SITES,
        FakeBrowser(FakePage(download=BYTES)),
        CLOCK,
        FakeIdGenerator(),
        protected={},
        pages=pages,
    )

    result = await tool.execute(of_a_task(BROWSER_DOWNLOAD), DOWNLOAD, FakeStop())

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert pages.released == [TASK]


@pytest.mark.parametrize("click", [None, "a#file"], ids=["the address", "a click"])
async def test_a_folder_that_cannot_be_made_ends_the_step_before_the_gesture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, click: str | None
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    tool = download(browser, folder)
    arguments = with_(
        DOWNLOAD, file="ELA/nuova/scaricato.bin", **({} if click is None else {"click": click})
    )

    def refuses(self: Path, *args: Any, **named: Any) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "mkdir", refuses)
    result = await tool.execute(decision(BROWSER_DOWNLOAD), arguments, FakeStop())

    assert result.error is not None and result.error.code == IO_ERROR
    assert "PermissionError" in result.error.message and result.output["gestures"] == 0
    assert browser.downloads == []


@pytest.mark.parametrize(
    ("fell", "code"),
    [
        (BrowserFailed("the browser fell"), FAILED),
        (BrowserStopped("ELA is stopping"), STOPPED),
        (BrowserNotInstalled("not there"), NOT_INSTALLED),
        (SiteUnreachable("ConnectionRefused"), UNREACHABLE),
    ],
)
async def test_a_download_from_an_address_falls_in_the_ways_a_page_falls(
    tmp_path: Path, fell: Exception, code: str
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    browser.raising["downloaded_from"] = fell

    result = await asked_and_run(download(browser, folder), DOWNLOAD, BROWSER_DOWNLOAD)

    assert result.error is not None and result.error.code == code
    assert os.listdir(folder / "ELA" / "prova") == []
    if code in {FAILED, STOPPED}:
        assert result.output["gestures"] == 1, "once the browser has the gesture it counts as made"
        assert result.error.message.endswith("may have been made")


async def test_a_download_whose_time_runs_out_says_so_and_counts_its_gesture(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    browser.stall("downloaded_from")
    tool = BrowserDownloadTool(
        folder,
        Browsing(sites=SITES.sites, timeout_seconds=0),
        browser,
        CLOCK,
        FakeIdGenerator(),
        protected={},
        pages=FakeTaskPages(),
    )

    result = await tool.execute(decision(BROWSER_DOWNLOAD), DOWNLOAD, FakeStop())

    assert result.error is not None and result.error.code == TIMEOUT
    assert "had not ended after 0 s" in result.error.message
    assert result.output["gestures"] in {0, 1}
    assert os.listdir(folder / "ELA" / "prova") == []


@pytest.mark.parametrize("click", [None, "a#file"], ids=["the address", "a click"])
async def test_a_task_stopped_while_the_file_arrives_cancels_the_download(
    tmp_path: Path, click: str | None
) -> None:
    """Criterion 5. The stop of the task is heard while the browser waits for the file: its call
    is cancelled, the result is the tool's — stopped, the gesture counted — and nothing stays."""
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    reached, _ = browser.stall("downloaded_from" if click is None else "download")
    arguments = DOWNLOAD if click is None else with_(DOWNLOAD, path="/links", click=click)
    stop = FakeStop()

    running = asyncio.ensure_future(
        download(browser, folder).execute(decision(BROWSER_DOWNLOAD), arguments, stop)
    )
    await reached.wait()
    stop.event.set()
    result = await running

    assert result.error is not None and result.error.code == STOPPED
    assert "while the download from httpbin.org was arriving" in result.error.message
    assert result.output["gestures"] == 1
    assert ("status" in result.output) is (click is not None)
    assert os.listdir(folder / "ELA" / "prova") == []


async def test_a_download_that_ends_while_the_stop_is_heard_is_a_download_that_ended(
    tmp_path: Path,
) -> None:
    """The call of the browser is cancelled when the task stops — and one that had ended by then
    is not thrown away for it."""
    tool = download(FakeBrowser(), root(tmp_path))
    stop = FakeStop()
    began = asyncio.Event()

    async def ends_all_the_same() -> Downloaded:
        began.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return Downloaded("ended")
        raise AssertionError("nobody stopped it")

    waiting = asyncio.ensure_future(tool._unless_stopped(ends_all_the_same(), stop))  # noqa: SLF001
    await began.wait()
    stop.event.set()

    assert await waiting == Downloaded("ended")


async def test_a_click_awaited_when_the_task_stops_clicks_nothing(tmp_path: Path) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    reached, _ = browser.stall("appeared")
    stop = FakeStop()

    running = asyncio.ensure_future(
        download(browser, folder).execute(
            decision(BROWSER_DOWNLOAD), with_(DOWNLOAD, path="/links", click="a#file"), stop
        )
    )
    await reached.wait()
    stop.event.set()
    with pytest.raises(ToolStopped):
        await running

    assert browser.downloads == [] and stop.listened[-1] == DOWNLOAD_GESTURE
    assert browser.closed == ["page-1"], "the page is closed: nothing is left open behind a stop"


async def test_a_click_that_names_more_than_one_element_starts_nothing(tmp_path: Path) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES, counts={"a.file": 2}))

    result = await asked_and_run(
        download(browser, folder), with_(DOWNLOAD, path="/links", click="a.file"), BROWSER_DOWNLOAD
    )

    assert result.error is not None and result.error.code == ELEMENT_AMBIGUOUS
    assert result.output["gestures"] == 0 and browser.downloads == []
    assert result.error.message.endswith("was not made")


async def test_a_click_that_starts_no_download_says_the_status_of_its_page(tmp_path: Path) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=None))

    result = await asked_and_run(
        download(browser, folder), with_(DOWNLOAD, path="/links", click="a#file"), BROWSER_DOWNLOAD
    )

    assert result.error is not None and result.error.code == DOWNLOAD_NOT_STARTED
    assert result.output == {"status": 200, "gestures": 1}


async def test_an_address_that_sends_the_browser_elsewhere_says_so_by_its_origin(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES, left="https://altro.example/file?k=1"))

    result = await asked_and_run(download(browser, folder), DOWNLOAD, BROWSER_DOWNLOAD)

    assert result.error is not None and result.error.code == LEFT_SITE
    assert "https://altro.example" in result.error.message and "k=1" not in result.error.message
    assert os.listdir(folder / "ELA" / "prova") == []


class Leaving(FakeBrowser):
    """A browser that leaves in the folder what the test says, under the name the test says."""

    def __init__(self, name: str, *, made: str = "a file") -> None:
        super().__init__(FakePage(download=BYTES))
        self.name, self.made = name, made

    def _downloaded(self, into: str) -> Downloaded:
        if self.made == "a folder":
            (Path(into) / self.name).mkdir()
        elif self.made == "a file":
            (Path(into) / self.name).write_bytes(BYTES)
        return Downloaded(self.name)


@pytest.mark.parametrize(
    ("name", "made", "code"),
    [
        ("../fuori", "nothing", FAILED),
        ("", "nothing", FAILED),
        ("una-cartella", "a folder", FAILED),
        ("mai-scritto", "nothing", IO_ERROR),
    ],
    ids=["a name outside the folder", "no name", "a folder", "nothing there"],
)
async def test_what_the_browser_says_it_left_is_not_believed(
    tmp_path: Path, name: str, made: str, code: str
) -> None:
    """The name is the browser's word: it has to be a name, of a regular file that is there."""
    folder = root(tmp_path)

    result = await asked_and_run(
        download(Leaving(name, made=made), folder), DOWNLOAD, BROWSER_DOWNLOAD
    )

    assert result.error is not None and result.error.code == code
    assert not (folder / "ELA" / "prova" / "scaricato.bin").exists()
    assert not (tmp_path / "fuori").exists()


async def test_a_file_that_appears_while_the_download_arrives_is_not_replaced(
    tmp_path: Path,
) -> None:
    """Created without replacing: the plan said nothing was there, and what arrived is removed."""
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "scaricato.bin"
    browser = FakeBrowser(FakePage(download=BYTES))
    reached, released = browser.stall("downloaded_from")

    running = asyncio.ensure_future(
        asked_and_run(download(browser, folder), DOWNLOAD, BROWSER_DOWNLOAD)
    )
    await reached.wait()
    target.write_bytes(b"arrivato intanto")
    released.set()
    result = await running

    assert result.error is not None and result.error.code == OVERWRITE_MISMATCH
    assert target.read_bytes() == b"arrivato intanto"
    assert os.listdir(target.parent) == ["scaricato.bin"], "what was downloaded was removed"


async def test_a_page_that_fails_before_the_click_counts_no_gesture(tmp_path: Path) -> None:
    folder = root(tmp_path)
    browser = FakeBrowser(FakePage(download=BYTES))
    browser.raising["appeared"] = BrowserFailed("the page fell")

    result = await asked_and_run(
        download(browser, folder), with_(DOWNLOAD, path="/links", click="a#file"), BROWSER_DOWNLOAD
    )

    assert result.error is not None and result.error.code == FAILED
    assert result.output["gestures"] == 0 and result.error.message.endswith("was not made")


def test_the_root_of_the_two_is_the_declared_one_resolved(tmp_path: Path) -> None:
    folder = root(tmp_path)

    assert download(FakeBrowser(), folder).root == folder.resolve()
    assert upload(FakeBrowser(), folder).root == folder.resolve()


# ----------------------------------------------------------------------------------------
# Every way an upload can fall
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wrong",
    [
        {"file": ""},
        {"fill": "x"},
        {"file_field": ">> x"},
        {"click": ">> x"},
        {"expect_text": ""},
        {"continues": True},
    ],
    ids=["no file", "a fill", "a field", "a click", "no text", "continues"],
)
async def test_an_upload_whose_shape_is_wrong_is_refused_before_the_question_and_after_the_yes(
    tmp_path: Path, wrong: dict[str, Any]
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    arguments = with_(UPLOAD, **wrong)

    prospect = await tool.prospect(arguments)
    result = await tool.execute(decision(BROWSER_UPLOAD), arguments, FakeStop(), {})

    assert prospect.refusal is not None and prospect.refusal.code == ARGUMENTS_INVALID
    assert result.error is not None and result.error.code == ARGUMENTS_INVALID
    assert browser.opened == [] and browser.given == []


async def test_a_site_that_is_not_declared_gives_nothing_before_the_question_or_after_the_yes(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    arguments = with_(UPLOAD, site="altro.example")

    prospect = await tool.prospect(arguments)
    result = await tool.execute(decision(BROWSER_UPLOAD), arguments, FakeStop(), {})

    assert prospect.refusal is not None and prospect.refusal.code == SITE_NOT_DECLARED
    assert result.error is not None and result.error.code == SITE_NOT_DECLARED
    assert browser.opened == [] and browser.given == []


async def test_a_file_that_becomes_a_link_between_the_question_and_the_yes_is_not_read_through_it(
    tmp_path: Path,
) -> None:
    """Criterion 7. The link leads to a file with **the same bytes**: read through it, the size
    and the sha256 would be the ones the question named — and it is not read."""
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "da-caricare.txt"
    target.write_bytes(BYTES)
    (folder / "ELA" / "lo-stesso.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    prospect = await tool.prospect(UPLOAD)
    assert prospect.refusal is None
    target.unlink()
    target.symlink_to(folder / "ELA" / "lo-stesso.txt")

    result = await tool.execute(decision(BROWSER_UPLOAD), UPLOAD, FakeStop(), prospect.named or {})

    assert result.error is not None and result.error.code == PATH_SYMLINK
    assert result.output == {"gestures": 0}
    assert browser.opened == [] and browser.given == []


async def test_a_file_that_cannot_be_read_is_not_a_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)

    def refuses(target: Path) -> bytes:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(browser_files, "read_bytes", refuses)
    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == IO_ERROR
    assert "PermissionError" in prospect.refusal.message


async def test_a_file_that_grew_past_the_limit_while_it_was_read_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The size is asked of the disk first, and what was read is counted too."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(b"12345")
    monkeypatch.setattr(browser_files, "UPLOAD_MAX_BYTES", 10)
    monkeypatch.setattr(browser_files, "read_bytes", lambda target: b"x" * 11)

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == FILE_TOO_LARGE


async def test_a_field_awaited_when_the_task_stops_receives_nothing(tmp_path: Path) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    reached, _ = browser.stall("appeared")
    tool = upload(browser, folder)
    prospect = await tool.prospect(UPLOAD)
    stop = FakeStop()

    running = asyncio.ensure_future(
        tool.execute(decision(BROWSER_UPLOAD), UPLOAD, stop, prospect.named or {})
    )
    await reached.wait()
    stop.event.set()
    with pytest.raises(ToolStopped):
        await running

    assert browser.given == [] and stop.listened[-1] == "the first gesture"


async def test_a_field_that_names_more_than_one_element_receives_nothing(tmp_path: Path) -> None:
    """Criterion 11: the field the yes named is one element."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}, counts={"#fileinput": 2}))

    result = await asked_and_run(upload(browser, folder), UPLOAD, BROWSER_UPLOAD)

    assert result.error is not None and result.error.code == ELEMENT_AMBIGUOUS
    assert browser.given == [] and result.output["gestures"] == 0


async def test_an_upload_stopped_after_the_file_says_one_gesture_and_clicks_nothing(
    tmp_path: Path,
) -> None:
    """Criterion 10: stopped after the file and before the click."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    tool = upload(browser, folder)
    prospect = await tool.prospect(UPLOAD)

    result = await tool.execute(
        decision(BROWSER_UPLOAD), UPLOAD, FakeStop(after="the first gesture"), prospect.named or {}
    )

    assert result.error is not None and result.error.code == STOPPED
    assert result.output["gestures"] == 1 and result.output["stopped_at"] == 2
    assert len(browser.given) == 1 and browser.clicks == []


async def test_the_page_of_an_upload_goes_to_its_verifier_and_to_no_step_after_it(
    tmp_path: Path,
) -> None:
    """The page that holds a file is nobody else's: kept for the look, never left to the room —
    even for a step the room would let continue."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))
    pages = FakeTaskPages(continued=[STEP])
    tool = BrowserUploadTool(folder, SITES, browser, CLOCK, FakeIdGenerator(), pages=pages)
    prospect = await tool.prospect(UPLOAD)

    result = await tool.execute(of_a_task(BROWSER_UPLOAD), UPLOAD, FakeStop(), prospect.named or {})

    assert result.status is ExecutionStatus.SUCCEEDED, result.error
    assert pages.offered == [] and browser.kept == [str(result.output["page"])]
    assert browser.holding_a_file == [str(result.output["page"])]


# ----------------------------------------------------------------------------------------
# The verifier, and what it does not trust
# ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "said",
    [
        {"size": len(BYTES), "digest": 7},
        {"size": "41", "digest": "x"},
        {"size": True, "digest": "x"},
        {},
    ],
)
async def test_the_verifier_asks_the_result_for_a_size_and_a_fingerprint(
    tmp_path: Path, said: dict[str, Any]
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(BYTES)

    (failure,) = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert failure.code == "verification.arguments_invalid"


async def test_the_verifier_says_a_file_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(BYTES)
    said = {"size": len(BYTES), "digest": digest(BYTES)}

    def refuses(target: Path) -> tuple[int, str]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(browser_files, "measured", refuses)
    (failure,) = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert failure.code == FILE_UNREADABLE and failure.retryable


async def test_the_verifier_says_a_file_of_the_same_size_and_another_content(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(BYTES[::-1])
    said = {"size": len(BYTES), "digest": digest(BYTES)}

    (failure,) = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert failure.code == FILE_MISMATCH and "of another content" in failure.message
    assert digest(BYTES) not in failure.message and digest(BYTES[::-1]) not in failure.message
    assert failure.details == {
        "condition": FILE_DOWNLOADED,
        "expected_bytes": len(BYTES),
        "actual_bytes": len(BYTES),
    }


def test_the_two_with_the_profile_are_capabilities_of_their_own(tmp_path: Path) -> None:
    folder = root(tmp_path)

    assert AccountFileDownloadedVerifier(folder).capability_id == BROWSER_DOWNLOAD_AS_YOU
    assert AccountUploadVerifier(FakeAccountBrowser(), 30.0).capability_id == BROWSER_UPLOAD_AS_YOU
    assert UploadVerifier(FakeBrowser(), 30.0).capability_id == BROWSER_UPLOAD
    assert download(FakeAccountBrowser(), folder, profile=True).profile
    assert upload(FakeAccountBrowser(), folder, profile=True).profile


def test_none_of_the_four_travels_and_none_continues(tmp_path: Path) -> None:
    """Criterion 15: no node receives or verifies one of them, and none has ``continues``."""
    from tests.docs.test_adr_travel import travelling
    from tests.tools.test_registry import _production

    tools, verifiers, _ = _production(tmp_path)
    four = {BROWSER_DOWNLOAD, BROWSER_DOWNLOAD_AS_YOU, BROWSER_UPLOAD, BROWSER_UPLOAD_AS_YOU}

    assert four <= {tool.capability_id for tool in tools.tools()}
    assert not four & set(travelling(tools, verifiers))
    for tool in tools.tools():
        if tool.capability_id in four:
            assert not tool.relocatable and not tool.idempotent
            assert tool.continuing == ""  # type: ignore[attr-defined]


def test_what_is_measured_is_a_regular_file_and_its_own_bytes(tmp_path: Path) -> None:
    """The size and the sha256 a download's result and its verifier say are read from the file,
    never through a link, and from nothing that is not a regular file."""
    from ela.tools.fs import measured

    whole = tmp_path / "whole.bin"
    whole.write_bytes(BYTES * 5000)
    (tmp_path / "link.bin").symlink_to(whole)

    assert measured(whole) == (len(BYTES) * 5000, digest(BYTES * 5000))
    with pytest.raises(OSError, match="regular|directory|denied"):
        measured(tmp_path)
    with pytest.raises(OSError):
        measured(tmp_path / "link.bin")
