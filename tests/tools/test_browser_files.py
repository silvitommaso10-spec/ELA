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

import hashlib
import os
import stat
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from ela.tools.browser_files import (
    DOWNLOAD_NOT_STARTED,
    FILE_CHANGED,
    FILE_DOWNLOADED,
    FILE_TOO_LARGE,
    NOT_A_FILE_FIELD,
    SITE_NOT_DECLARED,
    UPLOAD_MAX_BYTES,
    AccountDownloadTool,
    AccountUploadTool,
    BrowserDownloadTool,
    BrowserUploadTool,
    FileDownloadedVerifier,
)

from ela.domain import (
    DecisionId,
    ExecutionResult,
    ExecutionStatus,
    PermissionDecision,
    PermissionOutcome,
    RiskLevel,
)
from ela.permissions import (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
    production_catalogue,
)
from ela.ports import DOWNLOAD_GESTURE, Downloaded, GivenFile
from ela.testing.fakes import (
    FakeAccountBrowser,
    FakeBrowser,
    FakeClock,
    FakeIdGenerator,
    FakePage,
    FakeStop,
    FakeTaskPages,
)
from ela.tools.browser import (
    DOWNLOAD_REFUSED,
    BrowserActTool,
    Browsing,
)
from ela.tools.fs import NO_ROOT, OVERWRITE_MISMATCH
from ela.tools.paths import PATH_IS_DIRECTORY, PATH_MISSING, PATH_OUTSIDE_ROOT, PATH_SYMLINK
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
    browser: FakeBrowser, folder: Path, *, profile: bool = False
) -> BrowserDownloadTool | AccountDownloadTool:
    kind = AccountDownloadTool if profile else BrowserDownloadTool
    return kind(folder, SITES, browser, CLOCK, FakeIdGenerator(), pages=FakeTaskPages())  # type: ignore[arg-type]


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
    ("file", "made", "code"),
    [
        ("../fuori.bin", None, PATH_OUTSIDE_ROOT),
        ("ELA/prova", None, PATH_IS_DIRECTORY),
        ("ELA/link.bin", "link", PATH_SYMLINK),
    ],
)
async def test_a_download_refuses_what_fs_write_refuses(
    tmp_path: Path, file: str, made: str | None, code: str
) -> None:
    folder = root(tmp_path)
    if made == "link":
        (folder / "ELA" / "link.bin").symlink_to(tmp_path / "elsewhere")
    prospect = await download(FakeBrowser(), folder).prospect(with_(DOWNLOAD, file=file))

    assert prospect.refusal is not None and prospect.refusal.code == code


@pytest.mark.parametrize(("there", "overwrite"), [(True, False), (False, True)])
async def test_overwrite_is_an_assertion_on_the_world_both_ways(
    tmp_path: Path, there: bool, overwrite: bool
) -> None:
    folder = root(tmp_path)
    if there:
        (folder / "ELA" / "prova" / "scaricato.bin").write_bytes(b"c'era")

    prospect = await download(FakeBrowser(), folder).prospect(with_(DOWNLOAD, overwrite=overwrite))

    assert prospect.refusal is not None and prospect.refusal.code == OVERWRITE_MISMATCH


async def test_without_a_root_nothing_is_asked(tmp_path: Path) -> None:
    prospect = await download(FakeBrowser(), tmp_path / "missing").prospect(DOWNLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == NO_ROOT


@pytest.mark.parametrize(
    ("make", "code"),
    [("missing", PATH_MISSING), ("directory", PATH_IS_DIRECTORY), ("link", PATH_SYMLINK)],
)
async def test_an_upload_refuses_what_fs_read_refuses(tmp_path: Path, make: str, code: str) -> None:
    folder = root(tmp_path)
    target = folder / "ELA" / "prova" / "da-caricare.txt"
    if make == "directory":
        target.mkdir()
    elif make == "link":
        (tmp_path / "vero.txt").write_bytes(BYTES)
        target.symlink_to(tmp_path / "vero.txt")

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == code


async def test_bytes_that_are_not_text_are_uploaded(tmp_path: Path) -> None:
    """Answer 19: what ``fs.read`` refuses is its root and its classification — the refusal of a
    text that is not UTF-8 stays ``fs.read``'s, whose text enters a result. A PDF is uploaded."""
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(b"%PDF-1.7\n\xff\xfe\x00 binario")

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is None


async def test_a_file_over_the_limit_a_page_takes_is_refused_before_the_question(
    tmp_path: Path,
) -> None:
    """Answer 20: Playwright gives a page at most 50 MiB as bytes, and a question is composed only
    for what would succeed now. A sparse file: its size is asked of the disk, not read."""
    folder = root(tmp_path)
    with (folder / "ELA" / "prova" / "da-caricare.txt").open("wb") as big:
        big.truncate(UPLOAD_MAX_BYTES + 1)

    prospect = await upload(FakeBrowser(), folder).prospect(UPLOAD)

    assert prospect.refusal is not None and prospect.refusal.code == FILE_TOO_LARGE


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


async def test_a_file_changed_between_the_question_and_the_yes_does_not_leave(
    tmp_path: Path,
) -> None:
    folder = root(tmp_path)
    (folder / "ELA" / "prova" / "da-caricare.txt").write_bytes(BYTES)
    browser = FakeBrowser(FakePage(fields={"#fileinput": _file_field()}))

    result = await asked_and_run(
        upload(browser, folder), UPLOAD, BROWSER_UPLOAD, changed=BYTES + b"cambiato"
    )

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
    from ela.ports import NAVIGATION, ToolStopped

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

    failures = await FileDownloadedVerifier(folder).verify(
        [FILE_DOWNLOADED], DOWNLOAD, succeeded(BROWSER_DOWNLOAD, output=said)
    )

    assert len(failures) == 1


def _file_field() -> Any:
    from ela.ports import Field

    return Field("file", "")


def _text_field() -> Any:
    from ela.ports import Field

    return Field("text", "")
