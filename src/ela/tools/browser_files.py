"""The files from the browser (M13.13, ADR 0066): **a download is judged as an ``fs.write``, an
upload as an ``fs.read``, and the question names the file**.

Four capabilities, all ``HIGH``, each asking at every use unless a policy of its own covers it
(M13.15, ADR 0071): ``browser.download`` and
``browser.upload`` on ELA's empty browser, ``browser.download_as_you`` and
``browser.upload_as_you`` on the one with the user's accounts — capabilities of their own,
because a consent is not inherited (ADR 0034).

* **The scope is the file.** A capability has one scope, and theirs is ``ELA_FS_SCOPE`` on
  ``file``: a file outside it is the Guardian's ``DENIED``, as for ``fs.*``. So **the site is the
  boundary of the tool**, and one that was not declared is refused here, before the question
  (:data:`SITE_NOT_DECLARED`) — where for every other ``browser.*`` it is the Guardian's.
* **Every refusal that can come before the question does** (ADR 0045 §6-bis): the shape, the site,
  the browser and its profile, the root, and the file with the classification ``fs`` shares — a
  download refuses what ``fs.write`` refuses, with ``overwrite`` an assertion on the world both
  ways; an upload what ``fs.read`` refuses, and a file larger than a page can be given
  (:data:`FILE_TOO_LARGE`).
* **An upload gives bytes and a name, never a path.** ELA reads the file when it composes the
  question — a regular file with one name, never through a link, nothing of ELA's — and the size
  and the sha256 travel with the yes; after the yes it reads it again, and a file that is not the
  one the question named does not leave (:data:`FILE_CHANGED`). **Under a policy** (M13.15, ADR
  0071) no question was asked: the file is read once, and the result says the size and the sha256
  of the bytes that left. Giving the file is the first gesture, and from that instant the page
  holds a file: the adapter lets it ask nothing of another origin.
* **A download is written under a name the site does not choose**, in the folder of the target,
  by a door that is closed for every other page and every other instant; then the file takes the
  plan's name — created without replacing, or replacing when ``overwrite`` says so — and the mode
  ``600``, always. A download that does not start is :data:`DOWNLOAD_NOT_STARTED`.

None of the four continues on a page, none leaves one to the step after it, none travels.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import stat
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, ClassVar, Final

from ela.domain import (
    CapabilityId,
    ErrorMetadata,
    ExecutionResult,
    JsonMapping,
    JsonValue,
    PermissionDecision,
    TaskId,
)
from ela.permissions import (
    BROWSER_DOWNLOAD,
    BROWSER_DOWNLOAD_AS_YOU,
    BROWSER_UPLOAD,
    BROWSER_UPLOAD_AS_YOU,
)
from ela.ports import (
    DOWNLOAD_GESTURE,
    AccountBrowser,
    Browser,
    Clock,
    Downloaded,
    DownloadNotStarted,
    GivenFile,
    IdGenerator,
    Opened,
    Prospect,
    StopPoint,
    Target,
    TaskPages,
    TaskStop,
)
from ela.tools.account import ACCOUNT_CODES, _OnTheProfile
from ela.tools.base import ARGUMENTS_INVALID, Outcome, under_a_policy
from ela.tools.browser import (
    ANOTHER_PAGE,
    BROWSER_CODES,
    DOWNLOAD_REFUSED,
    ELEMENT_AMBIGUOUS,
    FAILED,
    FELL,
    FIRST_GESTURE,
    LEFT_SITE,
    LEFT_WHILE_WAITING,
    NO_PAGE_TO_CONTINUE,
    SECRET_FIELD,
    STOPPED,
    BrowserActTool,
    Browsing,
    _BrowserTool,
    _Call,
    _Done,
    _expected,
    _filling,
    _pairs,
    _retrieved,
    _selector,
    boundary,
    origin_of,
)
from ela.tools.disk import MAKING_THE_FOLDER, NO_ANSWER, WRITING, Disk, DiskSilent, Gone
from ela.tools.fs import (
    CREATES,
    DIRECTORY_MODE,
    ELA_S_OWN,
    FILE,
    FILE_MODE,
    HARD_LINK,
    IO_ERROR,
    NO_ROOT,
    OVERWRITE_MISMATCH,
    READ_REFUSALS,
    WRITE_REFUSALS,
    MoreThanOneName,
    looked_for_a_folder,
    looked_for_a_read,
    looked_for_a_write,
    measured,
    more_than_one_name_read,
    read_bytes,
    which_place,
)
from ela.tools.paths import PATH_CODES, PathProblem, classify, resolve_workspace
from ela.tools.verifiers import LOOK_GRACE_SECONDS, BrowserActVerifier, _PageVerifier
from ela.tools.verify import COMMON_FAILURE_CODES, VERIFICATION_ARGUMENTS_INVALID, Verifier

__all__ = [
    "BROWSER_DOWNLOAD_AS_YOU_TOOL_NAME",
    "BROWSER_DOWNLOAD_AS_YOU_VERIFIER_NAME",
    "BROWSER_DOWNLOAD_TOOL_NAME",
    "BROWSER_DOWNLOAD_VERIFIER_NAME",
    "BROWSER_UPLOAD_AS_YOU_TOOL_NAME",
    "BROWSER_UPLOAD_AS_YOU_VERIFIER_NAME",
    "BROWSER_UPLOAD_TOOL_NAME",
    "BROWSER_UPLOAD_VERIFIER_NAME",
    "DOWNLOAD_NOT_STARTED",
    "FILE_CHANGED",
    "FILE_DOWNLOADED",
    "FILE_MISMATCH",
    "FILE_TOO_LARGE",
    "FILE_UNREADABLE",
    "NOT_A_FILE_FIELD",
    "SITE_NOT_DECLARED",
    "UPLOAD_MAX_BYTES",
    "AccountDownloadTool",
    "AccountFileDownloadedVerifier",
    "AccountUploadTool",
    "AccountUploadVerifier",
    "BrowserDownloadTool",
    "BrowserUploadTool",
    "FileDownloadedVerifier",
    "UploadVerifier",
]

BROWSER_DOWNLOAD_TOOL_NAME: Final = "browser-download"
BROWSER_DOWNLOAD_AS_YOU_TOOL_NAME: Final = "browser-download-as-you"
BROWSER_UPLOAD_TOOL_NAME: Final = "browser-upload"
BROWSER_UPLOAD_AS_YOU_TOOL_NAME: Final = "browser-upload-as-you"
BROWSER_DOWNLOAD_VERIFIER_NAME: Final = "browser-download-verifier"
BROWSER_DOWNLOAD_AS_YOU_VERIFIER_NAME: Final = "browser-download-as-you-verifier"
BROWSER_UPLOAD_VERIFIER_NAME: Final = "browser-upload-verifier"
BROWSER_UPLOAD_AS_YOU_VERIFIER_NAME: Final = "browser-upload-as-you-verifier"

SITE_NOT_DECLARED: Final = "browser.site_not_declared"
"""The site of a call is not one the user declared (``ELA_BROWSER_SITES``). The tool's, and before
the question: the scope of these capabilities is the file, so the Guardian does not look at the
site (X11 of M13.10)."""
NOT_A_FILE_FIELD: Final = "browser.not_a_file_field"
"""The element the question named for the file is not an ``input`` of type ``file``: nothing was
given to the page."""
FILE_CHANGED: Final = "browser.file_changed"
"""The file is not the one the question named any more — another size, or another sha256 —: the
yes was spent, no page was opened and nothing left."""
FILE_TOO_LARGE: Final = "browser.file_too_large"
"""The file is larger than a page can be given as bytes (:data:`UPLOAD_MAX_BYTES`): refused before
the question, because a question is composed only for what would succeed now (ADR 0045 §6-bis)."""
DOWNLOAD_NOT_STARTED: Final = "browser.download_not_started"
"""The gesture was made and the browser announced no download: nothing was written."""
UPLOAD_MAX_BYTES: Final = 50 * 1024 * 1024
"""What Playwright gives a file field as bytes, at most (answer 20 of the review of M13.13's SPEC):
past it the engine refuses, after the yes."""
OCTET_STREAM: Final = "application/octet-stream"
"""The type of a file whose name says none."""

FILE_DOWNLOADED: Final = "browser.file_downloaded"
"""The condition of a download: the file the plan named is there — regular, inside the root — and
holds what the result says it holds, by size and by sha256."""
FILE_MISMATCH: Final = "browser.file_mismatch"
"""The file is there and is not the one the result describes. Said in sizes, never in hashes: the
hash of a short file inverts by dictionary (ADR 0045 §8)."""
FILE_UNREADABLE: Final = "browser.file_unreadable"
"""The file is there and could not be read to compare it."""

DOWNLOADS: Final = (
    "downloads one file from this site, in ELA's own browser, which is empty — no cookies, no "
    "logins: the site sees a visitor, not you —, and writes it in the file named here, inside the "
    "folder you authorised; the gesture that starts it may do more on the site than start a "
    "download, and ELA cannot know that before it happens"
)
"""What a yes to a download does, said by the capability (ADR 0045 §6)."""
DOWNLOADS_AS_YOU: Final = (
    "downloads one file from this site in ELA's own browser, which keeps the sites you signed in "
    "to: where you are signed in the site sees you, and what arrives is your own content; it is "
    "written in the file named here, inside the folder you authorised; the gesture that starts it "
    "may do more on the site than start a download, and it would do it as you"
)
UPLOADS: Final = (
    "gives this site one file of yours — its name and its bytes, as they are now — in ELA's own "
    "browser, which is empty: the site sees a visitor, not your account; what the site does with "
    "the file ELA cannot know before it happens, nor take the file back after"
)
"""What a yes to an upload does: what leaves is the content, and the yes covers that."""
UPLOADS_AS_YOU: Final = (
    "gives this site one file of yours — its name and its bytes, as they are now — in ELA's own "
    "browser, which keeps the sites you signed in to: where you are signed in the file is given "
    "as you, on your account there; what the site does with it ELA cannot know before it happens, "
    "nor take the file back after"
)
CREATES_BY_DOWNLOAD: Final = f"{CREATES}, with what the download brings"
OVERWRITES_BY_DOWNLOAD: Final = (
    "overwrites a file that is already there, with what the download brings"
)
LEAVES: Final = "is read and given to the site: its name and its bytes leave this machine"
"""What happens to the file of an upload, in the question's place of ``fs.read``'s sentence."""
DOWNLOADS_IN: Final = "downloads into this folder"
"""What a policy of a download lets ELA do in a place, in the tool's words (M13.15, ADR 0071)."""
GIVES_FROM: Final = "gives the files of this folder"
"""What a policy of an upload lets ELA do in a place, in the tool's words (M13.15, ADR 0071)."""
NAMED_SIZE: Final = "size"
NAMED_DIGEST: Final = "digest"
"""What the question of an upload named of the file, kept beside the approval and handed back
with the yes (ADR 0065 §2): the size in bytes and the sha256, in hexadecimal."""


@dataclass(frozen=True, slots=True)
class _Download(_Call):
    """A download that would start: the call of the page, and the file it would leave."""

    file: str = ""
    overwrite: bool = False


@dataclass(frozen=True, slots=True)
class _Upload(_Call):
    """An upload that would start: the call of the page, the file, the field that receives it —
    and, once the yes is there, what ELA read to give."""

    file: str = ""
    field: str = ""
    given: GivenFile | None = None


def _refusal(refused: Outcome, tool_name: str) -> Prospect:
    return Prospect(
        refusal=ErrorMetadata(
            code=refused.code or ARGUMENTS_INVALID,
            message=refused.message,
            tool_name=tool_name,
            retryable=refused.retryable,
        )
    )


async def _place(
    tool: BrowserDownloadTool | BrowserUploadTool, place: str, sites: tuple[str, ...], does: str
) -> Prospect:
    """Whether a call of one of the four could start now in ``place`` with each of ``sites`` — one
    entry of the scope of a policy and its second dimension, at its birth (M13.15, ADR 0071;
    decisions 6 and 7). In the order of every call (ADR 0066 §4): each site among the declared ones,
    the browser and for the two «as you» the profile, then the folder — **the one function**
    ``fs.write`` asks too: there, a folder, inside the root without a link, and nothing of ELA's in
    both directions, for a reader as for a writer. The answer names the folder as this disk does."""
    for site in sites:
        refused = _undeclared(tool._browsing, site)  # noqa: SLF001 — the tool's own boundary
        if refused is not None:
            return _refusal(refused, tool.name)
    missing = await tool._installed()  # noqa: SLF001 — the look every call of the tool takes
    if missing is not None:
        return _refusal(missing, tool.name)
    try:
        refused, target = await tool.disk.run(
            lambda _: looked_for_a_folder(tool.root, place, protected=tool.protected, does=does),
            f"a look at {place!r}",
        )
    except DiskSilent as silent:
        return _refusal(Outcome({}, NO_ANSWER, str(silent)), tool.name)
    if refused is not None or target is None:
        return _refusal(refused or Outcome({}, IO_ERROR, "the folder was not judged"), tool.name)
    return Prospect(target=target)


def _undeclared(browsing: Browsing, site: str) -> Outcome | None:
    """The refusal of a site the user did not declare, or ``None``."""
    if site in browsing.sites:
        return None
    return Outcome(
        {},
        SITE_NOT_DECLARED,
        f"{site} is not a site you declared (ELA_BROWSER_SITES): no page is opened",
    )


class BrowserDownloadTool(_BrowserTool):
    """Downloads one file of a declared site into a file under the root (**HIGH**)."""

    error_codes: ClassVar[frozenset[str]] = (
        frozenset(
            {
                ARGUMENTS_INVALID,
                SITE_NOT_DECLARED,
                DOWNLOAD_NOT_STARTED,
                NO_ROOT,
                OVERWRITE_MISMATCH,
                IO_ERROR,
                # The disk that does not answer (M13.17, ADR 0074): every look under the root
                # passes the guard, and an abandoned wait is this code.
                NO_ANSWER,
            }
        )
        | BROWSER_CODES
        | WRITE_REFUSALS
    ) - {SECRET_FIELD}
    output_keys: ClassVar[frozenset[str]] = frozenset(
        {
            "file",
            "size",
            "digest",
            "overwrote",
            "status",
            "gestures",
            ANOTHER_PAGE,
            DOWNLOAD_REFUSED,
        }
    )
    audit_numbers: ClassVar[frozenset[str]] = frozenset({"status", "gestures", "size"})
    """The status of the page a click was made on, whether the gesture was made, and the size of
    what arrived: never the file's name, the address or the sha256 (ADR 0047 §10)."""
    idempotent: ClassVar[bool] = False
    """**Not idempotent**: the gesture that starts a download is a click or a visit, and a site
    may count it; and a file written is not written again on a replay."""
    does: ClassVar[str] = DOWNLOADS
    acts: ClassVar[bool] = True
    under_the_root: ClassVar[bool] = True
    stop_point: ClassVar[StopPoint] = StopPoint(here=DOWNLOAD_GESTURE, on_a_node=None)
    """Right before the gesture that starts the download — the click, or the navigation to the
    address that is the file —, with the door open an instant before: one word for the two."""

    def __init__(
        self,
        root: Path | str,
        browsing: Browsing,
        browser: Browser,
        clock: Clock,
        ids: IdGenerator,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_DOWNLOAD_TOOL_NAME,
        pages: TaskPages,
        capability_id: CapabilityId = BROWSER_DOWNLOAD,
    ) -> None:
        super().__init__(capability_id, browsing, browser, clock, ids, name=name, pages=pages)
        self._root = resolve_workspace(root)
        # What ELA uses to exist (M13.14, ADR 0068): a download is a write, and no write reaches it.
        self._protected: Mapping[str, Path] = MappingProxyType(dict(protected))
        # The guard of every look and write on the disk (M13.17, ADR 0074).
        self._disk = Disk() if disk is None else disk

    @property
    def disk(self) -> Disk:
        """The guard every look and write of this tool passes (M13.17, ADR 0074)."""
        return self._disk

    @property
    def root(self) -> Path:
        """The resolved root: ``ELA_FS_ROOT``, never created here."""
        return self._root

    @property
    def protected(self) -> Mapping[str, Path]:
        """What ELA uses to exist, named: ``fs.write``'s list, and no download reaches it."""
        return self._protected

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        file, overwrite, click = (
            arguments.get("file"),
            arguments.get("overwrite"),
            arguments.get("click"),
        )
        if not isinstance(file, str) or not file:
            return Outcome({}, ARGUMENTS_INVALID, "file must be a path under the root")
        if not isinstance(overwrite, bool):
            return Outcome({}, ARGUMENTS_INVALID, "overwrite must be a boolean")
        if click is None:
            gestures: tuple[str, ...] = ("goes to the address, which is the file",)
        else:
            refused = _selector(click, "click")
            if refused is not None:
                return refused
            gestures = (f"clicks {click}, which starts the download",)
        return _Download(
            visit=self._visit(site, address, gestures, ""),
            fills=(),
            click=click if isinstance(click, str) else None,
            selector=None,
            allowed=boundary(frozenset({self._browsing.origin(site)})),
            file=file,
            overwrite=overwrite,
        )

    def _looked(self, arguments: JsonMapping) -> Outcome | _Download:
        """The call, of a declared site: what the question and the run both begin with."""
        looked = self._shaped(arguments)
        if isinstance(looked, Outcome):
            return looked
        assert isinstance(looked, _Download)  # noqa: S101 — a download never continues
        return _undeclared(self._browsing, looked.visit.site) or looked

    async def prospect_place(self, place: str, values: tuple[str, ...] = ()) -> Prospect:
        """Whether a download could start now into ``place`` from each of ``values``, the sites of
        a policy (M13.15, ADR 0071): :func:`_place`."""
        return await _place(self, place, values, DOWNLOADS_IN)

    async def prospect(self, arguments: JsonMapping, task: TaskId | None = None) -> Prospect:
        """The shape, the site, the browser, then the root and the file as ``fs.write`` judges
        them — and the question names both: the file, with what happens to it, and the site."""
        looked = self._looked(arguments)
        if not isinstance(looked, Outcome):
            looked = await self._installed(task) or looked
        if isinstance(looked, Outcome):
            return _refusal(looked, self.name)
        call = looked
        try:
            refused, target = await self._disk.run(
                lambda _: looked_for_a_write(
                    self._root, call.file, call.overwrite, protected=self._protected
                ),
                f"a look at {call.file!r}",
            )
        except DiskSilent as silent:
            return _refusal(Outcome({}, NO_ANSWER, str(silent)), self.name)
        if refused is not None or target is None:
            return _refusal(refused or Outcome({}, IO_ERROR, "the file was not judged"), self.name)
        does = OVERWRITES_BY_DOWNLOAD if target.exists else CREATES_BY_DOWNLOAD
        return Prospect(target=replace(target, does=does), visit=looked.visit)

    async def _decided(
        self,
        decision: PermissionDecision,
        arguments: JsonMapping,
        stop: TaskStop,
        named: JsonMapping,
    ) -> Outcome:
        looked = self._looked(arguments)
        if isinstance(looked, Outcome):
            return looked
        call = looked
        try:
            refused, _ = await self._disk.run(
                lambda _: looked_for_a_write(
                    self._root, call.file, call.overwrite, protected=self._protected
                ),
                f"a look at {call.file!r}",
            )
        except DiskSilent as silent:
            return Outcome({"gestures": 0}, NO_ANSWER, str(silent))
        if refused is not None:
            return refused
        return await self._ran(self._of(looked, decision), stop)

    async def _ran(self, looked: _Call, stop: TaskStop) -> Outcome:
        """With a click, the run of every page: opened, and the click made in :meth:`_work`.
        Without one **the address is the file**, and the browser opens a page of its own for the
        navigation that is the download — it falls in the ways a page falls."""
        assert isinstance(looked, _Download)  # noqa: S101 — built by ``_gestures``
        if looked.click is not None:
            return await super()._ran(looked, stop)
        site, done = looked.visit.site, _Done(total=1)
        try:
            async with asyncio.timeout(self._browsing.timeout_seconds):
                if looked.task is not None:
                    # The same task opens another page: the one it keeps is closed first.
                    await self._pages.release(looked.task)
                refused = await self._folder(looked, stop)
                if refused is not None:
                    return refused
                done.made = 1  # see :meth:`_after`: from here the gesture counts as made
                got = await self._unless_stopped(
                    self._browser.downloaded_from(
                        looked.visit.address,
                        looked.allowed,
                        stop,
                        str(self._target(looked).parent),
                    ),
                    stop,
                )
        except DownloadNotStarted as none:
            return self._not_started(site, done, none.left)
        except FELL as fell:
            return self._fell(fell, site, done, None)
        if got is None:
            return self._stopped_while_arriving(site, done)
        return await self._kept(looked, got, None)

    async def _work(self, call: _Call, opened: Opened, done: _Done, stop: TaskStop) -> Outcome:
        """The click that starts the download, on a page that answered: its element awaited with
        the stop, the folder made, and the click the browser makes with the door open."""
        assert isinstance(call, _Download) and call.click is not None  # noqa: S101
        site, done.total = call.visit.site, 1
        found = await self._awaited(
            opened.page, call.click, stop, done, "the element that starts the download"
        )
        if found is None:
            # The stop of the task came while the element was awaited: heard here, at the tool's
            # point, which raises — nothing was clicked, and the door was never opened.
            stop.listen(DOWNLOAD_GESTURE)
        assert found is not None  # noqa: S101 — the listening above raised
        if found > 1:
            return Outcome(
                self._partial(done),
                ELEMENT_AMBIGUOUS,
                f"click names {found} elements on the page of {site}{self._after(done)}",
            )
        refused = await self._folder(call, stop)
        if refused is not None:
            return refused
        done.made = 1  # see :meth:`_after`: from here the gesture counts as made
        try:
            got = await self._unless_stopped(
                self._browser.download(
                    opened.page, call.click, stop, str(self._target(call).parent)
                ),
                stop,
            )
        except DownloadNotStarted as none:
            return self._not_started(site, done, none.left, opened.status)
        if got is None:
            return self._stopped_while_arriving(site, done, opened.status)
        return await self._kept(call, got, opened.status)

    async def _unless_stopped(
        self, downloading: Coroutine[Any, Any, Downloaded], stop: TaskStop
    ) -> Downloaded | None:
        """The download — or ``None`` when **its task was stopped while the file was arriving**:
        the browser's call is cancelled then, and cancelling it is what cancels the download and
        takes away what it had written. A task stopped before the gesture never gets here: the
        browser hears it at the tool's point, and that leaves as ``ToolStopped``."""
        running = asyncio.ensure_future(downloading)
        halted = asyncio.ensure_future(stop.stopped())
        either: set[asyncio.Future[Any]] = {running, halted}
        try:
            await asyncio.wait(either, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            # The time of the step: the download is cancelled with it — **and waited for**,
            # because cancelling it is what takes away what the browser had written: a step that
            # said «nothing stays» before that was done would say it of a folder that still holds
            # half a file (found by the test of the real browsers, 2026-11-10).
            running.cancel()
            await asyncio.wait({running})
            _retrieved(running)
            raise
        finally:
            halted.cancel()
        if running.done():
            return running.result()
        running.cancel()
        try:
            return await running  # it ended while the stop was being heard: a download that ended
        except asyncio.CancelledError:
            return None

    def _stopped_while_arriving(self, site: str, done: _Done, status: int | None = None) -> Outcome:
        made: dict[str, JsonValue] = self._partial(done)
        if status is not None:
            made = {"status": status, **made}
        return Outcome(
            made,
            STOPPED,
            f"the task was stopped while the download from {site} was arriving: it was cancelled, "
            f"and what the browser had begun to write was removed{self._after(done)}",
        )

    def _target(self, call: _Download) -> Path:
        return self._root / call.file

    async def _folder(self, call: _Download, stop: TaskStop) -> Outcome | None:
        """The folder of the target, made if it is not there — as ``fs.write`` makes it, never
        the root. **A task already stopped leaves here**, at the tool's point, with
        ``ToolStopped`` and no folder; one that is not is listened to by the browser, right
        before its gesture — a stop that comes between the two finds the folder made, and empty.
        In the guard of the disk (M13.17, ADR 0074): an abandoned wait makes no folder after."""
        if stop.is_set():
            stop.listen(DOWNLOAD_GESTURE)
        folder = self._target(call).parent

        def made(gone: Gone) -> None:
            gone.begin(MAKING_THE_FOLDER)
            folder.mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)

        try:
            await self._disk.run(made, f"a write of {call.file!r}")
        except DiskSilent as silent:
            return Outcome({"gestures": 0}, NO_ANSWER, str(silent))
        except OSError as error:
            return Outcome(
                {"gestures": 0}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}"
            )
        return None

    def _not_started(
        self, site: str, done: _Done, left: str | None, status: int | None = None
    ) -> Outcome:
        """The gesture was made and no download began: it led to a page — or, with ``left``, the
        site sent the browser outside the boundary, which did not follow. Nothing was written."""
        made: dict[str, JsonValue] = self._partial(done)
        if status is not None:
            made = {"status": status, **made}
        if left is not None:
            return Outcome(made, LEFT_SITE, self._left(site, origin_of(left)) + self._after(done))
        return Outcome(
            made,
            DOWNLOAD_NOT_STARTED,
            f"the gesture was made and {site} started no download: nothing was written",
        )

    async def _kept(self, call: _Download, got: Downloaded, status: int | None) -> Outcome:
        """:meth:`_placed`, in the guard of the disk (M13.17, ADR 0074)."""
        made: dict[str, JsonValue] = {"gestures": 1}
        if status is not None:
            made["status"] = status
        try:
            return await self._disk.run(
                lambda gone: self._placed(call, got, status, gone), f"a write of {call.file!r}"
            )
        except DiskSilent as silent:
            return Outcome(made, NO_ANSWER, str(silent))

    def _placed(self, call: _Download, got: Downloaded, status: int | None, gone: Gone) -> Outcome:
        """The file the browser left under a name of its own takes **the plan's name** — created
        without replacing, or replacing when ``overwrite`` says so — and the mode ``600``, also
        when it replaces one. What the result says of it is read from the file itself."""
        target = self._target(call)
        left = target.parent / got.name
        made: dict[str, JsonValue] = {"gestures": 1}
        if status is not None:
            made["status"] = status
        if Path(got.name).name != got.name or got.name in {"", ".", ".."}:
            return Outcome(made, FAILED, "the browser named what it wrote outside the folder")
        # The target is looked at again with the function of ``fs.write`` before the file is placed
        # (M13.17, ADR 0074; decision 8): the window of the download is the whole download, and
        # what ELA uses to exist may have come under the folder meanwhile.
        refused, _ = looked_for_a_write(
            self._root, call.file, call.overwrite, protected=self._protected
        )
        if refused is not None:
            _removed(left)
            return replace(refused, output=made)
        try:
            if not stat.S_ISREG(os.lstat(left).st_mode):
                return Outcome(made, FAILED, "what the browser left in the folder is not a file")
            gone.begin(WRITING)
            os.chmod(left, FILE_MODE)
            if call.overwrite:
                os.replace(left, target)
            else:
                os.link(left, target)
                os.unlink(left)
            size, digest = measured(target)
        except FileExistsError:
            _removed(left)
            return Outcome(
                made,
                OVERWRITE_MISMATCH,
                f"{call.file!r} was declared as a new file and something is there now: what was "
                "downloaded was removed",
            )
        except OSError as error:
            _removed(left)
            return Outcome(made, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        return Outcome(
            {**made, "file": call.file, "size": size, "digest": digest, "overwrote": call.overwrite}
        )

    async def _handed_over(self, call: _Call, page: str) -> None:
        """The page of a download is nobody's after it: its verifier reads the disk."""
        await self._browser.close(page)

    def _still_at_work(self, site: str, done: _Done) -> str:
        return (
            f"the download from {site} had not ended after {self._browsing.timeout_seconds} s: "
            f"ELA closed the browser, and what it had begun to write was removed{self._after(done)}"
        )

    def _after(self, done: _Done) -> str:
        """What a download that fell says of its one gesture. The browser makes it — it opens the
        door, listens to the stop and clicks or navigates, in one call —, so the tool knows two
        things only: before that call the gesture **was not made**, and once the call began it
        **may have been**. It counts as made from then on (``gestures: 1``): a gesture that
        happened is never reported as one that did not, or it would be asked again on that word
        — and one that did not happen is not said to have."""
        if not done.made:
            return "; the gesture that starts the download was not made"
        return "; the gesture that starts the download may have been made"


def _removed(left: Path) -> None:
    """Take away what the browser left under its own name, when it cannot take the plan's."""
    try:
        os.unlink(left)
    except OSError:
        return


class AccountDownloadTool(_OnTheProfile, BrowserDownloadTool):
    """Downloads one file of a declared site with the profile (**HIGH**): what arrives is the
    user's own content."""

    error_codes: ClassVar[frozenset[str]] = BrowserDownloadTool.error_codes | ACCOUNT_CODES
    does: ClassVar[str] = DOWNLOADS_AS_YOU

    def __init__(
        self,
        root: Path | str,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_DOWNLOAD_AS_YOU_TOOL_NAME,
        pages: TaskPages,
    ) -> None:
        BrowserDownloadTool.__init__(
            self,
            root,
            browsing,
            browser,
            clock,
            ids,
            protected=protected,
            disk=disk,
            name=name,
            pages=pages,
            capability_id=BROWSER_DOWNLOAD_AS_YOU,
        )


class BrowserUploadTool(BrowserActTool):
    """Gives one file under the root to a page of a declared site, then fills and clicks
    (**HIGH**): the bytes ELA read, and the name — never the path.

    **Two roads** (M13.15, ADR 0071; answer 38 of the review of its SPEC). Under a yes, the
    question named the file's size and sha256, ELA reads the file again after the yes and gives it
    only if they agree (ADR 0066 §6). **Under a policy no question was asked**: ELA reads the file
    **once**, gives the page exactly those bytes, and the result says their size and sha256 — the
    road taken only for a decision that rests on a policy and on nothing else
    (:func:`~ela.tools.base.under_a_policy`). On both, a file that reaches what ELA uses to exist
    or that has more than one name is refused (decision 7, answer 36), and the result carries
    ``size`` and ``digest`` of what left — never the audit (ADR 0066 §5)."""

    error_codes: ClassVar[frozenset[str]] = (
        (BrowserActTool.error_codes - {NO_PAGE_TO_CONTINUE})
        | {SITE_NOT_DECLARED, NOT_A_FILE_FIELD, FILE_CHANGED, FILE_TOO_LARGE, NO_ROOT, IO_ERROR}
        | {ELA_S_OWN, HARD_LINK}
        | {NO_ANSWER}  # M13.17, ADR 0074: the guard of the disk
        | READ_REFUSALS
    )
    output_keys: ClassVar[frozenset[str]] = (BrowserActTool.output_keys - {LEFT_WHILE_WAITING}) | {
        NAMED_SIZE,
        NAMED_DIGEST,
    }
    does: ClassVar[str] = UPLOADS
    under_the_root: ClassVar[bool] = True
    """Reads a file under ``ELA_FS_ROOT`` (M13.17, ADR 0074): declared here, against the gesture
    it inherits its point from, which does not."""
    continuing: ClassVar[str] = ""
    """Never: an upload opens its own page, and the page that holds a file is nobody else's."""

    def __init__(
        self,
        root: Path | str,
        browsing: Browsing,
        browser: Browser,
        clock: Clock,
        ids: IdGenerator,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_UPLOAD_TOOL_NAME,
        pages: TaskPages,
        capability_id: CapabilityId = BROWSER_UPLOAD,
    ) -> None:
        _BrowserTool.__init__(
            self, capability_id, browsing, browser, clock, ids, name=name, pages=pages
        )
        self._root = resolve_workspace(root)
        # What ELA uses to exist (M13.15, ADR 0071; decision 7): no read of an upload reaches it.
        self._protected: Mapping[str, Path] = MappingProxyType(dict(protected))
        # The guard of every look and read on the disk (M13.17, ADR 0074).
        self._disk = Disk() if disk is None else disk

    @property
    def disk(self) -> Disk:
        """The guard every look and read of this tool passes (M13.17, ADR 0074)."""
        return self._disk

    @property
    def root(self) -> Path:
        """The resolved root: ``ELA_FS_ROOT``, never created here."""
        return self._root

    @property
    def protected(self) -> Mapping[str, Path]:
        """What ELA uses to exist, named: ``fs.read``'s list, and no upload reads it."""
        return self._protected

    def _gestures(self, arguments: JsonMapping, site: str, address: str) -> Outcome | _Call:
        file, field, click = (
            arguments.get("file"),
            arguments.get("file_field"),
            arguments.get("click"),
        )
        if not isinstance(file, str) or not file:
            return Outcome({}, ARGUMENTS_INVALID, "file must be a path under the root")
        fills = _pairs(arguments.get("fill", ()))
        if isinstance(fills, Outcome):
            return fills
        refused = (
            _selector(field, "file_field")
            or (None if click is None else _selector(click, "click"))
            or _expected(arguments.get("expect_text"))
        )
        if refused is not None:
            return refused
        assert isinstance(field, str)  # noqa: S101 — ``_selector`` said so
        gestures = (
            f"gives {field} the file — its name and its bytes, never where it is",
            *_filling(fills),
            *(() if click is None else (f"clicks {click}",)),
        )
        return _Upload(
            visit=self._visit(site, address, gestures, str(arguments["expect_text"])),
            fills=fills,
            click=click if isinstance(click, str) else None,
            selector=None,
            allowed=boundary(frozenset({self._browsing.origin(site)})),
            file=file,
            field=field,
        )

    def _looked(self, arguments: JsonMapping) -> Outcome | _Upload:
        looked = self._shaped(arguments)
        if isinstance(looked, Outcome):
            return looked
        assert isinstance(looked, _Upload)  # noqa: S101 — an upload never continues
        return _undeclared(self._browsing, looked.visit.site) or looked

    def _judged(self, file: str) -> Outcome | Target:
        """**What an upload refuses before a byte is read, in one place** (M13.15, ADR 0071; answer
        39): the file as ``fs.read`` judges it — the root, the classification, what ELA uses to
        exist, a second name — and its size asked of the disk. The question's road and the
        policy's call this, so the same refusal has the same code on both."""
        refused, target = looked_for_a_read(self._root, file, protected=self._protected)
        if refused is not None or target is None:
            return refused or Outcome({}, IO_ERROR, "the file was not judged")
        try:
            if os.lstat(self._root / file).st_size > UPLOAD_MAX_BYTES:
                return self._too_large(file)
        except OSError as error:
            return Outcome({}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        return target

    async def _read(self, file: str) -> Outcome | tuple[Target, bytes]:
        """:meth:`_read_now`, in the guard of the disk (M13.17, ADR 0074)."""
        try:
            return await self._disk.run(lambda _: self._read_now(file), f"a read of {file!r}")
        except DiskSilent as silent:
            return Outcome({}, NO_ANSWER, str(silent))

    async def _judged_now(self, file: str) -> Outcome | Target:
        """:meth:`_judged`, in the guard of the disk (M13.17, ADR 0074)."""
        try:
            return await self._disk.run(lambda _: self._judged(file), f"a look at {file!r}")
        except DiskSilent as silent:
            return Outcome({}, NO_ANSWER, str(silent))

    def _read_now(self, file: str) -> Outcome | tuple[Target, bytes]:
        """The file as :meth:`_judged` judges it, then its bytes — **at most the limit and one
        byte more** (decision 51): a file that grew after it was measured is refused without the
        rest being read; regular and with one name, asked of the descriptor that reads."""
        judged = self._judged(file)
        if isinstance(judged, Outcome):
            return judged
        try:
            data = read_bytes(self._root / file, at_most=UPLOAD_MAX_BYTES)
        except MoreThanOneName:
            return Outcome({}, HARD_LINK, more_than_one_name_read(file))
        except OSError as error:
            return Outcome({}, IO_ERROR, f"{type(error).__name__}: {error.strerror or error}")
        if len(data) > UPLOAD_MAX_BYTES:
            return self._too_large(file)
        return judged, data

    def _too_large(self, file: str) -> Outcome:
        return Outcome(
            {},
            FILE_TOO_LARGE,
            f"{file!r} is larger than the {UPLOAD_MAX_BYTES // (1024 * 1024)} MiB a page can be "
            "given: no question is asked",
        )

    async def _would_start(self, arguments: JsonMapping, task: TaskId | None) -> Outcome | _Upload:
        """The shape, the site, the browser: what every road of an upload begins with."""
        looked = self._looked(arguments)
        if not isinstance(looked, Outcome):
            looked = await self._installed(task) or looked
        return looked

    async def prospect(self, arguments: JsonMapping, task: TaskId | None = None) -> Prospect:
        """The shape, the site, the browser, then the root and the file as ``fs.read`` judges
        them. **The question names the file as it is now**: its resolved path, its size and its
        sha256 — and those two go with the yes, to be asked of the file again after it."""
        looked = await self._would_start(arguments, task)
        if isinstance(looked, Outcome):
            return _refusal(looked, self.name)
        read = await self._read(looked.file)
        if isinstance(read, Outcome):
            return _refusal(read, self.name)
        target, data = read
        size, digest = len(data), hashlib.sha256(data).hexdigest()
        return Prospect(
            target=replace(target, does=LEAVES, size=size, digest=digest),
            visit=looked.visit,
            named={NAMED_SIZE: size, NAMED_DIGEST: digest},
        )

    async def prospect_covered(
        self, arguments: JsonMapping, task: TaskId | None = None
    ) -> Prospect:
        """**Every refusal of :meth:`prospect`, and not a byte read** (M13.15, ADR 0071; decision
        3, answer 39): under a policy no question is composed, so nothing is measured — the
        shape, the site, the browser, the root, the file, what ELA uses to exist, a second name and
        the size the disk says. The use is spent only after this says the call would start."""
        looked = await self._would_start(arguments, task)
        if isinstance(looked, Outcome):
            return _refusal(looked, self.name)
        judged = await self._judged_now(looked.file)
        if isinstance(judged, Outcome):
            return _refusal(judged, self.name)
        return Prospect(target=replace(judged, does=LEAVES), visit=looked.visit)

    async def prospect_place(self, place: str, values: tuple[str, ...] = ()) -> Prospect:
        """Whether an upload could start now from ``place`` to each of ``values``, the sites of a
        policy (M13.15, ADR 0071): :func:`_place` — **not** the look at a site a gesture inherits,
        which would say «it would start» of any folder."""
        return await _place(self, place, values, GIVES_FROM)

    async def _decided(
        self,
        decision: PermissionDecision,
        arguments: JsonMapping,
        stop: TaskStop,
        named: JsonMapping,
    ) -> Outcome:
        """ELA reads the file, itself, and gives the page **those** bytes. Under a yes, a file
        that is not the one the question named — by size or by sha256 — does not leave. Under a
        policy there is no question to compare with: the file is read once, and what leaves is
        what the result says."""
        looked = self._looked(arguments)
        if isinstance(looked, Outcome):
            return looked
        read = await self._read(looked.file)
        if isinstance(read, Outcome):
            return replace(read, output={"gestures": 0})
        _, data = read
        size, digest = len(data), hashlib.sha256(data).hexdigest()
        if not under_a_policy(decision) and (
            named.get(NAMED_SIZE) != size or named.get(NAMED_DIGEST) != digest
        ):
            return Outcome(
                {"gestures": 0},
                FILE_CHANGED,
                f"{looked.file!r} is not the file the question named any more: the yes was "
                "spent, no page was opened and nothing left",
            )
        name = Path(looked.file).name
        given = GivenFile(name, mimetypes.guess_type(name)[0] or OCTET_STREAM, data)
        ran = await self._ran(
            replace(looked, task=decision.task_id, step=decision.step_id, given=given), stop
        )
        gestures = ran.output.get("gestures")
        if not isinstance(gestures, int) or gestures < 1:
            return ran
        # What left, said of the bytes that left: the size and the sha256 of exactly what was
        # given — in the result and on the surfaces, never in the audit (ADR 0066 §5).
        return replace(ran, output={**ran.output, NAMED_SIZE: size, NAMED_DIGEST: digest})

    async def _work(self, call: _Call, opened: Opened, done: _Done, stop: TaskStop) -> Outcome:
        """**Giving the file is the first gesture.** Its field is awaited with the stop, has to be
        one element and an ``input`` of type ``file``; the stop is listened to, and the file is
        given — from that instant the page holds a file. Then the fills and the click are the
        sequence of every action."""
        assert isinstance(call, _Upload) and call.given is not None  # noqa: S101
        page, site = opened.page, call.visit.site
        steps: list[tuple[str, str | None]] = [
            *call.fills,
            *(() if call.click is None else ((call.click, None),)),
        ]
        done.total = 1 + len(steps)
        which = f"gesture 1 of {done.total}"
        found = await self._awaited(page, call.field, stop, done, which)
        if found is None:
            # The stop of the task came while the field was awaited: heard here, at the tool's
            # point, which raises — no gesture was made, and nothing was given.
            stop.listen(FIRST_GESTURE)
        assert found is not None  # noqa: S101 — the listening above raised
        if found > 1:
            return self._refused_at(
                opened,
                done,
                ELEMENT_AMBIGUOUS,
                f"{which} names {found} elements on the page of {site}",
            )
        declared = await self._browser.field(page, call.field)
        if declared.type != FILE:
            return self._refused_at(
                opened,
                done,
                NOT_A_FILE_FIELD,
                f"{which} does not name a file field — an input of type file — on the page of "
                f"{site}: nothing was given to the page",
            )
        stop.listen(FIRST_GESTURE)
        await self._gesture(done, self._browser.give(page, call.field, call.given))
        refused = await self._sequence(opened, done, stop, steps, site)
        if refused is not None:
            return refused
        return await self._after_the_gestures(opened, done, site)

    async def _handed_over(self, call: _Call, page: str) -> None:
        """To the verifier, which closes it with its look — and never to the step after this
        one: the page that holds a file is nobody else's."""
        await self._browser.keep(page)


class AccountUploadTool(_OnTheProfile, BrowserUploadTool):
    """Gives one file under the root to a page of a declared site with the profile (**HIGH**):
    where the user is signed in, the file is given as them."""

    error_codes: ClassVar[frozenset[str]] = BrowserUploadTool.error_codes | ACCOUNT_CODES
    does: ClassVar[str] = UPLOADS_AS_YOU

    def __init__(
        self,
        root: Path | str,
        browsing: Browsing,
        browser: AccountBrowser,
        clock: Clock,
        ids: IdGenerator,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_UPLOAD_AS_YOU_TOOL_NAME,
        pages: TaskPages,
    ) -> None:
        BrowserUploadTool.__init__(
            self,
            root,
            browsing,
            browser,
            clock,
            ids,
            protected=protected,
            disk=disk,
            name=name,
            pages=pages,
            capability_id=BROWSER_UPLOAD_AS_YOU,
        )


class FileDownloadedVerifier(Verifier):
    """``browser.download``: **the file the plan named is there, and it is the one the result
    describes** (ADR 0066).

    The path is read from the **arguments**, the plan's intent (ADR 0014 §2), and judged with the
    classification ``fs`` shares: there, regular, inside the root. Then the file itself is
    measured, and its size and its sha256 are compared with what the tool said arrived — a tool
    that said one thing and left another is what this catches. **A failure says sizes, never
    hashes** (ADR 0045 §8). What it cannot say is that the bytes are the ones the site meant:
    nobody knows those before the download.
    """

    under_the_root: ClassVar[bool] = True
    reads_the_machine: ClassVar[bool] = True
    """The disk of this machine: neither capability travels."""
    conditions: ClassVar[frozenset[str]] = frozenset({FILE_DOWNLOADED})
    failure_codes: ClassVar[frozenset[str]] = (
        COMMON_FAILURE_CODES | PATH_CODES | {FILE_MISMATCH, FILE_UNREADABLE, NO_ANSWER, ELA_S_OWN}
    )

    def __init__(
        self,
        root: Path | str,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_DOWNLOAD_VERIFIER_NAME,
        capability_id: CapabilityId = BROWSER_DOWNLOAD,
    ) -> None:
        super().__init__(capability_id, name=name)
        self._root = resolve_workspace(root)
        # What ELA uses to exist (M13.17, ADR 0074; decision 8): no verifier reads it either.
        self._protected: Mapping[str, Path] = MappingProxyType(dict(protected))
        # The guard of the look and the read (M13.17, ADR 0074).
        self._disk = Disk() if disk is None else disk

    @property
    def disk(self) -> Disk:
        """The guard the look and the read of this verifier pass (M13.17, ADR 0074)."""
        return self._disk

    async def _check(
        self, condition: str, arguments: JsonMapping, result: ExecutionResult
    ) -> ErrorMetadata | None:
        file = arguments.get("file")
        size, digest = result.output.get("size"), result.output.get("digest")
        if (
            not isinstance(file, str)
            or not isinstance(size, int)
            or isinstance(size, bool)
            or not isinstance(digest, str)
        ):
            return self._failure(
                condition,
                VERIFICATION_ARGUMENTS_INVALID,
                "file must be a path, and the result must say the size and the sha256 of what "
                "arrived",
                retryable=False,
            )
        try:
            looked = await self._disk.run(lambda _: self._measured(file), f"a read of {file!r}")
        except DiskSilent as silent:
            return self._failure(condition, NO_ANSWER, str(silent), retryable=False)
        except OSError as error:
            return self._failure(
                condition,
                FILE_UNREADABLE,
                f"{file!r} could not be read: {type(error).__name__}: {error.strerror or error}",
                retryable=True,
            )
        if isinstance(looked, PathProblem):
            return self._failure(condition, looked.code, looked.message(file), retryable=False)
        there, holds = looked
        if (there, holds) == (size, digest):
            return None
        return self._failure(
            condition,
            FILE_MISMATCH,
            f"{file!r} is not the file the download left: the result says {size} bytes, and the "
            f"file holds {there}" + (" of another content" if there == size else ""),
            retryable=False,
            details={"expected_bytes": size, "actual_bytes": there},
        )

    def _measured(self, file: str) -> PathProblem | tuple[int, str]:
        """The classification, then the size and the sha256 of the file: in the guard's thread."""
        problem = classify(self._root, file)
        if problem is not None:
            return problem
        what = which_place(self._root / file, self._protected)
        if what is not None:
            return PathProblem(ELA_S_OWN, f"reaches {what}: a verifier of ELA never reads it")
        return measured(self._root / file)


class AccountFileDownloadedVerifier(FileDownloadedVerifier):
    """``browser.download_as_you``: the same question, of the same disk."""

    def __init__(
        self,
        root: Path | str,
        *,
        protected: Mapping[str, Path],
        disk: Disk | None = None,
        name: str = BROWSER_DOWNLOAD_AS_YOU_VERIFIER_NAME,
    ) -> None:
        super().__init__(
            root,
            protected=protected,
            disk=disk,
            name=name,
            capability_id=BROWSER_DOWNLOAD_AS_YOU,
        )


class UploadVerifier(BrowserActVerifier):
    """``browser.upload``: the page showed the text the plan expects, looked at after the last
    gesture — what ``browser.act`` is verified by, because an upload ends as an action does. **It
    says what the page showed, never that the site kept the file.**"""

    def __init__(
        self,
        browser: Browser,
        seconds: float,
        *,
        grace: float = LOOK_GRACE_SECONDS,
        name: str = BROWSER_UPLOAD_VERIFIER_NAME,
        capability_id: CapabilityId = BROWSER_UPLOAD,
    ) -> None:
        _PageVerifier.__init__(self, capability_id, browser, seconds, grace=grace, name=name)


class AccountUploadVerifier(UploadVerifier):
    """``browser.upload_as_you``: the same look, on the browser with the profile."""

    def __init__(
        self,
        browser: AccountBrowser,
        seconds: float,
        *,
        grace: float = LOOK_GRACE_SECONDS,
        name: str = BROWSER_UPLOAD_AS_YOU_VERIFIER_NAME,
    ) -> None:
        super().__init__(
            browser, seconds, grace=grace, name=name, capability_id=BROWSER_UPLOAD_AS_YOU
        )
