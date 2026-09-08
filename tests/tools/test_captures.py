"""The read-only classification of a screen capture (M10.2, ADR 0029 §1, §5).

What the tool writes and what the verifier reads back go through this module, so these tests are
the ones that stop the two from disagreeing. Nothing here needs a permission, a screen or a Mac:
a PNG is twenty-four bytes of header, and every failure mode is a file a test can lay down.
"""

from __future__ import annotations

import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ela.tools.captures import (
    CAPTURE_MALFORMED,
    CAPTURE_MISSING,
    CAPTURE_NAME_INVALID,
    CAPTURE_NOT_REGULAR,
    CAPTURE_UNREADABLE,
    HEADER_BYTES,
    PNG_SIGNATURE,
    CaptureProblem,
    Size,
    _read,
    inspect,
    is_capture_name,
    measure,
    name_for,
    path_for,
    png_size,
    retained,
    room,
)

TTL = timedelta(seconds=300)
NAME = "3f2504e0-4f89-41d3-9a0c-0305e82c3301.png"
OTHER = "9c858901-8a57-4791-81fe-4c455b099bc9.png"


def png(width: int = 2560, height: int = 1664, *, tail: bytes = b"\x00" * 64) -> bytes:
    """A PNG as far as anything ELA reads is concerned: signature, IHDR, then bytes."""
    return (
        PNG_SIGNATURE
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + tail
    )


def write(directory: Path, name: str, data: bytes, *, age: timedelta | None = None) -> Path:
    """A capture in the store, optionally aged by setting its ``mtime`` back."""
    target = directory / name
    target.write_bytes(data)
    if age is not None:
        stamp = (datetime.now(tz=UTC) - age).timestamp()
        os.utime(target, (stamp, stamp))
    return target


# ----------------------------------------------------------------------------------------
# png_size: four ways to be None, and each is a file a helper can really leave behind
# ----------------------------------------------------------------------------------------


def test_a_png_header_gives_the_size_the_ihdr_declares() -> None:
    assert png_size(png()[:HEADER_BYTES]) == Size(2560, 1664)


def test_too_few_bytes_is_not_a_png() -> None:
    """A child killed mid-write leaves exactly this."""
    assert png_size(png()[: HEADER_BYTES - 1]) is None


def test_a_wrong_signature_is_not_a_png() -> None:
    """An error page, a JPEG, a file the helper truncated to nothing."""
    assert png_size(b"<!doctype html>" + b"\x00" * 32) is None


def test_a_first_chunk_that_is_not_ihdr_is_not_a_png() -> None:
    header = bytearray(png())
    header[12:16] = b"pHYs"
    assert png_size(bytes(header)) is None


@pytest.mark.parametrize(("width", "height"), [(0, 1664), (2560, 0)])
def test_a_zero_dimension_is_a_capture_of_nothing(width: int, height: int) -> None:
    assert png_size(png(width, height)) is None


# ----------------------------------------------------------------------------------------
# Names: the store issues them, so anything else is not one it issued
# ----------------------------------------------------------------------------------------


def test_a_name_the_store_issues_is_a_uuid_and_png() -> None:
    assert is_capture_name(name_for("3f2504e0-4f89-41d3-9a0c-0305e82c3301"))


@pytest.mark.parametrize(
    "name",
    [
        "../ela.db",
        "notes/briefing.md",
        "3f2504e0-4f89-41d3-9a0c-0305e82c3301.jpg",
        "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
        "3F2504E0-4F89-41D3-9A0C-0305E82C3301.png",
        "",
    ],
)
def test_anything_else_is_not(name: str) -> None:
    """A separator stops being expressible rather than being filtered — the name arrives from a
    persisted result when the verifier reads it back (ADR 0029 §4)."""
    assert not is_capture_name(name)


def test_a_name_the_store_did_not_issue_leads_nowhere(tmp_path: Path) -> None:
    problem = path_for(tmp_path, "../ela.db")

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NAME_INVALID
    assert "../ela.db" in problem.message("../ela.db")


def test_a_name_the_store_issued_leads_into_the_store(tmp_path: Path) -> None:
    assert path_for(tmp_path, NAME) == tmp_path / NAME


