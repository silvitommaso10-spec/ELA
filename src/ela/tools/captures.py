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
* **It expires**, and the expiry is read from the capture's own ``mtime`` rather than from an
  index: what :func:`retained` reports is what the purge will apply, and there is no second
  record of the user's screen to keep in step.
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
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

__all__ = [
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

CAPTURE_CODES: Final[frozenset[str]] = frozenset(
    {
        CAPTURE_MISSING,
        CAPTURE_NOT_REGULAR,
        CAPTURE_UNREADABLE,
        CAPTURE_MALFORMED,
        CAPTURE_NAME_INVALID,
    }
)
"""Every code this module can answer with: one set, shared by the tool and by the verifier."""

CAPTURE_SUFFIX: Final = ".png"
CAPTURE_NAME: Final = re.compile(r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\.png$")
"""A UUID and ``.png``, and nothing else. Tight on purpose: the store issues the name, so
anything that does not look like one it issued is not one it issued — and a name with a path
separator in it stops being expressible rather than being filtered."""

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
class Retained:
    """One capture the store is holding right now, for ``/diagnostics`` and for the ceilings."""

    name: str
    bytes: int
    expires_at: datetime


def is_capture_name(name: str) -> bool:
    """Whether ``name`` is a name this store issues: a UUID and ``.png``, one path segment."""
    return CAPTURE_NAME.match(name) is not None


def name_for(capture_id: str) -> str:
    """The file name a capture with this id gets. The only place a name is made."""
    return f"{capture_id}{CAPTURE_SUFFIX}"


def path_for(directory: Path, name: str) -> Path | CaptureProblem:
    """Where ``name`` lives inside ``directory``, or why it is not a name this store issues."""
    if not is_capture_name(name):
        return CaptureProblem(CAPTURE_NAME_INVALID, "is not a name this store issues")
    return directory / name


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
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return CaptureProblem(CAPTURE_MISSING, "was not written")
    except OSError as error:
        return CaptureProblem(CAPTURE_UNREADABLE, f"cannot be reached: {type(error).__name__}")
    if not stat.S_ISREG(mode):
        return CaptureProblem(CAPTURE_NOT_REGULAR, "is not a regular file")
    try:
        data = _read(path)
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
    """
    located = path_for(directory, name)
    if isinstance(located, CaptureProblem):
        return located
    return measure(located, ttl)


def retained(directory: Path, ttl: timedelta) -> tuple[Retained, ...]:
    """Every capture the store is holding, soonest expiry first.

    Only files this store issued are counted, and only regular ones: a directory or a stranger's
    file inside the store is not ELA's to count — and, as the purge reads the same list, not
    ELA's to delete either.
    """
    return tuple(sorted(_entries(directory, ttl), key=lambda one: (one.expires_at, one.name)))


def room(directory: Path, ttl: timedelta, *, max_count: int, max_bytes: int) -> str | None:
    """``None`` if another capture fits under both ceilings, else the reason it does not.

    Called **after** the purge, so what it counts is what has not expired. It refuses; it never
    evicts (ADR 0029 §15).
    """
    held = retained(directory, ttl)
    if len(held) >= max_count:
        return f"the store already holds {len(held)} captures that have not expired"
    total = sum(one.bytes for one in held)
    if total >= max_bytes:
        return f"the store already holds {total} bytes that have not expired"
    return None


def _entries(directory: Path, ttl: timedelta) -> Iterator[Retained]:
    """Every regular file in ``directory`` whose name this store issued."""
    try:
        names = sorted(entry.name for entry in directory.iterdir())
    except OSError:  # the directory is gone or unreadable: nothing is held
        return
    for name in names:
        if not is_capture_name(name):
            continue
        try:
            info = (directory / name).lstat()
        except OSError:  # vanished between the listing and the stat
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        yield Retained(name, info.st_size, _expiry(info.st_mtime, ttl))


def _expiry(mtime: float, ttl: timedelta) -> datetime:
    """When a capture written at ``mtime`` stops being held.

    Read from the file rather than from a clock ELA carries: the expiry reported is the expiry
    the purge applies, and there is no second record to fall out of step. In production the
    injected clock and the filesystem tell the same time; a test that wants a capture to be old
    sets its ``mtime``.
    """
    return datetime.fromtimestamp(mtime, tz=UTC) + ttl


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
