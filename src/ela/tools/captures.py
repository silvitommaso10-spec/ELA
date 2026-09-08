"""What a screen capture is, classified once for the tool and for its verifier (M10.2,
ADR 0029 §1, §5).

The tool writes the artefact; the verifier reads it back. If each had its own checks they could
disagree — on what counts as a name, on whether a link is a file, on when a capture has expired —
and a capture the tool declared would be one the verifier cannot find. So the classification
lives here, once, and is **read-only by construction**: ``lstat``, ``open(O_RDONLY|O_NOFOLLOW)``
and ``iterdir``, never a write. Architecture rule 18 covers this module as it covers
:mod:`ela.tools.paths` and the verifiers, and for the same reason. Everything that *writes* — the
directory, the ``chmod``, the purge, the removal of a failed capture — lives with the tool, in
:mod:`ela.tools.screen`.

**What is being protected.** A capture is the first content ELA produces that nobody dictated:
not a note the user wrote, not a provider's answer to a question the user approved — a
photograph of whatever was in front of them. Three properties carry that, and each is
structural rather than promised:

* **It is not in the workspace.** The workspace is what §23 describes as synchronised, and
  content in a folder something may one day sync leaves the machine without anybody deciding it.
  The store is a sibling of the database (:func:`~ela.tools.settings.default_capture_dir`), and
  ADR 0029 §1 records that as a permanent constraint, not this milestone's convenience.
* **It expires**, and the expiry is read from the capture's ``mtime`` rather than from an index:
  what :func:`retained` reports is what the purge will apply, and there is no second record of
  the user's screen to keep in step. Since M10.3 an image can have a *derived* artefact — the
  text Vision read out of it — and the derived one has no clock of its own: it inherits the
  image's expiry, and an orphan whose image is gone is :data:`ALREADY_EXPIRED`. The lifetime is
  shared by construction, not by anybody remembering to share it.
* **The ceilings refuse, they do not evict** (:func:`room`, ADR 0029 §15). Deleting a capture
  somebody may still be reading in order to make room is acting on something else, and §33 says
  not to act.

Nothing here decodes an image. :func:`png_size` reads twenty-four bytes of header and answers
what the IHDR chunk says, which is the whole of what ELA needs to know about the pixels: how
many there were. Those twenty lines of ``struct`` are the declared price of keeping ``ctypes``
away from the riskiest read in the project (ADR 0029 §3).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

__all__ = [
    "ALREADY_EXPIRED",
    "CAPTURE_CODES",
    "CAPTURE_MALFORMED",
    "CAPTURE_MISSING",
    "CAPTURE_NAME_INVALID",
    "CAPTURE_NOT_REGULAR",
    "CAPTURE_SUFFIX",
    "CAPTURE_UNREADABLE",
    "HEADER_BYTES",
    "PNG_SIGNATURE",
    "Capture",
    "CaptureProblem",
    "Retained",
    "Size",
    "inspect",
    "is_capture_name",
    "measure",
    "name_for",
    "path_for",
    "png_size",
    "retained",
    "room",
    "TEXT_MALFORMED",
    "TEXT_SUFFIX",
    "RecognisedLine",
    "TextArtefact",
    "capture_id_of",
    "inspect_text",
    "is_artefact_name",
    "is_text_name",
    "jsonl_lines",
    "measure_text",
    "text_name_for",
]

CAPTURE_MISSING: Final = "capture.missing"
CAPTURE_NOT_REGULAR: Final = "capture.not_regular"
"""What is at the path is a directory, a link, a socket — anything but a regular file. A symbolic
link that points at a real PNG lands here too: going *through* a link is a doubt (§33)."""
CAPTURE_UNREADABLE: Final = "capture.unreadable"
CAPTURE_MALFORMED: Final = "capture.malformed"
"""There are bytes, and they are not a PNG this version can read: no signature, no IHDR, or a
zero dimension. A helper that exits 0 and leaves that behind has not captured anything."""
CAPTURE_NAME_INVALID: Final = "capture.name_invalid"
"""The name is not one this store issues. It matters because the name arrives from a persisted
:class:`~ela.domain.ExecutionResult` when the verifier reads it back, and a name that could carry
a path separator would be a way to point the verifier out of the store."""

TEXT_MALFORMED: Final = "text.malformed"
"""There are bytes and they are not the JSON Lines this store writes. The text counterpart of
:data:`CAPTURE_MALFORMED`, and a separate code because it is a separate fact: a capture that is
not a PNG and a recognition that is not JSON Lines fail for different reasons and are fixed in
different places."""

CAPTURE_CODES: Final[frozenset[str]] = frozenset(
    {
        CAPTURE_MISSING,
        CAPTURE_NOT_REGULAR,
        CAPTURE_UNREADABLE,
        CAPTURE_MALFORMED,
        CAPTURE_NAME_INVALID,
        TEXT_MALFORMED,
    }
)
"""Every code this module can answer with: one set, shared by the tool and by the verifier."""

CAPTURE_SUFFIX: Final = ".png"
TEXT_SUFFIX: Final = ".jsonl"
"""What a recognition is called. The **stem is the capture's id**, which is the whole mechanism
of the shared lifetime: there is no index saying which text belongs to which image, because the
name *is* the link (M10.3 dec. 10)."""

_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
CAPTURE_NAME: Final = re.compile(rf"^{_UUID}\.png$")
"""A UUID and ``.png``, and nothing else. Tight on purpose: the store issues the name, so
anything that does not look like one it issued is not one it issued — and a name with a path
separator in it stops being expressible rather than being filtered."""
TEXT_NAME: Final = re.compile(rf"^{_UUID}\.jsonl$")
ARTEFACT_NAME: Final = re.compile(rf"^({_UUID})\.(?:png|jsonl)$")
"""Either artefact, with the capture id captured: one path segment, and the id is group 1."""

ALREADY_EXPIRED: Final = datetime.min.replace(tzinfo=UTC)
"""The expiry of a derived artefact whose capture is gone — in the past for every possible ``now``.