# ----------------------------------------------------------------------------------------
# measure: what is there, in the order the first problem names itself
# ----------------------------------------------------------------------------------------


def test_a_capture_is_measured_from_the_disk(tmp_path: Path) -> None:
    import hashlib

    data = png()
    target = write(tmp_path, NAME, data)

    found = measure(target, TTL)

    assert not isinstance(found, CaptureProblem)
    assert found.name == NAME
    assert found.bytes == len(data)
    assert found.sha256 == hashlib.sha256(data).hexdigest()
    assert found.size == Size(2560, 1664)


def test_the_expiry_comes_from_the_file_and_not_from_a_clock(tmp_path: Path) -> None:
    """ADR 0029 §1: what ELA reports is what the purge will apply, and there is no second
    record of the user's screen to keep in step."""
    target = write(tmp_path, NAME, png(), age=timedelta(seconds=100))

    found = measure(target, TTL)

    assert not isinstance(found, CaptureProblem)
    assert (found.expires_at - datetime.now(tz=UTC)).total_seconds() == pytest.approx(200, abs=5)


def test_a_capture_that_was_never_written_is_missing(tmp_path: Path) -> None:
    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MISSING


def test_a_directory_at_the_name_is_not_a_regular_file(tmp_path: Path) -> None:
    (tmp_path / NAME).mkdir()

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NOT_REGULAR


def test_a_link_is_not_a_regular_file_even_when_it_points_at_a_png(tmp_path: Path) -> None:
    """Going *through* a link is a doubt (§33), and the target is never opened."""
    real = write(tmp_path, OTHER, png())
    (tmp_path / NAME).symlink_to(real)

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NOT_REGULAR


def test_a_name_inside_an_unreachable_directory_is_unreadable(tmp_path: Path) -> None:
    closed = tmp_path / "closed"
    closed.mkdir()
    write(closed, NAME, png())
    closed.chmod(0o000)
    try:
        problem = measure(closed / NAME, TTL)
    finally:
        closed.chmod(0o700)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_UNREADABLE
    assert "PermissionError" in problem.reason


def test_a_file_that_cannot_be_opened_is_unreadable(tmp_path: Path) -> None:
    """``lstat`` said regular file and the read still failed: the second net, and it reports."""
    target = write(tmp_path, NAME, png())
    target.chmod(0o000)
    try:
        problem = measure(target, TTL)
    finally:
        target.chmod(0o600)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_UNREADABLE


def test_bytes_that_are_not_a_png_are_malformed_and_report_only_a_size(tmp_path: Path) -> None:
    """A helper that exits 0 and leaves this behind has not captured anything. The reason carries
    a length and never a byte (§57)."""
    write(tmp_path, NAME, b"not an image at all")

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MALFORMED
    assert "19 bytes" in problem.reason
    assert "not an image" not in problem.reason