This is the whole of M10.3 dec. 10, and it is a value rather than a branch on purpose. The worst
thing this milestone could do is leave the *text* of somebody's screen on the disk after the
*image* has been purged, and the way to make that impossible is to give a derived artefact no
lifetime of its own to fall back on: an expiry is inherited from the origin, and an orphan has
nothing to inherit.

Because it is a value, the property is a **classification** and not an ordering: :func:`retained`
answers ``ALREADY_EXPIRED`` for an orphan with no purge having run, and the purge — which
compares ``expires_at <= now`` and nothing else — cannot fail to take it, whatever its ``now`` and
whatever order it walks the directory in. A test proves it by writing ``mtime``s and reading the
classification, which is what "impossible by construction" means as opposed to "the operations
happen to be in the right order"."""

PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
HEADER_BYTES: Final = 24
"""Signature (8) + chunk length (4) + ``IHDR`` (4) + width (4) + height (4). Nothing after the
IHDR is read: this does not decode the image, it counts the pixels."""

READ_FLAGS: Final = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
"""How a capture is opened: read-only, and never through a link."""


@dataclass(frozen=True, slots=True)
class Size:
    """What the IHDR chunk says the image is."""

    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CaptureProblem:
    """Why a name does not lead to a readable capture: a code and the reason.

    ``reason`` names the capture's name and the type of an OS error, never a byte of the image
    and never the absolute path — the store lives under the user's home, and a home directory in
    an audit trail is a name nobody asked to publish (§57).
    """

    code: str
    reason: str

    def message(self, name: str) -> str:
        return f"{name!r} {self.reason}"


@dataclass(frozen=True, slots=True)
class Capture:
    """A capture as read from the disk: what the tool reports and what the verifier re-derives."""

    name: str
    bytes: int
    sha256: str
    size: Size
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RecognisedLine:
    """One line Vision read, with how sure it was.

    The confidence travels with the text rather than being summarised away, because it is the
    difference between "ELA read your screen" and "ELA produced ``pl¢¢ols'.18``" — the measured
    output of the fast recognition level, which is why that level does not ship. Filtering on it
    here was the alternative and it is not ELA's to do: a threshold is a decision and belongs to
    whoever decides (§45, ADR 0028 §5), so nothing is dropped and the reader chooses.
    """

    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class TextArtefact:
    """A recognition as read from the disk: what the tool reports and the verifier re-derives.

    ``characters`` is the sum of the line lengths and not the file size: the file carries JSON
    punctuation and confidences, and what a reader wants to know is how much of their screen
    became text.
    """

    name: str
    bytes: int
    sha256: str
    lines: int
    characters: int
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Retained:
    """One capture the store is holding right now, for ``/diagnostics`` and for the ceilings."""

    name: str
    bytes: int
    expires_at: datetime


def is_capture_name(name: str) -> bool:
    """Whether ``name`` is a name this store issues: a UUID and ``.png``, one path segment."""
    return CAPTURE_NAME.match(name) is not None


def is_text_name(name: str) -> bool:
    """Whether ``name`` is a recognition this store issues: a UUID and ``.jsonl``."""
    return TEXT_NAME.match(name) is not None


def is_artefact_name(name: str) -> bool:
    """Whether ``name`` is either artefact this store issues."""
    return ARTEFACT_NAME.match(name) is not None


def capture_id_of(name: str) -> str | None:
    """The capture this artefact belongs to, or ``None`` if the name is not one this store issues.

    The stem, and that is the point: the id is the link between an image and its text, so the two
    cannot drift apart the way an index could.
    """
    match = ARTEFACT_NAME.match(name)
    return match.group(1) if match else None


def name_for(capture_id: str) -> str:
    """The file name a capture with this id gets. The only place a name is made."""
    return f"{capture_id}{CAPTURE_SUFFIX}"


def text_name_for(capture_id: str) -> str:
    """The file name the recognition of that capture gets. Same stem, by construction."""
    return f"{capture_id}{TEXT_SUFFIX}"


def path_for(directory: Path, name: str) -> Path | CaptureProblem:
    """Where ``name`` lives inside ``directory``, or why it is not a name this store issues."""
    if not is_artefact_name(name):
        return CaptureProblem(CAPTURE_NAME_INVALID, "is not a name this store issues")
    return directory / name


def jsonl_lines(data: bytes) -> tuple[RecognisedLine, ...] | None:
    """The recognition these bytes carry, or ``None`` if they are not the JSON Lines ELA writes.

    Strict on purpose, and the strictness is the point of choosing this format: JSON Lines is
    **self-delimiting**, so a helper killed halfway through leaves bytes that fail to parse rather
    than a shorter answer that looks like an answer. That is the property base64 does not have,
    and the reason M10.3 could send the text over stdout where M10.2 could not send the image
    (dec. 7).
    """
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        return None
    lines: list[RecognisedLine] = []
    for raw in text.splitlines():
        record = _record(raw)
        if record is None:
            return None
        lines.append(record)
    return tuple(lines)


def _record(raw: str) -> RecognisedLine | None:
    """One JSON Lines record, or ``None`` if it is not one ELA wrote."""
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or set(parsed) != {"text", "confidence"}:
        return None
    text, confidence = parsed["text"], parsed["confidence"]
    if not isinstance(text, str):
        return None
    # ``bool`` is an ``int``, and ``{"confidence": true}`` is not a confidence.
    if isinstance(confidence, bool) or not isinstance(confidence, int | float):
        return None
    return RecognisedLine(text, float(confidence))


def measure_text(path: Path, expires_at: datetime) -> TextArtefact | CaptureProblem:
    """Read the recognition at ``path`` and say what it is, or why it is not one.

    ``expires_at`` is passed in rather than read here, and that is the mechanism of dec. 10: a
    derived artefact has no lifetime of its own to consult. Its caller looks up the origin.

    The text itself stays in memory for the length of one hash and one count, and never enters a
    :class:`CaptureProblem`: a failure carries a size, never a byte — the same discipline
    :func:`measure` follows for the pixels (§57).
    """
    located = _regular_bytes(path)
    if isinstance(located, CaptureProblem):
        return located
    lines = jsonl_lines(located)
    if lines is None:
        return CaptureProblem(TEXT_MALFORMED, f"is not JSON Lines ({len(located)} bytes)")
    return TextArtefact(
        name=path.name,
        bytes=len(located),
        sha256=hashlib.sha256(located).hexdigest(),
        lines=len(lines),
        characters=sum(len(one.text) for one in lines),
        expires_at=expires_at,
    )