def test_an_empty_file_is_malformed(tmp_path: Path) -> None:
    write(tmp_path, NAME, b"")

    problem = measure(tmp_path / NAME, TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_MALFORMED


def test_a_capture_replaced_by_a_directory_between_the_checks_and_the_read_is_refused(
    tmp_path: Path,
) -> None:
    """The ``fstat`` after ``open`` is the net behind ``lstat``, probed on the read itself."""
    (tmp_path / "adir").mkdir()

    with pytest.raises(OSError, match="not a regular file"):
        _read(tmp_path / "adir")


# ----------------------------------------------------------------------------------------
# inspect: the verifier's entry point
# ----------------------------------------------------------------------------------------


def test_inspect_refuses_a_name_before_touching_the_disk(tmp_path: Path) -> None:
    problem = inspect(tmp_path, "../ela.db", TTL)

    assert isinstance(problem, CaptureProblem)
    assert problem.code == CAPTURE_NAME_INVALID


def test_inspect_finds_what_the_tool_wrote(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())

    found = inspect(tmp_path, NAME, TTL)

    assert not isinstance(found, CaptureProblem)
    assert found.size == Size(2560, 1664)


# ----------------------------------------------------------------------------------------
# retained: only what the store issued, only regular files
# ----------------------------------------------------------------------------------------


def test_an_empty_store_holds_nothing(tmp_path: Path) -> None:
    assert retained(tmp_path, TTL) == ()


def test_a_store_that_is_not_there_holds_nothing(tmp_path: Path) -> None:
    """A read must not raise because the directory went away: ``/diagnostics`` calls this."""
    assert retained(tmp_path / "gone", TTL) == ()


def test_a_store_that_cannot_be_listed_holds_nothing(tmp_path: Path) -> None:
    tmp_path.chmod(0o000)
    try:
        assert retained(tmp_path, TTL) == ()
    finally:
        tmp_path.chmod(0o700)


def test_a_stranger_in_the_store_is_not_counted(tmp_path: Path) -> None:
    """Not ELA's to count — and, as the purge reads this same list, not ELA's to delete."""
    write(tmp_path, NAME, png())
    (tmp_path / "somebody-elses-file.txt").write_text("mine", encoding="utf-8")

    assert [one.name for one in retained(tmp_path, TTL)] == [NAME]


def test_a_directory_named_like_a_capture_is_not_counted(tmp_path: Path) -> None:
    (tmp_path / NAME).mkdir()

    assert retained(tmp_path, TTL) == ()


def test_a_dangling_link_named_like_a_capture_is_not_counted(tmp_path: Path) -> None:
    (tmp_path / NAME).symlink_to(tmp_path / "nowhere.png")

    assert retained(tmp_path, TTL) == ()


def test_a_capture_that_vanishes_between_the_listing_and_the_stat_is_not_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A race no test can stage for real: the file is listed and gone a microsecond later.

    Injected rather than staged, and injected at the syscall the race is *in* — not asserted by a
    mock that only proves ``lstat`` was called. Without this branch ``/diagnostics`` would answer
    500 because a capture expired while it was being counted.
    """
    write(tmp_path, NAME, png())
    real = Path.lstat

    def vanishing(self: Path) -> os.stat_result:
        if self.name == NAME:
            raise FileNotFoundError(self)
        return real(self)

    monkeypatch.setattr(Path, "lstat", vanishing)

    assert retained(tmp_path, TTL) == ()


def test_captures_come_back_soonest_expiry_first(tmp_path: Path) -> None:
    write(tmp_path, NAME, png(), age=timedelta(seconds=10))
    write(tmp_path, OTHER, png(), age=timedelta(seconds=200))

    assert [one.name for one in retained(tmp_path, TTL)] == [OTHER, NAME]


def test_what_is_held_carries_the_size_on_disk(tmp_path: Path) -> None:
    data = png()
    write(tmp_path, NAME, data)

    assert retained(tmp_path, TTL)[0].bytes == len(data)


# ----------------------------------------------------------------------------------------
# room: the ceilings refuse, they never evict (ADR 0029 §15)
# ----------------------------------------------------------------------------------------


def test_an_empty_store_has_room(tmp_path: Path) -> None:
    assert room(tmp_path, TTL, max_count=20, max_bytes=1 << 30) is None


def test_the_count_ceiling_refuses(tmp_path: Path) -> None:
    write(tmp_path, NAME, png())

    refusal = room(tmp_path, TTL, max_count=1, max_bytes=1 << 30)

    assert refusal is not None
    assert "1 captures" in refusal


def test_the_byte_ceiling_refuses(tmp_path: Path) -> None:
    data = png()
    write(tmp_path, NAME, data)

    refusal = room(tmp_path, TTL, max_count=20, max_bytes=len(data))

    assert refusal is not None
    assert f"{len(data)} bytes" in refusal


def test_a_full_store_still_holds_what_it_held(tmp_path: Path) -> None:
    """The whole point of §15: refusing is not evicting, and the first capture stays."""
    write(tmp_path, NAME, png())

    assert room(tmp_path, TTL, max_count=1, max_bytes=1 << 30) is not None
    assert (tmp_path / NAME).is_file()


def test_the_mode_of_a_capture_is_not_the_classifications_business(tmp_path: Path) -> None:
    """This module reads; tightening the mode is the store's, in :mod:`ela.tools.screen`."""
    target = write(tmp_path, NAME, png())
    target.chmod(0o644)

    assert not isinstance(measure(target, TTL), CaptureProblem)
    assert stat.S_IMODE(target.stat().st_mode) == 0o644