def inspect_text(directory: Path, name: str, ttl: timedelta) -> TextArtefact | CaptureProblem:
    """What is at ``name`` right now, re-derived from the disk — the text verifier's entry point.

    The expiry comes from :func:`_group_expiry`, so what this reports is what the purge applies:
    the image's ``mtime``, or :data:`ALREADY_EXPIRED` when the image is gone.
    """
    if not is_text_name(name):
        return CaptureProblem(CAPTURE_NAME_INVALID, "is not a name this store issues")
    capture_id = capture_id_of(name)
    assert capture_id is not None  # noqa: S101 — guaranteed by ``is_text_name`` above
    return measure_text(directory / name, _group_expiry(directory, capture_id, ttl))


def _group_expiry(directory: Path, capture_id: str, ttl: timedelta) -> datetime:
    """When every artefact of this capture stops being held (M10.3 dec. 10).

    Read from the **image**, always: the capture is the origin, and everything derived from it
    expires with it. A ``.jsonl`` written five minutes after its ``.png`` does not get five extra
    minutes, because it never had a clock of its own to consult.

    No image means no origin, and no origin means :data:`ALREADY_EXPIRED` — the fail-safe
    direction of §33 applied to content: in doubt, discard rather than hold.
    """
    try:
        origin = (directory / name_for(capture_id)).lstat()
    except OSError:
        return ALREADY_EXPIRED
    if not stat.S_ISREG(origin.st_mode):
        return ALREADY_EXPIRED
    return _expiry(origin.st_mtime, ttl)


def png_size(header: bytes) -> Size | None:
    """What the PNG header says the image is, or ``None`` if these bytes are not one.

    Four ways to be ``None``, and each is a real thing a helper can leave behind: too few bytes (a
    child killed mid-write), a wrong signature (an error page, a JPEG, a truncated file), a first
    chunk that is not IHDR, and a zero dimension — a capture of nothing. Pure, and every branch is
    a branch over bytes a test can write down.
    """
    if len(header) < HEADER_BYTES:
        return None
    if header[:8] != PNG_SIGNATURE:
        return None
    if header[12:16] != b"IHDR":
        return None
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width == 0 or height == 0:
        return None
    return Size(width, height)


def measure(path: Path, ttl: timedelta) -> Capture | CaptureProblem:
    """Read what is at ``path`` and say what it is, or why it is not a capture.

    In order, the first problem naming itself: it is there; it is a **regular file reached
    through no link**; it can be read; it is a PNG with a usable IHDR. The bytes stay in memory
    for the length of one hash and never enter a message (§57) — a failure carries a size, never
    a byte.
    """
    data = _regular_bytes(path)
    if isinstance(data, CaptureProblem):
        return data
    try:
        expires_at = _expiry(path.lstat().st_mtime, ttl)
    except OSError as error:
        return CaptureProblem(CAPTURE_UNREADABLE, f"could not be read: {type(error).__name__}")
    size = png_size(data[:HEADER_BYTES])
    if size is None:
        return CaptureProblem(CAPTURE_MALFORMED, f"is not a PNG ({len(data)} bytes)")
    return Capture(
        name=path.name,
        bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        size=size,
        expires_at=expires_at,
    )


def inspect(directory: Path, name: str, ttl: timedelta) -> Capture | CaptureProblem:
    """What is at ``name`` right now, re-derived from the disk — the verifier's entry point.

    The verifier calls this and nothing else: it re-derives every number the tool reported instead
    of reading the tool's word, which is what §20 asks for and what §63 calls verifying.

    A recognition's name is refused here rather than measured as a broken PNG: each artefact has
    one reader, and a ``.jsonl`` arriving as ``capture.malformed`` would be the right answer to
    the wrong question (:func:`inspect_text` is its reader).
    """
    if not is_capture_name(name):
        return CaptureProblem(CAPTURE_NAME_INVALID, "is not a name this store issues")
    return measure(directory / name, ttl)


def retained(directory: Path, ttl: timedelta) -> tuple[Retained, ...]:
    """Every artefact the store is holding, soonest expiry first.

    Only files this store issued are counted, and only regular ones: a directory or a stranger's
    file inside the store is not ELA's to count — and, as the purge reads the same list, not
    ELA's to delete either.

    Since M10.3 this includes the recognitions, and each one carries **its capture's** expiry
    (:func:`_group_expiry`). That is what makes an image and its text live and die together
    without anything having to remember that they should.
    """
    return tuple(sorted(_entries(directory, ttl), key=lambda one: (one.expires_at, one.name)))


def room(directory: Path, ttl: timedelta, *, max_count: int, max_bytes: int) -> str | None:
    """``None`` if another capture fits under both ceilings, else the reason it does not.

    Called **after** the purge, so what it counts is what has not expired. It refuses; it never
    evicts (ADR 0029 §15).

    The count is of **captures**, not of files: the ceiling asks how many screens ELA is holding,
    and reading the text of one does not make it two. The byte ceiling counts everything, because
    that one asks about the disk — and there the text is noise, ~6 KB of JSON Lines against
    0,8–4 MB of PNG, measured.
    """
    held = retained(directory, ttl)
    captures = {capture_id_of(one.name) for one in held}
    if len(captures) >= max_count:
        return f"the store already holds {len(captures)} captures that have not expired"
    total = sum(one.bytes for one in held)
    if total >= max_bytes:
        return f"the store already holds {total} bytes that have not expired"
    return None


def _entries(directory: Path, ttl: timedelta) -> Iterator[Retained]:
    """Every regular file in ``directory`` whose name this store issued, with its group's expiry.

    The expiry is looked up per capture id and not per file: an artefact does not get to consult
    its own ``mtime``, because a recognition written after its image would then outlive it — the
    one way this milestone could leave the text of somebody's screen behind (M10.3 dec. 10).
    """
    try:
        names = sorted(entry.name for entry in directory.iterdir())
    except OSError:  # the directory is gone or unreadable: nothing is held
        return
    expiries: dict[str, datetime] = {}
    for name in names:
        capture_id = capture_id_of(name)
        if capture_id is None:
            continue
        try:
            info = (directory / name).lstat()
        except OSError:  # vanished between the listing and the stat
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        if capture_id not in expiries:
            expiries[capture_id] = _group_expiry(directory, capture_id, ttl)
        yield Retained(name, info.st_size, expiries[capture_id])


def _expiry(mtime: float, ttl: timedelta) -> datetime:
    """When a capture written at ``mtime`` stops being held.

    Read from the file rather than from a clock ELA carries: the expiry reported is the expiry
    the purge applies, and there is no second record to fall out of step. In production the
    injected clock and the filesystem tell the same time; a test that wants a capture to be old
    sets its ``mtime``.
    """
    return datetime.fromtimestamp(mtime, tz=UTC) + ttl


def _regular_bytes(path: Path) -> bytes | CaptureProblem:
    """The bytes of a regular file reached through no link, or why there are none.

    The checks in order, the first problem naming itself: it is there; it is a regular file and
    not a link; it can be read. Shared by the image and by the text so the two cannot disagree
    about what a readable artefact is — the reason this module exists (ADR 0029 §5).
    """
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return CaptureProblem(CAPTURE_MISSING, "was not written")
    except OSError as error:
        return CaptureProblem(CAPTURE_UNREADABLE, f"cannot be reached: {type(error).__name__}")
    if not stat.S_ISREG(mode):
        return CaptureProblem(CAPTURE_NOT_REGULAR, "is not a regular file")
    try:
        return _read(path)
    except OSError as error:
        return CaptureProblem(CAPTURE_UNREADABLE, f"could not be read: {type(error).__name__}")


def _read(path: Path) -> bytes:
    """The bytes, opened read-only and never through a link; ``fstat`` on the open descriptor
    reconfirms the regular file ``lstat`` saw (a directory slipped in between is refused)."""
    descriptor = os.open(path, READ_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(None, "not a regular file")
        chunks = []
        while chunk := os.read(descriptor, 1 << 16):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)
